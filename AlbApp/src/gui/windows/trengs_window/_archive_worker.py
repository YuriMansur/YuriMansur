from PyQt6.QtCore import QThread, pyqtSignal  # фоновый поток и сигнал передачи данных в GUI
from influxdb_client import InfluxDBClient    # клиент для запросов к базе данных InfluxDB

INFLUX_URL       = "http://localhost:8086"
INFLUX_TOKEN     = "wWASbkPKK0KKf4_kL6-FXqR5VENQM89VMgjJln1CNfPFBRgvlLkWPcQOU4p_zX2Up0zaWTKw59aQX0mmQ2Gc7Q=="
INFLUX_ORG       = "Albreht"
INFLUX_BUCKET    = "plc_data"
LIVE_RENDER_MS   = 50       # интервал скролла X-оси (~20 fps)
LIVE_WINDOW_SECS = 60       # глубина live-окна (сек)
MAX_LIVE_POINTS  = 20_000   # буфер на 60 с при 4 мс/точку
N_ARCHIVE_WORKERS = 4


class _ArchiveWorker(QThread):
    """Один параллельный запрос архива — своя часть диапазона."""
    part_ready = pyqtSignal(int, list, list)   # (idx, times, values)

    def __init__(self, idx: int, query: str, parent=None):
        super().__init__(parent)
        self._idx   = idx
        self._query = query

    def run(self):
        client = None
        try:
            client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            stream = client.query_api().query_stream(self._query)
            times, values = [], []
            for record in stream:
                times.append(record.get_time().timestamp())
                values.append(record.get_value())
            self.part_ready.emit(self._idx, times, values)
        except Exception as e:
            print(f"[ArchiveWorker-{self._idx}] ошибка: {e}")
            self.part_ready.emit(self._idx, [], [])
        finally:
            if client:
                client.close()
