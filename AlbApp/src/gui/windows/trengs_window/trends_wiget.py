import datetime as _dt
from collections import deque
import numpy as np
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton,
                             QFormLayout, QGroupBox, QColorDialog,
                             QDateEdit, QTimeEdit, QCheckBox,
                             QStackedWidget, QHBoxLayout)
from PyQt6.QtCore import Qt, QDateTime, QTimer, QThread, pyqtSignal
import pyqtgraph as pg
from influxdb_client import InfluxDBClient

def _translate_pg_menus(plot_widget):
    """Переводит контекстное меню pyqtgraph на русский."""
    vb = plot_widget.getViewBox()
    m  = vb.menu   # ViewBoxMenu

    # ── ViewBox: верхний уровень ──────────────────────────────
    m.viewAll.setText("Показать всё")
    m.mouseModes[0].setText("3 кнопки (панорама)")
    m.mouseModes[1].setText("1 кнопка (выделение)")

    # ── ViewBox: подменю осей и режима мыши ──────────────────
    _sub_ru = {"X axis": "Ось X", "Y axis": "Ось Y", "Mouse Mode": "Режим мыши"}
    for action in m.actions():
        if action.menu() and action.text() in _sub_ru:
            action.menu().setTitle(_sub_ru[action.text()])
        # Export... встречается прямо в меню ViewBox (без подменю)
        if action.text().replace("&", "") in ("Export...", "Export"):
            action.setText("Экспорт...")

    # ── ViewBox: форм-виджеты осей (X=ctrl[0], Y=ctrl[1]) ────
    for ui in m.ctrl:
        ui.autoRadio       .setText("Авто")
        ui.manualRadio     .setText("Вручную")
        ui.invertCheck     .setText("Инвертировать ось")
        ui.mouseCheck      .setText("Управление мышью")
        ui.visibleOnlyCheck.setText("Только видимые данные")
        ui.autoPanCheck    .setText("Только авто-сдвиг")
        ui.label           .setText("Привязать к:")

    # ── PlotItem: меню "Plot Options" и его подменю ───────────
    pi = plot_widget.getPlotItem()
    if not (hasattr(pi, "ctrlMenu") and pi.ctrlMenu):
        return

    pi.ctrlMenu.setTitle("Параметры графика")

    _submenu_ru = {
        "Transforms": "Преобразования",
        "Downsample": "Прореживание",
        "Average":    "Усреднение",
        "Alpha":      "Прозрачность",
        "Grid":       "Сетка",
        "Points":     "Точки",
        "Export...":  "Экспорт...",
        "Export":     "Экспорт",
    }
    for action in pi.ctrlMenu.actions():
        if action.text() in _submenu_ru:
            if action.menu():
                action.menu().setTitle(_submenu_ru[action.text()])
            else:
                action.setText(_submenu_ru[action.text()])

    # ── Диалог экспорта — переводим при первом открытии ──────
    def _on_export_triggered(pi=pi):
        from PyQt6.QtCore import QTimer as _QTimer
        def _do_translate():
            dlg = getattr(pi, "exportDialog", None)
            if dlg is None:
                return
            dlg.setWindowTitle("Экспорт")
            ui = dlg.ui
            if hasattr(ui, "exportBtn"): ui.exportBtn.setText("Экспорт")
            if hasattr(ui, "closeBtn"):  ui.closeBtn .setText("Закрыть")
            if hasattr(ui, "copyBtn"):   ui.copyBtn  .setText("Копировать")
        _QTimer.singleShot(50, _do_translate)

    for action in pi.ctrlMenu.actions():
        txt = action.text().replace("&", "")
        if txt in ("Export...", "Export"):
            action.triggered.connect(_on_export_triggered)

    # ── PlotItem: форм-виджеты внутри подменю ────────────────
    c = pi.ctrl

    # Transforms
    c.fftCheck         .setText("Спектр мощности (БПФ)")
    c.subtractMeanCheck.setText("Вычесть среднее")
    c.logXCheck        .setText("Лог X")
    c.logYCheck        .setText("Лог Y")
    c.derivativeCheck  .setText("dy/dx")
    c.phasemapCheck    .setText("Y vs. Y'")

    # Downsample
    c.downsampleCheck    .setText("Прореживание")
    c.autoDownsampleCheck.setText("Авто")
    c.subsampleRadio     .setText("Подвыборка")
    c.meanRadio          .setText("Среднее")
    c.peakRadio          .setText("Пик")
    c.clipToViewCheck    .setText("Обрезать по виду")
    c.maxTracesCheck     .setText("Макс. кривых:")
    c.forgetTracesCheck  .setText("Удалять скрытые")

    # Grid
    c.xGridCheck.setText("Сетка X")
    c.yGridCheck.setText("Сетка Y")
    c.label     .setText("Непрозрачность")

    # Alpha
    c.autoAlphaCheck.setText("Авто")

    # Points
    c.autoPointsCheck.setText("Авто")
    # заголовки QGroupBox внутри виджетов
    c.averageGroup.setTitle("Усреднение")
    c.pointsGroup .setTitle("Точки")
    c.alphaGroup  .setTitle("Прозрачность")


