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
    array_size        — размер кольцевого буфера на ПЛК (max_array_length);
                        0 = ещё не известен, батчи не разбираем до чтения с ПЛК.
    poll_ms           — период опроса массива, мс (servers.json → polls[].interval).
    """

    def __init__(self, write_api, bucket: str, org: str,
                 measurement: str, cc_nid: str, arr_nid: str, on_points,
                 scalar_nid: str = None, scalar_measurement: str = None,
                 on_scalar=None, array_size: int = 0, poll_ms: float = 0.0,
                 stream: str = "", on_rate=None):
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
        self.stream      = stream or measurement   # имя потока в шине (points_msg)
        self._on_rate    = on_rate                 # callable(step_ms) — фактический темп
        self._array:     list            = []
        self._cc:        int             = -1
        self._prev_cc:   int             = -1
        self._srv:       str             = ""
        self._prev_batch_ts: datetime | None = None   # реальное время предыдущего батча
        self._new_array: bool            = False
        self._new_cc:    bool            = False
        self._batch_ts:  datetime | None = None
        self._scalar_val: float | None   = None

        # размер кольца и производный от него шаг точек (см. set_array_size);
        # на живом соединении переопределяется значением max_array_length с ПЛК
        self._poll_ms          = poll_ms
        self._array_size: int  = 0
        self._step: timedelta  = timedelta(0)
        self._diag_left: int   = 3     # сколько батчей продиагностировать (см. _flush)
        self._rate_sent: float | None = None   # последний отданный наружу темп, мс
        # Пишем в БД только во время испытания (включается командой из GUI, см.
        # set_recording). Живой поток через on_points идёт всегда — график и
        # окошки значений работают и между испытаниями.
        self._recording: bool  = False
        self.set_array_size(array_size)

    def set_array_size(self, array_size: int) -> None:
        """Задать размер кольца (max_array_length с ПЛК) и пересчитать шаг точек.

        За один период опроса ПЛК заполняет половину кольца, поэтому на отсчёт
        приходится poll_ms / (array_size / 2): 100 мс и 200 отсчётов → 1 мс.
        Обе величины берутся из конфига/ПЛК, а не зашиты: меняем max_array_length —
        раскладка точек по времени едет следом.

        При изменении размера на живом соединении окно кольца привязываем заново:
        прежний prev_cc относится к другой геометрии буфера.
        """
        changed = array_size != self._array_size
        self._array_size = array_size
        self._step = (timedelta(milliseconds=self._poll_ms / (array_size / 2))
                      if array_size > 0 and self._poll_ms > 0 else timedelta(0))
        if changed:
            self._prev_cc = -1
            self._prev_batch_ts = None
            self._diag_left = 3
            self._rate_sent = None

    def set_recording(self, on: bool) -> None:
        """Включить/выключить запись потока в БД (идёт испытание или нет)."""
        self._recording = on

    @property
    def step_ms(self) -> float:
        """Номинальный шаг между отсчётами батча, мс."""
        return self._step.total_seconds() * 1000

    def on_data(self, srv: str, nid: str, val):
        if nid == self._arr_nid:
            self._array     = list(val) if val else []
            self._srv       = srv
            self._new_array = True
            # Геометрию кольца берём из самого массива: его длина — единственный
            # источник, который не может разойтись с сервером. Конфиг и отдельные
            # теги (max_array_length) описывают ПЛК-сторону и с длиной
            # публикуемого массива не обязаны совпадать.
            if self._array and len(self._array) != self._array_size:
                self.set_array_size(len(self._array))
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
        self._prev_batch_ts = None   # после реконнекта таймлайн привязываем заново

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

    def _flush(self, srv: str, curr: int):
        size = self._array_size
        if size <= 0 or self._poll_ms <= 0:
            # геометрия кольца ещё не известна (массив не прочитан) либо не задан
            # период опроса — разбирать батч нечем, ждём
            return
        prev = self._prev_cc
        # Голову кольца (слот под текущим cc) НЕ читаем: ПЛК может писать её прямо
        # сейчас, а cc и массив приходят разными OPC-чтениями — на этом слоте ловится
        # полузаписанное/старое с прошлого витка значение (одиночные выбросы на графике).
        # Отстаём на один отсчёт: разбираем (prev … safe], safe = cc-1 — заведомо готовые
        # слоты. Голова доедет следующим тиком, потерь нет.
        safe = (curr - 1) % size
        if safe == prev:
            return
        self._prev_cc = safe          # окно (prev … safe] считаем обработанным

        indices = []
        i = (prev + 1) % size
        while True:
            indices.append(i)
            if i == safe:
                break
            i = (i + 1) % size
            if len(indices) > size:
                break

        if len(indices) >= size:
            print(f"[{self._measure}] cc leap (prev={prev}, curr={curr}), skipping")
            return

        # Времена точек привязываем к РЕАЛЬНОМУ времени: n отсчётов батча раскладываем
        # равномерно на интервал (prev_batch_ts … batch_ts], последний = batch_ts (now).
        # Так таймлайн не уходит от now и точки не вылетают за живое окно трендов; между
        # батчами строго монотонно. (Секция 4 рисует по индексу отсчёта — ей это неважно.)
        now   = self._batch_ts
        valid = [idx for idx in indices if idx < len(self._array)]
        if not valid:
            self._prev_batch_ts = now
            return
        n    = len(valid)
        span = (now - self._prev_batch_ts) if self._prev_batch_ts is not None else timedelta(0)
        if span <= timedelta(0):
            # Первый батч после подключения: реального интервала ещё нет. Берём
            # период опроса — именно за него батч и набрался. Номинал из размера
            # кольца тут не годится: темп задаёт цикл ПЛК, а не глубина буфера
            # (замер: буфер 200, а шаг всё равно ~4 мс).
            span = timedelta(milliseconds=self._poll_ms)
        dt    = span / n
        start = self._prev_batch_ts if self._prev_batch_ts is not None else (now - dt * n)

        # Фактический темп наружу: живой график выделяет буфер под окно по нему,
        # а не по номиналу — шаг задаёт ПЛК, а не размер кольца. Шлём только при
        # заметном изменении: измеренный шаг слегка плавает от батча к батчу.
        if self._on_rate is not None and self._prev_batch_ts is not None:
            ms = dt.total_seconds() * 1000
            if self._rate_sent is None or abs(ms - self._rate_sent) > self._rate_sent * 0.25:
                self._rate_sent = ms
                self._on_rate(ms)

        # Диагностика темпа: сколько отсчётов реально принёс батч и какой из этого
        # выходит шаг — против номинального (poll_ms / (размер_кольца / 2)).
        # Расхождение значит, что ПЛК пишет не половину кольца за период опроса:
        # на стенде так и есть — частоту задаёт цикл ПЛК, а не глубина буфера.
        if self._diag_left > 0:
            self._diag_left -= 1
            print(f"[{self._measure}] батч: {n} отсчётов за "
                  f"{span.total_seconds() * 1000:.1f} мс → фактический шаг "
                  f"{dt.total_seconds() * 1000:.2f} мс "
                  f"(номинальный {self.step_ms:.2f} мс, кольцо {size})")

        points = [
            Point(self._measure)
            .tag("server", srv)
            .field("value", float(self._array[idx]))
            .time(start + dt * (k + 1), WritePrecision.NS)
            for k, idx in enumerate(valid)
        ]
        sp_ts = now                            # скаляр (уставка) — на правом краю батча

        all_points = list(points)
        has_scalar = self._scalar_nid is not None and self._scalar_val is not None
        if has_scalar:
            all_points.append(
                Point(self._scalar_measure)
                .tag("server", srv)
                .field("value", self._scalar_val)
                .time(sp_ts, WritePrecision.NS)
            )

        # В БД пишем только во время испытания; вне его точки всё равно уходят
        # в GUI ниже — живой график и текущие значения работают всегда.
        if self._recording:
            try:
                self._write_api.write(bucket=self._bucket, org=self._org, record=all_points)
            except Exception as e:
                print(f"[{self._measure}] write error: {e}")
                return

        self._prev_batch_ts = now              # следующий батч продолжит от текущего now

        times = [p._time.timestamp() for p in points]
        vals  = [p._fields["value"] for p in points]
        self._on_points(times, vals)

        if has_scalar and self._on_scalar:
            self._on_scalar([sp_ts.timestamp()], [self._scalar_val])
