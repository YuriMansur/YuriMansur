"""
ring_buffer.py — кольцевой буфер потокового массива (Qt-free).

RingProc разворачивает массив, который ПЛК заполняет по кругу с индексом cc:
на каждом продвижении cc берёт окно новых элементов (prev_cc … cc], пишет их
точками в InfluxDB (шаг между точками — фикс. интервал) и отдаёт live-точки
через колбэк. Опциональный scalar-тег (например, уставка) пишется одной точкой
на таймлайне массива. Не зависит от PyQt и asyncua — чистая логика + запись.
"""

from datetime import datetime, timezone, timedelta
from influxdb_client import Point, WritePrecision


class RingProc:
    """Кольцевой буфер потокового массива, разворачиваемого по индексу cc.

    Один экземпляр на поток (тензо, перемещение, …). Вместо Qt-сигналов —
    колбэки on_points / on_scalar.

    measurement       — имя measurement в InfluxDB для точек массива.
    cc_nid / arr_nid  — NodeId индекса кольца и самого массива.
    on_points         — callable(times: list[float], vals: list[float]).
    scalar_nid        — опц. NodeId скалярного тега (пишется рядом с батчем).
    scalar_measurement— имя measurement для скалярного тега.
    on_scalar         — опц. callable(times, vals) для скалярного тега.
    array_size        — размер кольцевого буфера на ПЛК.
    """

    def __init__(self, write_api, bucket: str, org: str,
                 measurement: str, cc_nid: str, arr_nid: str, on_points,
                 scalar_nid: str = None, scalar_measurement: str = None,
                 on_scalar=None, array_size: int = 50):
        self._write_api  = write_api
        self._bucket     = bucket
        self._org        = org
        self._measure    = measurement
        self._cc_nid     = cc_nid
        self._arr_nid    = arr_nid
        self._on_points  = on_points
        self._scalar_nid = scalar_nid
        self._scalar_measure = scalar_measurement
        self._on_scalar  = on_scalar
        self._array_size = array_size

        self._array:     list            = []
        self._cc:        int             = -1
        self._prev_cc:   int             = -1
        self._srv:       str             = ""
        self._last_ts:   datetime | None = None
        self._new_array: bool            = False
        self._new_cc:    bool            = False
        self._batch_ts:  datetime | None = None
        self._scalar_val: float | None   = None

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
        elif self._scalar_nid is not None and nid == self._scalar_nid:
            self._scalar_val = float(val)

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

        size = self._array_size
        indices = []
        i = (prev + 1) % size
        while True:
            indices.append(i)
            if i == curr:
                break
            i = (i + 1) % size
            if len(indices) > size:
                break

        if len(indices) >= size:
            print(f"[{self._measure}] cc leap (prev={prev}, curr={curr}), skipping")
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
                Point(self._measure)
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
        has_scalar = self._scalar_nid is not None and self._scalar_val is not None
        if has_scalar:
            all_points.append(
                Point(self._scalar_measure)
                .tag("server", srv)
                .field("value", self._scalar_val)
                .time(sp_ts, WritePrecision.NS)
            )

        try:
            self._write_api.write(bucket=self._bucket, org=self._org, record=all_points)
        except Exception as e:
            print(f"[{self._measure}] write error: {e}")
            self._last_ts = None
            return

        times = [p._time.timestamp() for p in points]
        vals  = [p._fields["value"] for p in points]
        self._on_points(times, vals)

        if has_scalar and self._on_scalar:
            self._on_scalar([sp_ts.timestamp()], [self._scalar_val])
