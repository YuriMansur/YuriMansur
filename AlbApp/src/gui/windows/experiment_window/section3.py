from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QLineEdit, QMessageBox,
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
        # данные, введённые на шаге «Установка образца» — сохраняются между перерисовками
        self._setup_values = {"load": "", "disp": "", "force": "", "cycles": ""}
        self._fixture_used = None  # выбор «использовалось ли спец. приспособление» (шаг 1)
        # данные шага «Параметры испытания» (комбинация + длины сегментов)
        self._param_values  = {"combo": "", "seg1": "", "seg2": "", "seg3": ""}
        self._param_fixture = None  # «использовалось ли спец. приспособление» (шаг 2)
        # первоначальные смещения на нагрузочных рычагах (шаг 3)
        self._disp_values   = {"lower": "", "upper": ""}
        self._disp_fixture  = None  # «использовалось ли спец. приспособление» (шаг 3)
        self._adj_fixture   = None  # «использовалось ли спец. приспособление» (шаг 5)
        self._adj_disp      = {"lower": "", "upper": ""}  # окончательные смещения (шаг 5)
        self._arm_values    = {"d11": "", "lower": "", "upper": ""}  # δ11 и плечи рычагов (шаг 6)
        # δ13, смещения и действительные плечи рычагов при Fcmax (шаг 7)
        self._fcmax_values  = {"d13": "", "disp_lower": "", "disp_upper": "",
                               "arm_lower": "", "arm_upper": ""}
        # разрушение образца при Fcmin (шаг 8): None — выбор не сделан
        self._fracture      = None
        self._fcmin_values  = {"force": "", "time": "", "inspect": ""}
        # стабильные условия цикла (шаг 9): None — выбор не сделан
        self._stable        = None
        self._cyclic_values = {"freq": "", "cycles": ""}
        self._onecycle_values = {"d13": ""}  # регистрация δ13 в одном цикле (шаг 10)
        # счёт циклов (шаг 11): флаг останова + «достигнуто число циклов?» (None — выбор не сделан)
        self._stopped11     = False
        self._reached11     = None
        self._cycles11_values = {"freq": "", "ncycles": "1·10⁶", "nreplace": "", "nreg": "",
                                 "reason": "", "duration": "", "inspect": ""}
        # решение о продолжении испытания (под-шаг ветки «Нет»): None — не выбрано
        self._continue11    = None
        self._jump_target   = None  # индекс шага, на который указывает стрелка «→»
        # ветка «Да» шага 11 — два под-шага (Fcmin / Fcmax): δ, смещения, плечи рычагов
        self._yes_fcmin = {"d": "", "disp_lower": "", "disp_upper": "", "arm_lower": "", "arm_upper": ""}
        self._yes_fcmax = {"d": "", "disp_lower": "", "disp_upper": "", "arm_lower": "", "arm_upper": "", "parts": ""}
        # решение о продолжении испытания во 2-м под-шаге (Fcmax): None — не выбрано
        self._continue_yes = None
        self._yes_dest     = None  # выбранный шаг продолжения (индекс): 9 / 4 / 1
        # шаг 12: разрушение образца, и в ветке «Да» — частота < 3 Гц (None — не выбрано)
        self._frac12        = None
        self._freq12        = None
        self._step12_values = {"ffin": "1750", "v": "от 100 до 250", "t": "30 ± 3", "inspect": ""}
        # шаг 13: выдержал ли образец испытание (влияет на надпись в протоколе)
        self._passed13      = None
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
        self._content = QVBoxLayout(self._panel)
        self._content.setContentsMargins(16, 14, 16, 14)
        self._content.setSpacing(10)
        body.addWidget(self._panel, 1)
        root.addLayout(body, 1)

        self._refresh_sidebar()
        self._render_step(self._current)

    # ── формирование шагов ─────────────────────────────────────────────────
    def _build_steps(self):
        if self._method == "17.4.5" and self._gost in ("Р ИСО 10328-2021", "Р53868-2021"):
            self._htitle = "Циклическое испытание замков коленных узлов"
            self._steps = [
                {"group": "ПОДГОТОВКА", "title": "Установка образца",                "sub": "Оборудование / приспособление",            "kind": "setup"},
                {"group": "ПОДГОТОВКА", "title": "Комбинация и значения установленных длин сегментов", "sub": "F=0, длины сегментов", "kind": "params"},
                {"group": "ПОДГОТОВКА", "title": "Смещения на нагрузочных рычагах",   "sub": "F=0, нижний и верхний рычаги",              "kind": "disp"},
                {"group": "НАГРУЖЕНИЕ", "title": "Стабилизирующая нагрузка",          "sub": "Fstab = 800 Н, 20 с, F=0 12 мин",           "kind": "stab", "decision": False, "banner": False},
                {"group": "НАГРУЖЕНИЕ", "title": "Регулировки",                       "sub": "Fstab = 50 Н, приспособление",              "kind": "adjust"},
                {"group": "НАГРУЖЕНИЕ", "title": "Действительные плечи рычагов",       "sub": "Fstab = 50 Н, δ11, плечи рычагов",          "kind": "arms"},
                {"group": "НАГРУЖЕНИЕ", "title": "Fcmax",                             "sub": "Fcmax, регистрация δ13",                    "kind": "fcmax"},
                {"group": "НАГРУЖЕНИЕ", "title": "Fcmin",                             "sub": "Fcmin, контроль разрушения образца",        "kind": "fcmin"},
                {"group": "ЦИКЛИЧЕСКОЕ НАГРУЖЕНИЕ", "title": "Циклическое нагружение F-c(t)",     "sub": "F-c(t), частота, стабильные условия",        "kind": "cyclic"},
                {"group": "ЦИКЛИЧЕСКОЕ НАГРУЖЕНИЕ", "title": "Один цикл",                        "sub": "Fcmax, δ13, Fcmin",                         "kind": "onecycle"},
                {"group": "ЦИКЛИЧЕСКОЕ НАГРУЖЕНИЕ", "title": "Циклическое нагружение — счёт циклов", "sub": "F-c(t), число циклов, останов",          "kind": "cycles11"},
                {"group": "ЦИКЛИЧЕСКОЕ НАГРУЖЕНИЕ", "title": "Разрушение образца",                "sub": "Разрушение, частота, нагружение",           "kind": "fracture12"},
                {"group": "ЦИКЛИЧЕСКОЕ НАГРУЖЕНИЕ", "title": "Образец выдержал испытание",        "sub": "Оценка результата испытания",               "kind": "passed13"},
                {"group": "ЗАВЕРШЕНИЕ", "title": "Протокол",                         "sub": "Экспорт результатов",                       "kind": "protocol"},
            ]
            self._current = 0
        else:
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
        """Кнопка «Прервать» — диалог подтверждения, при согласии сброс к началу."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Прерывание испытания")
        box.setText("Прервать испытание?")
        box.setInformativeText("Текущий прогресс будет сброшен к первому шагу.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.button(QMessageBox.StandardButton.Yes).setText("Да, прервать")
        box.button(QMessageBox.StandardButton.No).setText("Отмена")
        if box.exec() == QMessageBox.StandardButton.Yes:
            self._abort_test()

    def _abort_test(self):
        """Сброс прогресса визарда к первому шагу после прерывания."""
        self._fracture = None
        self._stable = None
        self._reached11 = None
        self._continue11 = None
        self._continue_yes = None
        self._yes_dest = None
        self._frac12 = None
        self._freq12 = None
        self._passed13 = None
        self._set_cycles11_substeps()   # убрать вложенные под-шаги шага 11
        self._set_step12_substeps()     # убрать вложенный под-шаг шага 12
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
            badge_text += "  •  просмотр (без перехода)"
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f"background: {_WZ['card_bg']}; color: {_WZ['accent']};"
            f" border: 1px solid {_WZ['accent']}; border-radius: 11px;"
            " padding: 3px 12px; font-size: 11px; font-weight: bold;")
        badge_row = QHBoxLayout()
        badge_row.addWidget(badge, 0)
        badge_row.addStretch()
        self._content.addLayout(badge_row)

        if step["kind"] == "stab":
            self._render_stabilization(step.get("decision", True), step.get("banner", True), step.get("inputs", True))
        elif step["kind"] == "setup":
            self._render_setup()
        elif step["kind"] == "params":
            self._render_params()
        elif step["kind"] == "disp":
            self._render_displacements()
        elif step["kind"] == "adjust":
            self._render_adjust()
        elif step["kind"] == "arms":
            self._render_arms()
        elif step["kind"] == "fcmax":
            self._render_fcmax()
        elif step["kind"] == "fcmin":
            self._render_fcmin()
        elif step["kind"] == "cyclic":
            self._render_cyclic()
        elif step["kind"] == "onecycle":
            self._render_onecycle()
        elif step["kind"] == "cycles11":
            self._render_cycles11()
        elif step["kind"] == "shutdown":
            self._render_shutdown()
        elif step["kind"] == "yes_fcmin":
            self._render_fc_delta("Fcmin", "Приложить Fcmin", self._yes_fcmin)
        elif step["kind"] == "yes_fcmax":
            self._render_fc_delta("Fcmax", "Приложить Fcmax", self._yes_fcmax, decision=True)
        elif step["kind"] == "fracture12":
            self._render_fracture12()
        elif step["kind"] == "finload":
            self._render_finload()
        elif step["kind"] == "passed13":
            self._render_passed13()
        elif step["kind"] == "protocol":
            self._render_protocol()
        else:
            self._render_action(step, idx)

    # ── панель навигации шага: в режиме просмотра — только возврат ──────────
    def _step_nav(self, primary_text: str, finish: bool = False) -> QHBoxLayout:
        nav = QHBoxLayout()
        if self._previewing:
            nav.addStretch()
            ret = self._btn("← Вернуться к текущему шагу", primary=True)
            ret.clicked.connect(lambda: self._render_step(self._current))
            nav.addWidget(ret, 0)
            return nav
        nav.addStretch()
        primary = self._btn("✓ Завершить" if finish else primary_text, primary=True)
        if finish:
            primary.clicked.connect(lambda: self._goto(0))
        else:
            primary.clicked.connect(lambda: self._goto(self._current + 1))
        nav.addWidget(primary, 0)
        return nav

    # ── контент первого шага «Установка образца» ───────────────────────────
    def _render_setup(self):
        c = self._content
        h = QLabel("Установка образца")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        banner = QLabel(
            "Зарегистрировать уровень нагрузки, значения смещений"
            " и испытательных сил, числа циклов")
        banner.setWordWrap(True)
        banner.setStyleSheet(
            f"background: {_WZ['card_bg']}; color: {_WZ['text']};"
            f" border-left: 3px solid {_WZ['blue']}; border-radius: 4px; padding: 8px 12px;")
        c.addWidget(banner)

        vals = self._setup_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addLayout(self._input("Уровень нагрузки (Н)",     vals["load"],   _store("load")),   1)
        row1.addLayout(self._input("Значения смещений (мм)",   vals["disp"],   _store("disp")),   1)
        c.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addLayout(self._input("Испытательные силы (Н)",   vals["force"],  _store("force")),  1)
        row2.addLayout(self._input("Число циклов",             vals["cycles"], _store("cycles")), 1)
        c.addLayout(row2)

        lbl = QLabel("Использовалось специальное приспособление?")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(lbl)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self._btn_fixture_yes = self._toggle_btn("✓ Да")
        self._btn_fixture_no  = self._toggle_btn("✕ Нет")
        self._btn_fixture_yes.clicked.connect(lambda: self._set_fixture(True))
        self._btn_fixture_no.clicked.connect(lambda: self._set_fixture(False))
        # пройденный (не текущий) шаг открыт только для просмотра — выбор менять нельзя
        self._btn_fixture_yes.setEnabled(not self._previewing)
        self._btn_fixture_no.setEnabled(not self._previewing)
        toggle.addWidget(self._btn_fixture_yes, 1)
        toggle.addWidget(self._btn_fixture_no, 1)
        c.addLayout(toggle)
        self._set_fixture(self._fixture_used)

        c.addStretch()
        c.addLayout(self._step_nav("Далее →"))

    # ── контент второго шага «Параметры испытания» ─────────────────────────
    def _render_params(self):
        c = self._content
        h = QLabel("Комбинация и значения установленных длин сегментов")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        # F=0 — обнуление нагрузки перед установкой длин сегментов
        f0_row = QHBoxLayout()
        btn_f0 = self._btn("Установить F = 0")
        btn_f0.setEnabled(not self._previewing)
        f0_row.addWidget(btn_f0, 0)
        f0_row.addStretch()
        c.addLayout(f0_row)

        # инструкция (просто текст)
        instr = QLabel("Установить длины сегментов образца")
        instr.setWordWrap(True)
        instr.setStyleSheet(f"color: {_WZ['text']}; font-weight: bold; background: transparent; padding-top: 4px;")
        c.addWidget(instr)

        # регистрация комбинации и значений длин сегментов (поля для просмотра и записи)
        reg = QLabel("Зарегистрировать комбинацию и значения установленных длин сегментов")
        reg.setWordWrap(True)
        reg.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(reg)

        vals = self._param_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addLayout(self._input("Комбинация", vals["combo"], _store("combo")), 1)
        c.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addLayout(self._input("Длина сегмента 1 (мм)", vals["seg1"], _store("seg1")), 1)
        row2.addLayout(self._input("Длина сегмента 2 (мм)", vals["seg2"], _store("seg2")), 1)
        row2.addLayout(self._input("Длина сегмента 3 (мм)", vals["seg3"], _store("seg3")), 1)
        c.addLayout(row2)

        lbl = QLabel("Использовалось специальное приспособление?")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(lbl)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self._btn_pfix_yes = self._toggle_btn("✓ Да")
        self._btn_pfix_no  = self._toggle_btn("✕ Нет")
        self._btn_pfix_yes.clicked.connect(lambda: self._set_param_fixture(True))
        self._btn_pfix_no.clicked.connect(lambda: self._set_param_fixture(False))
        # пройденный (не текущий) шаг открыт только для просмотра — выбор менять нельзя
        self._btn_pfix_yes.setEnabled(not self._previewing)
        self._btn_pfix_no.setEnabled(not self._previewing)
        toggle.addWidget(self._btn_pfix_yes, 1)
        toggle.addWidget(self._btn_pfix_no, 1)
        c.addLayout(toggle)
        self._set_param_fixture(self._param_fixture)

        c.addStretch()
        c.addLayout(self._step_nav("Далее →"))

    # ── контент третьего шага «Смещения на нагрузочных рычагах» ─────────────
    def _render_displacements(self):
        c = self._content
        h = QLabel("Смещения на нагрузочных рычагах")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        # F=0 — обнуление нагрузки перед установкой смещений
        f0_row = QHBoxLayout()
        btn_f0 = self._btn("Установить F = 0")
        btn_f0.setEnabled(not self._previewing)
        f0_row.addWidget(btn_f0, 0)
        f0_row.addStretch()
        c.addLayout(f0_row)

        # инструкция (просто текст)
        instr = QLabel("Установить смещения на нижнем и верхнем нагрузочных рычагах")
        instr.setWordWrap(True)
        instr.setStyleSheet(f"color: {_WZ['text']}; font-weight: bold; background: transparent; padding-top: 4px;")
        c.addWidget(instr)

        # регистрация первоначальных смещений (поля для просмотра и записи)
        reg = QLabel("Записать первоначальные значения смещений")
        reg.setWordWrap(True)
        reg.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(reg)

        vals = self._disp_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addLayout(self._input("Нижний рычаг (мм)",  vals["lower"], _store("lower")), 1)
        row.addLayout(self._input("Верхний рычаг (мм)", vals["upper"], _store("upper")), 1)
        c.addLayout(row)

        lbl = QLabel("Использовалось специальное приспособление?")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(lbl)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self._btn_dfix_yes = self._toggle_btn("✓ Да")
        self._btn_dfix_no  = self._toggle_btn("✕ Нет")
        self._btn_dfix_yes.clicked.connect(lambda: self._set_disp_fixture(True))
        self._btn_dfix_no.clicked.connect(lambda: self._set_disp_fixture(False))
        # пройденный (не текущий) шаг открыт только для просмотра — выбор менять нельзя
        self._btn_dfix_yes.setEnabled(not self._previewing)
        self._btn_dfix_no.setEnabled(not self._previewing)
        toggle.addWidget(self._btn_dfix_yes, 1)
        toggle.addWidget(self._btn_dfix_no, 1)
        c.addLayout(toggle)
        self._set_disp_fixture(self._disp_fixture)

        c.addStretch()
        c.addLayout(self._step_nav("Далее →"))

    # ── контент пятого шага «Регулировки» ──────────────────────────────────
    def _render_adjust(self):
        c = self._content
        h = QLabel("Регулировки")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        # Fstab = 50 Н — приложить нагрузку для регулировок
        f_row = QHBoxLayout()
        btn_f = self._btn("Fstab = 50 Н")
        btn_f.setEnabled(not self._previewing)
        f_row.addWidget(btn_f, 0)
        f_row.addStretch()
        c.addLayout(f_row)

        # инструкция (просто текст)
        instr = QLabel("Выполнить регулировки")
        instr.setWordWrap(True)
        instr.setStyleSheet(f"color: {_WZ['text']}; font-weight: bold; background: transparent; padding-top: 4px;")
        c.addWidget(instr)

        # регистрация окончательных смещений (поля для просмотра и записи)
        reg = QLabel("Записать окончательные значения смещений")
        reg.setWordWrap(True)
        reg.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(reg)

        vals = self._adj_disp

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addLayout(self._input("Нижний рычаг (мм)",  vals["lower"], _store("lower")), 1)
        row.addLayout(self._input("Верхний рычаг (мм)", vals["upper"], _store("upper")), 1)
        c.addLayout(row)

        lbl = QLabel("Использовалось специальное приспособление?")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(lbl)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self._btn_afix_yes = self._toggle_btn("✓ Да")
        self._btn_afix_no  = self._toggle_btn("✕ Нет")
        self._btn_afix_yes.clicked.connect(lambda: self._set_adj_fixture(True))
        self._btn_afix_no.clicked.connect(lambda: self._set_adj_fixture(False))
        # пройденный (не текущий) шаг открыт только для просмотра — выбор менять нельзя
        self._btn_afix_yes.setEnabled(not self._previewing)
        self._btn_afix_no.setEnabled(not self._previewing)
        toggle.addWidget(self._btn_afix_yes, 1)
        toggle.addWidget(self._btn_afix_no, 1)
        c.addLayout(toggle)
        self._set_adj_fixture(self._adj_fixture)

        c.addStretch()
        c.addLayout(self._step_nav("Далее →"))

    # ── контент шестого шага «Действительные плечи рычагов» ────────────────
    def _render_arms(self):
        c = self._content
        h = QLabel("Действительные плечи рычагов")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        # Fstab = 50 Н — приложить нагрузку
        f_row = QHBoxLayout()
        btn_f = self._btn("Fstab = 50 Н")
        btn_f.setEnabled(not self._previewing)
        f_row.addWidget(btn_f, 0)
        f_row.addStretch()
        c.addLayout(f_row)

        vals = self._arm_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        # регистрация δ11 (поле для просмотра и записи)
        reg_d11 = QLabel("Регистрация δ11")
        reg_d11.setWordWrap(True)
        reg_d11.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(reg_d11)

        d11_row = QHBoxLayout()
        d11_row.setSpacing(8)
        d11_row.addLayout(self._input("δ11 (мм)", vals["d11"], _store("d11")), 1)
        c.addLayout(d11_row)

        # измерить и записать действительные плечи рычагов (поля для просмотра и записи)
        reg = QLabel("Измерить и записать действительные плечи рычагов")
        reg.setWordWrap(True)
        reg.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(reg)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addLayout(self._input("Нижний рычаг (мм)",  vals["lower"], _store("lower")), 1)
        row.addLayout(self._input("Верхний рычаг (мм)", vals["upper"], _store("upper")), 1)
        c.addLayout(row)

        c.addStretch()
        c.addLayout(self._step_nav("Далее →"))

    # ── контент седьмого шага «Fcmax» ──────────────────────────────────────
    def _render_fcmax(self):
        c = self._content
        h = QLabel("Fcmax")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        # приложить максимальную нагрузку цикла Fcmax
        f_row = QHBoxLayout()
        btn_f = self._btn("Приложить Fcmax")
        btn_f.setEnabled(not self._previewing)
        f_row.addWidget(btn_f, 0)
        f_row.addStretch()
        c.addLayout(f_row)

        vals = self._fcmax_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        # регистрация δ13 (поле для просмотра и записи)
        reg = QLabel("Регистрация δ13")
        reg.setWordWrap(True)
        reg.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(reg)

        d13_row = QHBoxLayout()
        d13_row.setSpacing(8)
        d13_row.addLayout(self._input("δ13 (мм)", vals["d13"], _store("d13")), 1)
        c.addLayout(d13_row)

        # измерить и записать смещения (поля для просмотра и записи) шаг 7
        reg_disp = QLabel("Измерить и записать смещения")
        reg_disp.setWordWrap(True)
        reg_disp.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(reg_disp)

        disp_row = QHBoxLayout()
        disp_row.setSpacing(8)
        disp_row.addLayout(self._input("Нижний рычаг (мм)",  vals["disp_lower"], _store("disp_lower")), 1)
        disp_row.addLayout(self._input("Верхний рычаг (мм)", vals["disp_upper"], _store("disp_upper")), 1)
        c.addLayout(disp_row)

        # действительные плечи рычагов (поля для просмотра и записи)
        reg_arm = QLabel("Действительные плечи рычагов")
        reg_arm.setWordWrap(True)
        reg_arm.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(reg_arm)

        arm_row = QHBoxLayout()
        arm_row.setSpacing(8)
        arm_row.addLayout(self._input("Нижний рычаг (мм)",  vals["arm_lower"], _store("arm_lower")), 1)
        arm_row.addLayout(self._input("Верхний рычаг (мм)", vals["arm_upper"], _store("arm_upper")), 1)
        c.addLayout(arm_row)

        c.addStretch()
        c.addLayout(self._step_nav("Далее →"))

    # ── контент восьмого шага «Fcmin» (с ветвлением по разрушению) ─────────
    def _render_fcmin(self):
        c = self._content
        h = QLabel("Fcmin")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        # приложить минимальную нагрузку цикла Fcmin
        f_row = QHBoxLayout()
        btn_f = self._btn("Приложить Fcmin")
        btn_f.setEnabled(not self._previewing)
        f_row.addWidget(btn_f, 0)
        f_row.addStretch()
        c.addLayout(f_row)

        # ── разрушение образца? ───────────────────────────────────────────
        q = QLabel("Разрушение образца?")
        q.setWordWrap(True)
        q.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(q)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self._btn_frac_yes = self._toggle_btn("✓ Да")
        self._btn_frac_no  = self._toggle_btn("✕ Нет")
        self._btn_frac_yes.clicked.connect(lambda: self._choose_fracture(True))
        self._btn_frac_no.clicked.connect(lambda: self._choose_fracture(False))
        self._btn_frac_yes.setEnabled(not self._previewing)
        self._btn_frac_no.setEnabled(not self._previewing)
        toggle.addWidget(self._btn_frac_yes, 1)
        toggle.addWidget(self._btn_frac_no, 1)
        c.addLayout(toggle)
        self._style_toggle_pair(self._btn_frac_yes, self._btn_frac_no, self._fracture)

        # ── при «Да» — динамически открываем поля разрушения ──────────────
        if self._fracture is True:
            vals = self._fcmin_values

            def _store(key):
                return lambda text: vals.__setitem__(key, text)

            reg = QLabel("Регистрация F и t при разрушении")
            reg.setWordWrap(True)
            reg.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
            c.addWidget(reg)

            ft_row = QHBoxLayout()
            ft_row.setSpacing(8)
            ft_row.addLayout(self._input("F при разрушении (Н)", vals["force"], _store("force")), 1)
            ft_row.addLayout(self._input("t при разрушении (с)", vals["time"],  _store("time")),  1)
            c.addLayout(ft_row)

            ins = QLabel("Осмотр образца с указанием характера и места повреждения")
            ins.setWordWrap(True)
            ins.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
            c.addWidget(ins)

            ins_row = QHBoxLayout()
            ins_row.setSpacing(8)
            ins_row.addLayout(self._input("Характер и место повреждения", vals["inspect"], _store("inspect")), 1)
            c.addLayout(ins_row)

        c.addStretch()
        if self._previewing:
            c.addLayout(self._step_nav("Далее →"))
        elif self._fracture is True:
            # разрушение → испытание завершено, переход к протоколу
            nav = QHBoxLayout()
            nav.addStretch()
            btn = self._btn("📄 Сформировать протокол", primary=True)
            btn.clicked.connect(self._goto_protocol_interrupted)
            nav.addWidget(btn, 0)
            c.addLayout(nav)
        elif self._fracture is False:
            # образец цел → разрешаем переход на следующий шаг
            c.addLayout(self._step_nav("Далее →"))
        # выбор не сделан (None) — переход закрыт

    # ── контент девятого шага «Циклическое нагружение F-c(t)» ──────────────
    def _render_cyclic(self):
        c = self._content
        h = QLabel("Циклическое нагружение F-c(t)")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        # запустить циклическое нагружение F-c(t)
        f_row = QHBoxLayout()
        btn_f = self._btn("Запустить F-c(t)")
        btn_f.setEnabled(not self._previewing)
        f_row.addWidget(btn_f, 0)
        f_row.addStretch()
        c.addLayout(f_row)

        vals = self._cyclic_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        freq_row = QHBoxLayout()
        freq_row.setSpacing(8)
        freq_row.addLayout(self._input("Частота (Гц)", vals["freq"], _store("freq")), 1)
        c.addLayout(freq_row)

        # ── достигнуты стабильные условия? ────────────────────────────────
        q = QLabel("Достигнуты стабильные условия?")
        q.setWordWrap(True)
        q.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(q)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self._btn_stbl_yes = self._toggle_btn("✓ Да")
        self._btn_stbl_no  = self._toggle_btn("✕ Нет")
        self._btn_stbl_yes.clicked.connect(lambda: self._choose_stable(True))
        self._btn_stbl_no.clicked.connect(lambda: self._choose_stable(False))
        self._btn_stbl_yes.setEnabled(not self._previewing)
        self._btn_stbl_no.setEnabled(not self._previewing)
        toggle.addWidget(self._btn_stbl_yes, 1)
        toggle.addWidget(self._btn_stbl_no, 1)
        c.addLayout(toggle)
        self._style_toggle_pair(self._btn_stbl_yes, self._btn_stbl_no, self._stable)

        # ── при «Да» — остановка оборудования и регистрация числа циклов ──
        if self._stable is True:
            stop = QLabel("Остановка оборудования")
            stop.setWordWrap(True)
            stop.setStyleSheet(f"color: {_WZ['text']}; font-weight: bold; background: transparent; padding-top: 4px;")
            c.addWidget(stop)

            reg = QLabel("Регистрация числа циклов для достижения стабильных условий")
            reg.setWordWrap(True)
            reg.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
            c.addWidget(reg)

            cyc_row = QHBoxLayout()
            cyc_row.setSpacing(8)
            cyc_row.addLayout(self._input("Число циклов", vals["cycles"], _store("cycles")), 1)
            c.addLayout(cyc_row)

        c.addStretch()
        if self._previewing or self._stable is True:
            # условия достигнуты → переход на следующий шаг
            c.addLayout(self._step_nav("Далее →"))
        elif self._stable is False:
            # условия не достигнуты → повторяем цикл
            rep = QLabel("🔁  Стабильные условия не достигнуты — повторить цикл нагружения")
            rep.setWordWrap(True)
            rep.setStyleSheet(
                f"background: {_WZ['card_bg']}; color: {_WZ['text']};"
                f" border-left: 3px solid {_WZ['amber']}; border-radius: 4px; padding: 8px 12px;")
            c.addWidget(rep)
            nav = QHBoxLayout()
            nav.addStretch()
            btn = self._btn("🔁 Повторить цикл", primary=True)
            btn.clicked.connect(self._repeat_cycle)
            nav.addWidget(btn, 0)
            c.addLayout(nav)
        # выбор не сделан (None) — переход закрыт

    # ── контент десятого шага «Один цикл» ──────────────────────────────────
    def _render_onecycle(self):
        c = self._content
        h = QLabel("Один цикл")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        # Fcmax
        fmax_row = QHBoxLayout()
        btn_fmax = self._btn("Приложить Fcmax")
        btn_fmax.setEnabled(not self._previewing)
        fmax_row.addWidget(btn_fmax, 0)
        fmax_row.addStretch()
        c.addLayout(fmax_row)

        vals = self._onecycle_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        # регистрация δ13 (поле для просмотра и записи)
        reg = QLabel("Регистрация δ13")
        reg.setWordWrap(True)
        reg.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(reg)

        d13_row = QHBoxLayout()
        d13_row.setSpacing(8)
        d13_row.addLayout(self._input("δ13 (мм)", vals["d13"], _store("d13")), 1)
        c.addLayout(d13_row)

        # Fcmin
        fmin_row = QHBoxLayout()
        btn_fmin = self._btn("Приложить Fcmin")
        btn_fmin.setEnabled(not self._previewing)
        fmin_row.addWidget(btn_fmin, 0)
        fmin_row.addStretch()
        c.addLayout(fmin_row)

        c.addStretch()
        c.addLayout(self._step_nav("Далее →"))

    # ── контент одиннадцатого шага «Счёт циклов» (с ветвлением) ────────────
    def _render_cycles11(self):
        c = self._content
        h = QLabel("Циклическое нагружение — счёт циклов")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        # запустить циклическое нагружение F-c(t)
        f_row = QHBoxLayout()
        btn_f = self._btn("Запустить F-c(t)")
        btn_f.setEnabled(not self._previewing)
        f_row.addWidget(btn_f, 0)
        f_row.addStretch()
        c.addLayout(f_row)

        vals = self._cycles11_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        # частота + число циклов
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addLayout(self._input("Частота (Гц)", vals["freq"], _store("freq")), 1)
        row1.addLayout(self._input("Число циклов", vals["ncycles"], _store("ncycles")), 1)
        c.addLayout(row1)

        # число циклов до замены деталей
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addLayout(self._input("Число циклов до замены деталей", vals["nreplace"], _store("nreplace")), 1)
        c.addLayout(row2)

        # ── остановка оборудования: флаг + кнопка → регистрация числа циклов ──
        stop_row = QHBoxLayout()
        stop_row.setSpacing(8)
        btn_stop = self._toggle_btn("⏹ Остановка оборудования")
        btn_stop.setChecked(self._stopped11)
        btn_stop.clicked.connect(self._toggle_stop11)
        btn_stop.setEnabled(not self._previewing)
        if self._stopped11:
            btn_stop.setStyleSheet(
                f"QPushButton {{ background: {_WZ['blue']}; color: white; border: none;"
                " border-radius: 6px; padding: 6px 14px; font-weight: bold; }")
        else:
            btn_stop.setStyleSheet(
                f"QPushButton {{ background: {_WZ['btn_bg']}; color: {_WZ['text']};"
                f" border: 1px solid {_WZ['border']}; border-radius: 6px; padding: 6px 12px; }}"
                f" QPushButton:hover {{ background: {_WZ['card_bg']}; }}")
        stop_row.addWidget(btn_stop, 0)
        stop_row.addStretch()
        c.addLayout(stop_row)

        if self._stopped11:
            reg = QLabel("Регистрация числа циклов")
            reg.setWordWrap(True)
            reg.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
            c.addWidget(reg)
            nreg_row = QHBoxLayout()
            nreg_row.setSpacing(8)
            nreg_row.addLayout(self._input("Число циклов (зарегистрировано)", vals["nreg"], _store("nreg")), 1)
            c.addLayout(nreg_row)

        # ── достигнуто число циклов? ──────────────────────────────────────
        q = QLabel("Достигнуто число циклов?")
        q.setWordWrap(True)
        q.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(q)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self._btn_rch_yes = self._toggle_btn("✓ Да")
        self._btn_rch_no  = self._toggle_btn("✕ Нет")
        self._btn_rch_yes.clicked.connect(lambda: self._choose_reached11(True))
        self._btn_rch_no.clicked.connect(lambda: self._choose_reached11(False))
        self._btn_rch_yes.setEnabled(not self._previewing)
        self._btn_rch_no.setEnabled(not self._previewing)
        toggle.addWidget(self._btn_rch_yes, 1)
        toggle.addWidget(self._btn_rch_no, 1)
        c.addLayout(toggle)
        self._style_toggle_pair(self._btn_rch_yes, self._btn_rch_no, self._reached11)

        c.addStretch()
        # выбор сделан (Да или Нет) → ниже в степпере появился вложенный под-шаг,
        # «Далее» ведёт в него
        if self._previewing or self._reached11 is not None:
            c.addLayout(self._step_nav("Далее →"))

    # ── вложенный под-шаг ветки «Нет»: регистрация отключения ──────────────
    def _render_shutdown(self):
        c = self._content
        h = QLabel("Регистрация отключения")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        vals = self._cycles11_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        reason = QLabel("Регистрация причины отключения")
        reason.setWordWrap(True)
        reason.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(reason)
        rr = QHBoxLayout()
        rr.setSpacing(8)
        rr.addLayout(self._input("Причина отключения", vals["reason"], _store("reason")), 1)
        c.addLayout(rr)

        dur = QLabel("Регистрация продолжительности отключения (дата, время)")
        dur.setWordWrap(True)
        dur.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(dur)
        dr = QHBoxLayout()
        dr.setSpacing(8)
        dr.addLayout(self._input("Продолжительность отключения (дата, время)", vals["duration"], _store("duration")), 1)
        c.addLayout(dr)

        ins = QLabel("Регистрация осмотра образца")
        ins.setWordWrap(True)
        ins.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(ins)
        ir = QHBoxLayout()
        ir.setSpacing(8)
        ir.addLayout(self._input("Осмотр образца", vals["inspect"], _store("inspect")), 1)
        c.addLayout(ir)

        # ── решение о продолжении испытания ───────────────────────────────
        dec = QLabel("Решение о продолжении испытания")
        dec.setWordWrap(True)
        dec.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(dec)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self._btn_cont_yes = self._toggle_btn("✓ Продолжить")
        self._btn_cont_no  = self._toggle_btn("✕ Не продолжать")
        self._btn_cont_yes.clicked.connect(lambda: self._choose_continue(True))
        self._btn_cont_no.clicked.connect(lambda: self._choose_continue(False))
        self._btn_cont_yes.setEnabled(not self._previewing)
        self._btn_cont_no.setEnabled(not self._previewing)
        toggle.addWidget(self._btn_cont_yes, 1)
        toggle.addWidget(self._btn_cont_no, 1)
        c.addLayout(toggle)
        self._style_toggle_pair(self._btn_cont_yes, self._btn_cont_no, self._continue11)

        c.addStretch()
        if self._previewing:
            c.addLayout(self._step_nav("Далее →"))
        elif self._continue11 is True:
            # продолжить → стрелка на шаг 9 (циклическое F-c(t)) и переход туда
            target = next(i for i, s in enumerate(self._steps) if s.get("kind") == "cyclic")
            self._jump_target = target
            self._refresh_sidebar()
            nav = QHBoxLayout()
            nav.addStretch()
            btn = self._btn("Далее →", primary=True)
            # _checked поглощает bool из сигнала clicked, чтобы он не подменил target
            btn.clicked.connect(lambda _checked=False, t=target: self._goto(t))
            nav.addWidget(btn, 0)
            c.addLayout(nav)
        elif self._continue11 is False:
            # не продолжать → без стрелки, обычный переход на следующий шаг
            self._jump_target = None
            self._refresh_sidebar()
            c.addLayout(self._step_nav("Далее →"))
        # выбор не сделан (None) — переход закрыт

    # ── вложенные под-шаги ветки «Да»: Fcmin / Fcmax (δ, смещения, плечи) ──
    def _render_fc_delta(self, title: str, btn_label: str, vals: dict, decision: bool = False):
        c = self._content
        h = QLabel(title)
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        # приложить нагрузку (Fcmin / Fcmax)
        f_row = QHBoxLayout()
        btn_f = self._btn(btn_label)
        btn_f.setEnabled(not self._previewing)
        f_row.addWidget(btn_f, 0)
        f_row.addStretch()
        c.addLayout(f_row)

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        # регистрация δ
        reg_d = QLabel("Регистрация δ")
        reg_d.setWordWrap(True)
        reg_d.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(reg_d)
        d_row = QHBoxLayout()
        d_row.setSpacing(8)
        d_row.addLayout(self._input("δ (мм)", vals["d"], _store("d")), 1)
        c.addLayout(d_row)

        # измерить и записать смещения
        reg_disp = QLabel("Измерить и записать смещения")
        reg_disp.setWordWrap(True)
        reg_disp.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(reg_disp)
        disp_row = QHBoxLayout()
        disp_row.setSpacing(8)
        disp_row.addLayout(self._input("Нижний рычаг (мм)",  vals["disp_lower"], _store("disp_lower")), 1)
        disp_row.addLayout(self._input("Верхний рычаг (мм)", vals["disp_upper"], _store("disp_upper")), 1)
        c.addLayout(disp_row)

        # действительные плечи рычагов
        reg_arm = QLabel("Действительные плечи рычагов")
        reg_arm.setWordWrap(True)
        reg_arm.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(reg_arm)
        arm_row = QHBoxLayout()
        arm_row.setSpacing(8)
        arm_row.addLayout(self._input("Нижний рычаг (мм)",  vals["arm_lower"], _store("arm_lower")), 1)
        arm_row.addLayout(self._input("Верхний рычаг (мм)", vals["arm_upper"], _store("arm_upper")), 1)
        c.addLayout(arm_row)

        if not decision:
            c.addStretch()
            c.addLayout(self._step_nav("Далее →"))
            return

        # ── решение о продолжении испытания (только 2-й под-шаг, Fcmax) ────
        dec = QLabel("Решение о продолжении испытания")
        dec.setWordWrap(True)
        dec.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
        c.addWidget(dec)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self._btn_cy_yes = self._toggle_btn("✓ Продолжить")
        self._btn_cy_no  = self._toggle_btn("✕ Не продолжать")
        self._btn_cy_yes.clicked.connect(lambda: self._choose_continue_yes(True))
        self._btn_cy_no.clicked.connect(lambda: self._choose_continue_yes(False))
        self._btn_cy_yes.setEnabled(not self._previewing)
        self._btn_cy_no.setEnabled(not self._previewing)
        toggle.addWidget(self._btn_cy_yes, 1)
        toggle.addWidget(self._btn_cy_no, 1)
        c.addLayout(toggle)
        self._style_toggle_pair(self._btn_cy_yes, self._btn_cy_no, self._continue_yes)

        # при «Да» — замена деталей + выбор шага продолжения (3 пути)
        if self._continue_yes is True:
            rep = QLabel("Замена деталей")
            rep.setWordWrap(True)
            rep.setStyleSheet(f"color: {_WZ['text']}; font-weight: bold; background: transparent; padding-top: 4px;")
            c.addWidget(rep)
            pr = QHBoxLayout()
            pr.setSpacing(8)
            pr.addLayout(self._input("Конкретные заменённые детали", vals["parts"], _store("parts")), 1)
            c.addLayout(pr)

            # выбор, с какого шага продолжить испытание
            dlbl = QLabel("Продолжить с шага:")
            dlbl.setWordWrap(True)
            dlbl.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
            c.addWidget(dlbl)

            dests = QHBoxLayout()
            dests.setSpacing(8)
            for caption, idx in (("Шаг 9", self._step_idx("cyclic")),
                                 ("Шаг 4", self._step_idx_step4()),
                                 ("Шаг 1", self._step_idx("setup"))):
                b = self._toggle_btn(caption)
                b.setEnabled(not self._previewing and idx is not None)
                b.clicked.connect(lambda _c=False, t=idx: self._choose_yes_dest(t))
                self._style_one_toggle(b, self._yes_dest == idx)
                dests.addWidget(b, 1)
            c.addLayout(dests)

        c.addStretch()
        if self._previewing:
            c.addLayout(self._step_nav("Далее →"))
        elif self._continue_yes is True and self._yes_dest is not None:
            # продолжить → стрелка на выбранный шаг и переход туда
            self._jump_target = self._yes_dest
            self._refresh_sidebar()
            nav = QHBoxLayout()
            nav.addStretch()
            btn = self._btn("Далее →", primary=True)
            btn.clicked.connect(lambda _checked=False, t=self._yes_dest: self._goto(t))
            nav.addWidget(btn, 0)
            c.addLayout(nav)
        elif self._continue_yes is False:
            # не продолжать → без стрелки, обычный переход на следующий шаг
            self._jump_target = None
            self._refresh_sidebar()
            c.addLayout(self._step_nav("Далее →"))
        else:
            # «Да» без выбранного шага продолжения → переход закрыт, стрелки нет
            self._jump_target = None
            self._refresh_sidebar()

    # ── шаг 12: разрушение образца (с ветвлением) ──────────────────────────
    def _render_fracture12(self):
        c = self._content
        h = QLabel("Разрушение образца")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        vals = self._step12_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        # разрушение образца?
        q = QLabel("Разрушение образца?")
        q.setWordWrap(True)
        q.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(q)

        t1 = QHBoxLayout()
        t1.setSpacing(8)
        self._btn_f12_yes = self._toggle_btn("✓ Да")
        self._btn_f12_no  = self._toggle_btn("✕ Нет")
        self._btn_f12_yes.clicked.connect(lambda: self._choose_frac12(True))
        self._btn_f12_no.clicked.connect(lambda: self._choose_frac12(False))
        self._btn_f12_yes.setEnabled(not self._previewing)
        self._btn_f12_no.setEnabled(not self._previewing)
        t1.addWidget(self._btn_f12_yes, 1)
        t1.addWidget(self._btn_f12_no, 1)
        c.addLayout(t1)
        self._style_toggle_pair(self._btn_f12_yes, self._btn_f12_no, self._frac12)

        # ── ветка «Да» — вопрос про частоту (инлайн) ──────────────────────
        if self._frac12 is True:
            q2 = QLabel("Частота < 3 Гц?")
            q2.setWordWrap(True)
            q2.setStyleSheet(f"color: {_WZ['muted']}; background: transparent; padding-top: 4px;")
            c.addWidget(q2)

            t2 = QHBoxLayout()
            t2.setSpacing(8)
            self._btn_fr_yes = self._toggle_btn("✓ Да")
            self._btn_fr_no  = self._toggle_btn("✕ Нет")
            self._btn_fr_yes.clicked.connect(lambda: self._choose_freq12(True))
            self._btn_fr_no.clicked.connect(lambda: self._choose_freq12(False))
            self._btn_fr_yes.setEnabled(not self._previewing)
            self._btn_fr_no.setEnabled(not self._previewing)
            t2.addWidget(self._btn_fr_yes, 1)
            t2.addWidget(self._btn_fr_no, 1)
            c.addLayout(t2)
            self._style_toggle_pair(self._btn_fr_yes, self._btn_fr_no, self._freq12)

            if self._freq12 is True:
                ins = QLabel("Осмотр образца с указанием характера и места повреждения")
                ins.setWordWrap(True)
                ins.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
                c.addWidget(ins)
                ir = QHBoxLayout()
                ir.setSpacing(8)
                ir.addLayout(self._input("Характер и место повреждения", vals["inspect"], _store("inspect")), 1)
                c.addLayout(ir)
            elif self._freq12 is False:
                note = QLabel("🔁  Повторить испытание нового образца на частоте < 3 Гц")
                note.setWordWrap(True)
                note.setStyleSheet(
                    f"background: {_WZ['card_bg']}; color: {_WZ['text']};"
                    f" border-left: 3px solid {_WZ['amber']}; border-radius: 4px; padding: 8px 12px;")
                c.addWidget(note)

        c.addStretch()
        # ── навигация ─────────────────────────────────────────────────────
        if self._previewing:
            c.addLayout(self._step_nav("Далее →"))
        elif self._frac12 is False:
            # разрушения нет → переход во вложенный под-шаг «Окончательное нагружение»
            self._jump_target = None
            self._refresh_sidebar()
            c.addLayout(self._step_nav("Далее →"))
        elif self._frac12 is True and self._freq12 is True:
            # частота < 3 Гц → осмотр, далее на следующий невложенный шаг
            self._jump_target = None
            self._refresh_sidebar()
            c.addLayout(self._step_nav("Далее →"))
        elif self._frac12 is True and self._freq12 is False:
            # частота не < 3 Гц → повторить на новом образце, стрелка к шагу 1
            target = self._step_idx("setup")
            self._jump_target = target
            self._refresh_sidebar()
            nav = QHBoxLayout()
            nav.addStretch()
            btn = self._btn("Далее →", primary=True)
            btn.clicked.connect(lambda _checked=False, t=target: self._goto(t))
            nav.addWidget(btn, 0)
            c.addLayout(nav)
        else:
            # выбор не завершён → переход закрыт
            self._jump_target = None
            self._refresh_sidebar()

    # ── под-шаг ветки «Нет» шага 12: окончательное нагружение ──────────────
    def _render_finload(self):
        c = self._content
        h = QLabel("Окончательное нагружение")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        vals = self._step12_values

        def _store(key):
            return lambda text: vals.__setitem__(key, text)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addLayout(self._input("Ffin (Н)", vals["ffin"], _store("ffin")), 1)
        row.addLayout(self._input("V (Н/с)", vals["v"], _store("v")), 1)
        row.addLayout(self._input("t (с)", vals["t"], _store("t")), 1)
        c.addLayout(row)

        c.addStretch()
        c.addLayout(self._step_nav("Далее →"))

    # ── шаг 13: образец выдержал испытание? ────────────────────────────────
    def _render_passed13(self):
        c = self._content
        h = QLabel("Образец выдержал испытание")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        q = QLabel("Образец выдержал испытание?")
        q.setWordWrap(True)
        q.setStyleSheet(f"color: {_WZ['muted']}; background: transparent;")
        c.addWidget(q)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self._btn_p13_yes = self._toggle_btn("✓ Да")
        self._btn_p13_no  = self._toggle_btn("✕ Нет")
        self._btn_p13_yes.clicked.connect(lambda: self._choose_passed13(True))
        self._btn_p13_no.clicked.connect(lambda: self._choose_passed13(False))
        self._btn_p13_yes.setEnabled(not self._previewing)
        self._btn_p13_no.setEnabled(not self._previewing)
        toggle.addWidget(self._btn_p13_yes, 1)
        toggle.addWidget(self._btn_p13_no, 1)
        c.addLayout(toggle)
        self._style_toggle_pair(self._btn_p13_yes, self._btn_p13_no, self._passed13)

        c.addStretch()
        self._jump_target = None
        self._refresh_sidebar()
        # и «Да», и «Нет» → переход на следующий шаг (протокол), без стрелки
        if self._previewing or self._passed13 is not None:
            c.addLayout(self._step_nav("Далее →"))

    # ── последний шаг: протокол (с надписью о несоответствии при «Нет») ────
    def _render_protocol(self):
        c = self._content
        h = QLabel("Протокол")
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        if self._passed13 is False:
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
        nav.addStretch()
        btn = self._btn("📄 Генерация протокола", primary=True)
        nav.addWidget(btn, 0)
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
            btn.setStyleSheet(
                f"QPushButton {{ background: {_WZ['blue']}; color: white; border: none;"
                " border-radius: 6px; padding: 6px 14px; font-weight: bold; }")
        else:
            btn.setChecked(False)
            btn.setStyleSheet(
                f"QPushButton {{ background: {_WZ['btn_bg']}; color: {_WZ['text']};"
                f" border: 1px solid {_WZ['border']}; border-radius: 6px; padding: 6px 12px; }}"
                f" QPushButton:hover {{ background: {_WZ['card_bg']}; }}")

    def _style_toggle_pair(self, btn_yes, btn_no, used):
        """Подсветить «Да/Нет» по выбранному значению (общая для шагов 1 и 2)."""
        self._style_one_toggle(btn_yes, used is True)
        self._style_one_toggle(btn_no, used is False)

    def _set_fixture(self, used):
        self._fixture_used = used
        self._style_toggle_pair(self._btn_fixture_yes, self._btn_fixture_no, used)

    def _set_param_fixture(self, used):
        self._param_fixture = used
        self._style_toggle_pair(self._btn_pfix_yes, self._btn_pfix_no, used)

    def _set_disp_fixture(self, used):
        self._disp_fixture = used
        self._style_toggle_pair(self._btn_dfix_yes, self._btn_dfix_no, used)

    def _set_adj_fixture(self, used):
        self._adj_fixture = used
        self._style_toggle_pair(self._btn_afix_yes, self._btn_afix_no, used)

    def _choose_fracture(self, used):
        """Выбор «разрушение образца» — перерисовать шаг (поля появляются/скрываются)."""
        self._fracture = used
        self._render_step(self._current)

    def _choose_stable(self, reached):
        """Выбор «достигнуты стабильные условия» — перерисовать шаг."""
        self._stable = reached
        self._render_step(self._current)

    def _repeat_cycle(self):
        """Стабильные условия не достигнуты — повторяем цикл (сброс выбора)."""
        self._stable = None
        self._render_step(self._current)

    def _toggle_stop11(self):
        """Флаг «Остановка оборудования» (шаг 11) — открывает регистрацию числа циклов."""
        self._stopped11 = not self._stopped11
        self._render_step(self._current)

    def _choose_reached11(self, reached):
        """Выбор «достигнуто число циклов» (шаг 11) — вставить вложенные под-шаги
        в левый степпер и перерисовать."""
        self._reached11 = reached
        self._set_cycles11_substeps()
        self._rebuild_sidebar()
        self._render_step(self._current)

    def _set_cycles11_substeps(self):
        """Сформировать вложенные под-шаги шага 11 по выбору «достигнуто число циклов».
        Под-шаги помечаются parent='cycles11' и indent=True (отступ в степпере)."""
        # убрать прежние под-шаги шага 11
        self._steps = [s for s in self._steps if s.get("parent") != "cycles11"]
        anchor = next((i for i, s in enumerate(self._steps) if s.get("kind") == "cycles11"), None)
        if anchor is None:
            return   # шага cycles11 нет (например, не 17.4.5) — вложенных под-шагов не бывает
        grp = self._steps[anchor]["group"]
        subs = []
        if self._reached11 is False:
            subs = [{"group": grp, "indent": True, "parent": "cycles11", "kind": "shutdown",
                     "title": "Регистрация отключения", "sub": "Причина, продолжительность, осмотр"}]
        elif self._reached11 is True:
            subs = [{"group": grp, "indent": True, "parent": "cycles11", "kind": "yes_fcmin",
                     "title": "Fcmin", "sub": "δ, смещения, плечи рычагов"},
                    {"group": grp, "indent": True, "parent": "cycles11", "kind": "yes_fcmax",
                     "title": "Fcmax", "sub": "δ, смещения, плечи рычагов"}]
        for off, s in enumerate(subs):
            self._steps.insert(anchor + 1 + off, s)

    def _set_step12_substeps(self):
        """Под-шаг шага 12 в ветке «Нет» (разрушения нет) — «Окончательное нагружение»."""
        self._steps = [s for s in self._steps if s.get("parent") != "fracture12"]
        anchor = next((i for i, s in enumerate(self._steps) if s.get("kind") == "fracture12"), None)
        if anchor is None:
            return
        if self._frac12 is False:
            sub = {"group": self._steps[anchor]["group"], "indent": True, "parent": "fracture12",
                   "kind": "finload", "title": "Окончательное нагружение", "sub": "Ffin, V, t"}
            self._steps.insert(anchor + 1, sub)

    def _choose_frac12(self, val):
        """Выбор «разрушение образца» на шаге 12. «Нет» → под-шаг нагружения."""
        self._frac12 = val
        self._freq12 = None
        self._set_step12_substeps()
        self._rebuild_sidebar()
        self._render_step(self._current)

    def _choose_freq12(self, val):
        """Выбор «частота < 3 Гц» в ветке «Да» шага 12."""
        self._freq12 = val
        self._render_step(self._current)

    def _choose_passed13(self, val):
        """Выбор «образец выдержал испытание» на шаге 13."""
        self._passed13 = val
        self._render_step(self._current)

    def _next_nonnested(self, idx: int) -> int:
        """Индекс первого невложенного шага после idx (следующий обычный шаг)."""
        for j in range(idx + 1, len(self._steps)):
            if not self._steps[j].get("parent"):
                return j
        return len(self._steps) - 1

    def _step_idx(self, kind: str):
        """Индекс первого шага заданного типа (или None)."""
        return next((i for i, s in enumerate(self._steps) if s.get("kind") == kind), None)

    def _step_idx_step4(self):
        """Индекс шага 4 («Стабилизирующая нагрузка» — stab с decision=False)."""
        return next((i for i, s in enumerate(self._steps)
                     if s.get("kind") == "stab" and s.get("decision") is False), None)

    def _choose_continue(self, cont):
        """Решение о продолжении испытания (под-шаг ветки «Нет»). Цель перехода и
        стрелка вычисляются в _render_shutdown по значению self._continue11."""
        self._continue11 = cont
        self._render_step(self._current)

    def _choose_continue_yes(self, cont):
        """Решение о продолжении испытания во 2-м под-шаге ветки «Да» (Fcmax)."""
        self._continue_yes = cont
        self._yes_dest = None   # сброс выбранного шага продолжения
        self._render_step(self._current)

    def _choose_yes_dest(self, target):
        """Выбор шага продолжения (9 / 4 / 1) во 2-м под-шаге ветки «Да»."""
        self._yes_dest = target
        self._render_step(self._current)

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
