from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QLineEdit, QDialog,
)
from PyQt6.QtCore import pyqtSignal, QTimer, Qt, QPoint
from PyQt6.QtGui import QPainter, QColor, QPolygon


class _StripedOverlay(QWidget):
    """Анимированные диагональные полоски поверх кнопки."""
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def start(self):
        self._offset = 0
        self._timer.start()
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._offset = (self._offset + 2) % 40
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        w, h = self.width(), self.height()
        stripe = 20
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(39, 174, 96, 130))
        p.drawRoundedRect(0, 0, w, h, 3, 3)
        p.setBrush(QColor(255, 255, 255, 45))
        x = -stripe * 2 + self._offset
        while x < w + h:
            p.drawPolygon(QPolygon([
                QPoint(x,          0),
                QPoint(x + stripe, 0),
                QPoint(x + stripe - h, h),
                QPoint(x - h,      h),
            ]))
            x += stripe * 2

# ── Словарь процедур испытания ───────────────────────────────────────────────
#
# Ключ: кортеж (гост, методика) — однозначно идентифицирует процедуру.
# Значение: список шагов. Каждый шаг — словарь с обязательным полем "type".
#
# Типы шагов:
#   "title"    — заголовок процедуры (крупный текст, название раздела ГОСТа)
#   "subtitle" — подзаголовок / инструкция (например, "Установите образец")
#   "info"     — информационная строка (текст требований, примечаний)
#   "f0row"    — строка обнуления нагрузки: кнопка "F=0" + поле ввода значения
#   "step"     — пронумерованный шаг с описанием временного интервала и кнопкой
#                  num  — номер шага (строка)
#                  desc — текст описания (например, "t = не менее 10с и не более 30с")
#                  btn  — метка кнопки действия (например, "Fset")
#   "button"   — отдельная кнопка с номером и меткой
#                  num  — префикс-номер (строка)
#                  text — метка кнопки
#   "protocol" — кнопка "Сформировать Протокол" с растяжкой сверху
#                  (всегда добавляется последней в процедуре)

# Шаги которые прерываются аварией и красятся красным: (гост, методика) -> {индекс}
ALARM_INTERRUPT_STEPS: dict[tuple, set[int]] = {
    ("Р ИСО 10328-2021", "16.2.2"):    {3},   # шаг 4
    ("Р ИСО 10328-2021", "16.2.2+С"):  {3},
    ("Р ИСО 10328-2021", "16.2.1"):    {2},   # шаг 3
    ("Р ИСО 10328-2021", "13.2.1.2"):  {3},   # шаг 4
    ("Р53868-2021",       "16.2.2"):    {3},
    ("Р53868-2021",       "16.2.2+С"):  {3},
    ("Р53868-2021",       "16.2.1"):    {2},
    ("Р53868-2021",       "13.2.1.2"):  {3},
}

PROCEDURES: dict[tuple, list[dict]] = {

    # ── ГОСТ Р ИСО 10328-2021, методика 16.2.2 ──────────────────────────────
    # Основное статическое испытание: установка образца, приложение нагрузки
    # Fset на 10–30 с, снятие нагрузки на 10–20 мин, фиксация Fstab и Fsu upper.
    ("Р ИСО 10328-2021", "16.2.2"): [
        {"type": "title",    "text": "16.2.2  Основное статическое испытание"},
        {"type": "subtitle", "text": "Установите образец"},
        # Требование ГОСТа: зарегистрировать условие нагружения до начала
        {"type": "info",     "text": "· Зарегистрировать условие нагружения и уровень нагрузки, значения"},
        # Обнуление показаний датчика нагрузки перед нагружением
        {"type": "f0row"},
        # Шаг 4 — приложить Fset и удерживать заданное время
        {"type": "step",     "num": "4", "desc": "t = не менее 10с и не более 30с",           "btn": "Fset"},
        # Шаг 5 — выдержка без нагрузки (релаксация образца)
        {"type": "step",     "num": "5", "desc": "t = не менее 10 мин и не более 20 мин",      "btn": "F=0"},
        # Шаг 6 — приложить стабилизирующую нагрузку Fstab
        {"type": "button",   "text": "Fstab",    "num": "6."},
        # Шаг 8 — обнулить показания второго датчика после стабилизации
        {"type": "button",   "text": "Записать", "num": "8. Обнулить 2"},
        # Шаг 5 повторно — приложить верхнюю нагрузку испытания Fsu upper
        {"type": "button",   "text": "Fsu upper","num": "5."},
        # Формирование итогового протокола испытания
        {"type": "protocol"},
    ],

    # ── ГОСТ Р ИСО 10328-2021, методика 16.2.2+С ────────────────────────────
    # Испытание со стабилизацией: аналогично 16.2.2, но без шага обнуления
    # второго датчика — вместо него сразу переход к Fsu upper.
    ("Р ИСО 10328-2021", "16.2.2+С"): [
        {"type": "title",    "text": "16.2.2+С  Испытание со стабилизацией"},
        {"type": "subtitle", "text": "Установите образец"},
        {"type": "info",     "text": "· Зарегистрировать условие нагружения и уровень нагрузки, значения"},
        {"type": "f0row"},
        {"type": "step",     "num": "4", "desc": "t = не менее 10с и не более 30с",           "btn": "Fset"},
        {"type": "step",     "num": "5", "desc": "t = не менее 10 мин и не более 20 мин",      "btn": "F=0"},
        {"type": "button",   "text": "Fstab",    "num": "6."},
        # В варианте +С шаг 7 — сразу Fsu upper без промежуточного обнуления
        {"type": "button",   "text": "Fsu upper","num": "7."},
        {"type": "protocol"},
    ],

       ("Р53868-2021", "16.2.2+С"): [
        {"type": "title",    "text": "16.2.2+С  Испытание со стабилизацией"},
        {"type": "subtitle", "text": "Установите образец"},
        {"type": "info",     "text": "· Зарегистрировать условие нагружения и уровень нагрузки, значения"},
        {"type": "f0row"},
        {"type": "step",     "num": "4", "desc": "t = не менее 10с и не более 30с",           "btn": "Fset"},
        {"type": "step",     "num": "5", "desc": "t = не менее 10 мин и не более 20 мин",      "btn": "F=0"},
        {"type": "button",   "text": "Fstab",    "num": "6."},
        # В варианте +С шаг 7 — сразу Fsu upper без промежуточного обнуления
        {"type": "button",   "text": "Fsu upper","num": "7."},
        {"type": "protocol"},
    ],

      ("Р53868-2021", "16.2.2"): [
        {"type": "title",    "text": "16.2.2  Основное статическое испытание"},
        {"type": "subtitle", "text": "Установите образец"},
        # Требование ГОСТа: зарегистрировать условие нагружения до начала
        {"type": "info",     "text": "· Зарегистрировать условие нагружения и уровень нагрузки, значения"},
        # Обнуление показаний датчика нагрузки перед нагружением
        {"type": "f0row"},
        # Шаг 4 — приложить Fset и удерживать заданное время
        {"type": "step",     "num": "4", "desc": "t = не менее 10с и не более 30с",           "btn": "Fset"},
        # Шаг 5 — выдержка без нагрузки (релаксация образца)
        {"type": "step",     "num": "5", "desc": "t = не менее 10 мин и не более 20 мин",      "btn": "F=0"},
        # Шаг 6 — приложить стабилизирующую нагрузку Fstab
        {"type": "button",   "text": "Fstab",    "num": "6."},
        # Шаг 8 — обнулить показания второго датчика после стабилизации
        {"type": "button",   "text": "Записать", "num": "8. Обнулить 2"},
        # Шаг 5 повторно — приложить верхнюю нагрузку испытания Fsu upper
        {"type": "button",   "text": "Fsu upper","num": "5."},
        # Формирование итогового протокола испытания
        {"type": "protocol"},
    ],
}

