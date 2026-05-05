from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QComboBox, QSpinBox,
)
from PyQt6.QtCore import Qt

# Процедуры: ключ — (gost, method), значение — список шагов.
# Каждый шаг: dict с полями:
#   type: "title" | "subtitle" | "info" | "step" | "button" | "f0row" | "protocol"
PROCEDURES: dict[tuple, list[dict]] = {
    ("Р ИСО 10328-2021", "16.2.2"): [
        {"type": "title",    "text": "16.2.2  Основное статическое испытание"},
        {"type": "subtitle", "text": "Установите образец"},
        {"type": "info",     "text": "· Зарегистрировать условие нагружения и уровень нагрузки, значения"},
        {"type": "f0row"},
        {"type": "step",     "num": "4", "desc": "t = не менее 10с и не более 30с",           "btn": "Fset"},
        {"type": "step",     "num": "5", "desc": "t = не менее 10 мин и не более 20 мин",      "btn": "F=0"},
        {"type": "button",   "text": "Fstab",   "num": "6."},
        {"type": "button",   "text": "Записать","num": "8. Обнулить 2"},
        {"type": "button",   "text": "Fsu upper","num": "5."},
        {"type": "protocol"},
    ],
    ("Р ИСО 10328-2021", "16.2.2+С"): [
        {"type": "title",    "text": "16.2.2+С  Испытание со стабилизацией"},
        {"type": "subtitle", "text": "Установите образец"},
        {"type": "info",     "text": "· Зарегистрировать условие нагружения и уровень нагрузки, значения"},
        {"type": "f0row"},
        {"type": "step",     "num": "4", "desc": "t = не менее 10с и не более 30с",           "btn": "Fset"},
        {"type": "step",     "num": "5", "desc": "t = не менее 10 мин и не более 20 мин",      "btn": "F=0"},
        {"type": "button",   "text": "Fstab",   "num": "6."},
        {"type": "button",   "text": "Fsu upper","num": "7."},
        {"type": "protocol"},
    ],
}

# Процедура по умолчанию если комбинация не найдена
_DEFAULT_PROCEDURE = [
    {"type": "info", "text": "Для данного сочетания ГОСТ / Методика процедура не задана."},
]


class Section3Widget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self._scroll)

        self._gost   = ""
        self._method = ""
        self._rebuild()

    def set_params(self, gost: str, method: str):
        if gost == self._gost and method == self._method:
            return
        self._gost   = gost
        self._method = method
        self._rebuild()

    def _rebuild(self):
        steps = PROCEDURES.get((self._gost, self._method), _DEFAULT_PROCEDURE)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(10)

        for step in steps:
            t = step["type"]

            if t == "title":
                lbl = QLabel(step["text"])
                lbl.setWordWrap(True)
                lay.addWidget(lbl)

            elif t == "subtitle":
                lbl = QLabel(step["text"])
                lay.addWidget(lbl)

            elif t == "info":
                lbl = QLabel(step["text"])
                lbl.setWordWrap(True)
                lay.addWidget(lbl)

            elif t == "f0row":
                row = QHBoxLayout()
                row.addWidget(QPushButton("F=0"))
                spin = QSpinBox(); spin.setRange(-99999, 99999); spin.setValue(0)
                row.addWidget(spin)
                row.addStretch()
                lay.addLayout(row)

            elif t == "step":
                num_lbl = QLabel(f"{step['num']}.")
                desc_lbl = QLabel(step["desc"])
                desc_lbl.setWordWrap(True)
                row = QHBoxLayout()
                row.setSpacing(6)
                row.addWidget(num_lbl)
                row.addWidget(desc_lbl, 1)
                lay.addLayout(row)
                lay.addWidget(QPushButton(step["btn"]))

            elif t == "button":
                lbl = QLabel(step["num"])
                lay.addWidget(lbl)
                lay.addWidget(QPushButton(step["text"]))

            elif t == "protocol":
                lay.addStretch()
                btn = QPushButton("Сформировать Протокол")
                lay.addWidget(btn)

        self._scroll.setWidget(container)


def _make_section3() -> Section3Widget:
    return Section3Widget()
