from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QLineEdit, QDialog,
)
from PyQt6.QtCore import pyqtSignal, QTimer, Qt, QPoint, QSize
from PyQt6.QtGui import QPainter, QColor, QPolygon, QIcon

from tag_binder import tags, link   # теги ПЛК по имени + состояние связи с ПЛК
from gui.icons import make_icon      # значки статусов рисуются кодом (см. gui/icons.py)
from event_bus import bus     # живые значения потоков/тегов для карточек (cards)


def _defer(fn) -> None:
    """Отложить fn на следующий тик, безопасно к уничтожению виджетов.

    singleShot(0)-колбэки часто стреляют уже после пересборки панели/закрытия,
    когда C++-объект виджета удалён — глушим RuntimeError вместо мусора в консоли.
    """
    def _run():
        try:
            fn()
        except RuntimeError:
            pass
    QTimer.singleShot(0, _run)


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
    """Загрузить описание методики из patch/<файл>.json (или None, если нет)."""
    import json
    from pathlib import Path
    fname = _METHODIC_FILES.get(method)
    if not fname:
        return None
    # методики подкладываются в AlbApp/patch (src/gui/windows/experiment_window → AlbApp)
    path = Path(__file__).parents[4] / "patch" / fname
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


class _HeaderFrame(QFrame):
    """Шапка мастера: при нехватке ширины прячет блок метаданных, чтобы
    содержимое (иконка, заголовок, «Прервать») не вылезало за границу секции."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._meta = None        # сворачиваемый блок метаданных
        self._min_full = 0       # минимальная ширина, при которой блок показываем
        self._elide: list = []   # [(метка, полный текст)] — ужимаем многоточием
        self._eliding = False    # защита от рекурсии: setText → layout → resizeEvent

    def set_collapsible(self, meta, min_full: int):
        self._meta = meta
        self._min_full = min_full
        self._update_meta()

    def set_elided(self, pairs: list):
        """Метки, которые надо ужимать многоточием под текущую ширину.

        Высота шапки фиксирована, поэтому переносить текст нельзя — не влезет
        и обрежется. Вместо переноса укорачиваем строку, полный текст остаётся
        в подсказке.
        """
        self._elide = pairs
        self._update_elide()

    def _update_meta(self):
        if self._meta is not None:
            self._meta.setVisible(self.width() >= self._min_full)

    def _update_elide(self):
        if self._eliding or not self._elide:
            return
        from PyQt6.QtGui import QFontMetrics
        self._eliding = True
        try:
            for lbl, full in self._elide:
                fm = QFontMetrics(lbl.font())
                lbl.setText(fm.elidedText(full, Qt.TextElideMode.ElideRight,
                                          max(0, lbl.width())))
                lbl.setToolTip(full)
        finally:
            self._eliding = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_meta()
        self._update_elide()
        # ещё раз следующим тиком: в момент resize метки внутри шапки ещё не
        # получили финальную ширину, и обрезать было бы не по чему
        _defer(self._update_elide)


class _CyclicWizard(QWidget):
    """Пошаговый мастер испытания: шаги из PROCEDURES, стиль из темы приложения."""
    started = pyqtSignal(bool)

    def __init__(self, gost: str, method: str, state: dict | None = None, parent=None):
        super().__init__(parent)
        _refresh_wz()
        self._gost   = gost
        self._method = method
        self._items: list[_StepItem] = []
        self._previewing = False   # True — показан просмотр другого (пройденного) шага
        self._step_locked = False  # True — шаг выполнен: поля и кнопки шага закрыты
        # значения полей form-шагов: {step_id: {field_key: value, "__fixture__": ..., "__decision__": ...}}
        self._form_values: dict[str, dict] = {}
        # флаги, выставляемые опциями decision (например, passed для протокола)
        self._flags: dict = {}
        self._sample_info_provider = None   # callable → dict «инфо об образце» (сек.2)
        self._jump_target = None    # индекс шага, на который указывает стрелка «→»
        # Живые значения для карточек cards (как окошко в секции 4): кэш «имя→последнее
        # значение» наполняется одной постоянной подпиской на шину, а таймер обновляет
        # только видимые сейчас карточки (список пересобирается при каждом рендере шага —
        # так подписки не копятся и не ссылаются на удалённые QLabel).
        self._live_last: dict = {}     # имя потока/тега → последнее значение
        self._live_cards: list = []    # [{label, src, fmt, unit}] — карточки текущего шага
        bus.stream_points.connect(self._on_live_points)   # tenza/displacement/setpoint
        bus.tag_state.connect(self._on_live_tag)           # скалярные теги (nowSetpoint…)
        # метки плиток шага инициализации — пока этот шаг отрисован, иначе None;
        # подписки одни на визард, как у живых карточек
        self._link_icon = None
        self._alarm_icon = None
        self._status_btns: dict = {}   # ключ статуса → кнопка-иконка в шапке
        self._nav_btns: list = []      # кнопки перехода текущего шага
        link.changed.connect(self._on_link)
        self._build_steps()
        if state:                     # перенос прогресса при пересборке (смена темы)
            self._restore_state(state)

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
        if state:                     # бейджи — поверх пересчитанных по self._current
            self._restore_badges(state["badges"])

        # таймер обновления живых карточек (значение + подпись) текущего шага
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(200)
        self._live_timer.timeout.connect(self._refresh_live_cards)
        self._live_timer.start()

        self._render_step(self._current)

    # ── формирование шагов ─────────────────────────────────────────────────
    # Нулевой шаг инициализации — общий для всех методик (добавляется первым).
    # Нулевой шаг — пуск испытания. Содержимого нет: только кнопка, которая
    # взводит на ПЛК признак «испытание идёт» (commands[EXPERIMENT_RUN] = TRUE).
    _START_STEP = {"id": "__start__", "group": "НАЧАЛО",
                   "title": "Начало испытания",
                   "sub": "Запуск испытания", "kind": "start",
                   "button": "▶ Начать испытание",
                   "start_tag": "cmdExperimentRun", "start_value": 1}

    # Теги команд испытания на ПЛК. Пуск задан в самом шаге (start_tag выше),
    # завершение и прерывание отправляются кнопками мастера.
    _END_TAG   = "cmdExperimentEnd"      # ✓ Завершить испытание
    _ABORT_TAG = "cmdExperimentAbort"    # ⛔ Прервать

    # Группы, на которых испытание ещё не идёт. Только нулевой шаг: как только
    # нажата «Начать испытание» (commands[EXPERIMENT_RUN] = TRUE), испытание идёт —
    # сек.2 блокирует выбор ГОСТ/методики, сек.1 — ручное управление стендом.
    _IDLE_GROUPS = ("НАЧАЛО",)

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
        # нулевой шаг пуска — первым во всех методиках
        self._steps.insert(0, dict(self._START_STEP))

    # ── перенос прогресса между экземплярами (пересборка при смене темы) ────
    def export_state(self) -> dict:
        """Снимок прогресса: шаги, введённые оператором значения, флаги, позиция."""
        return {
            # шаги — со всеми вставленными по ходу вложенными под-шагами
            "steps":       [dict(s) for s in self._steps],
            "current":     self._current,
            "form_values": {k: dict(v) for k, v in self._form_values.items()},
            "flags":       dict(self._flags),
            "jump_target": self._jump_target,
            # состояния бейджей — иначе «прерванный» протокол пометит пройденными
            # и те шаги, которые были пропущены
            "badges":      [it._state for it in self._items],
        }

    def _restore_state(self, state: dict) -> None:
        """Восстановить прогресс из снимка. Вызывается до построения степпера:
        шаги из снимка уже содержат выбранные ранее вложенные под-шаги."""
        self._steps       = [dict(s) for s in state["steps"]]
        self._form_values = {k: dict(v) for k, v in state["form_values"].items()}
        self._flags       = dict(state["flags"])
        self._jump_target = state["jump_target"]
        self._current     = max(0, min(state["current"], len(self._steps) - 1))

    def _restore_badges(self, badges: list) -> None:
        """Вернуть состояния бейджей степпера (после его построения)."""
        for item, st in zip(self._items, badges):
            item.set_state(st)

    # ── шапка ──────────────────────────────────────────────────────────────
    def _build_header(self) -> QFrame:
        f = _HeaderFrame()
        f.setObjectName("wzHeader")
        f.setStyleSheet(
            f"QFrame#wzHeader {{ background: {_WZ['header_bg']};"
            f" border: 1px solid {_WZ['border']}; border-radius: 8px; }}"
            " QLabel { background: transparent; }")
        f.setFixedHeight(56)   # фиксированная высота — шапка не меняет размер
        lay = QHBoxLayout(f)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)

        icon = QLabel()
        icon.setPixmap(_make_activity_icon(34))

        # Две отдельные строки вместо одной с переносом: высота шапки фиксирована,
        # и перенесённый текст просто обрезался бы. Длинные строки ужимаются
        # многоточием (см. _HeaderFrame.set_elided), полный текст — в подсказке.
        head = QWidget()
        hv = QVBoxLayout(head)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(1)
        l_name = QLabel()
        l_name.setStyleSheet(f"color: {_WZ['title']}; font-weight: bold; background: transparent;")
        l_sub = QLabel()
        l_sub.setStyleSheet(f"color: {_WZ['muted']}; font-size: 11px; background: transparent;")
        for l in (l_name, l_sub):
            l.setWordWrap(False)
            l.setMinimumWidth(1)     # не диктует ширину шапки — ужимается
            hv.addWidget(l)

        lay.addWidget(icon, 0)
        lay.addWidget(head, 1)
        f.set_elided([(l_name, f"{self._gost} — {self._method}"), (l_sub, self._htitle)])

        # метаданные сессии — один компактный блок (разделители внутри, чтобы
        # не раздувать ширину шапки и не вылезать за границу секции)
        meta = QWidget()
        mrow = QHBoxLayout(meta)
        mrow.setContentsMargins(0, 0, 0, 0)
        mrow.setSpacing(8)
        mrow.addWidget(self._h_meta("Образец", "Коленный узел"))
        mrow.addWidget(self._h_sep())
        mrow.addWidget(self._h_meta("Шифр", "#КУ-2024-017"))
        mrow.addWidget(self._h_sep())
        mrow.addWidget(self._h_meta("Оборудование", "● подключено",
                                    value_color=_WZ['green'], caption_color=_WZ['green']))
        mrow.addWidget(self._h_sep())
        mrow.addWidget(self._h_meta("Сессия", "14:32"))
        # блок метаданных не должен задавать минимальную ширину шапки, иначе
        # она не сожмётся в узкой колонке и вылезет за границу секции
        from PyQt6.QtWidgets import QSizePolicy
        meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(meta, 0)
        # метаданные показываем только когда шапке хватает ширины; иначе
        # сворачиваем, чтобы «Прервать» и заголовок не уходили за границу секции
        meta.adjustSize()
        # + место под иконки статусов, иначе блок метаданных не свернётся вовремя
        f.set_collapsible(meta, meta.sizeHint().width() + 320 + 3 * self._ICON_BOX)

        # кнопка прерывания испытания — доступна на каждом шаге
        # статусы оборудования — слева от «Прервать», на виду весь ход испытания;
        # зазор отделяет индикаторы от кнопки, чтобы не читались одним блоком
        lay.addWidget(self._status_row(), 0)
        lay.addSpacing(18)

        # «Прервать» — тоже иконкой, в один ряд со статусами: подпись съедала
        # ширину, из-за которой заголовок не помещался в шапку
        btn_stop = QPushButton()
        btn_stop.setObjectName("wzStop")
        btn_stop.setIcon(QIcon(make_icon("stop", "#ffffff", self._ICON_PX)))
        btn_stop.setIconSize(QSize(self._ICON_PX, self._ICON_PX))
        btn_stop.setFixedSize(self._ICON_BOX, self._ICON_BOX)
        btn_stop.setToolTip("Прервать испытание")
        btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        # Залита красным с рамкой: рядом стоят плоские иконки статусов, и без
        # заливки кнопка читалась бы как ещё один индикатор, а не как действие.
        btn_stop.setStyleSheet(
            f"QPushButton#wzStop {{ background: {_WZ['red']}; border: 1px solid {_WZ['red']};"
            " border-radius: 6px; }"
            " QPushButton#wzStop:hover { background: #e74c3c; border-color: #e74c3c; }"
            " QPushButton#wzStop:pressed { background: #a93226; border-color: #a93226; }")
        btn_stop.clicked.connect(self._interrupt_test)
        lay.addWidget(btn_stop, 0)
        return f

    # ── элементы шапки: разделитель и блок «подпись над значением» ──────────
    def _h_sep(self) -> QFrame:
        """Тонкая вертикальная линия-разделитель между блоками метаданных."""
        s = QFrame()
        s.setFixedWidth(1)
        s.setFixedHeight(30)
        s.setStyleSheet(f"background: {_WZ['border']};")
        return s

    def _h_meta(self, caption: str, value: str,
                value_color: str = None, caption_color: str = None) -> QWidget:
        """Блок метаданных: серая подпись сверху, значение снизу (выровнены)."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        cap = QLabel(caption)
        cap.setStyleSheet(
            f"color: {caption_color or _WZ['muted']}; font-size: 10px; background: transparent;")
        val = QLabel(value)
        val.setStyleSheet(
            f"color: {value_color or _WZ['text']}; font-size: 12px; font-weight: bold;"
            " background: transparent;")
        v.addWidget(cap)
        v.addWidget(val)
        return w

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
            _defer(lambda: self._side_scroll.ensureWidgetVisible(active, 0, 40))

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
        # испытание считается «идущим» вне групп подготовки → блок комбобоксов сек.2
        self.started.emit(self._steps[idx]["group"] not in self._IDLE_GROUPS)

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
            # ПЛК сообщаем именно о прерывании; _abort_test() ниже только сбрасывает
            # состояние мастера и переиспользуется завершением — команды там нет
            tags.write(self._ABORT_TAG, 1)   # commands[EXPERIMENT_ABORT] = TRUE
            self._abort_test()

    def _abort_test(self):
        """Сброс прогресса визарда к первому шагу после прерывания."""
        self._flags = {}
        self._form_values = {}    # сброс значений и выбранных веток form-шагов
        self._jump_target = None
        self._build_steps()       # перечитать шаги из конфига (убрать вложенные под-шаги)
        self._rebuild_sidebar()
        self._sync_status_icons() # шапка не пересобирается — снимаем отметки вручную
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
            _defer(lambda: self._side_scroll.ensureWidgetVisible(active, 0, 40))
        self.started.emit(self._steps[proto]["group"] not in self._IDLE_GROUPS)

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
        self._live_cards = []      # карточки прошлого шага удалены _clear — забываем их
        self._nav_btns = []        # ­— то же для кнопок перехода (их блокируют статусы)
        self._step_locked = False  # снимается на каждом шаге; ставит _render_form
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

        if step["kind"] == "start":
            self._render_start(step)
        elif step["kind"] == "form":
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
        _defer(lambda: self._panel_scroll.verticalScrollBar().setValue(0))

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
            # только переход: действия шага выполняют кнопки в его теле (они шлют
            # свой tag и остаются на месте), навигация ничего на ПЛК не пишет
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
            b.setEnabled(not self._read_only)
            # кнопка с полем "tag" сама пишет на ПЛК (значение из "value", по
            # умолчанию 1) — движок понимает из конфига, что слать
            tag = blk.get("tag")
            if tag is not None:
                val = blk.get("value", 1)
                b.clicked.connect(lambda _c=False, t=tag, v=val: tags.write(t, v))
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
        elif bt == "cards":
            # информационные плитки (значение + подпись); цвет — имя из палитры.
            # Опц. "tag"/"stream" — живой источник (tenza/displacement/setpoint/скаляр):
            # значение обновляется в реальном времени, как окошко в секции 4.
            row = QHBoxLayout()
            row.setSpacing(8)
            for it in blk["items"]:
                col = accents.get(it.get("color")) or _WZ.get(it.get("color", "title"), _WZ["title"])
                card = self._card(it.get("value", "—"), col, it.get("caption", ""))
                src = it.get("tag") or it.get("stream")
                if src:
                    self._live_cards.append({"label": card._val, "src": src,
                                             "fmt": it.get("fmt", ".1f"),
                                             "unit": it.get("unit", "")})
                row.addWidget(card, 1)
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
            b.setEnabled(not self._read_only)
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

    @property
    def _read_only(self) -> bool:
        """Ввод закрыт: смотрим чужой шаг либо текущий уже выполнен."""
        return self._previewing or self._step_locked

    def _render_form(self, step: dict):
        c = self._content
        store = self._form_values.setdefault(step.get("id", step["title"]), {})
        # выполненный шаг закрыт на правку до нажатия «Повторить» (см. _exec_nav);
        # ставим до отрисовки тела — блоки читают признак через _read_only
        self._step_locked = bool(store.get("__executed__"))

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
            c.addLayout(self._exec_nav(step, store))

    # ── кнопки шага: выполнение → повтор / переход ─────────────────────────
    def _exec_nav(self, step: dict, store: dict) -> QVBoxLayout:
        """Тумблер выполнения шага и, для выполненного шага, переход дальше.

        Отжат — «Выполнить шаг»: поля и кнопки шага доступны. Нажат — «Повторить»:
        шаг выполнен, его поля и кнопки закрыты, рядом появляется «Следующий шаг».
        Повторное нажатие открывает шаг заново. Выполнение никуда не перекидывает:
        оператор сам решает, переделать шаг или идти дальше.

        Признак живёт в значениях шага, поэтому сохраняется при возврате к шагу
        и переносится при смене темы, а «Прервать» его сбрасывает.
        """
        if self._previewing:
            return self._step_nav("Следующий шаг")   # в просмотре — только возврат

        done = bool(store.get("__executed__"))
        # кнопки друг под другом на всю ширину — в узкой колонке надписи целиком
        col = QVBoxLayout()
        col.setSpacing(8)

        tgl = self._toggle_btn("🔁 Повторить" if done else "Выполнить шаг")
        self._style_one_toggle(tgl, done)
        tgl.clicked.connect(lambda _c=False: self._toggle_exec(step, store))
        col.addWidget(tgl)

        if done:
            nxt = self._btn("Следующий шаг", primary=True)
            nxt.clicked.connect(lambda: self._goto(self._current + 1))
            col.addWidget(self._register_nav(nxt))
        return col

    def _toggle_exec(self, step: dict, store: dict):
        """Переключить состояние шага: выполнить (команда на ПЛК + блокировка
        полей) либо снять выполнение по «Повторить» — тогда поля и кнопки шага
        снова доступны, а команда уйдёт заново при следующем «Выполнить шаг»."""
        if store.get("__executed__"):
            store["__executed__"] = False
        else:
            tag = step.get("tag")
            if tag is not None:
                tags.write(tag, step.get("value", 1))
            store["__executed__"] = True
        self._rerender_keep_scroll()

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
        nav.addWidget(self._register_nav(btn), 1)
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
        yes.setEnabled(not self._read_only)
        no.setEnabled(not self._read_only)
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
        btn = self._btn("✓ Завершить испытание", primary=True)
        btn.clicked.connect(self._finish_test)
        nav.addWidget(btn, 1)
        c.addLayout(nav)

    def _finish_test(self):
        """Завершение испытания: создать папку испытания с Протоколом и Журналом,
        сообщить ПЛК о завершении и завершить алгоритм (сброс мастера к началу
        для нового образца)."""
        if not self._create_test_docs():
            return                       # документы не созданы — мастер не сбрасываем
        tags.write(self._END_TAG, 1)     # commands[EXPERIMENT_END] = TRUE
        self._abort_test()               # завершение алгоритма: сброс состояния и шагов

    def _create_test_docs(self) -> bool:
        """Создать папку испытания с Протокол.docx и Журнал.docx, открыть её.
        Возвращает True при успехе."""
        from PyQt6.QtWidgets import QMessageBox
        data = {
            "gost":    self._gost,
            "method":  self._method,
            "title":   self._htitle,
            "passed":  self._flags.get("passed"),
            "fields":  self._form_values,
        }
        # данные «Информация об исследуемом образце» из секции 2
        if self._sample_info_provider:
            data.update(self._sample_info_provider() or {})
        try:
            from protocols.generator import generate_test_docs
            folder = generate_test_docs(data)
        except Exception as e:                       # noqa: BLE001 — показать любую ошибку
            QMessageBox.critical(self, "Испытание",
                                 f"Не удалось создать документы испытания:\n{e}")
            return False
        # открыть папку испытания (в ней Протокол.docx и Журнал.docx)
        try:
            import os
            os.startfile(str(folder))
        except OSError as e:
            QMessageBox.warning(
                self, "Испытание",
                f"Документы созданы:\n{folder}\n\nНо открыть папку не удалось:\n{e}")
        return True

    # ── нулевой шаг: пуск испытания (без содержимого — только кнопка) ───────
    def _render_start(self, step: dict):
        c = self._content
        h = QLabel(step.get("title", "Начало испытания"))
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {_WZ['title']}; font-size: 18px; font-weight: bold; background: transparent;")
        c.addWidget(h)

        c.addStretch()
        c.addLayout(self._start_nav(step))

    def _start_nav(self, step: dict) -> QHBoxLayout:
        """Кнопка пуска шага (пуск испытания / инициализация оборудования).
        Надпись и отправляемый тег берутся из самого шага; в режиме просмотра
        вместо пуска — обычная навигация."""
        if self._previewing:
            return self._step_nav("Далее →")
        nav = QHBoxLayout()
        btn = self._btn(step.get("button", "▶ Начать испытание"), primary=True)
        btn.clicked.connect(self._start_test)
        nav.addWidget(btn, 1)
        return nav

    # ── статусы оборудования (в шапке, рядом с «Прервать») ──────────────────
    def _status_row(self) -> QWidget:
        """Три иконки состояния: питание, связь с ПЛК, датчики.

        Живут в шапке мастера, а не внутри шага: состояние относится к стенду,
        а не к конкретному шагу, и должно быть на виду всё испытание. Строятся
        один раз на визард — шаги их не пересоздают.

        Питание и датчики подтверждает оператор (отдельных сигналов об их
        исправности ПЛК не отдаёт), связь берётся из состояния OPC-сессии.
        Состояние общее на всё испытание (ключ __status__ в значениях мастера):
        переносится при смене темы и сбрасывается «Прервать». Подписей нет —
        пояснение всплывает при наведении.
        """
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(self._check_icon(
            "__power__", "power",
            "Питание включено", "Питание: не подтверждено"))
        self._link_icon = QLabel()
        self._link_icon.setFixedSize(self._ICON_BOX, self._ICON_BOX)
        self._link_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._link_icon)
        self._on_link(link.state)                # связь — сразу, не дожидаясь события
        row.addWidget(self._check_icon(
            "__sensors__", "sensor",
            "Датчики исправны", "Датчики: не подтверждено"))
        # авария — не кликается: состояние приходит тегом с ПЛК
        self._alarm_icon = QLabel()
        self._alarm_icon.setFixedSize(self._ICON_BOX, self._ICON_BOX)
        self._alarm_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._alarm_icon)
        self._refresh_alarm_icon()
        return w

    # состояние связи → (текст подсказки, цвет из палитры визарда)
    _LINK_VIEW = {
        link.UP:           ("Связь с ПЛК: есть",              "green"),
        link.DOWN:         ("Связь с ПЛК: нет",               "red"),
        link.RECONNECTING: ("Связь с ПЛК: переподключение…",  "amber"),
        link.UNKNOWN:      ("Связь с ПЛК: состояние неизвестно", "muted"),
    }

    _ICON_PX = 24        # размер иконки статуса
    _ICON_BOX = 34       # размер кликабельной области под ней

    # Группы, где стенд под нагрузкой: идти дальше можно только с подтверждённым
    # оборудованием. На подготовке и в завершении блокировки нет.
    _LOAD_GROUPS = ("НАГРУЖЕНИЕ", "ЦИКЛИЧЕСКОЕ НАГРУЖЕНИЕ")
    _LOCK_TIP = ("Подтвердите питание и датчики в шапке "
                 "и дождитесь связи с ПЛК")

    def _status_ready(self) -> bool:
        """Оборудование готово: питание и датчики отмечены, связь с ПЛК есть."""
        store = self._status_store()
        return (bool(store.get("__power__")) and bool(store.get("__sensors__"))
                and link.state == link.UP)

    def _nav_blocked(self) -> bool:
        """Переход к следующему шагу запрещён (нагружение без готовности стенда)."""
        if not (0 <= self._current < len(self._steps)):
            return False
        return (self._steps[self._current]["group"] in self._LOAD_GROUPS
                and not self._status_ready())

    def _register_nav(self, btn: QPushButton) -> QPushButton:
        """Взять кнопку перехода под блокировку статусов (см. _refresh_nav_lock)."""
        self._nav_btns.append(btn)
        blocked = self._nav_blocked()
        btn.setEnabled(not blocked)
        btn.setToolTip(self._LOCK_TIP if blocked else "")
        return btn

    def _refresh_nav_lock(self):
        """Обновить доступность кнопок перехода — по отметкам статусов и связи.

        Шапка живёт отдельно от шага, поэтому клик по иконке статуса не
        перерисовывает шаг: правим доступность кнопок на месте, без мигания.
        """
        blocked = self._nav_blocked()
        for b in self._nav_btns:
            try:
                b.setEnabled(not blocked)
                b.setToolTip(self._LOCK_TIP if blocked else "")
            except RuntimeError:
                pass          # кнопка прошлого шага уже удалена — пропускаем

    def _status_store(self) -> dict:
        """Значения статусов оборудования. Ищем каждый раз заново: _abort_test
        заменяет _form_values целиком, и захваченная ссылка стала бы висячей."""
        return self._form_values.setdefault("__status__", {})

    def _sync_status_icons(self):
        """Привести иконки статусов к текущим значениям (после сброса мастера)."""
        store = self._status_store()
        for key, b in self._status_btns.items():
            b.setChecked(bool(store.get(key)))

    def _check_icon(self, key: str, kind: str,
                    tip_on: str, tip_off: str) -> QPushButton:
        """Статус-иконка ручной проверки: без рамки и подписи, только значок.

        Клик переключает состояние (зелёная / приглушённая), пояснение всплывает
        при наведении. Состояние живёт в значениях мастера, поэтому переносится
        при смене темы и сбрасывается «Прервать».
        """
        b = QPushButton()
        b.setCheckable(True)
        b.setChecked(bool(self._status_store().get(key)))
        b.setFixedSize(self._ICON_BOX, self._ICON_BOX)
        b.setIconSize(QSize(self._ICON_PX, self._ICON_PX))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton { border: none; background: transparent; }"
            f" QPushButton:hover {{ background: {_WZ['card_bg']}; border-radius: 6px; }}")
        # доступна всегда: статус стенда не зависит от того, какой шаг открыт

        def _sync(on: bool):
            b.setIcon(QIcon(make_icon(
                kind, _WZ['green'] if on else _WZ['muted'], self._ICON_PX)))
            b.setToolTip(tip_on if on else tip_off)

        _sync(b.isChecked())
        b.toggled.connect(_sync)
        b.toggled.connect(lambda on, k=key: self._status_store().__setitem__(k, on))
        b.toggled.connect(lambda _on: self._refresh_nav_lock())
        self._status_btns[key] = b
        return b

    # тег аварии с ПЛК и вид иконки по его значению
    _ALARM_TAG = "general_fault"
    _ALARM_VIEW = {
        False: ("green", "Аварий нет"),
        True:  ("muted", "Авария на стенде"),
        None:  ("muted", "Авария: состояние неизвестно"),
    }

    def _refresh_alarm_icon(self):
        """Иконка «отсутствие аварии»: зелёная, пока тега аварии нет.

        Не кликается — значение приходит с ПЛК тегом general_fault: при аварии
        иконка гаснет.
        """
        if self._alarm_icon is None:
            return
        # значение берём из кэша биндера, а не из своего _live_last: визард
        # пересоздаётся при смене темы и методики, и его кэш каждый раз пуст —
        # тег приходит по изменению и второй раз может не прийти вовсе
        val = tags.last(self._ALARM_TAG)
        color, tip = self._ALARM_VIEW[None if val is None else bool(val)]
        self._alarm_icon.setPixmap(make_icon("alarm", _WZ[color], self._ICON_PX))
        self._alarm_icon.setToolTip(tip)

    def _on_link(self, state: str, _server: str = ""):
        """Перекрасить иконку связи и обновить её подсказку. Шаг инициализации
        общий для всех методик, поэтому индикатор появляется в каждой из них."""
        if self._link_icon is None:
            return                      # отрисован не шаг инициализации — обновлять нечего
        tip, color = self._LINK_VIEW.get(state, self._LINK_VIEW[link.UNKNOWN])
        self._link_icon.setPixmap(make_icon("link", _WZ[color], self._ICON_PX))
        self._link_icon.setToolTip(tip)
        self._refresh_nav_lock()        # связь пропала → переход снова закрыт

    def _start_test(self):
        """Начать испытание: если в шаге задан start_tag — отправить его на ПЛК
        (имя/значение берутся из конфига), затем перейти к первому шагу."""
        step = self._steps[self._current]
        tag = step.get("start_tag")
        if tag is not None:
            tags.write(tag, step.get("start_value", 1))
        self._goto(self._current + 1)

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
            note = QLabel("Цикл: приложить Fset = 800 Н на 20 с, затем F = 0 на 12 минут.")
            note.setWordWrap(True)
            note.setStyleSheet(
                f"background: {_WZ['card_bg']}; color: {_WZ['text']};"
                f" border-left: 3px solid {_WZ['amber']}; border-radius: 4px; padding: 8px 12px;")
            c.addWidget(note)

        if inputs:
            in_row = QHBoxLayout()
            in_row.setSpacing(8)
            in_row.addLayout(self._input("Fset (Н)", "800"), 1)
            in_row.addLayout(self._input("t нагрузки (с)", "20"), 1)
            in_row.addLayout(self._input("t разгрузки (мин)", "12"), 1)
            c.addLayout(in_row)

        cards = QHBoxLayout()
        cards.setSpacing(8)
        cards.addWidget(self._card("800 Н", _WZ['green'], "F текущее"), 1)
        cards.addWidget(self._card("18.4 с", _WZ['title'], "t прошло"), 1)
        cards.addWidget(self._card("2.1 мм", _WZ['title'], "δ при Fset"), 1)
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
        e.setReadOnly(self._read_only)
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
        # маленькая мин. ширина — ряд карточек ужимается под ширину панели и не
        # распирает её (иначе длинное значение сдвигает весь контент за край)
        f.setMinimumWidth(60)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        v = QLabel(value)
        v.setWordWrap(True)     # длинное значение переносится, а не тянет карточку вширь
        v.setStyleSheet(f"color: {color}; font-size: 17px; font-weight: bold;")
        cap = QLabel(caption)
        cap.setWordWrap(True)
        cap.setStyleSheet(f"color: {_WZ['muted']}; font-size: 11px;")
        lay.addWidget(v)
        lay.addWidget(cap)
        f._val = v          # ссылка на метку значения — для живого обновления карточки
        return f

    # ── живые значения карточек (cards с полем "tag"/"stream") ────────────────
    def _on_live_points(self, name: str, _times: list, vals: list):
        if vals:                       # поток точек — берём последнее значение батча
            self._live_last[name] = vals[-1]

    def _on_live_tag(self, name: str, val):
        self._live_last[name] = val    # скалярный тег (nowSetpoint и т.п.)
        if name == self._ALARM_TAG:
            self._refresh_alarm_icon()

    def _refresh_live_cards(self):
        for lc in self._live_cards:
            val = self._live_last.get(lc["src"])
            if val is None:
                continue
            try:
                txt = f"{float(val):{lc['fmt']}}"
            except (TypeError, ValueError):
                txt = str(val)
            if lc["unit"]:
                txt += f" {lc['unit']}"
            lc["label"].setText(txt)

    def _btn(self, text: str, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setMinimumHeight(36)
        # кнопка не должна задавать минимальную ширину панели своей надписью —
        # в узкой колонке она ужимается, а не выталкивает контент за край
        b.setMinimumWidth(60)
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

        self._gost    = ""
        self._method  = ""
        self._wizard  = None
        self._sample_info_provider = None   # callable → dict «инфо об образце»
        self._rebuild()

    def set_sample_info_provider(self, fn):
        """Источник данных «Информация об исследуемом образце» (из секции 2)
        для включения в протокол."""
        self._sample_info_provider = fn
        if self._wizard is not None:
            self._wizard._sample_info_provider = fn

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
        """Перестроить мастер под текущую палитру приложения (вызов из ExperimentWidget).
        Прогресс и введённые оператором значения переносятся в новый экземпляр —
        смена темы посреди испытания не должна стирать замеры."""
        if self._wizard is None:
            return
        self._build_wizard(state=self._wizard.export_state())

    def _build_wizard(self, state: dict | None = None):
        """Построить пошаговый мастер для текущей (ГОСТ, методика)."""
        self._wizard = _CyclicWizard(self._gost, self._method, state=state)
        self._wizard._sample_info_provider = self._sample_info_provider
        self._wizard.started.connect(self.started)   # проброс блокировки комбобоксов сек.2
        self._scroll.setWidget(self._wizard)

    def on_alarm(self):
        """Слот сигнала аварии (alarm_test). Прерывание в режиме мастера
        выполняется пользователем через кнопку «Прервать» внутри визарда —
        здесь обработки нет, метод сохранён только для подключения сигнала."""
        return


def _make_section3() -> Section3Widget:
    return Section3Widget()