# Заглушка — показывается когда комбинация (гост, методика) не описана в PROCEDURES.
# Пользователь видит сообщение вместо пустого виджета.
_DEFAULT_PROCEDURE = [
    {"type": "info", "text": "Для данного сочетания ГОСТ / Методика процедура не задана."},
]


# ── Описания методик (JSON) ──────────────────────────────────────────────────
# Структура шагов и вложенных под-шагов выносится в methodics/<файл>.json.
# Поведение (рендеры, ветвления) остаётся в коде и привязывается по полю "kind".
_METHODIC_FILES = {
    "17.4.5": "17_4_5.json",
    "16.3":   "16_3.json",
    "6.4.4":  "6_4_4.json",
}


def _load_methodic(gost: str, method: str) -> dict | None:
    """Загрузить описание методики из methodics/<файл>.json (или None, если нет)."""
    import json
    from pathlib import Path
    fname = _METHODIC_FILES.get(method)
    if not fname:
        return None
    path = Path(__file__).parent / "methodics" / fname
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# ── Пошаговый мастер испытания ───────────────────────────────────────────────
#
# Универсальный визард для любой пары (ГОСТ, методика): шаги берутся из
# PROCEDURES; для (ГОСТ 10328, 17.4.5) — расширенный сценарий со «Стабилизацией».
# Палитра наследуется от темы приложения (следует тёмной/светлой теме).

# Заполняется _refresh_wz() из палитры приложения перед построением визарда.
_WZ: dict = {}


def _refresh_wz() -> None:
    """Пересчитать палитру визарда из текущей палитры приложения."""
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QApplication
    pal = QApplication.instance().palette()
    R = QPalette.ColorRole
    c = lambda role: pal.color(role).name()
    _WZ.update({
        "header_bg": c(R.AlternateBase),
        "panel_bg":  c(R.Base),
        "side_bg":   c(R.Base),
        "card_bg":   c(R.AlternateBase),
        "btn_bg":    c(R.Button),
        "muted":     c(R.PlaceholderText),
        "title":     c(R.WindowText),
        "text":      c(R.WindowText),
        "border":    c(R.Mid),
        "blue":      "#2980b9",   # ожидающий/активный шаг (как в списке шагов)
        "green":     "#27ae60",   # выполненный шаг
        "accent":    "#1abc9c",   # акцент страницы «Испытания»
        "amber":     "#e0a030",
        "red":       "#c0392b",
    })


def _make_activity_icon(size: int = 34):
    """Иконка-пульс: синяя ломаная «activity» на скруглённой плитке (как на мокапе)."""
    from PyQt6.QtGui import QPixmap, QPen, QColor, QPolygonF
    from PyQt6.QtCore import QPointF
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # плитка
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(_WZ.get("btn_bg", "#2a2f37")))
    r = size * 0.24
    p.drawRoundedRect(0, 0, size, size, r, r)
    # ломаная в координатах 24×24 (Lucide «activity») → масштаб с полями
    pts = [(22, 12), (18, 12), (15, 21), (9, 3), (6, 12), (2, 12)]
    pad = size * 0.20
    span = size - 2 * pad
    poly = QPolygonF([QPointF(pad + x / 24 * span, pad + y / 24 * span) for x, y in pts])
    pen = QPen(QColor("#3498db"), max(2.0, size * 0.075))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline(poly)
    p.end()
    return pm


def _steps_from_procedure(proc: list) -> tuple:
    """Преобразовать список PROCEDURES в шаги визарда (group / title / sub / kind)."""
    title, intro, steps = "", [], []
    for s in proc:
        t = s["type"]
        if t == "title":
            title = s["text"]
        elif t in ("subtitle", "info"):
            intro.append(s["text"].lstrip("·").strip())
        elif t == "f0row":
            steps.append({"group": "ПОДГОТОВКА", "title": "Обнуление нагрузки",
                          "sub": "Установить F = 0 перед нагружением", "kind": "f0"})
        elif t == "step":
            steps.append({"group": "НАГРУЖЕНИЕ", "title": s["btn"],
                          "sub": s.get("desc", ""), "kind": "load", "value": s["btn"]})
        elif t == "button":
            steps.append({"group": "НАГРУЖЕНИЕ", "title": s["text"],
                          "sub": s.get("num", "").strip(), "kind": "action"})
        elif t == "protocol":
            steps.append({"group": "ЗАВЕРШЕНИЕ", "title": "Протокол",
                          "sub": "Сформировать протокол испытания", "kind": "protocol"})
    if intro:
        steps.insert(0, {"group": "ПОДГОТОВКА", "title": "Установка образца",
                         "sub": " ".join(x for x in intro if x), "kind": "info"})
    if not steps:
        steps = [{"group": "ПОДГОТОВКА", "title": "Нет шагов",
                  "sub": "Для выбранного ГОСТ / методики процедура не задана.", "kind": "info"}]
    return (title or "Процедура испытания"), steps


