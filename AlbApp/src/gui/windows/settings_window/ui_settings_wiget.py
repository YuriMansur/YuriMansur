from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QLabel, QComboBox,
    QPushButton,
)
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

        # ── Тема оформления (над блоком камер, в правой колонке) ───────────────
        theme_frame = QFrame()
        theme_frame.setObjectName("section")
        theme_frame.setStyleSheet("QFrame#section { border: 1px solid #555555; border-radius: 4px; }")
        theme_row = QHBoxLayout(theme_frame)
        theme_row.setContentsMargins(8, 6, 8, 6)
        theme_row.addWidget(QLabel("Тема:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Тёмная",  True)
        self.theme_combo.addItem("Светлая", False)
        self.theme_combo.setFixedWidth(160)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()

        cam_frame = QFrame()
        cam_frame.setObjectName("section")
        cam_frame.setStyleSheet("QFrame#section { border: 1px solid #555555; border-radius: 4px; }")
        cam_lay = QVBoxLayout(cam_frame)
        cam_lay.setContentsMargins(8, 8, 8, 8)
        cam_lay.addWidget(self.cameras_widget)

        # ── Кнопка «Наладка» (открывает немодальный попап) ─────────────────────
        self.btn_setup = QPushButton("Наладка")
        self.btn_setup.setStyleSheet(
            "font-size: 14px; padding: 6px 16px; border: 2px solid #1abc9c; border-radius: 4px;")
        self._setup_popup = None
        self.btn_setup.clicked.connect(self._open_setup_popup)

        setup_frame = QFrame()
        setup_frame.setObjectName("section")
        setup_frame.setStyleSheet("QFrame#section { border: 1px solid #555555; border-radius: 4px; }")
        setup_row = QHBoxLayout(setup_frame)
        setup_row.setContentsMargins(8, 6, 8, 6)
        setup_row.addWidget(self.btn_setup)
        setup_row.addStretch()

        # правая колонка: наладка, тема, под ними камеры
        right_col = QWidget()
        right_v = QVBoxLayout(right_col)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(8)
        right_v.addWidget(setup_frame)
        right_v.addWidget(theme_frame)
        right_v.addWidget(cam_frame)
        right_v.addStretch()

        from PyQt6.QtCore import Qt
        self.f_parameters_wiget._row_layout.addWidget(right_col, 0, Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self.f_parameters_wiget)

        scroll.setWidget(container)
        page_layout.addWidget(scroll)

    def _open_setup_popup(self):
        """Открыть попап «Наладка» (немодально; одно окно, поднимаем при повторе)."""
        from gui.popups.setup_popup import SetupPopup
        if self._setup_popup is None or not self._setup_popup.isVisible():
            self._setup_popup = SetupPopup(self.window())
            self._setup_popup.show()
        else:
            self._setup_popup.raise_()
            self._setup_popup.activateWindow()

    def set_theme(self, dark: bool):
        self.cameras_widget.set_theme(dark)
        self.f_parameters_wiget.set_theme(dark)
