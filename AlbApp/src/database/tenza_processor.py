"""
tenza_processor.py — обработчик данных тензодатчиков.

Слушает bus.data_updated, накапливает cc и массив,
вычисляет окно [prev_cc : cc] с учётом кольцевого буфера,
пишет в InfluxDB без участия GUI.
"""

from datetime import datetime, timezone, timedelta

from PyQt6.QtCore import QObject
from influxdb_client import Point, WritePrecision

from protocol_backend.event_bus import bus
from protocol_backend.tags.tags import Dev_192_168_6_6_OPC_Tags as Tags

ARRAY_SIZE = 50


class TenzaProcessor(QObject):

    def __init__(self, write_api, bucket: str, org: str, parent=None):
        super().__init__(parent)
        self._write_api = write_api
        self._bucket    = bucket
        self._org       = org

        self._array:       list            = []
        self._cc:          int             = -1
        self._prev_cc:     int             = -1
        self._srv:         str             = ""
        self._last_ts: datetime | None     = None
        self.logging:  bool                = True   # переключить снаружи для остановки лога

        # Флаги готовности данных текущего опроса
        self._new_array:   bool            = False
        self._new_cc:      bool            = False

        bus.data_updated.connect(self._on_data)

    def _on_data(self, srv: str, nid: str, val):
        if nid == Tags.tenzaSensorDataArr:
            self._array     = list(val) if val else []
            self._srv       = srv
            self._new_array = True
            self._try_flush()
        elif nid == Tags.cc:
            self._cc     = int(val)
            self._new_cc = True
            self._try_flush()

    def _try_flush(self):
        """Flush только когда оба значения (array и cc) пришли из одного опроса."""
        if not (self._new_array and self._new_cc):
            return

        self._new_array = False
        self._new_cc    = False

        if not self._array:
            self._prev_cc = self._cc
            return

        if self._prev_cc == -1:
            # первый цикл — нет истории, просто запоминаем
            self._prev_cc = self._cc
            return

        self._flush(self._srv, self._cc)
        self._prev_cc = self._cc

    def _flush(self, srv: str, curr: int):
        """Записать элементы от prev_cc до cc в InfluxDB."""
        prev = self._prev_cc

        if prev == curr:
            return  # ПЛК не продвинулся

        # собрать индексы от prev+1 до curr включительно (кольцевой)
        indices = []
        i = (prev + 1) % ARRAY_SIZE
        while True:
            indices.append(i)
            if i == curr:
                break
            i = (i + 1) % ARRAY_SIZE
            if len(indices) > ARRAY_SIZE:
                # защита от зависания если cc прыгнул на полный оборот
                break

        step = timedelta(milliseconds=4)
        if self._last_ts is None:
            self._last_ts = datetime.now(timezone.utc)
        else:
            self._last_ts += step  # следующий элемент сразу за предыдущим батчем

        points = []
        for i, idx in enumerate(indices):
            if idx >= len(self._array):
                continue
            point = (
                Point("tenza")
                .tag("server", srv)
                .field("value", float(self._array[idx]))
                .time(self._last_ts + step * i, WritePrecision.NS)
            )
            points.append(point)

        if points:
            self._last_ts = self._last_ts + step * (len(points) - 1)

        if points:
            try:
                self._write_api.write(bucket=self._bucket, org=self._org, record=points)
                if self.logging:
                    vals = [float(self._array[idx]) for idx in indices if idx < len(self._array)]
                    print(f"[DB] cc={self._cc} prev={self._prev_cc} n={len(vals)} values={vals}")
            except Exception as e:
                print(f"[TenzaProcessor] ошибка записи: {e}")

            times = [p._time.timestamp() for p in points]
            vals  = [p._fields["value"]   for p in points]
            bus.tenza_points.emit(times, vals)
