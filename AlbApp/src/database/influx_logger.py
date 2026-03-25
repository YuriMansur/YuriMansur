import queue
import re
import socket
import subprocess
import time
from pathlib import Path

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from PyQt6.QtCore import QObject, QThread

from protocol_backend.event_bus import bus
from database.tenza_processor import TenzaProcessor
from database.displacement_processor import DisplacementProcessor


_DISCONNECT = object()  # sentinel для события отключения


class _DbWorkerThread(QThread):
    """QThread с очередью вместо Qt event loop.

    Выполняет _on_data / _on_disconnect процессоров в контексте Qt-потока,
    что позволяет корректно эмитировать Qt-сигналы (bus.tenza_points и т.д.)
    из процессоров без участия главного потока.
    """

    def __init__(self, tenza: TenzaProcessor, disp: DisplacementProcessor, parent=None):
        super().__init__(parent)
        self._q:     queue.SimpleQueue = queue.SimpleQueue()
        self._tenza  = tenza
        self._disp   = disp

    def put(self, item):
        self._q.put(item)

    def run(self):  # переопределяем exec() — никакого Qt event loop
        while True:
            item = self._q.get()
            if item is None:
                break
            try:
                srv, nid, val = item
                if srv is _DISCONNECT:
                    self._tenza._on_disconnect(nid)   # nid хранит реальный srv
                    self._disp._on_disconnect(nid)
                else:
                    self._tenza._on_data(srv, nid, val)
                    self._disp._on_data(srv, nid, val)
            except Exception as e:
                print(f"[DbWorker] ошибка обработки: {e} | item={item}")

    def stop(self):
        self._q.put(None)   # poison pill
        self.wait(3000)


def _ensure_influxd() -> "subprocess.Popen | None":
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


# ── Конфигурация ──────────────────────────────────────────────────────────────
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "wWASbkPKK0KKf4_kL6-FXqR5VENQM89VMgjJln1CNfPFBRgvlLkWPcQOU4p_zX2Up0zaWTKw59aQX0mmQ2Gc7Q=="
INFLUX_ORG    = "Albreht"
INFLUX_BUCKET = "plc_data"

# теги которые не пишем напрямую — обрабатываются отдельно
_SKIP_TAGS = {"tenzaSensorDataArr", "cc", "displacementSensorArr", "nowSetpoint"}


class InfluxLogger(QObject):
    """Слушает bus.data_updated и пишет теги в InfluxDB.

    Процессоры работают в _DbWorkerThread (QThread + SimpleQueue).
    Главный поток только кладёт данные в очередь (мгновенно) — любой лаг GUI
    не влияет на запись в БД.
    """

    def __init__(self, parent=None, backend=None):
        super().__init__(parent)

        self._influxd_proc = _ensure_influxd()

        # Клиент для медленных тегов (кнопки и т.д.) — пишется в главном потоке
        self._client    = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)

        # Отдельный клиент для процессоров (SYNCHRONOUS не thread-safe между потоками)
        self._proc_client    = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        self._proc_write_api = self._proc_client.write_api(write_options=SYNCHRONOUS)

        self._tenza        = TenzaProcessor(       self._proc_write_api, INFLUX_BUCKET, INFLUX_ORG)
        self._displacement = DisplacementProcessor(self._proc_write_api, INFLUX_BUCKET, INFLUX_ORG)

        # QThread с очередью: Qt-контекст для корректных сигналов, GUI не ждёт БД
        self._db_thread = _DbWorkerThread(self._tenza, self._displacement, self)
        self._db_thread.start()

        bus.data_updated       .connect(self._enqueue_data)       # медленные теги (кнопки)
        bus.server_disconnected.connect(self._enqueue_disconnect)

        # Быстрый путь: данные массивов напрямую из потока OPC UA, минуя главный поток
        if backend is not None:
            backend.on_data_updated = self._direct_db_handler

    # ── Быстрый путь: из потока OPC UA, минуя главный поток ─────────────────────

    @staticmethod
    def _normalize_nid(nid: str) -> str:
        """Привести NodeId к формату ns=X;s=... (аналог ServerManager._normalize_nid)."""
        if not nid.startswith("NodeId("):
            return nid
        m_ns = re.search(r"NamespaceIndex=(\d+)", nid)
        m_id = re.search(r"Identifier='([^']+)'", nid)
        if m_ns and m_id:
            return f"ns={m_ns.group(1)};s={m_id.group(1)}"
        return nid

    def _direct_db_handler(self, srv: str, nid: str, val):
        """Вызывается прямо из потока OPC UA (DirectConnection).
        Только thread-safe операции: нормализация nid и put() в очередь.
        """
        nid = self._normalize_nid(nid)
        tag_name = nid.split(".")[-1]
        if tag_name in _SKIP_TAGS:
            self._db_thread.put((srv, nid, val))

    # ── Главный поток: медленные теги (кнопки) ───────────────────────────────

    def _enqueue_data(self, srv: str, nid: str, val):
        tag_name = nid.split(".")[-1]
        if tag_name not in _SKIP_TAGS:
            # Кнопки пишем прямо здесь — они редкие, задержка некритична
            point = (
                Point("plc_tag")
                .tag("server", srv)
                .tag("node_id", nid)
                .field(tag_name, float(val) if not isinstance(val, bool) else int(val))
                .time(None, WritePrecision.NS)
            )
            try:
                self._write_api.write(bucket=INFLUX_BUCKET, record=point)
            except Exception as e:
                print(f"[InfluxDB] ошибка записи: {e}")
        # SKIP_TAGS обрабатываются в _direct_db_handler (поток OPC UA)

    def _enqueue_disconnect(self, srv: str):
        self._db_thread.put((_DISCONNECT, srv, None))  # srv передаётся как второй элемент

    def close(self):
        """Закрыть соединение — вызвать при завершении приложения."""
        if self._influxd_proc is not None:
            self._influxd_proc.terminate()
            self._influxd_proc = None
        self._db_thread.stop()
        try:
            self._proc_write_api.close()
        except Exception:
            pass
        try:
            self._proc_client.close()
        except Exception:
            pass
        try:
            self._write_api.close()
        except Exception:
            pass
        try:
            self._client.close()
        except Exception:
            pass
        try:
            self._client._api_client._signout = lambda: None
        except Exception:
            pass