def _install_x_time_format(plot_widget):
    """
    Патчит поля ручного диапазона оси X:
    - updateState → отображает ЧЧ:ММ:СС вместо Unix-timestamp
    - text()      → возвращает float-строку, когда pyqtgraph читает значение
    Поля ищем через findChildren — не зависит от индекса ctrl.
    """
    from PyQt6.QtWidgets import QLineEdit
    vb   = plot_widget.getViewBox()
    menu = vb.menu

    # Найти подменю «Ось X» (уже переведено _translate_pg_menus)
    x_submenu = None
    for action in menu.actions():
        if action.menu() and action.text() in ("Ось X", "X Axis", "X axis"):
            x_submenu = action.menu()
            break
    if x_submenu is None:
        return

    les = x_submenu.findChildren(QLineEdit)
    if len(les) < 2:
        return
    min_le, max_le = les[0], les[1]

    def _fmt(orig_fn):
        try:
            return _dt.datetime.fromtimestamp(float(orig_fn())).strftime("%H:%M:%S")
        except (ValueError, OSError):
            return orig_fn()

    def _parse(orig_fn):
        text = orig_fn()
        try:
            float(text)
            return text                      # уже число — оставляем
        except ValueError:
            x0, x1 = vb.viewRange()[0]
            ref = _dt.datetime.fromtimestamp((x0 + x1) / 2)
            for fmt in ("%H:%M:%S", "%H:%M"):
                try:
                    t = _dt.datetime.strptime(text.strip(), fmt)
                    dt = ref.replace(hour=t.hour, minute=t.minute,
                                     second=t.second, microsecond=0)
                    return f"{dt.timestamp():.3f}"
                except ValueError:
                    continue
            return text

    # ── 1. updateState: после обновления полей → показать ЧЧ:ММ:СС ─────────
    orig_update  = menu.updateState
    orig_min_raw = min_le.text          # сохранить ДО shadowing
    orig_max_raw = max_le.text
    def _patched_update():
        orig_update()
        if not min_le.hasFocus():
            min_le.setText(_fmt(orig_min_raw))
        if not max_le.hasFocus():
            max_le.setText(_fmt(orig_max_raw))
    menu.updateState = _patched_update

    # ── 2. shadow text(): pyqtgraph читает float, даже если показано время ──
    min_le.text = lambda: _parse(orig_min_raw)
    max_le.text = lambda: _parse(orig_max_raw)


