from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton,
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
        root.addWidget(self._scroll, 1)

        # Кнопка Начать / Сбросить внизу секции
        self._btn_start = QPushButton("▶ Начать испытание")
        self._btn_start.setMinimumHeight(36)
        self._btn_start.clicked.connect(self._toggle_start)
        root.addWidget(self._btn_start)

        self._running = False
        self._gost    = ""
        self._method  = ""
        self._rebuild()

    def set_params(self, gost: str, method: str):
        """Вызывается из Section2Widget при смене ГОСТ или методики."""
        if gost == self._gost and method == self._method:
            return  # параметры не изменились — перестройка не нужна
        self._gost   = gost
        self._method = method
        self._rebuild()

    def _rebuild(self):
        """
        Пересоздаёт содержимое scroll-area по текущим self._gost / self._method.
        Ищет процедуру в PROCEDURES; если не найдена — показывает _DEFAULT_PROCEDURE.
        """
        steps = PROCEDURES.get((self._gost, self._method), _DEFAULT_PROCEDURE)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(10)

        # Информационные элементы (заголовки, описания)
        for step in steps:
            t = step["type"]
            if t == "title":
                lbl = QLabel(step["text"]); lbl.setWordWrap(True); lay.addWidget(lbl)
            elif t in ("subtitle", "info"):
                lbl = QLabel(step["text"]); lbl.setWordWrap(True); lay.addWidget(lbl)

        lay.addSpacing(8)

        self._step_buttons: list[QPushButton]     = []
        self._step_bars:    list[_StripedOverlay] = []
        step_labels = self._get_step_labels(steps)
        for i, label in enumerate(step_labels):
            btn = QPushButton(f"Шаг {i+1}: {label}")
            btn.setMinimumHeight(36)
            btn.setEnabled(False)
            bar = _StripedOverlay(btn)
            self._step_buttons.append(btn)
            self._step_bars.append(bar)
            lay.addWidget(btn)

        lay.addStretch()
        self._scroll.setWidget(container)
        self._current_step = 0
        self._running = False
        self._executing = False
        self._completed = False
        self._alarm_steps: set[int] = set()
        self._alarm_interrupts: set[int] = ALARM_INTERRUPT_STEPS.get(
            (self._gost, self._method), set()
        )
        self._step_timer = QTimer(self)
        self._step_timer.setSingleShot(True)
        self._step_timer.timeout.connect(self._on_step_timeout)
        self._btn_start.setText("▶ Начать испытание")
        self._update_buttons()

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
        if not self._executing or not self._running:
            return
        step = self._current_step
        if step in self._alarm_interrupts:
            self._step_timer.stop()
            self._executing = False
            self._alarm_steps.add(step)
            self._update_buttons()

    def _toggle_start(self):
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
