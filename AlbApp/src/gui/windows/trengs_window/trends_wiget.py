import datetime as _dt
import numpy as np
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton,
                             QColorDialog, QFileDialog, QFrame,
                             QDateEdit, QTimeEdit, QCheckBox,
                             QHBoxLayout, QProgressBar,
                             QLabel, QSpinBox, QWidgetAction)
from PyQt6.QtCore import Qt, QDateTime, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence, QAction
import pyqtgraph as pg
pg.setConfigOptions(antialias=True)
from influxdb_client import InfluxDBClient
from protocol_backend.event_bus import bus

def _translate_pg_menus(plot_widget):
    """Переводит контекстное меню pyqtgraph на русский."""
    vb = plot_widget.getViewBox()
    m  = vb.menu   # ViewBoxMenu

    # ── ViewBox: верхний уровень ──────────────────────────────
    m.viewAll.setVisible(False)
    m.mouseModes[0].setText("3 кнопки (панорама)")
    m.mouseModes[1].setText("1 кнопка (выделение)")

    # Режим мыши: 3 кнопки (панорама) по умолчанию, убрать из меню
    vb.setMouseMode(pg.ViewBox.PanMode)

    # ── ViewBox: подменю осей → перенести в "Масштаб" ────────
    _sub_ru = {"X axis": "Ось X", "Y axis": "Ось Y"}
    axis_actions = []
    for action in m.actions():
        if action.menu():
            if action.text() in _sub_ru:
                ru_title = _sub_ru[action.text()]
                action.menu().setTitle(ru_title)
                axis_actions.append((action, ru_title))
            elif action.text() in ("Mouse Mode", "Режим мыши"):
                action.setVisible(False)

    scale_menu = m.addMenu("Масштаб")
    for action, ru_title in axis_actions:
        m.removeAction(action)
        action.setText(ru_title)
        scale_menu.addAction(action)

    # Скрываем стандартный Export pyqtgraph при каждом открытии меню
    def _hide_default_export():
        for action in m.actions():
            txt = action.text().replace("&", "")
            if txt in ("Export...", "Export"):
                action.setVisible(False)
    m.aboutToShow.connect(_hide_default_export)

    # ── ViewBox: форм-виджеты осей (X=ctrl[0], Y=ctrl[1]) ────
    for ui in m.ctrl:
        ui.autoRadio       .setText("Авто")
        ui.manualRadio     .setText("Вручную")
        ui.invertCheck     .setVisible(False)
        ui.mouseCheck      .setVisible(False)
        ui.visibleOnlyCheck.setVisible(False)
        ui.autoPanCheck    .setVisible(False)
        ui.label           .setText("Привязать к:")

    # ── PlotItem: меню "Plot Options" и его подменю ───────────
    pi = plot_widget.getPlotItem()
    if not (hasattr(pi, "ctrlMenu") and pi.ctrlMenu):
        return

    pi.ctrlMenu.menuAction().setVisible(False)

    _submenu_ru = {
        "Transforms": "Преобразования",
        "Downsample": "Прореживание",
        "Average":    "Усреднение",
        "Alpha":      "Прозрачность",
        "Grid":       "Сетка",
    }
    _hidden = {"Points", "Alpha", "Grid", "Average", "Transforms", "Downsample"}
    for action in pi.ctrlMenu.actions():
        key = action.text().replace("&", "")
        if key in _hidden:
            action.setVisible(False)
            continue
        if key in _submenu_ru:
            if action.menu():
                action.menu().setTitle(_submenu_ru[key])
            else:
                action.setText(_submenu_ru[key])


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

    # ── Свой CSV-экспорт в самом низу меню (скрыт по умолчанию) ──
    sep_action = m.addSeparator()
    csv_action = QAction("Экспорт в CSV", m)
    csv_action.setVisible(False)
    m.addAction(csv_action)

    def _keep_at_bottom():
        m.removeAction(sep_action)
        m.removeAction(csv_action)
        m.addAction(sep_action)
        m.addAction(csv_action)
    m.aboutToShow.connect(_keep_at_bottom)

    return csv_action


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
LIVE_RENDER_MS   = 50     # интервал скролла X-оси (20 fps)
LIVE_WINDOW_SECS = 60     # глубина live-окна (сек)
# буфер на 60 с при 4 мс/точку = 15 000 точек; берём с запасом
MAX_LIVE_POINTS  = 20_000


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


