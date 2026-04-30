from PyQt6.QtWidgets import QWidget, QVBoxLayout
import pyqtgraph as pg

pg.setConfigOptions(antialias=True)

_CHART_TITLES = ["Нагружение, H", "Скорость нагружения H/сек", "Положение, L мм"]
_CH_COLORS    = ["#e67e22", "#3498db", "#2ecc71"]


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


def make_section4(parent_layout: QVBoxLayout) -> None:
    for title, color in zip(_CHART_TITLES, _CH_COLORS):
        parent_layout.addWidget(_make_plot(title, color), 1)