class _StepItem(QFrame):
    """Элемент бокового степпера: бейдж состояния + заголовок + подпись."""
    clicked = pyqtSignal(int)

    def __init__(self, index: int, title: str, subtitle: str, indent: bool = False,
                 number: int = None, parent=None):
        super().__init__(parent)
        self._index = index
        self._indent = indent  # True — вложенный под-шаг (с отступом в степпере)
        self._number = number if number is not None else index + 1  # отображаемый номер
        self.setObjectName("stepItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8 + (22 if indent else 0), 6, 8, 6)
        lay.setSpacing(8)

        self._badge = QLabel(str(self._number))
        self._badge.setFixedSize(22, 22)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        txt = QVBoxLayout()
        txt.setContentsMargins(0, 0, 0, 0)
        txt.setSpacing(0)
        self._title = QLabel(title)
        self._title.setWordWrap(True)
        self._sub   = QLabel(subtitle)
        self._sub.setWordWrap(True)
        txt.addWidget(self._title)
        txt.addWidget(self._sub)

        lay.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(txt, 1)
        self._state = "pending"
        self._highlighted = False
        self._apply_style()

    def mousePressEvent(self, _e):
        self.clicked.emit(self._index)

    def set_state(self, state: str):
        self._state = state
        self._apply_style()

    def badge_pt(self):
        """Левый край и вертикальный центр бейджа-кружка в координатах родителя (фрейма)."""
        return (self.x() + self._badge.x(),
                self.y() + self._badge.y() + self._badge.height() / 2)

    # подсветка фоном «как у активного» — для шага, выбранного для просмотра
    def set_highlight(self, on: bool):
        self._highlighted = on
        self._apply_style()

    def _apply_style(self):
        active_frame = (
            f"QFrame#stepItem {{ background: {_WZ['card_bg']};"
            f" border-right: 3px solid {_WZ['blue']}; border-radius: 4px; }}")
        idle_frame = "QFrame#stepItem { background: transparent; border-right: 3px solid transparent; }"
        self.setStyleSheet(active_frame if (self._highlighted or self._state == "active") else idle_frame)

        num = "•" if self._indent else str(self._number)
        if self._state == "active":
            self._badge.setText(num)
            self._badge.setStyleSheet(
                f"background: {_WZ['blue']}; color: white; border-radius: 11px;"
                " font-weight: bold; font-size: 11px;")
            self._title.setStyleSheet(f"color: {_WZ['title']}; font-weight: bold; background: transparent;")
        elif self._state == "done":
            self._badge.setText("✓")
            self._badge.setStyleSheet(
                f"background: {_WZ['green']}; color: white; border-radius: 11px;"
                " font-weight: bold; font-size: 12px;")
            self._title.setStyleSheet(f"color: {_WZ['title']}; font-weight: bold; background: transparent;")
        else:  # pending
            self._badge.setText(num)
            self._badge.setStyleSheet(
                f"background: {_WZ['btn_bg']}; color: {_WZ['muted']}; border-radius: 11px;"
                " font-weight: bold; font-size: 11px;")
            self._title.setStyleSheet(f"color: {_WZ['text']}; background: transparent;")
        self._sub.setStyleSheet(f"color: {_WZ['muted']}; font-size: 11px; background: transparent;")


class _ConnectorOverlay(QWidget):
    """Прозрачное наложение поверх степпера: рисует связующую стрелку между кружками
    двух шагов (источник → цель). Лежит над элементами, поэтому не перекрывается их фоном."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._src = None
        self._dst = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_connector(self, src, dst):
        self._src, self._dst = src, dst
        self.update()

    def paintEvent(self, e):
        if self._src is None or self._dst is None:
            return
        from PyQt6.QtGui import QPainter, QPen, QPainterPath, QPolygonF, QBrush
        from PyQt6.QtCore import QPointF
        sx, ys = self._src.badge_pt()   # левый край и центр кружка источника
        dx, yd = self._dst.badge_pt()   # левый край и центр кружка цели

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(_WZ["blue"])      # цвет как у подсветки активного шага
        pen = QPen(color, 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        gap = 6.0                        # зазор от кружка
        x_line = min(sx, dx) - 16.0      # вертикаль слева от обоих кружков
        r = 7.0                          # радиус скругления углов
        ah = 6.0                         # длина наконечника
        up = -1.0 if yd < ys else 1.0    # направление к цели по вертикали
        sx_e = sx - gap                  # старт у кружка источника
        tip_x = dx - gap                 # остриё наконечника у кружка цели
        base_x = tip_x - ah              # основание наконечника (туда приходит линия)

        path = QPainterPath()
        path.moveTo(sx_e, ys)                                  # у кружка источника
        path.lineTo(x_line + r, ys)
        path.quadTo(x_line, ys, x_line, ys + up * r)           # скруглённый угол
        path.lineTo(x_line, yd - up * r)                       # вертикаль
        path.quadTo(x_line, yd, x_line + r, yd)                # скруглённый угол
        path.lineTo(base_x, yd)                                # к кружку цели
        p.drawPath(path)

        # наконечник — аккуратный закрашенный треугольник, указывает на кружок
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        tri = QPolygonF([
            QPointF(tip_x, yd),
            QPointF(base_x, yd - ah * 0.7),
            QPointF(base_x, yd + ah * 0.7),
        ])
        p.drawPolygon(tri)
        p.end()


class _SideFrame(QFrame):
    """Фрейм степпера со связующей стрелкой (рисуется наложением поверх элементов)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._overlay = _ConnectorOverlay(self)
        self._overlay.hide()

    def set_connector(self, src, dst):
        self._overlay.set_connector(src, dst)
        if src is None or dst is None:
            self._overlay.hide()
        else:
            self._overlay.setGeometry(self.rect())
            self._overlay.raise_()
            self._overlay.show()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._overlay.setGeometry(self.rect())
        self._overlay.raise_()


class _CyclicWizard(QWidget):
    """Пошаговый мастер испытания: шаги из PROCEDURES, стиль из темы приложения."""
    started = pyqtSignal(bool)

    def __init__(self, gost: str, method: str, start_index=None, parent=None):
        super().__init__(parent)
        _refresh_wz()
        self._gost   = gost
        self._method = method
        self._items: list[_StepItem] = []
        self._previewing = False   # True — показан просмотр другого (пройденного) шага
        # значения полей form-шагов: {step_id: {field_key: value, "__fixture__": ..., "__decision__": ...}}
        self._form_values: dict[str, dict] = {}
        # флаги, выставляемые опциями decision (например, passed для протокола)
        self._flags: dict = {}
        self._jump_target = None    # индекс шага, на который указывает стрелка «→»
        self._build_steps()
        if start_index is not None:   # восстановление позиции при смене темы
            self._current = max(0, min(start_index, len(self._steps) - 1))

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(8)
        body.addWidget(self._build_sidebar(), 0)

        self._panel = QFrame()
        self._panel.setObjectName("wzPanel")
        self._panel.setStyleSheet(
            f"QFrame#wzPanel {{ background: {_WZ['panel_bg']};"
            f" border: 1px solid {_WZ['border']}; border-radius: 8px; }}")
        panel_outer = QVBoxLayout(self._panel)
        panel_outer.setContentsMargins(6, 6, 6, 6)   # отступ скролла от скруглённой рамки
        # контент шага — в собственном скролле: панель не меняет размер на «высоких»
        # шагах, лишнее прокручивается внутри (а не распирает секцию)
        self._panel_scroll = QScrollArea()
        self._panel_scroll.setWidgetResizable(True)
        self._panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._panel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._panel_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._panel_scroll.viewport().setStyleSheet("background: transparent;")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._content = QVBoxLayout(inner)
        self._content.setContentsMargins(10, 8, 10, 8)
        self._content.setSpacing(10)
        self._panel_scroll.setWidget(inner)
        panel_outer.addWidget(self._panel_scroll)
        body.addWidget(self._panel, 1)
        root.addLayout(body, 1)

        self._refresh_sidebar()
        self._render_step(self._current)

    # ── формирование шагов ─────────────────────────────────────────────────
    def _build_steps(self):
        data = (_load_methodic(self._gost, self._method)
                if self._gost in ("Р ИСО 10328-2021", "Р53868-2021") else None)
        if data:
            # структура шагов и вложенных под-шагов берётся из JSON-конфига методики
            self._htitle = data.get("title", "Процедура испытания")
            self._steps = [dict(s) for s in data["steps"]]
            self._substeps_cfg = data.get("substeps", {})
            self._current = 0
        else:
            self._substeps_cfg = {}
            proc = PROCEDURES.get((self._gost, self._method))
            self._htitle, self._steps = _steps_from_procedure(proc or _DEFAULT_PROCEDURE)
            self._current = 0

    # ── шапка ──────────────────────────────────────────────────────────────
    def _build_header(self) -> QFrame:
        f = QFrame()
        f.setObjectName("wzHeader")
        f.setStyleSheet(
            f"QFrame#wzHeader {{ background: {_WZ['header_bg']};"
            f" border: 1px solid {_WZ['border']}; border-radius: 8px; }}"
            " QLabel { background: transparent; }")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)

        icon = QLabel()
        icon.setPixmap(_make_activity_icon(34))
        title = QLabel(
            f"<span style='color:{_WZ['title']}; font-weight:bold;'>{self._gost} — {self._method}</span>"
            f"<br><span style='color:{_WZ['muted']}; font-size:11px;'>{self._htitle}</span>")
        title.setWordWrap(True)
        lay.addWidget(icon, 0)
        lay.addWidget(title, 1)

        sample = QLabel(
            f"<span style='color:{_WZ['muted']}; font-size:11px;'>Образец</span>"
            f"<br><span style='color:{_WZ['text']};'>#КУ-2024-017</span>")
        lay.addWidget(sample, 0)

        equip = QLabel(
            f"<span style='color:{_WZ['green']};'>● Оборудование</span>"
            f"<br><span style='color:{_WZ['green']};'>подключено</span>")
        lay.addWidget(equip, 0)

        sess = QLabel(
            f"<span style='color:{_WZ['muted']}; font-size:11px;'>Сессия…</span>"
            f"<br><span style='color:{_WZ['text']};'>14:32</span>")
        lay.addWidget(sess, 0)

        # кнопка прерывания испытания — доступна на каждом шаге
        btn_stop = QPushButton("⛔ Прервать")
        btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_stop.setStyleSheet(
            f"QPushButton {{ background: {_WZ['red']}; color: white; border: none;"
            " border-radius: 6px; padding: 6px 14px; font-weight: bold; }"
            " QPushButton:hover { background: #e74c3c; }")
        btn_stop.clicked.connect(self._interrupt_test)
        lay.addWidget(btn_stop, 0)
        return f

    # ── боковой степпер ────────────────────────────────────────────────────
    def _build_sidebar(self) -> QScrollArea:
        self._side_scroll = QScrollArea()
        self._side_scroll.setObjectName("wzSideScroll")
        self._side_scroll.setWidgetResizable(True)
        self._side_scroll.setFixedWidth(265)
        self._side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._side_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._side_scroll.setStyleSheet("QScrollArea#wzSideScroll { background: transparent; border: none; }")
        self._fill_sidebar()
        return self._side_scroll

    def _fill_sidebar(self):
        """(Пере)построить элементы степпера из текущего self._steps."""
        self._items = []
        f = _SideFrame()
        f.setObjectName("wzSide")
        f.setStyleSheet(
            f"QFrame#wzSide {{ background: {_WZ['side_bg']}; border: 1px solid {_WZ['border']};"
            " border-radius: 8px; } QLabel { background: transparent; }")
        lay = QVBoxLayout(f)
        # увеличенный левый отступ — «жёлоб» под связующую линию-стрелку
        lay.setContentsMargins(16, 8, 6, 8)
        lay.setSpacing(2)

        last_group = None
        step_no = 0   # сквозной номер только для невложенных шагов
        for i, step in enumerate(self._steps):
            if step["group"] != last_group:
                gl = QLabel(step["group"])
                gl.setStyleSheet(
                    f"color: {_WZ['muted']}; font-size: 10px; font-weight: bold;"
                    " letter-spacing: 1px; padding: 8px 6px 2px 6px;")
                lay.addWidget(gl)
                last_group = step["group"]
            indent = step.get("indent", False)
            if not indent:
                step_no += 1
            item = _StepItem(i, step["title"], step["sub"], indent=indent, number=step_no)
            item.clicked.connect(self._preview_step)
            self._items.append(item)
            lay.addWidget(item)
        lay.addStretch()
        self._side_frame = f
        self._side_scroll.setWidget(f)

    def _rebuild_sidebar(self):
        """Пересоздать степпер (после вставки/удаления вложенных под-шагов)."""
        self._fill_sidebar()
        self._refresh_sidebar()

    def _refresh_sidebar(self):
        for i, item in enumerate(self._items):
            item.set_state("done" if i < self._current else
                           "active" if i == self._current else "pending")
        # связующая стрелка от текущего шага к цели перехода (self._jump_target)
        if (self._jump_target is not None
                and 0 <= self._current < len(self._items)
                and 0 <= self._jump_target < len(self._items)):
            self._side_frame.set_connector(self._items[self._current],
                                           self._items[self._jump_target])
        else:
            self._side_frame.set_connector(None, None)
        # держать активный шаг в видимой области степпера
        if 0 <= self._current < len(self._items):
            active = self._items[self._current]
            QTimer.singleShot(0, lambda: self._side_scroll.ensureWidgetVisible(active, 0, 40))

    def _set_preview_highlight(self, idx):
        """Подсветить фоном (как у активного) выбранный для просмотра шаг — и только его."""
        for i, item in enumerate(self._items):
            item.set_highlight(i == idx)

    # ── просмотр содержимого любого шага без перехода к нему ───────────────
    def _preview_step(self, idx: int):
        """Показать содержимое любого шага (пройденного или ещё не пройденного),
        не делая его текущим — активный шаг и переход остаются за кнопкой «Далее».
        Клик по текущему шагу возвращает к нему в обычном режиме."""
        if idx == self._current:
            self._render_step(self._current)
            return
        self._render_step(idx, preview=True)

    # ── навигация ──────────────────────────────────────────────────────────
    def _goto(self, idx: int):
        idx = max(0, min(idx, len(self._steps) - 1))
        self._current = idx
        self._jump_target = None   # стрелка-указатель снимается после перехода
        self._refresh_sidebar()
        self._render_step(idx)
        # испытание считается «идущим» вне группы ПОДГОТОВКА → блок комбобоксов сек.2
        self.started.emit(self._steps[idx]["group"] != "ПОДГОТОВКА")

    def _interrupt_test(self):
        """Кнопка «Прервать» — крупный стилизованный диалог подтверждения."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Прерывание испытания")
        dlg.setModal(True)
        dlg.setMinimumSize(480, 240)
        dlg.setStyleSheet(
            f"QDialog {{ background: {_WZ['panel_bg']}; }}"
            f" QLabel {{ background: transparent; color: {_WZ['text']}; }}")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(28, 26, 28, 22)
        root.setSpacing(16)

        # заголовок с крупной иконкой
        head = QHBoxLayout()
        head.setSpacing(16)
        icon = QLabel("⛔")
        icon.setStyleSheet(f"color: {_WZ['red']}; font-size: 40px; background: transparent;")
        head.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        ttl = QLabel("Прервать испытание?")
        ttl.setWordWrap(True)
        ttl.setStyleSheet(f"color: {_WZ['title']}; font-size: 20px; font-weight: bold; background: transparent;")
        head.addWidget(ttl, 1)
        root.addLayout(head)

        msg = QLabel("Текущий прогресс будет сброшен к первому шагу.\nЭто действие нельзя отменить.")
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {_WZ['muted']}; font-size: 13px; background: transparent;")
        root.addWidget(msg)

        root.addStretch()

        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setMinimumSize(120, 40)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(
            f"QPushButton {{ background: {_WZ['btn_bg']}; color: {_WZ['text']};"
            f" border: 1px solid {_WZ['border']}; border-radius: 8px; padding: 8px 18px; font-size: 14px; }}"
            f" QPushButton:hover {{ background: {_WZ['card_bg']}; }}")
        btn_ok = QPushButton("⛔ Да, прервать")
        btn_ok.setMinimumSize(150, 40)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(
            f"QPushButton {{ background: {_WZ['red']}; color: white; border: none;"
            " border-radius: 8px; padding: 8px 18px; font-size: 14px; font-weight: bold; }"
            " QPushButton:hover { background: #e74c3c; }")
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok.clicked.connect(dlg.accept)
        btns.addWidget(btn_cancel, 0)
        btns.addWidget(btn_ok, 0)
        root.addLayout(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._abort_test()

    def _abort_test(self):
        """Сброс прогресса визарда к первому шагу после прерывания."""
        self._flags = {}
        self._form_values = {}    # сброс значений и выбранных веток form-шагов
        self._jump_target = None
        self._build_steps()       # перечитать шаги из конфига (убрать вложенные под-шаги)
        self._rebuild_sidebar()
        self._goto(0)

    def _goto_protocol_interrupted(self):
        """Переход к протоколу при досрочном завершении (разрушение образца):
        пройденными помечаем только шаги до текущего включительно, пропущенные
        промежуточные шаги остаются «pending», протокол — активным."""
        done_through = self._current
        proto = len(self._steps) - 1
        self._current = proto
        self._jump_target = None   # стрелка-указатель снимается после перехода
        for i, item in enumerate(self._items):
            item.set_state("done" if i <= done_through else
                           "active" if i == proto else "pending")
        self._render_step(proto)
        if self._items:
            active = self._items[proto]
            QTimer.singleShot(0, lambda: self._side_scroll.ensureWidgetVisible(active, 0, 40))
        self.started.emit(self._steps[proto]["group"] != "ПОДГОТОВКА")

    @staticmethod
    def _clear(lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
            elif it.layout() is not None:
                _CyclicWizard._clear(it.layout())

    def _rerender_keep_scroll(self):
        """Перерисовать текущий шаг, сохранив позицию вертикального скролла
        (для ветвлений/флагов — чтобы не отбрасывало к началу)."""
        sb = self._panel_scroll.verticalScrollBar()
        pos = sb.value()
        self._render_step(self._current)

        # диапазон скролла пересчитывается после перекомпоновки контента —
        # восстанавливаем позицию, когда диапазон обновится (и страховкой по таймеру)
        def _restore(*_):
            sb.setValue(pos)
            try:
                sb.rangeChanged.disconnect(_restore)
            except TypeError:
                pass

        sb.rangeChanged.connect(_restore)
        QTimer.singleShot(0, _restore)

    def _render_step(self, idx: int, preview: bool = False):
        self._clear(self._content)
        self._previewing = preview
        self._set_preview_highlight(idx if preview else None)
        step = self._steps[idx]

        # нумерация без учёта вложенных под-шагов (как в левом степпере)
        total = sum(1 for s in self._steps if not s.get("parent"))
        current_no = sum(1 for s in self._steps[:idx + 1] if not s.get("parent"))
        badge_text = f"⚡ Шаг {current_no} из {total}"
        if preview:
            badge_text += "  •  просмотр"
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f"background: {_WZ['card_bg']}; color: {_WZ['accent']};"
            f" border: 1px solid {_WZ['accent']}; border-radius: 11px;"
            " padding: 3px 12px; font-size: 11px; font-weight: bold;")
        badge_row = QHBoxLayout()
        badge_row.addWidget(badge, 0)
        badge_row.addStretch()
        self._content.addLayout(badge_row)

        if step["kind"] == "form":
            self._render_form(step)
        elif step["kind"] == "stab":
            self._render_stabilization(step.get("decision", True), step.get("banner", True), step.get("inputs", True))
        elif step["kind"] == "protocol":
            self._render_protocol()
        else:
            self._render_action(step, idx)

        # при смене шага показываем контент с начала (полоса прокрутки сохраняет
        # старое значение при перестройке — иначе верх нового шага «уезжает» вниз);
        # для перерисовки того же шага позицию восстанавливает _rerender_keep_scroll
        QTimer.singleShot(0, lambda: self._panel_scroll.verticalScrollBar().setValue(0))

    # ── панель навигации шага: в режиме просмотра — только возврат ──────────
    def _step_nav(self, primary_text: str, finish: bool = False) -> QHBoxLayout:
        # навигационная кнопка — на всю ширину строки, чтобы длинный текст
        # не вылезал за правый край панели в узкой колонке
        nav = QHBoxLayout()
        if self._previewing:
            ret = self._btn("← Вернуться к текущему шагу", primary=True)
            ret.clicked.connect(lambda: self._render_step(self._current))
            nav.addWidget(ret, 1)
            return nav
        primary = self._btn("✓ Завершить" if finish else primary_text, primary=True)
        if finish:
            primary.clicked.connect(lambda: self._goto(0))
        else:
            primary.clicked.connect(lambda: self._goto(self._current + 1))
        nav.addWidget(primary, 1)
        return nav

    # ── универсальный контент «form»: кнопки + блоки полей + тумблер ───────
    # Описание берётся из JSON-конфига методики (step["body"]); значения полей
    # хранятся в self._form_values[step_id]. Блоки: button / text / note /
    # banner / fields / fixture.
    @staticmethod
    def _form_setter(store: dict, key: str):
        return lambda text: store.__setitem__(key, text)

    def _render_block(self, c, store: dict, blk: dict):
        """Отрисовать один блок form-описания (button/banner/text/note/fields/fixture)."""
        accents = {"blue": _WZ["blue"], "amber": _WZ["amber"], "red": _WZ["red"], "green": _WZ["green"]}
        bt = blk.get("type")
        if bt == "button":
            row = QHBoxLayout()
            b = self._btn(blk["text"])
            b.setEnabled(not self._previewing)
            row.addWidget(b, 0)
            row.addStretch()
            c.addLayout(row)
        elif bt == "banner":
            lbl = QLabel(blk["text"])
            lbl.setWordWrap(True)
            col = accents.get(blk.get("accent", "blue"), _WZ["blue"])
            lbl.setStyleSheet(
                f"background: {_WZ['card_bg']}; color: {_WZ['text']};"
                f" border-left: 3px solid {col}; border-radius: 4px; padding: 8px 12px;")
            c.addWidget(lbl)
        elif bt == "text":
            lbl = QLabel(blk["text"])
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {_WZ['text']}; font-weight: bold; background: transparent; padding-top: 4px;")
            c.addWidget(lbl)
        elif bt == "note":
            lbl = QLabel(blk["text"])
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
            c.addWidget(lbl)
        elif bt == "fields":
            row = QHBoxLayout()
            row.setSpacing(8)
            for it in blk["items"]:
                key = it["key"]
                store.setdefault(key, it.get("default", ""))
                row.addLayout(self._input(it["label"], store[key], self._form_setter(store, key)), 1)
            c.addLayout(row)
        elif bt == "fixture":
            self._render_form_fixture(c, store, blk.get("question", "Использовалось специальное приспособление?"))
        elif bt == "flag":
            key = blk["key"]
            on = bool(store.get(key))
            row = QHBoxLayout()
            b = self._toggle_btn(blk["text"])
            b.setChecked(on)
            self._style_one_toggle(b, on)
            b.setEnabled(not self._previewing)
            b.clicked.connect(lambda _c=False, k=key: self._toggle_flag(store, k))
            row.addWidget(b, 0)
            row.addStretch()
            c.addLayout(row)
            if on:
                for sub in blk.get("reveal", []):
                    self._render_block(c, store, sub)

    def _toggle_flag(self, store: dict, key: str):
        store[key] = not store.get(key)
        self._rerender_keep_scroll()

    def _render_form(self, step: dict):
        c = self._content
        store = self._form_values.setdefault(step.get("id", step["title"]), {})

        h = QLabel(step.get("title", ""))
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        for blk in step.get("body", []):
            self._render_block(c, store, blk)

        dec = step.get("decision")
        if dec:
            self._render_decision(step, store, dec)
        else:
            c.addStretch()
            c.addLayout(self._step_nav("Далее →"))

    # ── интерпретатор ветвления «decision» (вопрос + варианты, вложенность) ─
    def _resolve_target(self, goto) -> int:
        """Индекс целевого шага: 'next'/'prev' или id шага."""
        if goto in (None, "next"):
            return self._current + 1
        if goto == "prev":
            return self._current - 1
        idx = next((i for i, s in enumerate(self._steps) if s.get("id") == goto), None)
        return idx if idx is not None else self._current + 1

    def _set_substeps(self, parent_id: str, value):
        """Вставить вложенные под-шаги для выбора value (ключ конфига
        '<parent_id>_<value>'); прежние под-шаги этого родителя удаляются."""
        self._steps = [s for s in self._steps if s.get("parent") != parent_id]
        anchor = next((i for i, s in enumerate(self._steps) if s.get("id") == parent_id), None)
        if anchor is None:
            return
        grp = self._steps[anchor]["group"]
        subs = self._substeps_cfg.get(f"{parent_id}_{value}", [])
        for off, s in enumerate(subs):
            self._steps.insert(anchor + 1 + off, dict(s, group=grp))

    def _choose_decision(self, step: dict, store: dict, key: str, value):
        store[key] = value
        # сбросить вложенные решения уровнем ниже
        for k in [k for k in store if k.startswith(key + "_")]:
            del store[k]
        # верхнеуровневое решение может разворачивать вложенные под-шаги в степпере
        if key == "__decision__":
            pid = step.get("id")
            if pid and any(k.startswith(pid + "_") for k in self._substeps_cfg):
                self._set_substeps(pid, value)
                self._rebuild_sidebar()
        self._rerender_keep_scroll()

    def _render_decision(self, step: dict, store: dict, dec: dict, key: str = "__decision__"):
        c = self._content
        chosen = store.get(key)

        q = QLabel(dec["question"])
        q.setWordWrap(True)
        q.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(q)

        trow = QHBoxLayout()
        trow.setSpacing(8)
        for opt in dec["options"]:
            b = self._toggle_btn(opt["label"])
            b.setEnabled(not self._previewing)
            b.clicked.connect(lambda _c=False, v=opt["value"]: self._choose_decision(step, store, key, v))
            self._style_one_toggle(b, chosen == opt["value"])
            trow.addWidget(b, 1)
        c.addLayout(trow)

        opt = next((o for o in dec["options"] if o["value"] == chosen), None)
        if opt:
            for blk in opt.get("reveal", []):
                self._render_block(c, store, blk)
            if "decision" in opt:           # вложенное решение рисует свою навигацию
                self._render_decision(step, store, opt["decision"], key=key + "_n")
                return

        c.addStretch()
        if self._previewing:
            c.addLayout(self._step_nav("Далее →"))
            return
        if opt is None:
            self._jump_target = None
            self._refresh_sidebar()
            return
        if opt.get("repeat"):
            nav = QHBoxLayout()
            rb = self._btn(opt.get("repeat_button", "🔁 Повторить"), primary=True)
            rb.clicked.connect(lambda _c=False: self._choose_decision(step, store, key, None))
            nav.addWidget(rb, 1)
            c.addLayout(nav)
            return
        # переход на целевой шаг (+ опц. стрелка / флаги / «прерванный» протокол)
        target = self._resolve_target(opt.get("goto", "next"))
        self._jump_target = target if opt.get("arrow") else None
        self._refresh_sidebar()
        nav = QHBoxLayout()
        btn = self._btn(opt.get("button", "Далее →"), primary=True)
        btn.clicked.connect(lambda _c=False, o=opt, t=target: self._decision_go(o, t))
        nav.addWidget(btn, 1)
        c.addLayout(nav)

    def _decision_go(self, opt: dict, target: int):
        self._flags.update(opt.get("set", {}))
        if opt.get("interrupted"):
            self._goto_protocol_interrupted()
        else:
            self._goto(target)

    def _render_form_fixture(self, c, store: dict, question: str):
        lbl = QLabel(question)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(lbl)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        yes = self._toggle_btn("✓ Да")
        no  = self._toggle_btn("✕ Нет")

        def set_fix(v):
            store["__fixture__"] = v
            self._style_toggle_pair(yes, no, v)

        yes.clicked.connect(lambda _c=False: set_fix(True))
        no.clicked.connect(lambda _c=False: set_fix(False))
        yes.setEnabled(not self._previewing)
        no.setEnabled(not self._previewing)
        toggle.addWidget(yes, 1)
        toggle.addWidget(no, 1)
        c.addLayout(toggle)
        set_fix(store.get("__fixture__"))

    # ── последний шаг: протокол (с надписью о несоответствии при «Нет») ────
    def _render_protocol(self):
        c = self._content
        h = QLabel("Протокол")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        if self._flags.get("passed") is False:
            warn = QLabel("Образец не удовлетворяет требованиям")
            warn.setWordWrap(True)
            warn.setStyleSheet(
                f"background: {_WZ['card_bg']}; color: {_WZ['red']}; font-weight: bold;"
                f" border-left: 3px solid {_WZ['red']}; border-radius: 4px; padding: 8px 12px;")
            c.addWidget(warn)

        c.addStretch()
        if self._previewing:
            c.addLayout(self._step_nav("Далее →"))
            return
        nav = QHBoxLayout()
        btn = self._btn("📄 Генерация протокола", primary=True)
        nav.addWidget(btn, 1)
        c.addLayout(nav)

    # ── кнопка-переключатель: меняет цвет при нажатии ───────────────────────
    def _toggle_btn(self, text: str) -> QPushButton:
        b = QPushButton(text)
        b.setCheckable(True)
        b.setMinimumHeight(36)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _style_one_toggle(self, btn, active: bool):
        """Подсветить одиночную кнопку-тумблер (выбран / не выбран)."""
        if active:
            btn.setChecked(True)
            # та же геометрия, что у неактивной (рамка 1px, паддинг, bold) —
            # отличается только цвет, чтобы кнопка не меняла размер при нажатии
            btn.setStyleSheet(
                f"QPushButton {{ background: {_WZ['blue']}; color: white;"
                f" border: 1px solid {_WZ['blue']}; border-radius: 6px;"
                " padding: 6px 12px; font-weight: bold; }")
        else:
            btn.setChecked(False)
            btn.setStyleSheet(
                f"QPushButton {{ background: {_WZ['btn_bg']}; color: {_WZ['text']};"
                f" border: 1px solid {_WZ['border']}; border-radius: 6px;"
                " padding: 6px 12px; font-weight: bold; }"
                f" QPushButton:hover {{ background: {_WZ['card_bg']}; }}")

    def _style_toggle_pair(self, btn_yes, btn_no, used):
        """Подсветить «Да/Нет» по выбранному значению (общая для шагов 1 и 2)."""
        self._style_one_toggle(btn_yes, used is True)
        self._style_one_toggle(btn_no, used is False)

    # ── контент шага «Стабилизация» (полный, как на мокапе) ────────────────
    def _render_stabilization(self, decision: bool = True, banner: bool = True, inputs: bool = True):
        c = self._content
        h = QLabel("Стабилизирующая нагрузка")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        if banner:
            note = QLabel("Цикл: приложить Fstab = 800 Н на 20 с, затем F = 0 на 12 минут.")
            note.setWordWrap(True)
            note.setStyleSheet(
                f"background: {_WZ['card_bg']}; color: {_WZ['text']};"
                f" border-left: 3px solid {_WZ['amber']}; border-radius: 4px; padding: 8px 12px;")
            c.addWidget(note)

        if inputs:
            in_row = QHBoxLayout()
            in_row.setSpacing(8)
            in_row.addLayout(self._input("Fstab (Н)", "800"), 1)
            in_row.addLayout(self._input("t нагрузки (с)", "20"), 1)
            in_row.addLayout(self._input("t разгрузки (мин)", "12"), 1)
            c.addLayout(in_row)

        cards = QHBoxLayout()
        cards.setSpacing(8)
        cards.addWidget(self._card("800 Н", _WZ['green'], "F текущее"), 1)
        cards.addWidget(self._card("18.4 с", _WZ['title'], "t прошло"), 1)
        cards.addWidget(self._card("2.1 мм", _WZ['title'], "δ при Fstab"), 1)
        c.addLayout(cards)

        if self._previewing or not decision:
            c.addStretch()
            c.addLayout(self._step_nav("Далее →"))
            return

        lbl = QLabel("Решение после стабилизации")
        lbl.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(lbl)

        q = QLabel("⚠  Использовалось специальное приспособление?")
        q.setWordWrap(True)
        q.setStyleSheet(
            f"background: {_WZ['card_bg']}; color: {_WZ['text']}; border: 1px solid {_WZ['border']};"
            " border-radius: 6px; padding: 8px 12px;")
        c.addWidget(q)

        dec = QHBoxLayout()
        dec.setSpacing(8)
        btn_yes = self._btn("✓ Да — установить в\nприспособление")
        btn_no  = self._btn("✕ Нет —\nпродолжить")
        btn_yes.clicked.connect(lambda: self._goto(self._current + 1))
        btn_no.clicked.connect(lambda: self._goto(self._current + 1))
        dec.addWidget(btn_yes, 1)
        dec.addWidget(btn_no, 1)
        c.addLayout(dec)
        c.addStretch()

    # ── контент остальных шагов (та же сетка) ──────────────────────────────
    def _render_action(self, step: dict, idx: int):
        c = self._content
        h = QLabel(step["title"])
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        if step.get("sub"):
            banner = QLabel(step["sub"])
            banner.setWordWrap(True)
            banner.setStyleSheet(
                f"background: {_WZ['card_bg']}; color: {_WZ['text']};"
                f" border-left: 3px solid {_WZ['blue']}; border-radius: 4px; padding: 8px 12px;")
            c.addWidget(banner)

        if step["kind"] == "load":
            cards = QHBoxLayout()
            cards.setSpacing(8)
            cards.addWidget(self._card("—", _WZ['green'], "F текущее"), 1)
            cards.addWidget(self._card("—", _WZ['title'], "t прошло"), 1)
            c.addLayout(cards)

        c.addStretch()

        action_label = {
            "f0":       "Установить F = 0",
            "load":     f"Приложить {step.get('value', 'нагрузку')}",
            "action":   "Выполнить шаг",
            "protocol": "📄 Сформировать протокол",
            "info":     "Далее →",
        }.get(step["kind"], "Далее →")

        last = idx >= len(self._steps) - 1
        c.addLayout(self._step_nav(action_label, finish=last))

    # ── мелкие конструкторы ────────────────────────────────────────────────
    def _input(self, label: str, value: str, on_change=None) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(3)
        l = QLabel(label)
        l.setWordWrap(True)
        l.setStyleSheet(f"color: {_WZ['muted']}; font-size: 11px; background: transparent;")
        e = QLineEdit(value)
        # маленькая мин. ширина — чтобы ряд из нескольких полей ужимался под
        # ширину панели и не вылезал за правый край
        e.setMinimumWidth(40)
        # пройденный (не текущий) шаг открыт только для просмотра — править нельзя
        e.setReadOnly(self._previewing)
        if on_change is not None:
            e.textChanged.connect(on_change)
        e.setStyleSheet(
            f"background: {_WZ['card_bg']}; color: {_WZ['title']}; border: 1px solid {_WZ['border']};"
            " border-radius: 6px; padding: 6px 10px; font-size: 16px; font-weight: bold;")
        box.addWidget(l)
        box.addWidget(e)
        return box

    def _card(self, value: str, color: str, caption: str) -> QFrame:
        f = QFrame()
        f.setObjectName("wzCard")
        f.setStyleSheet(
            f"QFrame#wzCard {{ background: {_WZ['card_bg']}; border: 1px solid {_WZ['border']};"
            " border-radius: 6px; } QLabel { background: transparent; }")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        v = QLabel(value)
        v.setStyleSheet(f"color: {color}; font-size: 17px; font-weight: bold;")
        cap = QLabel(caption)
        cap.setWordWrap(True)
        cap.setStyleSheet(f"color: {_WZ['muted']}; font-size: 11px;")
        lay.addWidget(v)
        lay.addWidget(cap)
        return f

    def _btn(self, text: str, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setMinimumHeight(36)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            b.setStyleSheet(
                f"QPushButton {{ background: {_WZ['blue']}; color: white; border: none;"
                " border-radius: 6px; padding: 6px 14px; font-weight: bold; }"
                " QPushButton:hover { background: #3498db; }")
        else:
            b.setStyleSheet(
                f"QPushButton {{ background: {_WZ['btn_bg']}; color: {_WZ['text']};"
                f" border: 1px solid {_WZ['border']}; border-radius: 6px; padding: 6px 12px; }}"
                f" QPushButton:hover {{ background: {_WZ['card_bg']}; }}")
        return b


class Section3Widget(QWidget):
    started = pyqtSignal(bool)  # True — испытание начато, False — сброшено

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self._scroll, 1)

        # Кнопка Начать / Сбросить внизу секции
        self._btn_start = QPushButton("▶ Начать испытание")
        self._btn_start.setMinimumHeight(36)
        self._btn_start.clicked.connect(self._toggle_start)
        root.addWidget(self._btn_start)

        self._running = False
        self._gost    = ""
        self._method  = ""
        self._wizard  = None   # _CyclicWizard в режиме 17.4.5, иначе None
        self._rebuild()

    def set_params(self, gost: str, method: str):
        """Вызывается из Section2Widget при смене ГОСТ или методики."""
        if gost == self._gost and method == self._method:
            return  # параметры не изменились — перестройка не нужна
        self._gost   = gost
        self._method = method
        self._rebuild()

    def _rebuild(self):
        """Пересоздаёт содержимое секции — пошаговый мастер для текущей (ГОСТ, методика)."""
        self._build_wizard()

    def set_theme(self, dark: bool):
        """Перестроить мастер под текущую палитру приложения (вызов из ExperimentWidget)."""
        if self._wizard is None:
            return
        self._build_wizard(start_index=self._wizard._current)

    def _build_wizard(self, start_index=None):
        """Построить пошаговый мастер для текущей (ГОСТ, методика)."""
        self._wizard = _CyclicWizard(self._gost, self._method, start_index=start_index)
        self._wizard.started.connect(self.started)   # проброс блокировки комбобоксов сек.2
        self._scroll.setWidget(self._wizard)
        self._btn_start.hide()
        # нейтрализуем состояние списочного режима, чтобы on_alarm/_toggle_start были безопасны
        self._running   = False
        self._executing = False
        self._completed = False
        self._step_buttons = []
        self._step_bars    = []
        self._alarm_steps      = set()
        self._alarm_interrupts = set()

    def _get_step_labels(self, steps: list) -> list:
        """Собирает метки для 5 шагов из процедуры."""
        labels = []
        for step in steps:
            t = step["type"]
            if t == "f0row":
                labels.append("F=0")
            elif t == "step":
                labels.append(step["btn"])
            elif t == "button":
                labels.append(step["text"])
            elif t == "protocol":
                labels.append("Сформировать протокол")
        # Дополняем до 5 если меньше, обрезаем если больше
        while len(labels) < 5:
            labels.append(f"Шаг {len(labels)+1}")
        return labels[:5]

    _STYLE_WAITING  = "QPushButton { background: #2980b9; color: white; font-weight: bold; min-height: 36px; }"
    _STYLE_DONE     = "QPushButton { background: #27ae60; color: white; font-weight: bold; min-height: 36px; }"
    _STYLE_ALARM    = "QPushButton { background: #c0392b; color: white; font-weight: bold; min-height: 36px; }"
    _STYLE_INACTIVE = "QPushButton { min-height: 36px; }"

    def on_alarm(self):
        """Вызывается при аварии — прерывает нужный шаг и красит красным."""
        if self._wizard is not None:
            return  # в режиме мастера авария обрабатывается иначе
        if not self._executing or not self._running:
            return
        step = self._current_step
        if step in self._alarm_interrupts:
            self._step_timer.stop()
            self._executing = False
            self._alarm_steps.add(step)
            self._update_buttons()

    def _toggle_start(self):
        if self._wizard is not None:
            return  # в режиме мастера кнопка скрыта
        self._running = not self._running
        self._executing = False
        self._completed = False
        self._alarm_steps.clear()
        self._step_timer.stop()
        if self._running:
            self._btn_start.setText("⏹ Сбросить испытание")
            self._current_step = 0
        else:
            self._btn_start.setText("▶ Начать испытание")
        self.started.emit(self._running)
        self._update_buttons()

    def _update_buttons(self):
        for i, (btn, bar) in enumerate(zip(self._step_buttons, self._step_bars)):
            try:
                btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            bar.stop()

            if i in self._alarm_steps:
                bar.stop()
                btn.setStyleSheet(self._STYLE_ALARM)
                btn.setEnabled(False)
                continue

            if self._completed:
                btn.setStyleSheet(self._STYLE_DONE)
                btn.setEnabled(False)
                continue

            if not self._running:
                btn.setStyleSheet(self._STYLE_INACTIVE)
                btn.setEnabled(False)
            elif i < self._current_step:
                btn.setStyleSheet(self._STYLE_DONE)
                btn.setEnabled(False)
            elif i == self._current_step and not self._executing:
                btn.setStyleSheet(self._STYLE_WAITING)
                btn.setEnabled(True)
                btn.clicked.connect(self._start_step)
                self._scroll.ensureWidgetVisible(btn)
            elif i == self._current_step and self._executing:
                btn.setStyleSheet(self._STYLE_WAITING)
                btn.setEnabled(False)
                bar.start()
                self._scroll.ensureWidgetVisible(btn)
            else:
                btn.setStyleSheet(self._STYLE_INACTIVE)
                btn.setEnabled(False)

    def _start_step(self):
        """Пользователь нажал кнопку шага — запускаем выполнение."""
        self._executing = True
        self._update_buttons()
        if self._current_step in self._alarm_interrupts:
            self._step_timer.start(10_000)
        else:
            self._on_step_timeout()

    def _on_step_timeout(self):
        """10 сек истекло — шаг выполнен, переходим к следующему или завершаем."""
        self._executing = False
        if self._current_step < len(self._step_buttons) - 1:
            self._current_step += 1
            self._update_buttons()
        else:
            # Последний шаг — все зелёные, параметры разблокированы
            self._current_step = len(self._step_buttons)
            self._running = False
            self._completed = True
            self._update_buttons()
            self._btn_start.setText("▶ Начать испытание")
            self.started.emit(False)


def _make_section3() -> Section3Widget:
    return Section3Widget()