class _TimeAxisItem(pg.AxisItem):
    """Ось X с метками в формате ЧЧ:ММ:СС (или дд.мм ЧЧ:ММ для больших диапазонов)."""

    def tickStrings(self, values, scale, spacing):  # noqa: ARG002
        result = []
        for v in values:
            try:
                dt = _dt.datetime.fromtimestamp(v)
                if spacing >= 86400:          # диапазон > суток → дд.мм ЧЧ:ММ
                    result.append(dt.strftime("%d.%m\n%H:%M"))
                elif spacing >= 3600:         # диапазон > часа → ЧЧ:ММ
                    result.append(dt.strftime("%H:%M"))
                elif spacing >= 1:            # секунды → ЧЧ:ММ:СС
                    result.append(dt.strftime("%H:%M:%S"))
                else:                         # миллисекунды
                    result.append(dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}")
            except (OSError, ValueError, OverflowError):
                result.append("")
        return result


INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "wWASbkPKK0KKf4_kL6-FXqR5VENQM89VMgjJln1CNfPFBRgvlLkWPcQOU4p_zX2Up0zaWTKw59aQX0mmQ2Gc7Q=="
INFLUX_ORG    = "Albreht"
INFLUX_BUCKET = "plc_data"
LIVE_QUERY_MS    = 300    # интервал запроса новых точек из InfluxDB
LIVE_RENDER_MS   = 50     # интервал перерисовки (20 fps), не зависит от запроса
LIVE_WINDOW_SECS = 60     # глубина live-окна (сек)
MAX_DISPLAY      = 1500   # макс. точек на экране (шаг-прорежка, реальные значения)


class _QueryWorker(QThread):
    """Выполняет запрос к InfluxDB в фоновом потоке."""
    result_ready = pyqtSignal(list, list)

    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self._query = query

    def run(self):
        try:
            client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            tables = client.query_api().query(self._query)
            client.close()
        except Exception as e:
            print(f"[TrendsWidget] ошибка запроса: {e}")
            self.result_ready.emit([], [])
            return

        records = []
        for table in tables:
            records.extend(table.records)
        records.sort(key=lambda r: r.get_time())

        times  = [r.get_time().timestamp() for r in records]
        values = [r.get_value()             for r in records]
        self.result_ready.emit(times, values)


