"""
displacement_processor.py — обработчик данных датчика перемещения.

Аналог TenzaProcessor: слушает bus.data_updated, накапливает cc и массив,
вычисляет окно [prev_cc : cc] с учётом кольцевого буфера,
пишет в InfluxDB без участия GUI.
"""

from datetime import datetime, timezone, timedelta

from PyQt6.QtCore import QObject
from influxdb_client import Point, WritePrecision

from protocol_backend.event_bus import bus
from protocol_backend.tags.tags import Dev_192_168_6_6_OPC_Tags as Tags

ARRAY_SIZE = 50


class DisplacementProcessor(QObject):

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
        self.logging:  bool                = True

        self._new_array:   bool            = False
        self._new_cc:      bool            = False
        self._batch_ts:    datetime | None = None   # время получения cc текущего цикла

        # Подключение управляется снаружи (InfluxLogger)

    def _on_data(self, srv: str, nid: str, val):
        if nid == Tags.displacementSensorArr:
            self._array     = list(val) if val else []
            self._srv       = srv
            self._new_array = True
            self._try_flush()
        elif nid == Tags.cc:
            self._cc       = int(val)
            self._batch_ts = datetime.now(timezone.utc)
            self._new_cc   = True
            self._try_flush()

    def _on_disconnect(self, _srv: str):
        """При разрыве сбрасываем счётчик — первый батч после реконнекта пропускаем."""
        self._prev_cc    = -1
        self._new_cc     = False
        self._new_array  = False

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
            self._prev_cc = self._cc
            return

        self._flush(self._srv, self._cc)
        self._prev_cc = self._cc

    def _flush(self, srv: str, curr: int):
        """Записать элементы от prev_cc до cc в InfluxDB."""
        prev = self._prev_cc

        if prev == curr:
            return

        indices = []
        i = (prev + 1) % ARRAY_SIZE
        while True:
            indices.append(i)
            if i == curr:
                break
            i = (i + 1) % ARRAY_SIZE
            if len(indices) > ARRAY_SIZE:
                break

        # Если окно охватывает весь буфер — cc прыгнул через полный оборот
        # (реконнект, пропуск цикла). Данные ненадёжны — пропускаем батч.
        if len(indices) >= ARRAY_SIZE:
            print(f"[displacement] cc leap (prev={prev}, curr={curr}), skipping")
            return

        step = timedelta(milliseconds=4)
        if self._last_ts is None:
            self._last_ts = self._batch_ts
        else:
            self._last_ts += step

        points = []
        for i, idx in enumerate(indices):
            if idx >= len(self._array):
                continue
            point = (
                Point("displacement")
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
                    print(f"[DB displacement] cc={self._cc} prev={self._prev_cc} n={len(vals)} values={vals}")
            except Exception as e:
                print(f"[DisplacementProcessor] ошибка записи: {e}")
                self._last_ts = None  # следующий батч стартует от реального времени

            times = [p._time.timestamp() for p in points]
            vals  = [p._fields["value"]   for p in points]
            bus.displacement_points.emit(times, vals)
