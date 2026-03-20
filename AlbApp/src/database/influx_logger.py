from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from PyQt6.QtCore import QObject

from protocol_backend.event_bus import bus
from database.tenza_processor import TenzaProcessor


# ── Конфигурация ──────────────────────────────────────────────────────────────
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "wWASbkPKK0KKf4_kL6-FXqR5VENQM89VMgjJln1CNfPFBRgvlLkWPcQOU4p_zX2Up0zaWTKw59aQX0mmQ2Gc7Q=="
INFLUX_ORG    = "Albreht"
INFLUX_BUCKET = "plc_data"

# теги которые не пишем напрямую — обрабатываются отдельно
_SKIP_TAGS = {"tenzaSensorDataArr", "cc"}


class InfluxLogger(QObject):
    """Слушает bus.data_updated и пишет все входящие теги в InfluxDB."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._client    = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)

        self._tenza = TenzaProcessor(self._write_api, INFLUX_BUCKET, INFLUX_ORG, parent=self)

        bus.data_updated.connect(self._on_data)

    def _on_data(self, srv: str, nid: str, val):
        """Записать одну точку в InfluxDB."""
        tag_name = nid.split(".")[-1]  # берём короткое имя тега
        if tag_name in _SKIP_TAGS:
            return  # обрабатывается TenzaProcessor
        point = (
            Point("plc_tag")
            .tag("server", srv)
            .tag("node_id", nid)
            .field(tag_name, float(val) if not isinstance(val, bool) else int(val))
            .time(None, WritePrecision.NS)  # текущее время
        )
        try:
            self._write_api.write(bucket=INFLUX_BUCKET, record=point)
        except Exception as e:
            print(f"[InfluxDB] ошибка записи: {e}")

    def close(self):
        """Закрыть соединение — вызвать при завершении приложения."""
        try:
            self._write_api.close()
        except Exception:
            pass
        try:
            self._client.close()
        except Exception:
            pass
        # Баг influxdb_client: __del__ вызывает _signout когда Python уже
        # обнулил глобалы. Обнуляем заранее чтобы подавить TypeError.
        try:
            self._client._api_client._signout = lambda: None
        except Exception:
            pass
