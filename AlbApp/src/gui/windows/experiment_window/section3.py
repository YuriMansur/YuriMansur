from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QComboBox, QSpinBox,
)
from PyQt6.QtCore import Qt


def _make_section3() -> QWidget:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

    container = QWidget()
    container.setStyleSheet("""
        QWidget { background: transparent; }
        QLabel  { color: #ecf0f1; font-size: 12px; background: transparent; border: none; }
        QPushButton {
            background: #3d5166; color: #ecf0f1;
            border: 1px solid #4a6278; border-radius: 3px;
            padding: 4px 12px; min-height: 24px; font-size: 12px;
        }
        QPushButton:hover  { background: #4a6a82; }
        QPushButton:pressed { background: #2980b9; }
        QComboBox {
            background: #2c3e50; color: #ecf0f1;
            border: 1px solid #4a6278; border-radius: 3px;
            padding: 3px 6px; min-height: 22px; font-size: 12px;
        }
        QSpinBox {
            background: #2c3e50; color: #ecf0f1;
            border: 1px solid #4a6278; border-radius: 3px;
            padding: 3px 6px; min-height: 22px; font-size: 12px; min-width: 60px;
        }
    """)
    lay = QVBoxLayout(container)
    lay.setContentsMargins(6, 6, 6, 6)
    lay.setSpacing(10)

    def _orange(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #e67e22; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        lbl.setWordWrap(True)
        return lbl

    def _btn(text: str) -> QPushButton:
        return QPushButton(text)

    def _step(num: str, desc: str, btn_text: str) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(_orange(f"{num}."))
        lbl = QLabel(desc)
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)
        lay.addLayout(row)
        lay.addWidget(_btn(btn_text))

    title_lbl = QLabel("16.2.2  Основное статическое испытание")
    title_lbl.setStyleSheet("color: #e67e22; font-size: 13px; font-weight: bold; background: transparent; border: none;")
    title_lbl.setWordWrap(True)
    lay.addWidget(title_lbl)

    sub = QLabel("Установите образец")
    sub.setStyleSheet("color: #1abc9c; font-size: 13px; font-weight: bold; background: transparent; border: none;")
    lay.addWidget(sub)

    info = QLabel("· Зарегистрировать условие нагружения и уровень нагрузки, значения")
    info.setWordWrap(True)
    lay.addWidget(info)

    row_f0 = QHBoxLayout()
    row_f0.addWidget(_btn("F=0"))
    spin_f = QSpinBox(); spin_f.setRange(-99999, 99999); spin_f.setValue(0)
    row_f0.addWidget(spin_f)
    row_f0.addStretch()
    lay.addLayout(row_f0)

    lay.addWidget(QLabel("Специальное приспособление 2"))
    cb_fixture = QComboBox()
    cb_fixture.addItems(["", "Приспособление A", "Приспособление B"])
    lay.addWidget(cb_fixture)

    _step("4", "t = не менее 10с и не более 30с", "Fset")
    _step("5", "t = не менее 10 мин и не более 20 мин", "F=0")

    lay.addWidget(_orange("6."))
    lay.addWidget(_btn("Fstab"))

    lay.addWidget(_orange("8.  Обнулить 2"))
    lay.addWidget(_btn("Записать"))

    lay.addWidget(_orange("5."))
    lay.addWidget(_btn("Fsu upper"))

    lay.addWidget(QLabel("Записать L1"))
    row_l1 = QHBoxLayout()
    row_l1.addWidget(_btn("Записать"))
    lbl_l1 = QLabel("L1")
    row_l1.addWidget(lbl_l1)
    spin_l1 = QSpinBox(); spin_l1.setRange(-99999, 99999); spin_l1.setValue(0)
    row_l1.addWidget(spin_l1)
    row_l1.addStretch()
    lay.addLayout(row_l1)

    lay.addStretch()

    btn_protocol = QPushButton("Сформировать Протокол")
    btn_protocol.setStyleSheet("""
        QPushButton {
            background: #2c3e50; color: #ecf0f1;
            border: 2px solid #1abc9c; border-radius: 4px;
            padding: 10px; font-size: 14px; font-weight: bold;
        }
        QPushButton:hover  { background: #1abc9c; color: #1a252f; }
        QPushButton:pressed { background: #17a589; }
    """)
    lay.addWidget(btn_protocol)

    scroll.setWidget(container)
    return scroll
