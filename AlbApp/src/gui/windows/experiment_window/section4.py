from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, QTimer
import pyqtgraph as pg

pg.setConfigOptions(antialias=True)

_CHART_TITLES = ["Нагружение, H", "Скорость нагружения H/сек", "Положение, L мм"]
_CH_COLORS    = ["#e67e22", "#3498db", "#2ecc71"]
_CHART_UNITS  = ["Н", "Н/сек", "мм"]


def _make_plot(title: str, color: str) -> pg.PlotWidget:
    pw = pg.PlotWidget()
    pw.setBackground("#1a252f")
    pw.showGrid(x=True, y=True, alpha=0.25)
    pw.setMinimumHeight(120)
    pi = pw.getPlotItem()
    pi.setTitle(title, color="#ecf0f1", size="10pt")
    pi.getAxis("bottom").setPen(pg.mkPen("#4a6278"))
    pi.getAxis("left")  .setPen(pg.mkPen("#4a6278"))
    pi.getAxis("bottom").setTextPen(pg.mkPen("#7f8c8d"))
    pi.getAxis("left")  .setTextPen(pg.mkPen("#7f8c8d"))
    pw.plot([], [], pen=pg.mkPen(color, width=1.5))
    return pw


def _make_value_box(color: str, unit: str) -> QFrame:
    """Окошко текущего значения под графиком: подпись · крупное значение · ед."""
    box = QFrame()
    box.setObjectName("valueBox")
    lay = QHBoxLayout(box)
    lay.setContentsMargins(10, 4, 10, 4)
    lay.setSpacing(6)

    cap = QLabel("Текущее")
    cap.setObjectName("vbCap")
    val = QLabel("—")
    val.setObjectName("vbVal")
    val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    u = QLabel(unit)
    u.setObjectName("vbUnit")

    lay.addWidget(cap, 0)
    lay.addStretch(1)
    lay.addWidget(val, 0)
    lay.addWidget(u, 0)

    box._val = val
    box._cap = cap
    box._unit = u
    box._accent = color
    _style_value_box(box, dark=True)
    return box


def _style_value_box(box: QFrame, dark: bool = None):
    """Стиль окошка значения из палитры приложения — вписывается в тему.
    Цвет графика остаётся только на самом числе, чтобы привязать его к кривой."""
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QApplication
    pal = QApplication.instance().palette()
    role = QPalette.ColorRole
    bg     = pal.color(role.AlternateBase).name()
    border = pal.color(role.Mid).name()
    text   = pal.color(role.WindowText).name()
    muted  = pal.color(role.PlaceholderText).name()
    box.setStyleSheet(
        f"QFrame#valueBox {{ background: {bg}; border: 1px solid {border};"
        " border-radius: 6px; } QLabel { background: transparent; }"
        f" QLabel#vbCap  {{ color: {muted}; font-size: 11px; }}"
        f" QLabel#vbVal  {{ color: {box._accent}; font-size: 16px; font-weight: bold; }}"
        f" QLabel#vbUnit {{ color: {text}; font-size: 11px; }}")


def style_value_boxes(plots: list, dark: bool = None):
    """Перекрасить окошки значений всех графиков (для ExperimentWidget.set_theme)."""
    for pw in plots:
        box = getattr(pw, "_value_box", None)
        if box is not None:
            _style_value_box(box)


def make_section4(parent_layout: QVBoxLayout) -> list:
    plots = []
    for title, color, unit in zip(_CHART_TITLES, _CH_COLORS, _CHART_UNITS):
        container = QWidget()
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        pw = _make_plot(title, color)
        box = _make_value_box(color, unit)
        col.addWidget(pw, 1)
        col.addWidget(box, 0)
        parent_layout.addWidget(container, 1)

        pw._value_box = box          # ссылки для обновления значения и темы
        pw._value_label = box._val
        plots.append(pw)

    # таймер: показывает последнее значение каждой кривой в окошке под графиком
    timer = QTimer(plots[0])
    timer.setInterval(200)
    timer.timeout.connect(lambda: _refresh_values(plots))
    timer.start()
    plots[0]._value_timer = timer    # держим ссылку, чтобы таймер не уничтожился

    return plots


def _refresh_values(plots: list):
    for pw in plots:
        items = pw.getPlotItem().listDataItems()
        text = "—"
        if items:
            _x, y = items[0].getData()
            if y is not None and len(y):
                text = f"{y[-1]:.1f}"
        pw._value_label.setText(text)
