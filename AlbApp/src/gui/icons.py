"""icons.py — иконки интерфейса, нарисованные кодом.

Внешних ресурсов (svg/png) в проекте нет, поэтому значки рисуются QPainter'ом
в сетке 24×24 и масштабируются под нужный размер. Цвет задаётся вызывающим —
одна и та же иконка используется в разных состояниях (серая / зелёная / красная).

    make_icon("power", "#27ae60", 24) -> QPixmap
"""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF, QPainterPath

KINDS = ("power", "link", "sensor", "alarm", "stop", "reset_fault")


def _pen(col: QColor, s: float) -> QPen:
    p = QPen(col, max(1.6, 2.2 * s))
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def _arc_arrow(p: QPainter, col: QColor, s: float,
               cx: float, cy: float, r: float, start_deg: float, span_deg: float):
    """Дуга со стрелкой на конце — основа значка «сброс»."""
    p.setPen(_pen(col, s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF((cx - r) * s, (cy - r) * s, 2 * r * s, 2 * r * s),
              int(start_deg * 16), int(span_deg * 16))
    a = math.radians(start_deg)
    hx, hy = cx + r * math.cos(a), cy - r * math.sin(a)
    h = 3.6
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawPolygon(QPolygonF([
        QPointF((hx + h) * s, hy * s),
        QPointF((hx - h * 0.5) * s, (hy - h * 0.9) * s),
        QPointF((hx - h * 0.5) * s, (hy + h * 0.9) * s),
    ]))


def make_icon(kind: str, color: str, size: int = 24) -> QPixmap:
    """Иконка заданного вида и цвета. Фон прозрачный."""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = QColor(color)
    s = size / 24.0

    if kind == "power":                       # молния
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        pts = [(13, 2), (4, 14), (11, 14), (10, 22), (19, 10), (12, 10)]
        p.drawPolygon(QPolygonF([QPointF(x * s, y * s) for x, y in pts]))

    elif kind == "link":                      # дуги сигнала и точка
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for r in (5, 9, 13):
            p.drawArc(QRectF((12 - r) * s, (18 - r) * s, 2 * r * s, 2 * r * s),
                      30 * 16, 120 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(12 * s, 18 * s), 1.7 * s, 1.7 * s)

    elif kind == "alarm":                     # треугольник с восклицательным знаком
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(12 * s, 3 * s)
        path.lineTo(22 * s, 20 * s)
        path.lineTo(2 * s, 20 * s)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(12 * s, 9.5 * s), QPointF(12 * s, 14.5 * s))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(12 * s, 17.2 * s), 1.25 * s, 1.25 * s)

    elif kind == "stop":                      # знак «кирпич»: круг с перекладиной
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(12 * s, 12 * s), 10 * s, 10 * s)
        # перекладину вырезаем прозрачностью — работает на любом фоне
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.drawRoundedRect(QRectF(6 * s, 10.2 * s, 12 * s, 3.6 * s), 1.2 * s, 1.2 * s)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    elif kind == "reset_fault":               # треугольник аварии в круговой стрелке
        _arc_arrow(p, col, s, 12, 12, 10, 55, 300)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPolygon(QPolygonF([QPointF(12 * s, 6.5 * s),
                                 QPointF(17 * s, 15.5 * s),
                                 QPointF(7 * s, 15.5 * s)]))
        # восклицательный знак — прозрачные вырезы, чтобы читался на любом фоне
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.drawRoundedRect(QRectF(11.3 * s, 9.5 * s, 1.4 * s, 3.4 * s), 0.7 * s, 0.7 * s)
        p.drawEllipse(QPointF(12 * s, 14.1 * s), 0.75 * s, 0.75 * s)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    else:                                     # sensor — шкала со стрелкой
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(3 * s, 6 * s, 18 * s, 18 * s), 0, 180 * 16)
        p.drawLine(QPointF(12 * s, 15 * s), QPointF(17 * s, 10 * s))

    p.end()
    return pm
