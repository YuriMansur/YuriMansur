from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame
from PyQt6.QtCore import pyqtSignal

from gui.windows.experiment_window.section1 import _make_section1
from gui.windows.experiment_window.section2 import Section2Widget
from gui.windows.experiment_window.section3 import Section3Widget
from gui.windows.experiment_window.section4 import make_section4


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

        self._col_frames = []
        for i in range(1, 5):
            frame = QFrame()
            frame.setObjectName(f"col_{i}")
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            self._col_frames.append(frame)
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
                self._sec4_plots = make_section4(col_layout)

            stretch = {1: 5, 2: 5, 3: 4, 4: 5}.get(i, 1)
            columns_layout.addWidget(frame, stretch)

        main_layout.addLayout(columns_layout, 1)

    def set_theme(self, dark: bool):
        import pyqtgraph as pg
        from PyQt6.QtWidgets import QFrame
        from gui.windows.experiment_window.section1 import _CameraWidget

        from PyQt6.QtGui import QPalette, QColor
        from PyQt6.QtWidgets import QComboBox, QDateTimeEdit
        for frame in self._col_frames:
            name = frame.objectName()
            frame.setStyleSheet(
                f"QFrame#{name} {{ border: 1px solid #777777; }}" if dark else ""
            )
        h = 26
        for w in self.findChildren((QComboBox, QDateTimeEdit)):
            w.setFixedHeight(h)
        for w in self.findChildren(QDateTimeEdit):
            w.setStyleSheet("")
        for frame in self.findChildren(QFrame):
            if frame.frameShape() in (QFrame.Shape.HLine, QFrame.Shape.VLine):
                if dark:
                    pal = frame.palette()
                    pal.setColor(QPalette.ColorRole.Mid,        QColor("#888888"))
                    pal.setColor(QPalette.ColorRole.Dark,       QColor("#888888"))
                    pal.setColor(QPalette.ColorRole.Light,      QColor("#888888"))
                    pal.setColor(QPalette.ColorRole.WindowText, QColor("#888888"))
                    frame.setPalette(pal)
                else:
                    frame.setPalette(self.palette())


        # камеры
        for cam in self.findChildren(_CameraWidget):
            if dark:
                cam._preview.setStyleSheet(
                    "background: #3a3a3a; color: #888888; font-size: 13px;"
                    " border: 1px solid #555555; border-radius: 4px;"
                )
            else:
                cam._preview.setStyleSheet(
                    "background: #d8d8d8; color: #888888; font-size: 13px;"
                    " border: 1px solid #b0b0b0; border-radius: 4px;"
                )

        # графики секции 4
        plot_bg    = "#2c2c2c" if dark else "#f5f5f5"
        axis_color = "#aaaaaa" if dark else "#333333"
        title_color = "#ecf0f1" if dark else "#1a1a1a"
        for pw in getattr(self, "_sec4_plots", []):
            pw.setBackground(plot_bg)
            for axis in ("left", "bottom"):
                pw.getAxis(axis).setPen(pg.mkPen(axis_color))
                pw.getAxis(axis).setTextPen(pg.mkPen(axis_color))
            pw.getPlotItem().setTitle(
                pw.getPlotItem().titleLabel.text,
                color=title_color, size="10pt"
            )

