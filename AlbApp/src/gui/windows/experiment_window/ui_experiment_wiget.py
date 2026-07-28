from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame
from PyQt6.QtCore import pyqtSignal

from gui.windows.experiment_window.section1 import _make_section1, set_manual_controls_enabled
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
        self._sec2 = sec2
        self._sec3 = sec3
        sec2.params_changed.connect(sec3.set_params)
        sec3.set_sample_info_provider(sec2.sample_info)   # «инфо об образце» → протокол
        sec3.set_params(sec2.cb_std.currentText(), sec2.cb_method.currentText())

        def _on_started(running: bool):
            for w in (sec2.cb_std, sec2.cb_load, sec2.cb_cond, sec2.cb_method):
                w.setEnabled(not running)
            # ручное управление стендом на время испытания недоступно
            if getattr(self, "_sec1", None) is not None:
                set_manual_controls_enabled(self._sec1, not running)

        sec3.started.connect(_on_started)

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
                sec1, self._btn_alarm_test = _make_section1()
                self._sec1 = sec1
                col_layout.addWidget(sec1, 1)
            elif i == 2:
                col_layout.addWidget(sec2, 1)
            elif i == 3:
                col_layout.addWidget(sec3, 1)
            elif i == 4:
                self._sec4_plots = make_section4(col_layout)

            stretch = {1: 5, 2: 3, 3: 6, 4: 5}.get(i, 1)
            columns_layout.addWidget(frame, stretch)

        main_layout.addLayout(columns_layout, 1)
        self.alarm_test.connect(sec3.on_alarm)


    def set_theme(self, dark: bool):
        import pyqtgraph as pg
        from PyQt6.QtWidgets import QFrame
        from gui.windows.experiment_window.section1 import _CameraWidget

        # секция 3 (мастер испытания) перестраивается под новую палитру
        if hasattr(self, "_sec3"):
            self._sec3.set_theme(dark)

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
                cam._overlay.setStyleSheet(
                    "background: rgba(30,30,30,180); border-radius: 4px;"
                )
                cam._lbl_cam_name.setStyleSheet(
                    "QLabel { color: white; font-size: 11px; font-weight: bold;"
                    " background: rgba(0,0,0,150); border-radius: 3px; padding: 2px 7px; }"
                )
            else:
                cam._preview.setStyleSheet(
                    "background: #d8d8d8; color: #888888; font-size: 13px;"
                    " border: 1px solid #b0b0b0; border-radius: 4px;"
                )
                cam._overlay.setStyleSheet(
                    "background: rgba(220,220,220,200); border-radius: 4px;"
                )
                cam._lbl_cam_name.setStyleSheet(
                    "QLabel { color: #1a1a1a; font-size: 11px; font-weight: bold;"
                    " background: rgba(200,200,200,180); border-radius: 3px; padding: 2px 7px; }"
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
        # окошки текущих значений под графиками — под текущую тему
        from gui.windows.experiment_window.section4 import style_value_boxes
        style_value_boxes(getattr(self, "_sec4_plots", []), dark)

