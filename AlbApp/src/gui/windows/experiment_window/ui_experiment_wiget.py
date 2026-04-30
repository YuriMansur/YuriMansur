from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame
from PyQt6.QtCore import pyqtSignal

from gui.windows.experiment_window.section1 import _make_section1
from gui.windows.experiment_window.section2 import Section2Widget
from gui.windows.experiment_window.section3 import Section3Widget
from gui.windows.experiment_window.section4 import make_section4

_FRAME_STYLE = """
    QFrame {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(26, 188, 156, 0.3);
        border-radius: 6px;
    }
"""


class ExperimentWidget(QWidget):
    alarm_test  = pyqtSignal()
    alarm_reset = pyqtSignal()

    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(2)

        sec2 = Section2Widget()
        sec3 = Section3Widget()
        sec2.params_changed.connect(sec3.set_params)
        sec3.set_params(sec2.cb_std.currentText(), sec2.cb_method.currentText())

        for i in range(1, 5):
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame.setStyleSheet(_FRAME_STYLE)
            col_layout = QVBoxLayout(frame)
            col_layout.setContentsMargins(8, 8, 8, 8)
            col_layout.setSpacing(4)

            if i == 1:
                col_layout.addWidget(_make_section1(), 1)
            elif i == 2:
                col_layout.addWidget(sec2, 1)
            elif i == 3:
                col_layout.addWidget(sec3, 1)
            elif i == 4:
                make_section4(col_layout)

            stretch = {1: 5, 2: 5, 3: 4, 4: 5}.get(i, 1)
            columns_layout.addWidget(frame, stretch)

        main_layout.addLayout(columns_layout, 1)
