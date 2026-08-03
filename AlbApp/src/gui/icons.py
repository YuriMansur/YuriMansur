"""icons.py — иконки интерфейса, нарисованные кодом.

Внешних ресурсов (svg/png) в проекте нет, поэтому значки рисуются QPainter'ом
в сетке 24×24 и масштабируются под нужный размер. Цвет задаётся вызывающим —
одна и та же иконка используется в разных состояниях (серая / зелёная / красная).

    make_icon("power", "#27ae60", 24) -> QPixmap
"""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF, QPainterPath

KINDS = ("power", "link", "sensor", "alarm", "stop", "reset_fault",
         "power_on", "power_off", "arrow_up", "arrow_down", "zero",
         "eye", "eye_off", "play", "record", "stop_sq", "points", "points_off",
         # разделы навигации
         "flask", "video", "chart", "chat", "export", "doc", "gear")


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

    elif kind in ("power_on", "power_off"):
        # Обозначения МЭК: «|» в круге — включить, «○» в круге — выключить.
        # Отличаются силуэтом, а не декором: кнопки гаснут на время испытания,
        # и цвет различать нельзя, а перечёркивание на 20 px сливалось со значком.
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(3 * s, 3 * s, 18 * s, 18 * s))
        if kind == "power_on":
            p.drawLine(QPointF(12 * s, 7 * s), QPointF(12 * s, 17 * s))
        else:
            p.drawEllipse(QRectF(8 * s, 8 * s, 8 * s, 8 * s))

    elif kind in ("arrow_up", "arrow_down"):  # толчок привода вверх/вниз
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        pts = ([(12, 4), (20, 16), (4, 16)] if kind == "arrow_up"
               else [(12, 20), (20, 8), (4, 8)])
        p.drawPolygon(QPolygonF([QPointF(x * s, y * s) for x, y in pts]))

    elif kind == "zero":                      # обнуление: стрелки сходятся к нулю
        # Знак тарирования, но вертикальный: стрелки сверху и снизу. Стрелка на
        # базовую линию читалась как «скачать», перечёркнутый ноль — как
        # «выкл. привод», поэтому взяли сходящиеся стрелки.
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(8 * s, 7 * s, 8 * s, 10 * s))   # ноль стоймя, как цифра
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPolygon(QPolygonF([QPointF(12 * s, 5.5 * s), QPointF(8.8 * s, 1.5 * s),
                                 QPointF(15.2 * s, 1.5 * s)]))
        p.drawPolygon(QPolygonF([QPointF(12 * s, 18.5 * s), QPointF(8.8 * s, 22.5 * s),
                                 QPointF(15.2 * s, 22.5 * s)]))

    elif kind == "eye":                       # открыть камеру (предпросмотр)
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(QPolygonF([QPointF(x * s, y * s) for x, y in
                                 ((2, 12), (7, 6), (17, 6), (22, 12), (17, 18), (7, 18))]))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(12 * s, 12 * s), 3.2 * s, 3.2 * s)

    elif kind == "eye_off":                   # закрыть камеру: закрытый глаз
        # опущенное веко дугой + ресницы; форма отличается от открытого глаза
        # силуэтом, поэтому различима и в 14 px
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(2.5 * s, 10 * s)
        path.quadTo(12 * s, 19 * s, 21.5 * s, 10 * s)
        p.drawPath(path)
        for x0, y0, x1, y1 in ((6, 15, 4.5, 18), (18, 15, 19.5, 18)):
            p.drawLine(QPointF(x0 * s, y0 * s), QPointF(x1 * s, y1 * s))

    elif kind == "play":                      # воспроизведение
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPolygon(QPolygonF([QPointF(7 * s, 4 * s), QPointF(20 * s, 12 * s),
                                 QPointF(7 * s, 20 * s)]))

    elif kind == "record":                    # запись
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(12 * s, 12 * s), 7 * s, 7 * s)

    elif kind == "stop_sq":                   # остановить запись
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(6 * s, 6 * s, 12 * s, 12 * s), 1.5 * s, 1.5 * s)

    elif kind == "flask":                     # испытания — колба
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(9 * s, 3 * s), QPointF(15 * s, 3 * s))
        path = QPainterPath()
        path.moveTo(10 * s, 3.5 * s)
        path.lineTo(10 * s, 10 * s)
        path.lineTo(4.5 * s, 19 * s)
        path.quadTo(3.5 * s, 21 * s, 6 * s, 21 * s)
        path.lineTo(18 * s, 21 * s)
        path.quadTo(20.5 * s, 21 * s, 19.5 * s, 19 * s)
        path.lineTo(14 * s, 10 * s)
        path.lineTo(14 * s, 3.5 * s)
        p.drawPath(path)
        p.drawLine(QPointF(7 * s, 15 * s), QPointF(17 * s, 15 * s))   # уровень жидкости

    elif kind == "video":                     # видеоналожение — кадр поверх кадра
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(2 * s, 6 * s, 13 * s, 12 * s), 2 * s, 2 * s)
        p.drawRoundedRect(QRectF(9 * s, 3 * s, 13 * s, 12 * s), 2 * s, 2 * s)

    elif kind == "chart":                     # тренды — оси и ломаная вверх
        pen2 = _pen(col, s)
        p.setPen(pen2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(3 * s, 3 * s), QPointF(3 * s, 20 * s))
        p.drawLine(QPointF(3 * s, 20 * s), QPointF(21 * s, 20 * s))
        path = QPainterPath()
        path.moveTo(6 * s, 16 * s)
        path.lineTo(10 * s, 11 * s)
        path.lineTo(14 * s, 14 * s)
        path.lineTo(19 * s, 6 * s)
        p.drawPath(path)

    elif kind in ("points", "points_off"):    # ломаная с маркерами / без них
        # Ломаная одна и та же — различаются только маркерами: рядом две кнопки
        # состояния, и разной формы линия сбивала бы с толку.
        verts = [(3, 17), (9, 8), (15, 14), (21, 5)]
        # с точками линию рисуем тоньше, иначе маркеры сливаются с ней и оба
        # значка выглядят одинаково
        line = _pen(col, s)
        if kind == "points":
            line.setWidthF(max(1.0, 1.3 * s))
        p.setPen(line)
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(verts[0][0] * s, verts[0][1] * s)
        for x, y in verts[1:]:
            path.lineTo(x * s, y * s)
        p.drawPath(path)
        if kind == "points":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            for x, y in verts:
                p.drawEllipse(QPointF(x * s, y * s), 2.7 * s, 2.7 * s)

    elif kind == "chat":                      # сообщения — облачко с хвостиком
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.addRoundedRect(QRectF(2.5 * s, 4 * s, 19 * s, 13 * s), 3 * s, 3 * s)
        path.moveTo(7 * s, 17 * s)
        path.lineTo(7 * s, 21.5 * s)
        path.lineTo(12 * s, 17 * s)
        p.drawPath(path)

    elif kind == "export":                    # экспорт — стрелка из лотка
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(4 * s, 14 * s), QPointF(4 * s, 20 * s))
        p.drawLine(QPointF(4 * s, 20 * s), QPointF(20 * s, 20 * s))
        p.drawLine(QPointF(20 * s, 20 * s), QPointF(20 * s, 14 * s))
        p.drawLine(QPointF(12 * s, 15 * s), QPointF(12 * s, 4 * s))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPolygon(QPolygonF([QPointF(12 * s, 2 * s), QPointF(7.5 * s, 7 * s),
                                 QPointF(16.5 * s, 7 * s)]))

    elif kind == "doc":                       # протоколы — лист со строками
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(5 * s, 2.5 * s)
        path.lineTo(14 * s, 2.5 * s)
        path.lineTo(19 * s, 7.5 * s)
        path.lineTo(19 * s, 21.5 * s)
        path.lineTo(5 * s, 21.5 * s)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(14 * s, 2.5 * s), QPointF(14 * s, 7.5 * s))   # загнутый угол
        p.drawLine(QPointF(14 * s, 7.5 * s), QPointF(19 * s, 7.5 * s))
        for y in (12, 15.5, 19):
            p.drawLine(QPointF(8 * s, y * s), QPointF(16 * s, y * s))

    elif kind == "gear":                      # настройки — шестерня
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.save()
        p.translate(12 * s, 12 * s)
        for _ in range(8):                    # зубья
            p.rotate(45)
            p.drawRoundedRect(QRectF(-1.7 * s, -11 * s, 3.4 * s, 5 * s), 1 * s, 1 * s)
        p.restore()
        p.drawEllipse(QPointF(12 * s, 12 * s), 7 * s, 7 * s)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.drawEllipse(QPointF(12 * s, 12 * s), 3 * s, 3 * s)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    else:                                     # sensor — шкала со стрелкой
        p.setPen(_pen(col, s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(3 * s, 6 * s, 18 * s, 18 * s), 0, 180 * 16)
        p.drawLine(QPointF(12 * s, 15 * s), QPointF(17 * s, 10 * s))

    p.end()
    return pm
