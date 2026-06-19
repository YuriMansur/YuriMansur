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


def worker_main(live_q, cmd_q):
    """Точка входа для multiprocessing.Process."""
    # На Windows asyncua требует SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    influxd_proc = influx.ensure_influxd()

    import atexit
    if influxd_proc is not None:
        atexit.register(influxd_proc.terminate)

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
