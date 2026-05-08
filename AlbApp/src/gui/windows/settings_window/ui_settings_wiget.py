from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame
from gui.windows.settings_window.F_parameters import FWindow
from gui.windows.settings_window.tab_wigets.ui_cameras_settings import CameraSettingsWidget


class SettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        self.f_parameters_wiget = FWindow()
        self.cameras_widget     = CameraSettingsWidget()

        cam_frame = QFrame()
        cam_frame.setObjectName("section")
        cam_frame.setStyleSheet("QFrame#section { border: 1px solid #555555; border-radius: 4px; }")
        cam_lay = QVBoxLayout(cam_frame)
        cam_lay.setContentsMargins(8, 8, 8, 8)
        cam_lay.addWidget(self.cameras_widget)

        from PyQt6.QtCore import Qt
        self.f_parameters_wiget._row_layout.addWidget(cam_frame, 0, Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self.f_parameters_wiget)

        scroll.setWidget(container)
        page_layout.addWidget(scroll)

    def set_theme(self, dark: bool):
        self.cameras_widget.set_theme(dark)
        self.f_parameters_wiget.set_theme(dark)
