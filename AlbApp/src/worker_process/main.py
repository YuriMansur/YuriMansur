"""
worker_process/main.py — изолированный рабочий процесс (отдельный GIL).

Выполняет:
  - OPC UA опрос + подписка (asyncua)
  - обработка кольцевого буфера (TenzaProc / DisplacementProc)
  - запись в InfluxDB (influxdb_client SYNCHRONOUS)
  - пересылка live-данных в GUI через multiprocessing.Queue (live_q)
  - приём команд записи тегов через multiprocessing.Queue (cmd_q)

Не импортирует ничего из PyQt6.
"""

import asyncio
import queue as _queue
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

# Добавляем src/ в sys.path на случай, если процесс запущен напрямую
sys.path.insert(0, str(Path(__file__).parent.parent))

from asyncua import Client, ua
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from worker_process._processors import TenzaProc, DisplacementProc

# ── Конфигурация ───────────────────────────────────────────────────────────────
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "wWASbkPKK0KKf4_kL6-FXqR5VENQM89VMgjJln1CNfPFBRgvlLkWPcQOU4p_zX2Up0zaWTKw59aQX0mmQ2Gc7Q=="
INFLUX_ORG    = "Albreht"
INFLUX_BUCKET = "plc_data"

OPC_ENDPOINT       = "opc.tcp://192.168.6.6:4840"
OPC_SERVER_ID      = "PLC1"
RECONNECT_INTERVAL = 5    # секунд до следующей попытки
POLL_INTERVAL      = 0.1  # секунд между опросами массивов

# ── NodeId тегов ──────────────────────────────────────────────────────────────
_BASE = "ns=4;s=|var|Xinje-Cortex-Linux-SM-CNC.Application.MAIN.StandLogicEx."

CC_NID            = _BASE + "cc"
TENZA_NID         = _BASE + "tenzaSensorDataArr"
DISPLACEMENT_NID  = _BASE + "displacementSensorArr"
NOWSETPOINT_NID   = _BASE + "nowSetpoint"
CMD_POWER_ON_NID  = _BASE + "cmdPowerOn"
CMD_POWER_OFF_NID = _BASE + "cmdPowerOff"
CMD_FORWARD_NID   = _BASE + "cmdForwardJogging"
CMD_BACKWARD_NID  = _BASE + "cmdBackwardJogging"
CMD_CTRL_NID      = _BASE + "cmdChangeControlMode"

# Порядок последовательного опроса: сначала cc, затем массивы
POLL_NIDS = [CC_NID, DISPLACEMENT_NID, TENZA_NID]

# Теги для подписки (кнопки + уставка)
SUBSCRIBE_NIDS = [
    CMD_POWER_ON_NID, CMD_POWER_OFF_NID,
    CMD_FORWARD_NID,  CMD_BACKWARD_NID,
    CMD_CTRL_NID,     NOWSETPOINT_NID,
]


def _normalize_nid(nid_str: str) -> str:
    """Привести NodeId к формату ns=X;s=... если asyncua вернул repr-формат."""
    if not nid_str.startswith("NodeId("):
        return nid_str
    m_ns = re.search(r"NamespaceIndex=(\d+)", nid_str)
    m_id = re.search(r"Identifier='([^']+)'", nid_str)
    if m_ns and m_id:
        return f"ns={m_ns.group(1)};s={m_id.group(1)}"
    return nid_str


class _SubHandler:
    """Обработчик подписок asyncua — вызывается из asyncio event loop."""

    def __init__(self, live_q, tenza_proc: TenzaProc):
        self._live_q     = live_q
        self._tenza_proc = tenza_proc

    def datachange_notification(self, node, val, data):
        try:
            nid = _normalize_nid(str(node.nodeid))
            # Уставка нужна TenzaProc для записи рядом с тензо-точками
            if nid == NOWSETPOINT_NID:
                self._tenza_proc.on_data(OPC_SERVER_ID, nid, val)
            self._live_q.put_nowait({'type': 'tag', 'nid': nid, 'val': val})
        except Exception as e:
            print(f"[SubHandler] error: {e}")