class TrendsWiget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_color = "#e67e22"
        self._archive_lines: list = []
        self._live_curve   = None
        self._query_worker = None
        self._display_t: deque = deque()   # точки уже на экране
        self._display_v: deque = deque()
        self._incoming_t: deque = deque() # получены из БД, ещё не показаны
        self._incoming_v: deque = deque()
        self._last_live_ts: float | None = None

        # запрос новых точек из БД
        self._query_timer = QTimer(self)
        self._query_timer.timeout.connect(self._live_query)

        # рендер — дозированно добавляет точки на экран
        self._render_timer = QTimer(self)
        self._render_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._render_timer.timeout.connect(self._render_frame)

        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # ── переключатель режимов ────────────────────────────────────────────
        row_mode = QHBoxLayout()
        self.btn_live    = QPushButton("● Live")
        self.btn_archive = QPushButton("Архив")
        self.btn_live   .setCheckable(True)
        self.btn_archive.setCheckable(True)
        self.btn_live.setChecked(True)
        self.btn_live   .clicked.connect(lambda: self._set_mode("live"))
        self.btn_archive.clicked.connect(lambda: self._set_mode("archive"))
        row_mode.addWidget(self.btn_live)
        row_mode.addWidget(self.btn_archive)
        row_mode.addStretch()
        self.chk_points = QCheckBox("Показывать точки")
        self.chk_points.toggled.connect(self._toggle_points)
        row_mode.addWidget(self.chk_points)
        root.addLayout(row_mode)

        # ── панели настроек (стек) ───────────────────────────────────────────
        self.stack = QStackedWidget()

        # страница 0: live
        live_group = QGroupBox("Live")
        live_layout = QFormLayout(live_group)
        self.color_btn = QPushButton()
        self.color_btn.setStyleSheet(f"background-color: {self.current_color};")
        self.color_btn.clicked.connect(self._change_color)
        live_layout.addRow("Цвет линии:", self.color_btn)

        self.stack.addWidget(live_group)

        # страница 1: архив
        arch_group = QGroupBox("Архив")
        arch_layout = QVBoxLayout(arch_group)

        presets = [
            ("5 мин",  300),
            ("30 мин", 1800),
            ("1 час",  3600),
            ("6 ч",    21600),
            ("24 ч",   86400),
            ("7 дн",   604800),
        ]
        row_presets = QHBoxLayout()
        for label, secs in presets:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, s=secs: self._apply_preset(s))
            row_presets.addWidget(btn)
        arch_layout.addLayout(row_presets)

        manual_layout = QFormLayout()
        now = QDateTime.currentDateTime()

        self.date_from = QDateEdit(now.addSecs(-300).date())
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        self.date_from.setCalendarPopup(True)
        self.date_from.setMinimumWidth(110)
        self.time_from = QTimeEdit(now.addSecs(-300).time())
        self.time_from.setDisplayFormat("HH:mm:ss")
        self.time_from.setMinimumWidth(85)
        row_from = QHBoxLayout()
        row_from.addWidget(self.date_from)
        row_from.addWidget(self.time_from)
        manual_layout.addRow("С:", row_from)

        self.date_to = QDateEdit(now.date())
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        self.date_to.setCalendarPopup(True)
        self.date_to.setMinimumWidth(110)
        self.time_to = QTimeEdit(now.time())
        self.time_to.setDisplayFormat("HH:mm:ss")
        self.time_to.setMinimumWidth(85)
        row_to = QHBoxLayout()
        row_to.addWidget(self.date_to)
        row_to.addWidget(self.time_to)
        manual_layout.addRow("По:", row_to)

        self.btn_load = QPushButton("Загрузить")
        self.btn_load.clicked.connect(self._load_archive)
        manual_layout.addRow(self.btn_load)
        arch_layout.addLayout(manual_layout)
        self.stack.addWidget(arch_group)

        root.addWidget(self.stack)

        # ── график ───────────────────────────────────────────────────────────
        self.plot_widget = pg.PlotWidget(axisItems={"bottom": _TimeAxisItem(orientation="bottom")})
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()
        root.addWidget(self.plot_widget, 1)

        # перевод контекстного меню
        _translate_pg_menus(self.plot_widget)

        # поля ручного диапазона оси X → формат ЧЧ:ММ:СС
        _install_x_time_format(self.plot_widget)

        self._live_curve = self.plot_widget.plot(
            [], [],
            pen=pg.mkPen(color=self.current_color, width=1),
            name="tenzaSensor (live)",
        )

        # ── перекрестие + метка значения ────────────────────────────────────
        dash = pg.mkPen(color="#888888", width=1, style=Qt.PenStyle.DashLine)
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=dash)
        self._hline = pg.InfiniteLine(angle=0,  movable=False, pen=dash)
        self._vline.setVisible(False)
        self._hline.setVisible(False)
        self.plot_widget.addItem(self._vline, ignoreBounds=True)
        self.plot_widget.addItem(self._hline, ignoreBounds=True)

        # ── постоянный маркер по клику ───────────────────────────────────────
        self._click_marker = pg.ScatterPlotItem(
            size=10,
            pen=pg.mkPen("#cc0000", width=2),
            brush=pg.mkBrush(255, 80, 80, 200),
        )
        self._click_label = pg.TextItem(
            anchor=(0, 1), color="#aa0000",
            fill=pg.mkBrush(255, 230, 230, 220),
        )
        self._click_marker.setZValue(30)
        self._click_label.setZValue(30)
        self._click_marker.setVisible(False)
        self._click_label.setVisible(False)
        self.plot_widget.addItem(self._click_marker, ignoreBounds=True)
        self.plot_widget.addItem(self._click_label,  ignoreBounds=True)

        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_clicked)

        self._set_mode("live")

    # ── режимы ────────────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self._mode = mode
        vb = self.plot_widget.getViewBox()
        if mode == "live":
            self.btn_live   .setChecked(True)
            self.btn_archive.setChecked(False)
            self.stack.setCurrentIndex(0)
            self.plot_widget.setLabel("bottom", "Время")
            self.plot_widget.setLabel("left", "Значение")
            self._clear_archive()
            self._display_t    = deque()
            self._display_v    = deque()
            self._incoming_t   = deque()
            self._incoming_v   = deque()
            self._last_live_ts = None
            self._live_curve.setVisible(True)
            vb.setAutoVisible(y=True)
            vb.enableAutoRange(axis='y')
            self._query_timer .start(LIVE_QUERY_MS)
            self._render_timer.start(LIVE_RENDER_MS)
        else:
            self.btn_live   .setChecked(False)
            self.btn_archive.setChecked(True)
            self.stack.setCurrentIndex(1)
            self._query_timer .stop()
            self._render_timer.stop()
            self._live_curve.setData([], [])
            self._live_curve.setVisible(False)
            vb.enableAutoRange()

    # ── live ──────────────────────────────────────────────────────────────────

    def _live_query(self):
        """300 мс: запускает фоновый запрос только новых точек."""
        try:
            if self._query_worker and self._query_worker.isRunning():
                return
        except RuntimeError:
            self._query_worker = None
        now   = QDateTime.currentDateTimeUtc()
        dt_to = now.toString("yyyy-MM-ddTHH:mm:ssZ")
        if self._last_live_ts is not None:
            last_dt = _dt.datetime.fromtimestamp(self._last_live_ts, tz=_dt.timezone.utc)
            dt_from = (last_dt + _dt.timedelta(microseconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            dt_from = now.addSecs(-LIVE_WINDOW_SECS).toString("yyyy-MM-ddTHH:mm:ssZ")
        self._run_query(dt_from, dt_to, self._on_live_result)

    def _on_live_result(self, times: list, values: list):
        """Фоновый поток: складывает новые точки в очередь ожидания."""
        if not times:
            return
        pairs = sorted(zip(times, values))
        initial_load = (self._last_live_ts is None)  # первый запрос — исторические данные
        for t, v in pairs:
            self._incoming_t.append(t)
            self._incoming_v.append(v)
        self._last_live_ts = pairs[-1][0]
        if initial_load:
            # показать все исторические данные сразу, без дрипа
            self._flush_all_incoming()

    def _flush_all_incoming(self):
        """Перенести все накопленные точки на экран немедленно (начальная загрузка)."""
        cutoff = QDateTime.currentDateTimeUtc().toMSecsSinceEpoch() / 1000.0 - LIVE_WINDOW_SECS
        while self._incoming_t:
            t = self._incoming_t.popleft()
            v = self._incoming_v.popleft()
            if t >= cutoff:
                self._display_t.append(t)
                self._display_v.append(v)
        if self._display_t:
            x, y = self._decimate(np.array(self._display_t), np.array(self._display_v))
            self._live_curve.setData(x, y)

    def _render_frame(self):
        """50 мс: дозированно переносит точки, обновляет кривую только при изменении данных."""
        data_changed = False

        # добавляем порцию точек из очереди
        pending = len(self._incoming_t)
        if pending:
            batch = max(1, pending * LIVE_RENDER_MS // LIVE_QUERY_MS)
            for _ in range(min(batch, pending)):
                self._display_t.append(self._incoming_t.popleft())
                self._display_v.append(self._incoming_v.popleft())
            data_changed = True

        # удаляем устаревшие точки
        cutoff = QDateTime.currentDateTimeUtc().toMSecsSinceEpoch() / 1000.0 - LIVE_WINDOW_SECS
        while self._display_t and self._display_t[0] < cutoff:
            self._display_t.popleft()
            self._display_v.popleft()
            data_changed = True

        if data_changed and self._display_t:
            x, y = self._decimate(np.array(self._display_t), np.array(self._display_v))
            self._live_curve.setData(x, y)

        # X-окно = [now-60s, now] — плавный скролл по wall clock, не зависит от прихода данных
        now_ts = QDateTime.currentDateTimeUtc().toMSecsSinceEpoch() / 1000.0
        self.plot_widget.setXRange(now_ts - LIVE_WINDOW_SECS, now_ts, padding=0)

    # ── архив ─────────────────────────────────────────────────────────────────

    def _apply_preset(self, secs: int):
        now = QDateTime.currentDateTime()
        frm = now.addSecs(-secs)
        self.date_from.setDate(frm.date())
        self.time_from.setTime(frm.time())
        self.date_to.setDate(now.date())
        self.time_to.setTime(now.time())
        self._load_archive()

    def _load_archive(self):
        qdt_from = QDateTime(self.date_from.date(), self.time_from.time()).toUTC()
        qdt_to   = QDateTime(self.date_to.date(),   self.time_to.time()  ).toUTC()
        dt_from  = qdt_from.toString("yyyy-MM-ddTHH:mm:ssZ")
        dt_to    = qdt_to  .toString("yyyy-MM-ddTHH:mm:ssZ")

        duration_s = max(1, qdt_from.secsTo(qdt_to))
        # точек в диапазоне при 4 мс/сэмпл
        raw_count  = duration_s * 1000 // 4
        if raw_count <= MAX_DISPLAY:
            # коротких данных мало — грузим сырые
            query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {dt_from}, stop: {dt_to})
  |> filter(fn: (r) => r._measurement == "tenza" and r._field == "value")
  |> sort(columns: ["_time"])
'''
        else:
            # агрегируем на стороне БД до MAX_DISPLAY точек
            window_ms = max(4, duration_s * 1000 // MAX_DISPLAY)
            if window_ms < 1000:
                every = f"{window_ms}ms"
            elif window_ms < 60_000:
                every = f"{window_ms // 1000}s"
            elif window_ms < 3_600_000:
                every = f"{window_ms // 60_000}m"
            else:
                every = f"{window_ms // 3_600_000}h"
            query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {dt_from}, stop: {dt_to})
  |> filter(fn: (r) => r._measurement == "tenza" and r._field == "value")
  |> aggregateWindow(every: {every}, fn: mean, createEmpty: false)
  |> sort(columns: ["_time"])
'''
        worker = _QueryWorker(query, parent=self)
        worker.result_ready.connect(self._on_archive_result)
        worker.finished.connect(lambda: setattr(self, "_query_worker", None))
        self._query_worker = worker
        worker.start()

    def _on_archive_result(self, times: list, values: list):
        if not times:
            return
        x = np.array(times)
        y = np.array(values)
        self._clear_archive()
        pen = pg.mkPen(color=self.current_color, width=1)
        show_pts = self.chk_points.isChecked()
        line = self.plot_widget.plot(
            x, y, pen=pen, name="tenzaSensor (архив)",
            symbol='o' if show_pts else None,
            symbolSize=5 if show_pts else 1,
            symbolBrush=pg.mkBrush(self.current_color) if show_pts else None,
        )
        self._archive_lines.append(line)

    # ── InfluxDB (фоновый поток) ───────────────────────────────────────────────

    def _run_query(self, dt_from: str, dt_to: str, callback):
        query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {dt_from}, stop: {dt_to})
  |> filter(fn: (r) => r._measurement == "tenza" and r._field == "value")
  |> sort(columns: ["_time"])
'''
        worker = _QueryWorker(query, parent=self)
        worker.result_ready.connect(callback)
        worker.finished.connect(lambda: setattr(self, "_query_worker", None))
        self._query_worker = worker
        worker.start()

    # ── перекрестие и подсказка ───────────────────────────────────────────────

    def _on_mouse_moved(self, pos):
        rect = self.plot_widget.sceneBoundingRect()
        if not rect.contains(pos):
            self._vline.setVisible(False)
            self._hline.setVisible(False)
            return

        mp = self.plot_widget.getPlotItem().vb.mapSceneToView(pos)
        xs, ys = self._get_visible_data()
        if xs is None or len(xs) == 0:
            return

        idx = int(np.searchsorted(xs, mp.x()))
        idx = np.clip(idx, 0, len(xs) - 1)
        if idx > 0 and abs(xs[idx - 1] - mp.x()) < abs(xs[idx] - mp.x()):
            idx -= 1

        self._vline.setPos(xs[idx])
        self._hline.setPos(ys[idx])
        self._vline.setVisible(True)
        self._hline.setVisible(True)

    def _on_mouse_clicked(self, event):
        # правый клик — убрать маркер
        if event.button() == Qt.MouseButton.RightButton:
            self._click_marker.setVisible(False)
            self._click_label.setVisible(False)
            return

        pos = event.scenePos()
        if not self.plot_widget.sceneBoundingRect().contains(pos):
            return

        mp = self.plot_widget.getPlotItem().vb.mapSceneToView(pos)
        xs, ys = self._get_visible_data()
        if xs is None or len(xs) == 0:
            return

        idx = int(np.searchsorted(xs, mp.x()))
        idx = np.clip(idx, 0, len(xs) - 1)
        if idx > 0 and abs(xs[idx - 1] - mp.x()) < abs(xs[idx] - mp.x()):
            idx -= 1

        x_pt, y_pt = xs[idx], ys[idx]
        time_str = _dt.datetime.fromtimestamp(x_pt).strftime("%H:%M:%S.%f")[:-3]

        self._click_marker.setData([x_pt], [y_pt])
        self._click_label.setText(f"{time_str}\n{y_pt:.4f}")
        self._click_label.setPos(x_pt, y_pt)
        self._click_marker.setVisible(True)
        self._click_label.setVisible(True)
        event.accept()

    def _get_visible_data(self):
        """Возвращает (xs, ys) активной кривой."""
        if self._mode == "live":
            xs, ys = self._live_curve.getData()
        elif self._archive_lines:
            xs, ys = self._archive_lines[-1].getData()
        else:
            return None, None
        if xs is None or len(xs) == 0:
            return None, None
        return xs, ys

    # ── вспомогательное ───────────────────────────────────────────────────────

    def _toggle_points(self, checked: bool):
        sym  = 'o' if checked else None
        size = 5   if checked else 1
        brush = pg.mkBrush(self.current_color)
        for curve in [self._live_curve] + self._archive_lines:
            if curve is None:
                continue
            curve.setSymbol(sym)
            curve.setSymbolSize(size)
            curve.setSymbolBrush(brush)

    @staticmethod
    def _decimate(x: np.ndarray, y: np.ndarray) -> tuple:
        """Равномерная прорежка до MAX_DISPLAY точек: x[::step].
        Значения реальные (не усредняются), шаг стабилен для одного объёма данных."""
        n = len(x)
        if n <= MAX_DISPLAY:
            return x, y
        step = max(1, n // MAX_DISPLAY)
        return x[::step], y[::step]

    def _clear_archive(self):
        for line in self._archive_lines:
            self.plot_widget.removeItem(line)
        self._archive_lines.clear()

    def _change_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.current_color = color.name()
            self.color_btn.setStyleSheet(f"background-color: {self.current_color};")
            self._live_curve.setPen(pg.mkPen(color=self.current_color, width=1))

    def set_labels(self, x_label="X", y_label="Y"):
        self.plot_widget.setLabel("bottom", x_label)
        self.plot_widget.setLabel("left", y_label)

    def save_plot(self, filename):
        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
        exporter.export(filename)
