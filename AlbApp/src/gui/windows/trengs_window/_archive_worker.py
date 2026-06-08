import warnings

import numpy as np                            # быстрые массивы точек
import pandas as pd                            # bulk-парсинг ответа InfluxDB (C-код, отпускает GIL)
from PyQt6.QtCore import QThread, pyqtSignal  # фоновый поток и сигнал передачи данных в GUI
from influxdb_client import InfluxDBClient    # клиент для запросов к базе данных InfluxDB
from influxdb_client.client.warnings import MissingPivotFunction

# Запрашиваем одно поле — pivot() не нужен; глушим советующее предупреждение клиента.
warnings.simplefilter("ignore", MissingPivotFunction)

_EMPTY = np.empty(0, dtype=np.float64)

INFLUX_URL       = "http://localhost:8086"
INFLUX_TOKEN     = "wWASbkPKK0KKf4_kL6-FXqR5VENQM89VMgjJln1CNfPFBRgvlLkWPcQOU4p_zX2Up0zaWTKw59aQX0mmQ2Gc7Q=="
INFLUX_ORG       = "Albreht"
INFLUX_BUCKET    = "plc_data"
LIVE_RENDER_MS   = 50        # интервал скролла X-оси (~20 fps)
LIVE_WINDOW_SECS = 300       # глубина live-окна (сек)
MAX_LIVE_POINTS  = 100_000   # буфер на 300 с при 4 мс/точку
N_ARCHIVE_WORKERS = 8


class _ArchiveWorker(QThread):
    """Один параллельный запрос архива — своя часть диапазона.

    Парсит ответ целиком через pandas (C-код), отдаёт numpy-массивы:
    в разы быстрее поштучного query_stream на больших объёмах.
    """
    part_ready = pyqtSignal(int, object, object)   # (idx, times: np.ndarray, values: np.ndarray)

    def __init__(self, idx: int, query: str, parent=None):
        super().__init__(parent)
        self._idx   = idx
        self._query = query

    def run(self):
        import time as _t                       # DEBUG-тайминг: убрать после диагностики
        client = None
        try:
            # enable_gzip — ответ Influx (annotated CSV) едет сжатым, в разы меньше байт по сети
            client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG,
                                    enable_gzip=True)
            _t0 = _t.perf_counter()
            df = client.query_api().query_data_frame(self._query)
            _t1 = _t.perf_counter()             # конец запроса+парсинга pandas
            # при нескольких таблицах клиент возвращает список DataFrame
            if isinstance(df, list):
                df = pd.concat(df, ignore_index=True) if df else None

            if df is None or len(df) == 0 or "_value" not in df.columns:
                self.part_ready.emit(self._idx, _EMPTY, _EMPTY)
                return

            # _time → секунды Unix; _value → float64 (векторно).
            # dtype='datetime64[ns]' нормализует разрешение (pandas 3 даёт us) и снимает tz.
            times  = df["_time"].to_numpy(dtype="datetime64[ns]").astype("int64") / 1e9
            values = df["_value"].to_numpy(dtype=np.float64)
            # сортировка внутри куска делается здесь, в фоновом потоке (на случай тегов /
            # нескольких таблиц). Куски воркеров по времени не пересекаются, поэтому в GUI
            # остаётся только склейка частей по порядку idx — без argsort на главном потоке.
            order = np.argsort(times, kind="stable")
            _t2 = _t.perf_counter()             # конец numpy-конвертации + сортировки
            print(f"[ArchiveWorker-{self._idx}] строк={len(df):>9}  "
                  f"запрос+парсинг={_t1 - _t0:6.2f}с  numpy+sort={_t2 - _t1:6.2f}с")
            self.part_ready.emit(self._idx, times[order], values[order])
        except Exception as e:
            print(f"[ArchiveWorker-{self._idx}] ошибка: {e}")
            self.part_ready.emit(self._idx, _EMPTY, _EMPTY)
        finally:
            if client:
                client.close()
