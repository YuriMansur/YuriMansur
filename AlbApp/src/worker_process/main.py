"""
worker_process/main.py — точка входа изолированного рабочего процесса (свой GIL).

Тонкий entry-point: создаёт write_api, собирает кольцевые процессоры и запускает
OPC-цикл. Реализация разнесена по модулям:
  - ring_buffer — RingProc: кольцевой буфер + запись в InfluxDB
  - influx      — запуск influxd + write_api
  - opc_worker  — конфиг (servers.json) + OPC UA опрос/подписка/реконнект + build_procs

Не импортирует ничего из PyQt6 — общение с GUI только через multiprocessing.Queue.
"""

import asyncio
import sys
from pathlib import Path

# Добавляем src/ в sys.path на случай, если процесс запущен напрямую
sys.path.insert(0, str(Path(__file__).parent.parent))

from worker_process.opc_worker import run_worker_loop, build_procs
from worker_process import influx


def _exit_with_parent():
    """Завершить воркер вместе с процессом окна стенда.

    daemon-процесс multiprocessing гасится только при штатном выходе родителя;
    если окно стенда убито снаружи, воркер остался бы висеть с открытым OPC.
    Ждём завершения родителя в фоновом потоке (Windows)."""
    if sys.platform != "win32":
        return
    import ctypes, os, threading
    SYNCHRONIZE = 0x00100000
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(SYNCHRONIZE, False, os.getppid())
    if not handle:
        return

    def _wait():
        k32.WaitForSingleObject(handle, 0xFFFFFFFF)   # INFINITE
        os._exit(0)

    threading.Thread(target=_wait, daemon=True, name="parent-watch").start()


def worker_main(live_q, cmd_q):
    """Точка входа для multiprocessing.Process."""
    # На Windows asyncua требует SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    _exit_with_parent()

    import stand
    stand.redirect_output_to_log()   # под pythonw — вывод в stands/<id>/app.log

    # influxd общий для всех стендов: кто первый — тот поднимает; при выходе
    # НЕ гасим — им может пользоваться окно другого стенда
    influx.ensure_influxd()

    influx_client, write_api = influx.create_write_api()

    # Кольцевые процессоры собираются из конфига внутри opc_worker
    procs = build_procs(write_api, influx.INFLUX_BUCKET, influx.INFLUX_ORG, live_q)

    try:
        asyncio.run(run_worker_loop(live_q, cmd_q, procs))
    finally:
        try:
            write_api.close()
        except Exception:
            pass
        try:
            influx_client.close()
        except Exception:
            pass
