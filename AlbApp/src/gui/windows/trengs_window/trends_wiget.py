import datetime as _dt                          # форматирование меток времени на графике
import numpy as np                              # кольцевые буферы и операции с массивами точек
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,   # базовые виджеты и компоновка
    QColorDialog, QFileDialog,                        # диалоги выбора цвета и сохранения файла
    QFrame, QDateEdit, QTimeEdit,                     # рамка навигации, поля ввода даты/времени
    QLabel, QSpinBox,
    QSlider, QWidgetAction, QCheckBox,                # слайдер прозрачности, чекбокс точек
    QDialog, QDialogButtonBox,                        # диалог выбора каналов для выгрузки
)
from PyQt6.QtCore import Qt, QDateTime, QTimer  # флаги Qt, работа с датой/временем, таймер скролла
from PyQt6.QtGui import QShortcut, QKeySequence, QAction, QColor  # горячие клавиши, пункты меню, цвет
import pyqtgraph as pg                          # графическая библиотека (PlotWidget, InfiniteLine и др.)
pg.setConfigOptions(antialias=True, useOpenGL=True)
from event_bus import bus      # шина событий: получение точек от worker'а

# ── локальные модули ──────────────────────────────────────────────────────────
from ._archive_worker import (
    INFLUX_BUCKET,       # имя bucket в InfluxDB
    LIVE_RENDER_MS,      # интервал таймера скролла live-графика (мс)
    LIVE_WINDOW_SECS,    # глубина отображаемого live-окна (сек)
    MAX_LIVE_POINTS,     # размер кольцевого буфера live-данных
    N_ARCHIVE_WORKERS,   # количество параллельных потоков загрузки архива
    _ArchiveWorker,      # QThread-воркер одного параллельного запроса к InfluxDB
)
from ._axis_item import _TimeAxisItem           # кастомная ось X с метками ЧЧ:ММ:СС
from ._pg_menu_utils import (
    _translate_pg_menus,                        # русификация контекстного меню pyqtgraph
    _install_x_time_format,                     # форматирование полей диапазона оси X как время
)

# цвета каналов по умолчанию
_CH_COLORS = ["#e67e22", "#3498db", "#2ecc71"]

# имена каналов (индекс 0 = канал 1)
_CH_NAMES = [
    "Текущая уставка нагружения",
    "Датчик нагружения",
    "Датчик перемещения",
]

def _panel_style(dark: bool) -> str:
    if dark:
        bg, text, ctrl_bg, border = "#2c3e50", "#ecf0f1", "#3d5166", "#4a6278"
    else:
        bg, text, ctrl_bg, border = "#dde3ea", "#1a1a1a", "#c5cdd6", "#a0aab4"
    return f"""
    QFrame#chPanel {{
        background-color: {bg};
        border-bottom: 2px solid #3498db;
    }}
    QWidget {{
        background-color: {bg};
    }}
    QLabel {{
        color: {text};
        background: transparent;
    }}
    QSpinBox {{
        background: {ctrl_bg};
        color: {text};
        border: 1px solid {border};
        border-radius: 3px;
        padding: 1px 4px;
        min-height: 20px;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        background: {border};
        border: none;
        width: 14px;
    }}
    QCheckBox {{
        color: {text};
        background: transparent;
        spacing: 5px;
    }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {border};
        border-radius: 2px;
        background: {ctrl_bg};
    }}
    QCheckBox::indicator:checked {{
        background: #3498db;
        border-color: #2980b9;
    }}
    QSlider::groove:horizontal {{
        background: {border};
        height: 4px;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: #3498db;
        width: 12px;
        height: 12px;
        margin: -4px 0;
        border-radius: 6px;
        border: none;
    }}
    QSlider::handle:horizontal:hover {{
        background: #5dade2;
    }}
"""


def _nav_style(dark: bool) -> str:
    bg = "#2c3e50" if dark else "#dde3ea"
    return f"QFrame {{ background-color: {bg}; border-bottom: 2px solid #3498db; }}"


def _btn_mode_style(dark: bool) -> str:
    text    = "#ecf0f1" if dark else "#1a1a1a"
    btn_bg  = "#3d5166" if dark else "#c5cdd6"
    btn_brd = "#4a6278" if dark else "#a0aab4"
    btn_hov = "#4a6a82" if dark else "#b0bcc8"
    return f"""
        QPushButton {{
            color: {text};
            background-color: {btn_bg};
            border: 1px solid {btn_brd};
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
            background-color: {btn_hov};
        }}
    """


# оставляем для совместимости с местами, где используется напрямую
_PANEL_STYLE = _panel_style(True)


