"""
_processors.py — Qt-free кольцевой буфер для тензодатчиков и датчика перемещения.

Аналоги TenzaProcessor / DisplacementProcessor без зависимости от PyQt6.
Вместо Qt-сигналов используют колбэки on_points / on_setpoint.
"""

from datetime import datetime, timezone, timedelta
from influxdb_client import Point, WritePrecision

ARRAY_SIZE = 50


class TenzaProc:
    """Qt-free обработчик данных тензодатчиков."""

    def __init__(self, write_api, bucket: str, org: str,
                 cc_nid: str, arr_nid: str, setpoint_nid: str,
                 on_points, on_setpoint=None):
        """
        on_points:   callable(times: list[float], vals: list[float])
        on_setpoint: callable(times: list[float], vals: list[float]) | None
        """
        self._write_api     = write_api
        self._bucket        = bucket
        self._org           = org
        self._cc_nid        = cc_nid
        self._arr_nid       = arr_nid
        self._setpoint_nid  = setpoint_nid
        self._on_points     = on_points
        self._on_setpoint   = on_setpoint

        self._array:     list            = []
        self._cc:        int             = -1
        self._prev_cc:   int             = -1
        self._srv:       str             = ""
        self._last_ts:   datetime | None = None
        self._new_array: bool            = False
        self._new_cc:    bool            = False
        self._batch_ts:  datetime | None = None
        self._nowsetpoint: float | None  = None

    def on_data(self, srv: str, nid: str, val):
        if nid == self._arr_nid:
            self._array     = list(val) if val else []
            self._srv       = srv
            self._new_array = True
            self._try_flush()
        elif nid == self._cc_nid:
            self._cc       = int(val)
            self._batch_ts = datetime.now(timezone.utc)
            self._new_cc   = True
            self._try_flush()
        elif nid == self._setpoint_nid:
            self._nowsetpoint = float(val)

    def on_disconnect(self, srv: str):
        self._prev_cc   = -1
        self._new_cc    = False
        self._new_array = False

    def _try_flush(self):
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

        if len(indices) >= ARRAY_SIZE:
            print(f"[tenza] cc leap (prev={prev}, curr={curr}), skipping")
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
                Point("tenza")
                .tag("server", srv)
                .field("value", float(self._array[idx]))
                .time(self._last_ts + step * i, WritePrecision.NS)
            )
            points.append(point)

        if points:
            self._last_ts = self._last_ts + step * (len(points) - 1)

        if not points:
            return

        all_points = list(points)
        sp_ts = self._last_ts
        if self._nowsetpoint is not None:
            all_points.append(
                Point("nowSetpoint")
                .tag("server", srv)
                .field("value", self._nowsetpoint)
                .time(sp_ts, WritePrecision.NS)
            )

        try:
            self._write_api.write(bucket=self._bucket, org=self._org, record=all_points)
            vals = [float(self._array[idx]) for idx in indices if idx < len(self._array)]
        except Exception as e:
            print(f"[TenzaProc] write error: {e}")
            self._last_ts = None
            return

        times = [p._time.timestamp() for p in points]
        vals  = [p._fields["value"] for p in points]
        self._on_points(times, vals)

        if self._nowsetpoint is not None and self._on_setpoint:
            self._on_setpoint([sp_ts.timestamp()], [self._nowsetpoint])


class DisplacementProc:
    """Qt-free обработчик данных датчика перемещения."""

    def __init__(self, write_api, bucket: str, org: str,
                 cc_nid: str, arr_nid: str,
                 on_points):
        """
        on_points: callable(times: list[float], vals: list[float])
        """
        self._write_api = write_api
        self._bucket    = bucket
        self._org       = org
        self._cc_nid    = cc_nid
        self._arr_nid   = arr_nid
        self._on_points = on_points

        self._array:     list            = []
        self._cc:        int             = -1
        self._prev_cc:   int             = -1
        self._srv:       str             = ""
        self._last_ts:   datetime | None = None
        self._new_array: bool            = False
        self._new_cc:    bool            = False
        self._batch_ts:  datetime | None = None

    def on_data(self, srv: str, nid: str, val):
        if nid == self._arr_nid:
            self._array     = list(val) if val else []
            self._srv       = srv
            self._new_array = True
            self._try_flush()
        elif nid == self._cc_nid:
            self._cc       = int(val)
            self._batch_ts = datetime.now(timezone.utc)
            self._new_cc   = True
            self._try_flush()

    def on_disconnect(self, srv: str):
        self._prev_cc   = -1
        self._new_cc    = False
        self._new_array = False

    def _try_flush(self):
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

        if not points:
            return

        try:
            self._write_api.write(bucket=self._bucket, org=self._org, record=points)
            vals = [float(self._array[idx]) for idx in indices if idx < len(self._array)]
        except Exception as e:
            print(f"[DisplacementProc] write error: {e}")
            self._last_ts = None
            return

        times = [p._time.timestamp() for p in points]
        vals  = [p._fields["value"] for p in points]
        self._on_points(times, vals)
