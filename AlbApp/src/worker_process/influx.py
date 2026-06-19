"""
influx.py — инфраструктура InfluxDB для рабочего процесса (Qt-free).

Запуск локального influxd.exe (если не поднят) и создание SYNCHRONOUS write_api.
Синхронная запись выбрана осознанно: немедленная обратная связь об ошибке (на
ней построен сброс таймлайна в RingProc), простота и порядок; БД локальная,
поэтому блокировка пренебрежимо мала.
"""

import socket
import subprocess
import time
from pathlib import Path

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "wWASbkPKK0KKf4_kL6-FXqR5VENQM89VMgjJln1CNfPFBRgvlLkWPcQOU4p_zX2Up0zaWTKw59aQX0mmQ2Gc7Q=="
INFLUX_ORG    = "Albreht"
INFLUX_BUCKET = "plc_data"


def ensure_influxd():
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


def create_write_api():
    """Создать клиент и SYNCHRONOUS write_api. Вернуть (client, write_api)."""
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    return client, client.write_api(write_options=SYNCHRONOUS)