class TrendsWiget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        # {ch_id: dict} — 3 фиксированных канала; структура ch-словаря описана в _setup_ui
        self._channels: dict = {}

        self._mode                    = ""
        self._archive_lines: dict     = {}   # {ch_id: PlotDataItem}
        self._archive_parts: dict     = {}   # {ch_id: {worker_idx: (times, values)}}
        self._archive_workers: list   = []   # плоский список всех активных воркеров
        self._workers_done            = 0
        self._total_archive_workers   = 0
        self._auto_scroll: bool  = True
        self._y_range:     tuple = (0.0, 1.0)
        self._ts_offset:   float = 0.0       # нормализация X для OpenGL (вычитается из timestamps)

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
        self._nav_frame = QFrame()
        self._nav_frame.setStyleSheet(_nav_style(True))
        nav_frame = self._nav_frame
        row_mode = QHBoxLayout(nav_frame)
        row_mode.setContentsMargins(6, 4, 6, 4)
        row_mode.setSpacing(6)

        self.btn_live    = QPushButton("● Live")
        self.btn_archive = QPushButton("Архив")
        self.btn_live   .setCheckable(True)
        self.btn_archive.setCheckable(True)
        self.btn_live   .setChecked(True)
        self.btn_live   .setStyleSheet(_btn_mode_style(True))
        self.btn_archive.setStyleSheet(_btn_mode_style(True))
        self.btn_live   .clicked.connect(lambda: self._set_mode("live"))
        self.btn_archive.clicked.connect(lambda: self._set_mode("archive"))
        row_mode.addWidget(self.btn_live)
        row_mode.addWidget(self.btn_archive)
        row_mode.addStretch()
        root.addWidget(nav_frame)

        # ── строка: панель каналов + панель архива ───────────────────────────
        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(4)
        root.addLayout(controls_row)

        self._ch_frame = QFrame()
        self._ch_frame.setObjectName("chPanel")
        self._ch_frame.setStyleSheet(_panel_style(True))
        ch_frame = self._ch_frame
        ch_outer = QVBoxLayout(ch_frame)
        ch_outer.setContentsMargins(4, 2, 4, 2)
        ch_outer.setSpacing(1)
        controls_row.addWidget(ch_frame)


        QShortcut(QKeySequence(Qt.Key.Key_Left),  self, self._pan_left)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._pan_right)

        # ── панель архива ────────────────────────────────────────────────────
        self._arch_panel = QFrame()
        self._arch_panel.setStyleSheet(_panel_style(True))
        arch_layout = QVBoxLayout(self._arch_panel)
        arch_layout.setContentsMargins(4, 2, 4, 2)
        arch_layout.setSpacing(2)

        # ряд пресетов
        presets_row = QHBoxLayout()
        presets_row.setSpacing(2)
        presets = [
            ("5м",  300),
            ("30м", 1800),
            ("1ч",  3600),
            ("6ч",  21600),
            ("24ч", 86400),
            ("7д",  604800),
        ]
        self._preset_buttons: list = []
        for label, secs in presets:
            btn = QPushButton(label)
            btn.setFixedHeight(18)
            btn.clicked.connect(lambda _, s=secs, b=btn: self._select_preset(s, b))
            presets_row.addWidget(btn)
            self._preset_buttons.append(btn)
        arch_layout.addLayout(presets_row)

        # сетка: С/По + кнопка Загрузить на 2 строки
        from PyQt6.QtWidgets import QGridLayout
        now = QDateTime.currentDateTime()
        grid = QGridLayout()
        grid.setSpacing(2)

        self.date_from = QDateEdit(now.addSecs(-300).date())
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        self.date_from.setCalendarPopup(True)
        self.date_from.setFixedHeight(18)
        self.time_from = QTimeEdit(now.addSecs(-300).time())
        self.time_from.setDisplayFormat("HH:mm:ss")
        self.time_from.setFixedHeight(18)

        self.date_to = QDateEdit(now.date())
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        self.date_to.setCalendarPopup(True)
        self.date_to.setFixedHeight(18)
        self.time_to = QTimeEdit(now.time())
        self.time_to.setDisplayFormat("HH:mm:ss")
        self.time_to.setFixedHeight(18)

        self.btn_load = QPushButton("Загрузить")
        self.btn_load.clicked.connect(self._load_archive)

        grid.addWidget(QLabel("С:"),      0, 0)
        grid.addWidget(self.date_from,    0, 1)
        grid.addWidget(self.time_from,    0, 2)
        grid.addWidget(QLabel("По:"),     1, 0)
        grid.addWidget(self.date_to,      1, 1)
        grid.addWidget(self.time_to,      1, 2)
        grid.addWidget(self.btn_load,     0, 3, 2, 1)  # span 2 строки

        arch_layout.addLayout(grid)

        for field in (self.date_from, self.time_from, self.date_to, self.time_to):
            field.dateTimeChanged.connect(
                lambda _: [b.setStyleSheet(self._PRESET_OFF) for b in self._preset_buttons])

        sp = self._arch_panel.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self._arch_panel.setSizePolicy(sp)
        self._arch_panel.setVisible(False)
        controls_row.addWidget(self._arch_panel)
        controls_row.addStretch()

        # ── график ───────────────────────────────────────────────────────────
        self._time_axis  = _TimeAxisItem(orientation="bottom")
        self.plot_widget = pg.PlotWidget(
            axisItems={"bottom": self._time_axis})
        self.plot_widget.setBackground("#2c2c2c")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        _auto_btn = self.plot_widget.getPlotItem().autoBtn
        _auto_btn.hide()
        _auto_btn.show = lambda: None  # запретить pyqtgraph показывать кнопку
        self._legend = self.plot_widget.addLegend()
        root.addWidget(self.plot_widget, 1)

        # ── накладная метка: число видимых точек ─────────────────────────────
        self._pts_label = QLabel("", self.plot_widget.viewport())
        self._pts_label.setStyleSheet(
            "background: rgba(0,0,0,160); color: #aaaaaa;"
            " font-size: 11px; padding: 2px 6px; border-radius: 3px;"
        )
        self._pts_label.move(8, 8)
        self._pts_label.raise_()
        self._pts_label.show()
        self._pts_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # перевод контекстного меню
        self._csv_export_action, self._xlsx_export_action, self._export_menu_action = \
            _translate_pg_menus(self.plot_widget)
        self._csv_export_action .triggered.connect(self._export_csv)
        self._xlsx_export_action.triggered.connect(self._export_excel)

        # поля ручного диапазона оси X → формат ЧЧ:ММ:СС
        _install_x_time_format(self.plot_widget)
        self._build_graph_context_menu()

        # ── перекрестие + метка значения ────────────────────────────────────
        dash = pg.mkPen(color="#888888", width=1, style=Qt.PenStyle.DashLine)
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=dash)
        self._hline = pg.InfiniteLine(angle=0,  movable=False, pen=dash)
        self._vline.setVisible(False)
        self._hline.setVisible(False)
        self.plot_widget.addItem(self._vline, ignoreBounds=True)
        self.plot_widget.addItem(self._hline, ignoreBounds=True)

        # ── маркер по клику ──────────────────────────────────────────────────
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

        # Ctrl+колесо → масштаб оси X; обычное колесо → масштаб оси Y
        _vb = self.plot_widget.getViewBox()
        _vb_wheel = type(_vb).wheelEvent
        def _wheel(ev, axis=None):
            if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
                _vb_wheel(_vb, ev, axis=0)
            else:
                _vb_wheel(_vb, ev, axis=1)
        _vb.wheelEvent = _wheel

        # ── 3 фиксированных канала ────────────────────────────────────────────

        for ch_id, (color, name) in enumerate(zip(_CH_COLORS, _CH_NAMES), start=1):
            self._init_channel(ch_id, color, name)
            row = self._make_channel_row(ch_id)
            self._channels[ch_id]['row'] = row
            ch_outer.addWidget(row)

        # статическая привязка каналов к именам потоков (источник — bus.stream_points)
        # порядок combo: 0=не привязан, 1=Датчик нагружения, 2=Датчик перемещения, 3=Текущая уставка нагружения
        _static = [
            (1, 3, 'setpoint'),       # Текущая уставка нагружения
            (2, 1, 'tenza'),          # Датчик нагружения
            (3, 2, 'displacement'),   # Датчик перемещения
        ]
        for ch_id, _, stream in _static:
            self._channels[ch_id]['signal'] = bus.stream_points
            self._channels[ch_id]['stream'] = stream
        self._channels[1]['hold'] = True   # уставка тянется непрерывно до now
        self._channels[1]['curve'].setClipToView(False)  # hold-канал рисует шаг-функцию вручную

        self._set_mode("live")

    # ── инициализация каналов ─────────────────────────────────────────────────

    def _init_channel(self, ch_id: int, color: str, name: str = ""):
        """Создать запись канала и его кривую; строку UI не создаёт."""
        curve = self.plot_widget.plot(
            [], [],
            pen=pg.mkPen(color=QColor(color), width=1),
        )
        curve.setDownsampling(auto=True, method='peak')
        curve.setClipToView(True)   # для hold-каналов сбрасывается ниже в _setup_ui
        curve.setSkipFiniteCheck(True)  # данные всегда конечны — пропуск NaN/inf проверки

        self._channels[ch_id] = {
            'curve':        curve,
            'name':         name or f"канал {ch_id}",
            'buf_t':        np.empty(MAX_LIVE_POINTS, dtype=np.float64),
            'buf_v':        np.empty(MAX_LIVE_POINTS, dtype=np.float64),
            'write':        0,
            'full':         False,
            'color':        color,
            'width':        1,
            'alpha':        255,
            'points':       False,
            'visible':      True,   # отображается ли канал на графике
            'hold':         False,  # True → линия продлевается до now на каждом кадре
            'last_val':     None,   # последнее полученное значение (для hold-режима)
            'signal':       None,
            'stream':       None,   # имя потока в bus.stream_points (фильтр в слоте)
            'slot':         None,   # сохранённая ссылка на lambda-слот для отключения
            'row':          None,
            'color_btn':    None,
            'toggle_btn':   None,
        }

    def _make_channel_row(self, ch_id: int) -> QWidget:
        """Собрать горизонтальную строку управления каналом."""
        ch = self._channels[ch_id]
        row = QWidget()
        row.setFixedHeight(22)
        hl = QHBoxLayout(row)
        hl.setContentsMargins(2, 0, 2, 0)
        hl.setSpacing(4)

        # ── вкл/выкл отображения ─────────────────────────────────────────────
        toggle_btn = QPushButton("●")
        toggle_btn.setCheckable(True)
        toggle_btn.setChecked(True)
        toggle_btn.setFixedSize(18, 18)
        toggle_btn.setToolTip("Показать / скрыть канал на графике")
        toggle_btn.setStyleSheet(_toggle_style(True))
        toggle_btn.toggled.connect(
            lambda checked, cid=ch_id: self._toggle_ch_visible(cid, checked))
        ch['toggle_btn'] = toggle_btn

        # ── цвет линии ───────────────────────────────────────────────────────
        color_btn = QPushButton()
        color_btn.setFixedSize(16, 16)
        color_btn.setToolTip("Цвет линии")
        color_btn.setStyleSheet(
            f"background-color:{ch['color']}; border-radius:3px; border:1px solid #7f8c8d;")
        color_btn.clicked.connect(lambda _=False, cid=ch_id: self._pick_channel_color(cid))
        ch['color_btn'] = color_btn

        # ── лейбл ────────────────────────────────────────────────────────────
        lbl = QLabel(ch['name'] + ":")
        lbl.setFixedWidth(180)

        # ── толщина ──────────────────────────────────────────────────────────
        width_spin = QSpinBox()
        width_spin.setRange(1, 10)
        width_spin.setValue(ch['width'])
        width_spin.setFixedWidth(46)
        width_spin.setToolTip("Толщина линии")
        width_spin.valueChanged.connect(
            lambda v, cid=ch_id: self._set_ch_width(cid, v))

        # ── прозрачность ─────────────────────────────────────────────────────
        alpha_slider = QSlider(Qt.Orientation.Horizontal)
        alpha_slider.setRange(0, 100)
        alpha_slider.setValue(100)
        alpha_slider.setFixedWidth(80)
        alpha_slider.setToolTip("Прозрачность линии")
        alpha_slider.valueChanged.connect(
            lambda v, cid=ch_id: self._set_ch_alpha(cid, v))

        # ── точки ────────────────────────────────────────────────────────────
        points_cb = QCheckBox("Точки")
        points_cb.setChecked(ch['points'])
        points_cb.toggled.connect(
            lambda v, cid=ch_id: self._set_ch_points(cid, v))

        hl.addWidget(toggle_btn)
        hl.addWidget(color_btn)
        hl.addWidget(lbl)
        hl.addWidget(_sep())
        hl.addWidget(QLabel("Толщина:"))
        hl.addWidget(width_spin)
        hl.addWidget(_sep())
        hl.addWidget(QLabel("Прозрачность:"))
        hl.addWidget(alpha_slider)
        hl.addWidget(_sep())
        hl.addWidget(points_cb)
        hl.addStretch()

        return row

    # ── per-channel controls ──────────────────────────────────────────────────

    def _toggle_ch_visible(self, ch_id: int, visible: bool):
        """Показать или скрыть канал на графике, подключив/отключив сигнал."""
        ch = self._channels.get(ch_id)
        if ch is None:
            return
        ch['visible'] = visible
        ch['curve'].setVisible(visible and self._mode == "live")
        if visible and self._mode == "live":
            self._connect_ch(ch_id, ch)
            self._legend.addItem(ch['curve'], ch['name'])
        else:
            self._disconnect_ch(ch)
            self._legend.removeItem(ch['curve'])
        if ch['toggle_btn'] is not None:
            ch['toggle_btn'].setStyleSheet(_toggle_style(visible))

    def _pick_channel_color(self, ch_id: int):
        """Открыть диалог выбора цвета для канала."""
        ch = self._channels.get(ch_id)
        if ch is None:
            return
        color = QColorDialog.getColor(QColor(ch['color']), self)
        if color.isValid():
            self.set_curve_color(ch_id, color.name())

    def _set_ch_width(self, ch_id: int, width: int):
        ch = self._channels.get(ch_id)
        if ch is None:
            return
        ch['width'] = width
        vb = self.plot_widget.getViewBox()
        saved = vb.viewRange()
        ch['curve'].opts['antialias'] = True
        ch['curve'].setPen(pg.mkPen(color=_ch_qcolor(ch), width=width))
        vb.setRange(xRange=saved[0], yRange=saved[1], padding=0)

    def _set_ch_alpha(self, ch_id: int, value: int):
        ch = self._channels.get(ch_id)
        if ch is None:
            return
        ch['alpha'] = int(value * 2.55)
        vb = self.plot_widget.getViewBox()
        saved = vb.viewRange()
        ch['curve'].setPen(pg.mkPen(color=_ch_qcolor(ch), width=ch['width']))
        vb.setRange(xRange=saved[0], yRange=saved[1], padding=0)

    def _set_ch_points(self, ch_id: int, checked: bool):
        ch = self._channels.get(ch_id)
        if ch is None:
            return
        ch['points'] = checked
        vb = self.plot_widget.getViewBox()
        saved = vb.viewRange()
        ch['curve'].setSymbol('o' if checked else None)
        ch['curve'].setSymbolSize(5 if checked else 1)
        ch['curve'].setSymbolBrush(pg.mkBrush(ch['color']) if checked else None)
        vb.setRange(xRange=saved[0], yRange=saved[1], padding=0)

    def _update_pts_label(self):
        (x0, x1), _ = self.plot_widget.getViewBox().viewRange()
        lines = []
        if self._mode == "live":
            for ch in self._channels.values():
                if not ch['visible']:
                    continue
                xs, _ = ch['curve'].getData()
                if xs is None or len(xs) == 0:
                    continue
                n = int(np.searchsorted(xs, x1, 'right') - np.searchsorted(xs, x0, 'left'))
                lines.append(f"{ch['name'][:22]}: {n}")
        else:
            for ch_id, line in self._archive_lines.items():
                xs, _ = line.getData()
                if xs is None or len(xs) == 0:
                    continue
                n = int(np.searchsorted(xs, x1, 'right') - np.searchsorted(xs, x0, 'left'))
                lines.append(f"{self._channels[ch_id]['name'][:22]}: {n}")
        self._pts_label.setText("\n".join(lines) if lines else "")
        self._pts_label.adjustSize()

    # ── режимы ────────────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        if mode == self._mode:
            return
        self._mode = mode
        vb = self.plot_widget.getViewBox()
        self._export_menu_action.setVisible(mode == "archive")
        if mode == "live":
            self.btn_live   .setChecked(True)
            self.btn_archive.setChecked(False)
            self._arch_panel.setVisible(False)
            self.plot_widget.setLabel("bottom", "Время")
            self.plot_widget.setLabel("left", "Значение")
            self._clear_archive()
            for ch_id, ch in self._channels.items():
                ch['write'] = 0
                ch['full']  = False
                ch['curve'].setVisible(ch['visible'])
                if ch['visible']:
                    self._connect_ch(ch_id, ch)
                    self._legend.addItem(ch['curve'], ch['name'])
            self._y_range     = (0.0, 1.0)
            self._auto_scroll = True
            vb.disableAutoRange()
            vb.setAutoVisible(y=False)
            self._render_timer.start(LIVE_RENDER_MS)
        else:
            self.btn_live   .setChecked(False)
            self.btn_archive.setChecked(True)
            self._arch_panel.setVisible(True)
            for ch in self._channels.values():
                self._disconnect_ch(ch)
                self._legend.removeItem(ch['curve'])
            for w in self._archive_workers:
                w.part_ready.disconnect()
            self._archive_workers.clear()
            self._render_timer.stop()
            self._clear_archive()
            for ch in self._channels.values():
                ch['curve'].setData([], [])
                ch['curve'].setVisible(False)
            vb.disableAutoRange()
            vb.enableAutoRange()

    def _connect_ch(self, ch_id: int, ch: dict):
        """Подключить сигнал канала (если привязан и ещё не подключён)."""
        if ch['signal'] is None or ch['slot'] is not None:
            return
        def slot(name, times, values, _cid=ch_id, _stream=ch['stream']):
            if name == _stream:
                self._push_points(_cid, times, values)
        ch['slot'] = slot
        # QueuedConnection обязателен: сигналы летят из _db_thread,
        # а кольцевой буфер читается из главного потока в _render_frame.
        # Без явного QueuedConnection лямбда вызывается из _db_thread → race condition.
        ch['signal'].connect(slot, Qt.ConnectionType.QueuedConnection)

    def _disconnect_ch(self, ch: dict):
        """Отключить сигнал канала, сохраняя привязку (signal остаётся)."""
        if ch['slot'] is None or ch['signal'] is None:
            return
        try:
            ch['signal'].disconnect(ch['slot'])
        except RuntimeError:
            pass
        ch['slot'] = None

    # ── live ──────────────────────────────────────────────────────────────────

    def _push_points(self, ch_id: int, times: list, values: list):
        """Записать точки в кольцевой буфер канала и обновить кривую."""
        if self._mode != "live":
            return
        ch = self._channels.get(ch_id)
        if ch is None:
            return
        buf_t = ch['buf_t']
        buf_v = ch['buf_v']
        for t, v in zip(times, values):
            w = ch['write']
            buf_t[w] = t
            buf_v[w] = v
            ch['write'] = (w + 1) % MAX_LIVE_POINTS
            if ch['write'] == 0:
                ch['full'] = True
        if values:
            ch['last_val'] = values[-1]

    def _get_buf_data(self, ch_id: int) -> tuple:
        """Вернуть (x, y) из кольцевого буфера канала в хронологическом порядке."""
        ch    = self._channels[ch_id]
        buf_t = ch['buf_t']
        buf_v = ch['buf_v']
        w     = ch['write']
        if ch['full']:
            x = np.concatenate([buf_t[w:], buf_t[:w]])
            y = np.concatenate([buf_v[w:], buf_v[:w]])
        else:
            x = buf_t[:w].copy()
            y = buf_v[:w].copy()
        return x, y

    def _render_frame(self):
        """50 мс: плавный скролл X-оси + обновление Y-диапазона."""
        now_ts = QDateTime.currentDateTimeUtc().toMSecsSinceEpoch() / 1000.0

        # Нормализация X: вычитаем ts_offset чтобы OpenGL работал с малыми числами
        # (float32 имеет точность ±256 сек на значении ~1.7e9 — видимая вибрация)
        if self._auto_scroll:
            self._ts_offset = now_ts - LIVE_WINDOW_SECS
            self._time_axis.ts_offset = self._ts_offset
            self.plot_widget.setXRange(0, LIVE_WINDOW_SECS, padding=0)

        x_ref    = self._ts_offset
        now_norm = now_ts - x_ref   # «сейчас» в нормализованных координатах

        # обновить все каналы синхронно
        for ch_id, ch in self._channels.items():
            if not ch['visible']:
                continue
            if ch['hold']:
                # hold-канал: шаг-функция от window_start до now_norm
                if ch['last_val'] is None:
                    continue
                win_start_norm = now_norm - LIVE_WINDOW_SECS
                if ch['full'] or ch['write'] > 0:
                    x, y = self._get_buf_data(ch_id)
                    x = x - x_ref
                    mask_before = x <= win_start_norm
                    if np.any(mask_before):
                        # есть точки до окна — продлить от win_start_norm
                        val_at_start = float(y[np.where(mask_before)[0][-1]])
                        mask_in = ~mask_before
                        x_win = np.concatenate([[win_start_norm], x[mask_in], [now_norm]])
                        y_win = np.concatenate([[val_at_start], y[mask_in], [ch['last_val']]])
                    else:
                        # все точки внутри окна — начинать с первой реальной точки
                        x_win = np.concatenate([x, [now_norm]])
                        y_win = np.concatenate([y, [ch['last_val']]])
                else:
                    x_win = np.array([win_start_norm, now_norm])
                    y_win = np.array([ch['last_val'], ch['last_val']])
                ch['curve'].setData(x_win, y_win)
            else:
                # обычный канал: данные из буфера, нормализованные
                if ch['full'] or ch['write'] > 0:
                    x, y = self._get_buf_data(ch_id)
                    ch['curve'].setData((x - x_ref).astype(np.float32),
                                        y.astype(np.float32))

        # Y-диапазон по всем активным и видимым буферам
        all_y = []
        for ch in self._channels.values():
            if not ch['visible']:
                continue
            n = MAX_LIVE_POINTS if ch['full'] else ch['write']
            if n > 0:
                all_y.append(ch['buf_v'][:n])
        if not all_y:
            self._update_pts_label()
            return
        y = np.concatenate(all_y)
        ymin, ymax = float(y.min()), float(y.max())
        span = (ymax - ymin) or abs(ymax) or 1.0
        lo, hi = ymin - span * 0.05, ymax + span * 0.05
        prev_lo, prev_hi = self._y_range
        prev_span = (prev_hi - prev_lo) or 1.0
        if abs(lo - prev_lo) / prev_span > 0.05 or abs(hi - prev_hi) / prev_span > 0.05:
            self.plot_widget.getViewBox().setYRange(lo, hi, padding=0)
            self._y_range = (lo, hi)
        self._update_pts_label()

    def _on_manual_pan(self):
        """Пользователь потащил график мышью — останавливаем авто-скролл."""
        if self._mode == "live":
            self._auto_scroll = False

    def _resume_autoscroll(self):
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
        self._auto_scroll = False
        self.plot_widget.setXRange(x0 + step, x1 + step, padding=0)

    # ── архив ─────────────────────────────────────────────────────────────────

    _PRESET_ON  = "background-color: #1a8fe3; color: white; font-weight: bold;"
    _PRESET_OFF = ""

    # ch_id → (measurement, field) для запросов архива
    _ARCHIVE_SOURCES = {
        1: ("nowSetpoint",  "value"),
        2: ("tenza",        "value"),
        3: ("displacement", "value"),
    }

    def _set_load_progress(self, fraction):
        """fraction=0..1 — заливка кнопки; None — сброс (загрузка завершена)."""
        if fraction is None:
            self.btn_load.setEnabled(True)
            self.btn_load.setText("Загрузить")
            self.btn_load.setStyleSheet("")
            return
        self.btn_load.setEnabled(False)
        pct = int(fraction * 100)
        stop = max(0.0, min(fraction, 1.0))
        self.btn_load.setText(f"Загрузка {pct}%")
        self.btn_load.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2980b9, stop:{stop:.3f} #2980b9,
                    stop:{min(stop + 0.001, 1.0):.3f} #555555, stop:1 #555555);
                color: white;
                border: none;
                border-radius: 3px;
            }}
        """)

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
        qdt_to   = QDateTime(self.date_to.date(),   self.time_to.time()).toUTC()

        # нормализация X для архива: отсчёт от начала запрошенного диапазона
        self._ts_offset = qdt_from.toMSecsSinceEpoch() / 1000.0
        self._time_axis.ts_offset = self._ts_offset

        for w in self._archive_workers:
            try:
                w.part_ready.disconnect()
            except RuntimeError:
                pass
            try:
                w.finished.disconnect(self._on_archive_worker_done)
            except RuntimeError:
                pass
        self._archive_workers.clear()

        for b in self._preset_buttons:
            b.setStyleSheet(self._PRESET_OFF)
        self._clear_archive()
        self._archive_parts.clear()
        self._workers_done = 0

        # видимые каналы для загрузки
        visible_sources = {
            ch_id: src
            for ch_id, src in self._ARCHIVE_SOURCES.items()
            if self._channels.get(ch_id, {}).get('visible', True)
        }
        if not visible_sources:
            return
        self._total_archive_workers = len(visible_sources) * N_ARCHIVE_WORKERS
        self._set_load_progress(0)

        total_ms = qdt_from.msecsTo(qdt_to)
        step_ms  = total_ms // N_ARCHIVE_WORKERS

        for ch_id, (measurement, field) in visible_sources.items():
            self._archive_parts[ch_id] = {}
            for i in range(N_ARCHIVE_WORKERS):
                p_from = qdt_from.addMSecs(i * step_ms)
                p_to   = qdt_from.addMSecs((i + 1) * step_ms) if i < N_ARCHIVE_WORKERS - 1 else qdt_to
                # keep — только нужные колонки (меньше байт по HTTP и парсинга);
                # group()/sort() не нужны: один воркер тянет непрерывный кусок
                # одной серии, Influx отдаёт его по времени по возрастанию.
                query  = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {p_from.toString("yyyy-MM-ddTHH:mm:ssZ")}, stop: {p_to.toString("yyyy-MM-ddTHH:mm:ssZ")})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{field}")
  |> keep(columns: ["_time", "_value"])
'''
                worker = _ArchiveWorker(i, query, parent=self)
                worker.part_ready.connect(
                    lambda idx, t, v, c=ch_id: self._on_archive_part(c, idx, t, v)
                )
                worker.finished.connect(self._on_archive_worker_done)
                self._archive_workers.append(worker)

        for w in self._archive_workers:
            w.start()

    def _on_archive_part(self, ch_id: int, idx: int, times, values):
        """Часть канала пришла (times/values — numpy-массивы от воркера)."""
        if ch_id not in self._archive_parts:
            return
        self._archive_parts[ch_id][idx] = (times, values)
        # ждём ВСЕ части канала, затем строим кривую один раз —
        # без промежуточных setData (каждый из них пересчитывал даунсэмпл по всем точкам)
        if len(self._archive_parts[ch_id]) < N_ARCHIVE_WORKERS:
            return
        parts_t, parts_v = [], []
        for i in range(N_ARCHIVE_WORKERS):
            t, v = self._archive_parts[ch_id][i]
            if len(t):
                parts_t.append(t)
                parts_v.append(v)
        if not parts_t:
            return
        # части идут в порядке idx 0…N-1; интервалы воркеров не пересекаются,
        # а внутри куска сортировка уже сделана в воркере → склейки достаточно,
        # полный argsort по всему массиву на GUI-потоке не нужен (он и морозил интерфейс)
        import time as _t                       # DEBUG-тайминг: убрать после диагностики
        _g0 = _t.perf_counter()
        x = np.concatenate(parts_t)
        y = np.concatenate(parts_v)
        _g1 = _t.perf_counter()
        self._update_archive_curve(ch_id, x, y)
        _g2 = _t.perf_counter()
        print(f"[GUI ch{ch_id}] точек={len(x):>9}  склейка={_g1 - _g0:6.3f}с  "
              f"setData/отрисовка={_g2 - _g1:6.3f}с")

    def _on_archive_worker_done(self):
        self._workers_done += 1
        self._set_load_progress(self._workers_done / max(self._total_archive_workers, 1))
        if self._workers_done >= self._total_archive_workers:
            self._archive_workers.clear()
            self._set_load_progress(None)

    def _update_archive_curve(self, ch_id: int, x, y):
        ch       = self._channels.get(ch_id, {})
        if ch.get('hold', False) and len(x) > 1:
            x, y = _step_xy(x, y)
        x_norm = x - self._ts_offset   # нормализация для OpenGL
        color    = ch.get('color',  "#e67e22")
        width    = ch.get('width',  1)
        show_pts = ch.get('points', False)
        name = ch.get('name', f"канал {ch_id}")
        pen  = pg.mkPen(color=color, width=width)
        if ch_id in self._archive_lines:
            self._archive_lines[ch_id].setData(x_norm, y)
        else:
            line = self.plot_widget.plot(
                x_norm, y, pen=pen,
                symbol='o' if show_pts else None,
                symbolSize=5 if show_pts else 1,
                symbolBrush=pg.mkBrush(color) if show_pts else None,
            )
            line.setDownsampling(auto=True, method='subsample')
            line.setClipToView(True)
            self._archive_lines[ch_id] = line
            self._legend.addItem(line, name)

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
        if event.button() == Qt.MouseButton.RightButton:
            self._click_marker.setVisible(False)
            self._click_label.setVisible(False)
            return
        if event.double():
            self._resume_autoscroll()
            return
        if self._mode == "live":
            self._auto_scroll = False
        pos = event.scenePos()
        if not self.plot_widget.sceneBoundingRect().contains(pos):
            return
        mp      = self.plot_widget.getPlotItem().vb.mapSceneToView(pos)
        click_x = mp.x()
        click_y = mp.y()

        best_ch_name, best_ch_xs, best_ch_ys = None, None, None
        best_y_dist = float('inf')
        for name, xs, ys in self._iter_curve_data():
            if len(xs) == 0:
                continue
            fi = int(np.searchsorted(xs, click_x, side='right')) - 1
            fi = np.clip(fi, 0, len(xs) - 1)
            y_at_click = float(ys[fi])
            if np.isnan(y_at_click):
                continue
            d = abs(y_at_click - click_y)
            if d < best_y_dist:
                best_y_dist = d
                best_ch_name, best_ch_xs, best_ch_ys = name, xs, ys

        if best_ch_name is None:
            return
        _, (y0, y1) = self.plot_widget.getViewBox().viewRange()
        y_span = (y1 - y0) or 1.0
        if best_y_dist / y_span > 0.05:
            return

        ni = int(np.searchsorted(best_ch_xs, click_x))
        ni = np.clip(ni, 0, len(best_ch_xs) - 1)
        if ni > 0 and abs(best_ch_xs[ni - 1] - click_x) < abs(best_ch_xs[ni] - click_x):
            ni -= 1
        best_x, best_y, best_name = float(best_ch_xs[ni]), float(best_ch_ys[ni]), best_ch_name
        time_str = _dt.datetime.fromtimestamp(best_x + self._ts_offset).strftime("%H:%M:%S.%f")[:-3]
        self._click_marker.setData([best_x], [best_y])
        self._click_label.setText(f"{best_name}\n{time_str}\n{best_y:.4f}")
        self._click_label.setPos(best_x, best_y)
        self._click_marker.setVisible(True)
        self._click_label.setVisible(True)
        event.accept()

    def _iter_curve_data(self):
        """Итератор (name, xs, ys) по всем видимым кривым."""
        if self._mode == "live":
            for ch in self._channels.values():
                if not ch['visible']:
                    continue
                xs, ys = ch['curve'].getData()
                if xs is not None and len(xs) > 0:
                    yield ch['name'], xs, ys
        else:
            for ch_id, line in self._archive_lines.items():
                xs, ys = line.getData()
                if xs is not None and len(xs) > 0:
                    yield self._channels[ch_id]['name'], xs, ys

    # ── контекстное меню графика ──────────────────────────────────────────────

    def set_theme(self, dark: bool):
        axis_color = "#aaaaaa" if dark else "#333333"
        plot_bg    = "#2c2c2c" if dark else "#f5f5f5"
        self.plot_widget.setBackground(plot_bg)
        for axis in ("left", "bottom"):
            self.plot_widget.getAxis(axis).setPen(pg.mkPen(axis_color))
            self.plot_widget.getAxis(axis).setTextPen(pg.mkPen(axis_color))

        panel_ss = _panel_style(dark)
        self._nav_frame.setStyleSheet(_nav_style(dark))
        self._ch_frame.setStyleSheet(panel_ss)
        self._arch_panel.setStyleSheet(panel_ss)
        btn_ss = _btn_mode_style(dark)
        self.btn_live.setStyleSheet(btn_ss)
        self.btn_archive.setStyleSheet(btn_ss)

    def _build_graph_context_menu(self):
        menu = self.plot_widget.getViewBox().menu
        menu.addSeparator()

        # настройки линий перенесены в панель каналов

        grid_menu = menu.addMenu("Сетка")
        act_grid_x = QAction("По X", grid_menu)
        act_grid_x.setCheckable(True)
        act_grid_x.setChecked(True)
        act_grid_y = QAction("По Y", grid_menu)
        act_grid_y.setCheckable(True)
        act_grid_y.setChecked(True)

        grid_alpha_val = [0.3]

        def _update_grid():
            self.plot_widget.showGrid(
                x=act_grid_x.isChecked(), y=act_grid_y.isChecked(),
                alpha=grid_alpha_val[0])

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

    # ── вспомогательное ───────────────────────────────────────────────────────

    def _clear_archive(self):
        for line in self._archive_lines.values():
            self._legend.removeItem(line)
            self.plot_widget.removeItem(line)
        self._archive_lines.clear()
        self._archive_parts.clear()

    # ── публичный API ─────────────────────────────────────────────────────────

    def bind_channel(self, ch_id: int, signal) -> None:
        """Привязать pyqtSignal к каналу ch_id (1, 2 или 3).

        signal должен иметь сигнатуру (times: list, values: list).
        Предыдущая привязка снимается автоматически.
        """
        ch = self._channels.get(ch_id)
        if ch is None:
            return
        self.unbind_channel(ch_id)
        ch['signal'] = signal
        if self._mode == "live" and ch['visible']:
            self._connect_ch(ch_id, ch)

    def unbind_channel(self, ch_id: int) -> None:
        """Снять привязку сигнала от канала ch_id."""
        ch = self._channels.get(ch_id)
        if ch is None:
            return
        self._disconnect_ch(ch)
        ch['signal'] = None

    def set_curve_color(self, ch_id: int, color: str) -> None:
        """Изменить цвет линии канала ch_id.

        Пример:
            trends.set_curve_color(1, "#ff0000")
        """
        ch = self._channels.get(ch_id)
        if ch is None:
            return
        ch['color'] = color
        ch['curve'].setPen(pg.mkPen(color=_ch_qcolor(ch), width=ch['width']))
        if ch['color_btn'] is not None:
            ch['color_btn'].setStyleSheet(
                f"background-color:{color}; border-radius:3px; border:1px solid #7f8c8d;")

    def set_labels(self, x_label="X", y_label="Y"):
        self.plot_widget.setLabel("bottom", x_label)
        self.plot_widget.setLabel("left", y_label)

    def save_plot(self, filename):
        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
        exporter.export(filename)

    # ── экспорт ───────────────────────────────────────────────────────────────

    def _ask_export_channels(self) -> list[int]:
        """Диалог выбора каналов для выгрузки. Возвращает список ch_id или []."""
        available = {
            ch_id: self._channels[ch_id]['name']
            for ch_id in self._archive_lines
            if ch_id in self._channels
        }
        if not available:
            return []

        dlg = QDialog(self)
        dlg.setWindowTitle("Выгрузка данных")
        dlg.setMinimumWidth(320)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Выберите каналы для выгрузки:"))

        checks: dict[int, QCheckBox] = {}
        for ch_id, name in available.items():
            cb = QCheckBox(name)
            cb.setChecked(True)
            checks[ch_id] = cb
            layout.addWidget(cb)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return []
        return [ch_id for ch_id, cb in checks.items() if cb.isChecked()]

    def _export_csv(self):
        selected = self._ask_export_channels()
        if not selected:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить CSV", "", "CSV файлы (*.csv)")
        if not path:
            return

        def _fmt(ts):
            dt = _dt.datetime.fromtimestamp(ts).astimezone()
            return dt.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3]

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            for ch_id in selected:
                xs, ys = self._archive_lines[ch_id].getData()
                if xs is None or len(xs) == 0:
                    continue
                name = self._channels[ch_id]['name']
                f.write(f"# {name}\n")
                f.write("Время,Значение\n")
                for t, v in zip(xs, ys):
                    f.write(f"{_fmt(t)},{round(float(v), 6)}\n")
                f.write("\n")

    def _export_excel(self):
        selected = self._ask_export_channels()
        if not selected:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить Excel", "", "Excel файлы (*.xlsx)")
        if not path:
            return

        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from influxdb_client import InfluxDBClient
        from ._archive_worker import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

        qdt_from = QDateTime(self.date_from.date(), self.time_from.time()).toUTC()
        qdt_to   = QDateTime(self.date_to.date(),   self.time_to.time()).toUTC()
        t_from   = qdt_from.toString("yyyy-MM-ddTHH:mm:ssZ")
        t_to     = qdt_to  .toString("yyyy-MM-ddTHH:mm:ssZ")

        self.btn_load.setEnabled(False)
        self.btn_load.setText("Экспорт…")

        # прямой запрос к InfluxDB для каждого выбранного канала
        ch_data: list[tuple[str, np.ndarray, np.ndarray]] = []
        try:
            client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG,
                                    enable_gzip=True)
            for ch_id in selected:
                measurement, field = self._ARCHIVE_SOURCES[ch_id]
                query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {t_from}, stop: {t_to})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{field}")
  |> group()
  |> sort(columns: ["_time"])
'''
                times, values = [], []
                for rec in client.query_api().query_stream(query):
                    times.append(rec.get_time().timestamp())
                    values.append(rec.get_value())
                if times:
                    ch_data.append((self._channels[ch_id]['name'],
                                    np.asarray(times,  dtype=np.float64),
                                    np.asarray(values, dtype=np.float64)))
        except Exception as e:
            print(f"[Export] ошибка запроса: {e}")
        finally:
            try:
                client.close()
            except Exception:
                pass
            self.btn_load.setEnabled(True)
            self.btn_load.setText("Загрузить")

        if not ch_data:
            return

        # мастер-сетка: тенза (ch_id=2), иначе канал с наибольшим числом точек
        master_name = self._channels[2]['name'] if 2 in selected else None
        master_ts   = None
        for name, xs, ys in ch_data:
            if name == master_name:
                master_ts = xs
                break
        if master_ts is None:
            master_ts = max(ch_data, key=lambda d: len(d[1]))[1]

        def _ffill(ts_chan, vs_chan, ts_all):
            """Forward-fill — для редких каналов (уставка)."""
            idx    = np.searchsorted(ts_chan, ts_all, side='right') - 1
            result = np.full(len(ts_all), np.nan)
            mask   = idx >= 0
            result[mask] = vs_chan[idx[mask]]
            if len(vs_chan) > 0 and not mask.all() and mask.any():
                first = int(np.searchsorted(ts_all, ts_chan[0], side='left'))
                result[:first] = vs_chan[0]
            return result

        def _nearest(ts_chan, vs_chan, ts_all, threshold=0.008):
            """Nearest-fill с порогом — для каналов с тем же темпом (смещение)."""
            if len(ts_chan) == 0:
                return np.full(len(ts_all), np.nan)
            idx    = np.searchsorted(ts_chan, ts_all)
            prev_i = np.clip(idx - 1, 0, len(ts_chan) - 1)
            next_i = np.clip(idx,     0, len(ts_chan) - 1)
            prev_d = np.abs(ts_chan[prev_i] - ts_all)
            next_d = np.abs(ts_chan[next_i] - ts_all)
            best_i = np.where(prev_d <= next_d, prev_i, next_i)
            best_d = np.minimum(prev_d, next_d)
            result = np.full(len(ts_all), np.nan)
            mask   = best_d <= threshold
            result[mask] = vs_chan[best_i[mask]]
            return result

        # смещение и тенза — один темп (nearest); уставка — редкая (ffill)
        _dense_names = {self._channels[2]['name'], self._channels[3]['name']}
        aligned = [
            (name, _nearest(xs, ys, master_ts) if name in _dense_names else _ffill(xs, ys, master_ts))
            for name, xs, ys in ch_data
        ]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Архив"

        header_fill = PatternFill("solid", fgColor="1A8FE3")
        header_font = Font(bold=True, color="FFFFFF")
        center = Alignment(horizontal="center")

        headers    = ["Дата", "Время"] + [f"Значение {name}" for name, _ in aligned]
        col_widths = [12, 15] + [max(20, len(h) + 2) for h in headers[2:]]
        for col, (h, w) in enumerate(zip(headers, col_widths), 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center
            ws.column_dimensions[cell.column_letter].width = w

        val_cols = [vals for _, vals in aligned]
        for row, ts in enumerate(master_ts, 2):
            dt = _dt.datetime.fromtimestamp(float(ts)).astimezone()
            ws.cell(row=row, column=1, value=dt.strftime("%d.%m.%Y"))
            ws.cell(row=row, column=2, value=dt.strftime("%H:%M:%S.%f")[:-3])
            for col, vals in enumerate(val_cols, 3):
                v = vals[row - 2]
                ws.cell(row=row, column=col,
                        value=round(float(v), 3) if not np.isnan(v) else None)

        wb.save(path)


# ── вспомогательные функции модуля ───────────────────────────────────────────

def _step_xy(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Преобразовать массивы точек в ступенчатую функцию (горизонталь + вертикальный прыжок).

    Для N точек возвращает 2N-1 точек:
        [x0, x1, x1, x2, x2, ..., xn-1]
        [y0, y0, y1, y1, ..., yn-1]
    """
    if len(x) <= 1:
        return x, y
    sx = np.repeat(x, 2)[1:]    # [x0, x1, x1, x2, x2, ..., xn-1]
    sy = np.repeat(y, 2)[:-1]   # [y0, y0, y1, y1, ..., yn-1]
    return sx, sy


def _sep() -> QFrame:
    """Вертикальный разделитель для строки канала."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setStyleSheet("color: #4a6278;")
    return sep


def _ch_qcolor(ch: dict) -> QColor:
    """QColor канала с учётом прозрачности."""
    c = QColor(ch['color'])
    c.setAlpha(ch['alpha'])
    return c


def _toggle_style(visible: bool) -> str:
    """Стиль кнопки вкл/выкл канала."""
    if visible:
        return (
            "QPushButton { color:#2ecc71; background:#2c3e50; "
            "border:1px solid #27ae60; border-radius:3px; font-size:13px; }"
            "QPushButton:hover { background:#27ae60; }"
        )
    return (
        "QPushButton { color:#7f8c8d; background:#2c3e50; "
        "border:1px solid #4a6278; border-radius:3px; font-size:13px; }"
        "QPushButton:hover { background:#3d5166; }"
    )