class TrendsWiget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_color       = "#e67e22"
        self._mode               = ""
        self._archive_lines: list = []
        self._archive_t:     list = []
        self._archive_v:     list = []
        self._archive_parts: dict = {}
        self._archive_workers: list = []
        self._workers_done       = 0
        self._live_curve         = None
        # кольцевой буфер для live-графика
        self._buf_t     = np.empty(MAX_LIVE_POINTS, dtype=np.float64)
        self._buf_v     = np.empty(MAX_LIVE_POINTS, dtype=np.float64)
        self._buf_write = 0
        self._buf_full  = False
        self._auto_scroll: bool  = True
        self._y_range:     tuple = (0.0, 1.0)
        self._show_points: bool  = False
        self._line_width:  int   = 1
        self._line_alpha:  int   = 255

        # таймер плавного скролла X-оси
        self._render_timer = QTimer(self)
        self._render_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._render_timer.timeout.connect(self._render_frame)

        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── переключатель режимов ────────────────────────────────────────────
        nav_frame = QFrame()
        nav_frame.setStyleSheet("""
            QFrame {
                background-color: #2c3e50;
                border-bottom: 2px solid #3498db;
            }
        """)
        row_mode = QHBoxLayout(nav_frame)
        row_mode.setContentsMargins(6, 4, 6, 4)
        row_mode.setSpacing(6)

        btn_style = """
            QPushButton {{
                color: #ecf0f1;
                background-color: #3d5166;
                border: 1px solid #4a6278;
                border-radius: 4px;
                padding: 4px 16px;
                font-size: 13px;
                min-width: 80px;
            }}
            QPushButton:checked {{
                background-color: #3498db;
                border: 1px solid #2980b9;
                color: white;
                font-weight: bold;
            }}
            QPushButton:hover:!checked {{
                background-color: #4a6a82;
            }}
        """
        self.btn_live    = QPushButton("● Live")
        self.btn_archive = QPushButton("Архив")
        self.btn_live   .setCheckable(True)
        self.btn_archive.setCheckable(True)
        self.btn_live   .setChecked(True)
        self.btn_live   .setStyleSheet(btn_style)
        self.btn_archive.setStyleSheet(btn_style)
        self.btn_live   .clicked.connect(lambda: self._set_mode("live"))
        self.btn_archive.clicked.connect(lambda: self._set_mode("archive"))
        row_mode.addWidget(self.btn_live)
        row_mode.addWidget(self.btn_archive)
        row_mode.addStretch()
        root.addWidget(nav_frame)

        # ── панель live ──────────────────────────────────────────────────────
        self._live_panel = QWidget()
        live_row = QHBoxLayout(self._live_panel)
        live_row.setContentsMargins(0, 2, 0, 2)
        live_row.setSpacing(6)

        live_row.addStretch()
        root.addWidget(self._live_panel)

        QShortcut(QKeySequence(Qt.Key.Key_Left),  self, self._pan_left)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._pan_right)

        # ── панель архива ────────────────────────────────────────────────────
        self._arch_panel = QWidget()
        arch_layout = QVBoxLayout(self._arch_panel)
        arch_layout.setContentsMargins(0, 2, 0, 2)
        arch_layout.setSpacing(2)

        arch_row = QHBoxLayout()
        arch_row.setSpacing(4)

        presets = [
            ("5 мин",  300),
            ("30 мин", 1800),
            ("1 час",  3600),
            ("6 ч",    21600),
            ("24 ч",   86400),
            ("7 дн",   604800),
        ]
        self._preset_buttons: list = []
        for label, secs in presets:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _, s=secs, b=btn: self._select_preset(s, b))
            arch_row.addWidget(btn)
            self._preset_buttons.append(btn)

        arch_row.addWidget(QLabel("С:"))
        now = QDateTime.currentDateTime()
        self.date_from = QDateEdit(now.addSecs(-300).date())
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        self.date_from.setCalendarPopup(True)
        self.date_from.setFixedHeight(24)
        self.time_from = QTimeEdit(now.addSecs(-300).time())
        self.time_from.setDisplayFormat("HH:mm:ss")
        self.time_from.setFixedHeight(24)
        arch_row.addWidget(self.date_from)
        arch_row.addWidget(self.time_from)

        arch_row.addWidget(QLabel("По:"))
        self.date_to = QDateEdit(now.date())
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        self.date_to.setCalendarPopup(True)
        self.date_to.setFixedHeight(24)
        self.time_to = QTimeEdit(now.time())
        self.time_to.setDisplayFormat("HH:mm:ss")
        self.time_to.setFixedHeight(24)
        arch_row.addWidget(self.date_to)
        arch_row.addWidget(self.time_to)

        for field in (self.date_from, self.time_from, self.date_to, self.time_to):
            field.dateTimeChanged.connect(lambda _: [b.setStyleSheet(self._PRESET_OFF) for b in self._preset_buttons])

        self.btn_load = QPushButton("Загрузить")
        self.btn_load.setFixedHeight(24)
        self.btn_load.clicked.connect(self._load_archive)
        arch_row.addWidget(self.btn_load)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, N_ARCHIVE_WORKERS)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        self._progress_bar.setFixedSize(100, 20)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #aaa;
                border-radius: 3px;
                background: #f0f0f0;
                text-align: center;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498db, stop:1 #2ecc71
                );
                border-radius: 3px;
            }
        """)
        self._progress_bar.setVisible(False)
        arch_row.addWidget(self._progress_bar)
        arch_row.addStretch()
        arch_layout.addLayout(arch_row)

        self._arch_panel.hide()
        root.addWidget(self._arch_panel)

        # ── график ───────────────────────────────────────────────────────────
        self.plot_widget = pg.PlotWidget(axisItems={"bottom": _TimeAxisItem(orientation="bottom")})
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        _auto_btn = self.plot_widget.getPlotItem().autoBtn
        _auto_btn.hide()
        _auto_btn.show = lambda: None  # запретить pyqtgraph показывать кнопку
        self.plot_widget.addLegend()
        root.addWidget(self.plot_widget, 1)

        # перевод контекстного меню
        self._csv_export_action = _translate_pg_menus(self.plot_widget)
        self._csv_export_action.triggered.connect(self._export_csv)

        # поля ручного диапазона оси X → формат ЧЧ:ММ:СС
        _install_x_time_format(self.plot_widget)
        self._build_graph_context_menu()

        self._live_curve = self.plot_widget.plot(
            [], [],
            pen=pg.mkPen(color=self.current_color, width=1),
            name="tenzaSensor (live)",
        )
        self._live_curve.setDownsampling(auto=True, method='peak')
        self._live_curve.setClipToView(True)

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
        self.plot_widget.getViewBox().sigRangeChangedManually.connect(self._on_manual_pan)

        self._set_mode("live")

    # ── режимы ────────────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        if mode == self._mode:
            return
        self._mode = mode
        vb = self.plot_widget.getViewBox()
        self._csv_export_action.setVisible(mode == "archive")
        if mode == "live":
            self.btn_live   .setChecked(True)
            self.btn_archive.setChecked(False)
            self._live_panel.show()
            self._arch_panel.hide()
            self.plot_widget.setLabel("bottom", "Время")
            self.plot_widget.setLabel("left", "Значение")
            self._clear_archive()
            self._buf_write   = 0
            self._buf_full    = False
            self._y_range     = (0.0, 1.0)
            self._auto_scroll = True
            self._live_curve.setVisible(True)
            vb.disableAutoRange()
            vb.setAutoVisible(y=False)
            self._render_timer.start(LIVE_RENDER_MS)
            bus.tenza_points.connect(self._on_tenza_points)
        else:
            self.btn_live   .setChecked(False)
            self.btn_archive.setChecked(True)
            self._live_panel.hide()
            self._arch_panel.show()
            try:
                bus.tenza_points.disconnect(self._on_tenza_points)
            except RuntimeError:
                pass
            for w in self._archive_workers:
                w.part_ready.disconnect()
            self._archive_workers.clear()
            self._render_timer.stop()
            self._clear_archive()
            self._live_curve.setData([], [])
            self._live_curve.setVisible(False)
            vb.disableAutoRange()
            vb.enableAutoRange()

    # ── live ──────────────────────────────────────────────────────────────────

    def _on_tenza_points(self, times: list, values: list):
        """Принимает готовые точки напрямую из TenzaProcessor (без InfluxDB)."""
        if self._mode != "live":
            return
        changed = False
        for t, v in zip(times, values):
            self._buf_t[self._buf_write] = t
            self._buf_v[self._buf_write] = v
            self._buf_write = (self._buf_write + 1) % MAX_LIVE_POINTS
            if self._buf_write == 0:
                self._buf_full = True
            changed = True

        if changed and (self._buf_full or self._buf_write > 0):
            self._live_curve.setData(*self._get_buf_data())

    def _get_buf_data(self) -> tuple:
        """Возвращает (x, y) из кольцевого буфера в хронологическом порядке."""
        if self._buf_full:
            w = self._buf_write
            x = np.concatenate([self._buf_t[w:], self._buf_t[:w]])
            y = np.concatenate([self._buf_v[w:], self._buf_v[:w]])
        else:
            x = self._buf_t[:self._buf_write].copy()
            y = self._buf_v[:self._buf_write].copy()
        return x, y

    def _render_frame(self):
        """50 мс: плавный скролл X-оси + обновление Y-диапазона."""
        now_ts = QDateTime.currentDateTimeUtc().toMSecsSinceEpoch() / 1000.0

        if not self._auto_scroll:
            return

        self.plot_widget.setXRange(now_ts - LIVE_WINDOW_SECS, now_ts, padding=0)

        n = MAX_LIVE_POINTS if self._buf_full else self._buf_write
        if n == 0:
            return
        y = self._buf_v[:n]
        ymin, ymax = float(y.min()), float(y.max())
        span = (ymax - ymin) or abs(ymax) or 1.0
        lo, hi = ymin - span * 0.05, ymax + span * 0.05
        prev_lo, prev_hi = self._y_range
        prev_span = (prev_hi - prev_lo) or 1.0
        if abs(lo - prev_lo) / prev_span > 0.05 or abs(hi - prev_hi) / prev_span > 0.05:
            self.plot_widget.getViewBox().setYRange(lo, hi, padding=0)
            self._y_range = (lo, hi)

    def _on_manual_pan(self):
        """Пользователь потащил график мышью — останавливаем авто-скролл."""
        if self._mode == "live":
            self._auto_scroll = False

    def _resume_autoscroll(self):
        """Кнопка '▶ В эфир' — вернуться к текущему времени."""
        if self._mode == "live":
            self._auto_scroll = True
            self._y_range = (0.0, 1.0)

    def _pan_left(self):
        if self._mode != "live":
            return
        vb = self.plot_widget.getViewBox()
        x0, x1 = vb.viewRange()[0]
        step = (x1 - x0) * 0.2
        self._auto_scroll = False
        self.plot_widget.setXRange(x0 - step, x1 - step, padding=0)

    def _pan_right(self):
        if self._mode != "live":
            return
        vb = self.plot_widget.getViewBox()
        x0, x1 = vb.viewRange()[0]
        step = (x1 - x0) * 0.2
        now_ts = QDateTime.currentDateTimeUtc().toMSecsSinceEpoch() / 1000.0
        self._auto_scroll = False
        self.plot_widget.setXRange(x0 + step, x1 + step, padding=0)


    # ── архив ─────────────────────────────────────────────────────────────────

    _PRESET_ON  = "background-color: #1a8fe3; color: white; font-weight: bold;"
    _PRESET_OFF = ""

    def _select_preset(self, secs: int, active_btn: QPushButton):
        now = QDateTime.currentDateTime()
        frm = now.addSecs(-secs)
        for field in (self.date_from, self.time_from, self.date_to, self.time_to):
            field.blockSignals(True)
        self.date_from.setDate(frm.date())
        self.time_from.setTime(frm.time())
        self.date_to.setDate(now.date())
        self.time_to.setTime(now.time())
        for field in (self.date_from, self.time_from, self.date_to, self.time_to):
            field.blockSignals(False)
        for b in self._preset_buttons:
            b.setStyleSheet(self._PRESET_ON if b is active_btn else self._PRESET_OFF)

    def _load_archive(self):
        qdt_from = QDateTime(self.date_from.date(), self.time_from.time()).toUTC()
        qdt_to = QDateTime(self.date_to.date(), self.time_to.time()).toUTC()

        # отменяем предыдущие воркеры
        for w in self._archive_workers:
            w.part_ready.disconnect()
        self._archive_workers.clear()

        for b in self._preset_buttons:
            b.setStyleSheet(self._PRESET_OFF)
        self._clear_archive()
        self._archive_parts.clear()
        self._workers_done = 0
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self.btn_load.setEnabled(False)

        total_ms = qdt_from.msecsTo(qdt_to)
        step_ms  = total_ms // N_ARCHIVE_WORKERS

        for i in range(N_ARCHIVE_WORKERS):
            p_from = qdt_from.addMSecs(i * step_ms)
            p_to   = qdt_from.addMSecs((i + 1) * step_ms) if i < N_ARCHIVE_WORKERS - 1 else qdt_to
            query  = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {p_from.toString("yyyy-MM-ddTHH:mm:ssZ")}, stop: {p_to.toString("yyyy-MM-ddTHH:mm:ssZ")})
  |> filter(fn: (r) => r._measurement == "tenza" and r._field == "value")
  |> group()
  |> sort(columns: ["_time"])
'''
            worker = _ArchiveWorker(i, query, parent=self)
            worker.part_ready.connect(self._on_archive_part)
            worker.finished.connect(self._on_archive_worker_done)
            self._archive_workers.append(worker)

        for w in self._archive_workers:
            w.start()

    def _on_archive_part(self, idx: int, times: list, values: list):
        self._archive_parts[idx] = (times, values)
        # показываем только последовательные части с начала
        merged_t, merged_v = [], []
        for i in range(N_ARCHIVE_WORKERS):
            if i not in self._archive_parts:
                break
            merged_t.extend(self._archive_parts[i][0])
            merged_v.extend(self._archive_parts[i][1])
        if not merged_t:
            return
        self._archive_t = merged_t
        self._archive_v = merged_v
        self._update_archive_curve()

    def _on_archive_worker_done(self):
        self._workers_done += 1
        self._progress_bar.setValue(self._workers_done)
        if self._workers_done == N_ARCHIVE_WORKERS:
            self._archive_workers.clear()
            self._progress_bar.setVisible(False)
            self.btn_load.setEnabled(True)

    def _update_archive_curve(self):
        x = np.array(self._archive_t)
        y = np.array(self._archive_v)
        w        = self._line_width
        pen      = pg.mkPen(color=self.current_color, width=w)
        show_pts = self._show_points
        if self._archive_lines:
            self._archive_lines[0].setData(x, y)
        else:
            line = self.plot_widget.plot(
                x, y, pen=pen, name="tenzaSensor (архив)",
                symbol='o' if show_pts else None,
                symbolSize=5 if show_pts else 1,
                symbolBrush=pg.mkBrush(self.current_color) if show_pts else None,
            )
            line.setDownsampling(auto=True, method='peak')
            line.setClipToView(True)
            self._archive_lines.append(line)

    # ── InfluxDB (фоновый поток) ───────────────────────────────────────────────

    # ── перекрестие и подсказка ───────────────────────────────────────────────

    def _on_mouse_moved(self, pos):
        rect = self.plot_widget.sceneBoundingRect()
        if not rect.contains(pos):
            self._vline.setVisible(False)
            self._hline.setVisible(False)
            return

        mp = self.plot_widget.getPlotItem().vb.mapSceneToView(pos)
        self._vline.setPos(mp.x())
        self._hline.setPos(mp.y())
        self._vline.setVisible(True)
        self._hline.setVisible(True)

    def _on_mouse_clicked(self, event):
        # правый клик — убрать маркер
        if event.button() == Qt.MouseButton.RightButton:
            self._click_marker.setVisible(False)
            self._click_label.setVisible(False)
            return

        # двойной клик — вернуться в эфир (live режим)
        if event.double():
            self._resume_autoscroll()
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

    def _build_graph_context_menu(self):
        """Добавить подменю 'Линия' в контекстное меню графика (ПКМ)."""
        from PyQt6.QtWidgets import QSlider
        menu = self.plot_widget.getViewBox().menu
        menu.addSeparator()

        line_menu = menu.addMenu("Линия")

        # Цвет
        action_color = QAction("Цвет...", line_menu)
        action_color.triggered.connect(self._change_color)
        line_menu.addAction(action_color)

        # Толщина — спинбокс
        width_w = QWidget()
        width_l = QHBoxLayout(width_w)
        width_l.setContentsMargins(16, 4, 8, 4)
        width_l.setSpacing(6)
        width_l.addWidget(QLabel("Толщина:"))
        spin = QSpinBox()
        spin.setRange(1, 10)
        spin.setValue(self._line_width)
        spin.setFixedWidth(52)
        spin.valueChanged.connect(self._change_line_width)
        width_l.addWidget(spin)
        wa = QWidgetAction(line_menu)
        wa.setDefaultWidget(width_w)
        line_menu.addAction(wa)

        # Прозрачность — слайдер 0–100 %
        alpha_w = QWidget()
        alpha_l = QHBoxLayout(alpha_w)
        alpha_l.setContentsMargins(16, 4, 8, 4)
        alpha_l.setSpacing(6)
        alpha_l.addWidget(QLabel("Прозрачность:"))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(100)
        slider.setFixedWidth(90)
        slider.valueChanged.connect(self._change_opacity)
        alpha_l.addWidget(slider)
        aa = QWidgetAction(line_menu)
        aa.setDefaultWidget(alpha_w)
        line_menu.addAction(aa)

        # Показать / скрыть точки
        line_menu.addSeparator()
        self._action_points = QAction("Показать точки", line_menu)
        self._action_points.setCheckable(True)
        self._action_points.toggled.connect(self._toggle_points)
        line_menu.addAction(self._action_points)

        # Сетка в корне меню
        menu.addSeparator()
        grid_menu = menu.addMenu("Сетка")
        act_grid_x = QAction("По X", grid_menu)
        act_grid_x.setCheckable(True)
        act_grid_x.setChecked(True)
        act_grid_y = QAction("По Y", grid_menu)
        act_grid_y.setCheckable(True)
        act_grid_y.setChecked(True)
        def _update_grid():
            self.plot_widget.showGrid(x=act_grid_x.isChecked(), y=act_grid_y.isChecked(), alpha=0.3)
        grid_alpha_val = [0.3]

        def _update_grid():
            self.plot_widget.showGrid(x=act_grid_x.isChecked(), y=act_grid_y.isChecked(), alpha=grid_alpha_val[0])

        act_grid_x.toggled.connect(lambda _: _update_grid())
        act_grid_y.toggled.connect(lambda _: _update_grid())
        grid_menu.addAction(act_grid_x)
        grid_menu.addAction(act_grid_y)

        grid_menu.addSeparator()
        alpha_gw = QWidget()
        alpha_gl = QHBoxLayout(alpha_gw)
        alpha_gl.setContentsMargins(16, 4, 8, 4)
        alpha_gl.setSpacing(6)
        alpha_gl.addWidget(QLabel("Прозрачность:"))
        grid_slider = QSlider(Qt.Orientation.Horizontal)
        grid_slider.setRange(0, 100)
        grid_slider.setValue(30)
        grid_slider.setFixedWidth(90)
        def _on_grid_alpha(v):
            grid_alpha_val[0] = v / 100.0
            _update_grid()
        grid_slider.valueChanged.connect(_on_grid_alpha)
        alpha_gl.addWidget(grid_slider)
        alpha_ga = QWidgetAction(grid_menu)
        alpha_ga.setDefaultWidget(alpha_gw)
        grid_menu.addAction(alpha_ga)

    def _toggle_points(self, checked: bool):
        self._show_points = checked
        self._action_points.setText("Скрыть точки" if checked else "Показать точки")
        sym   = 'o' if checked else None
        size  = 5   if checked else 1
        brush = pg.mkBrush(self.current_color)
        for curve in [self._live_curve] + self._archive_lines:
            if curve is None:
                continue
            curve.setSymbol(sym)
            curve.setSymbolSize(size)
            curve.setSymbolBrush(brush)

    def _clear_archive(self):
        for line in self._archive_lines:
            self.plot_widget.removeItem(line)
        self._archive_lines.clear()
        self._archive_t.clear()
        self._archive_v.clear()

    def _make_pen(self):
        from PyQt6.QtGui import QColor
        c = QColor(self.current_color)
        c.setAlpha(self._line_alpha)
        return pg.mkPen(color=c, width=self._line_width)

    def _apply_pen(self):
        pen = self._make_pen()
        for curve in [self._live_curve] + self._archive_lines:
            if curve is not None:
                curve.setPen(pen)

    def _change_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.current_color = color.name()
            self._apply_pen()

    def _change_opacity(self, value: int):
        self._line_alpha = int(value * 2.55)
        self._apply_pen()

    def _change_line_width(self, width: int):
        self._line_width = width
        self._apply_pen()

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить CSV", "", "CSV файлы (*.csv)"
        )
        if not path:
            return
        xs, ys = self._get_visible_data()
        if xs is None or len(xs) == 0:
            return
        def _rfc3339(ts):
            dt = _dt.datetime.fromtimestamp(ts).astimezone()
            off = dt.strftime("%z")          # +0300
            off_fmt = off[:3] + ":" + off[3:]  # +03:00
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + off_fmt
        t_start = _rfc3339(xs[0])
        t_stop  = _rfc3339(xs[-1])
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("#group,false,false,true,true,false,false,true,true,true\n")
            f.write("#datatype,string,long,dateTime:RFC3339,dateTime:RFC3339,dateTime:RFC3339,double,string,string,string\n")
            f.write("#default,_result,,,,,,,,\n")
            f.write(",result,table,_start,_stop,_time,_value,_field,_measurement,server\n")
            for t, v in zip(xs, ys):
                f.write(f",,0,{t_start},{t_stop},{_rfc3339(t)},{v},value,tenza,PLC1\n")

    def set_labels(self, x_label="X", y_label="Y"):
        self.plot_widget.setLabel("bottom", x_label)
        self.plot_widget.setLabel("left", y_label)

    def save_plot(self, filename):
        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
        exporter.export(filename)