async def _run_connected(client: Client, live_q, cmd_q,
                         tenza_proc: TenzaProc, disp_proc: DisplacementProc):
    """Работает пока соединение живо. Исключение = разрыв → reconnect."""
    live_q.put_nowait({'type': 'connected', 'server': OPC_SERVER_ID})

    # Кэш объектов узлов
    poll_nodes  = {nid: client.get_node(nid) for nid in POLL_NIDS}
    sub_nodes   = {nid: client.get_node(nid) for nid in SUBSCRIBE_NIDS}
    write_nodes: dict = {}

    # Подписка на кнопки и уставку
    handler = _SubHandler(live_q, tenza_proc)
    sub = await client.create_subscription(500, handler)
    await sub.subscribe_data_change(list(sub_nodes.values()))

    # Начальное чтение подписанных тегов (состояния кнопок)
    for nid, node in sub_nodes.items():
        try:
            val = await node.read_value()
            if nid == NOWSETPOINT_NID:
                tenza_proc.on_data(OPC_SERVER_ID, nid, val)
            live_q.put_nowait({'type': 'tag', 'nid': nid, 'val': val})
        except Exception as e:
            print(f"[worker] initial read {nid}: {e}")

    loop = asyncio.get_event_loop()

    while True:
        t_start = loop.time()

        # Выполнить команды записи из GUI (неблокирующий дрейн)
        while True:
            try:
                cmd = cmd_q.get_nowait()
                nid = cmd['nid']
                val = cmd['val']
                if nid not in write_nodes:
                    write_nodes[nid] = client.get_node(nid)
                try:
                    await write_nodes[nid].write_value(ua.DataValue(ua.Variant(int(val))))
                    readback = await write_nodes[nid].read_value()
                    live_q.put_nowait({'type': 'tag', 'nid': nid, 'val': readback})
                except Exception as e:
                    print(f"[worker] write {nid}: {e}")
            except _queue.Empty:
                break

        # Последовательный опрос массивов: cc → displacement → tenza
        for nid in POLL_NIDS:
            val = await poll_nodes[nid].read_value()   # исключение → выход → reconnect
            tenza_proc.on_data(OPC_SERVER_ID, nid, val)
            disp_proc.on_data(OPC_SERVER_ID, nid, val)
            if nid == TENZA_NID:
                live_q.put_nowait({'type': 'tenza_array',
                                   'data': list(val) if val else []})

        elapsed = loop.time() - t_start
        await asyncio.sleep(max(0.0, POLL_INTERVAL - elapsed))


async def _worker_loop(live_q, cmd_q,
                       tenza_proc: TenzaProc, disp_proc: DisplacementProc):
    """Основной цикл с авто-переподключением."""
    while True:
        try:
            async with Client(url=OPC_ENDPOINT) as client:
                await _run_connected(client, live_q, cmd_q, tenza_proc, disp_proc)
        except Exception as e:
            print(f"[worker] disconnected: {e}")

        tenza_proc.on_disconnect(OPC_SERVER_ID)
        disp_proc.on_disconnect(OPC_SERVER_ID)
        live_q.put_nowait({'type': 'disconnected',  'server': OPC_SERVER_ID})
        live_q.put_nowait({'type': 'reconnecting',  'server': OPC_SERVER_ID,
                           'interval': RECONNECT_INTERVAL})
        await asyncio.sleep(RECONNECT_INTERVAL)


def worker_main(live_q, cmd_q):
    """Точка входа для multiprocessing.Process."""
    # На Windows asyncua требует SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    influxd_proc = _ensure_influxd()

    import atexit
    if influxd_proc is not None:
        atexit.register(influxd_proc.terminate)

    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api     = influx_client.write_api(write_options=SYNCHRONOUS)

    def on_tenza(times, vals):
        live_q.put_nowait({'type': 'tenza', 'times': times, 'vals': vals})

    def on_displacement(times, vals):
        live_q.put_nowait({'type': 'displacement', 'times': times, 'vals': vals})

    def on_setpoint(times, vals):
        live_q.put_nowait({'type': 'setpoint', 'times': times, 'vals': vals})

    tenza_proc = TenzaProc(
        write_api, INFLUX_BUCKET, INFLUX_ORG,
        cc_nid=CC_NID, arr_nid=TENZA_NID, setpoint_nid=NOWSETPOINT_NID,
        on_points=on_tenza, on_setpoint=on_setpoint,
    )
    disp_proc = DisplacementProc(
        write_api, INFLUX_BUCKET, INFLUX_ORG,
        cc_nid=CC_NID, arr_nid=DISPLACEMENT_NID,
        on_points=on_displacement,
    )

    try:
        asyncio.run(_worker_loop(live_q, cmd_q, tenza_proc, disp_proc))
    finally:
        try:
            write_api.close()
        except Exception:
            pass
        try:
            influx_client.close()
        except Exception:
            pass


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _ensure_influxd():
    """Запустить influxd если не запущен. Вернуть процесс или None."""
    try:
        with socket.create_connection(("localhost", 8086), timeout=1):
            return None  # уже работает
    except OSError:
        pass

    influxd = Path(__file__).parent.parent.parent / "influxdb" / "influxd.exe"
    if not influxd.exists():
        print(f"[InfluxDB] influxd.exe не найден: {influxd}")
        return None

    proc = subprocess.Popen(
        [str(influxd)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    print("[InfluxDB] запуск influxd...")
    for _ in range(30):
        time.sleep(0.5)
        try:
            with socket.create_connection(("localhost", 8086), timeout=1):
                print("[InfluxDB] influxd готов")
                return proc
        except OSError:
            pass
    print("[InfluxDB] influxd не запустился за 15 сек")
    return proc
