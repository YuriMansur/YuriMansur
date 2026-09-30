"""Экран «Настройки» — две секции рядом.

Секция 1 «Стенд и испытание»: параметры оборудования стенда и параметры
испытания (FWindow). Секция 2 «Прочее»: наладка, тема оформления, камеры.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QLabel, QComboBox,
    QPushButton,
)
from PyQt6.QtCore import Qt
from gui.windows.settings_window.F_parameters import FWindow
from gui.windows.settings_window.tab_wigets.ui_cameras_settings import CameraSettingsWidget

_SECTION_STYLE = "QFrame#section { border: 1px solid #555555; border-radius: 4px; }"
_HEADER_STYLE  = "font-size: 16px; font-weight: bold; color: #9b59b6;"
_PAGE_TITLE_STYLE = "font-size: 20px; font-weight: bold; color: #9b59b6; padding: 2px 4px;"


def _section_frame() -> QFrame:
    f = QFrame()
    f.setObjectName("section")
    f.setStyleSheet(_SECTION_STYLE)
    return f


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
        outer = QVBoxLayout(container)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # заголовок экрана
        self._title = QLabel("Настройки")
        self._title.setObjectName("settings_title")
        self._title.setStyleSheet(_PAGE_TITLE_STYLE)
        outer.addWidget(self._title)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(8)
        outer.addLayout(columns, 1)

        self.f_parameters_wiget = FWindow()
        self.cameras_widget     = CameraSettingsWidget()

        # ── Секция 1: параметры оборудования стенда и параметры испытания ─────
        self._col1 = self._column("Стенд и испытание")
        self._col1.layout().addWidget(self.f_parameters_wiget)
        self._col1.layout().addStretch()

        # ── Секция 2: всё остальное — наладка, тема, камеры ───────────────────
        self._col2 = self._column("Прочее")
        col2 = self._col2.layout()

        # Наладка (открывает немодальный попап)
        self.btn_setup = QPushButton("Наладка")
        self.btn_setup.setStyleSheet(
            "font-size: 14px; padding: 6px 16px; border: 2px solid #1abc9c; border-radius: 4px;")
        self._setup_popup = None
        self.btn_setup.clicked.connect(self._open_setup_popup)
        setup_frame = _section_frame()
        setup_row = QHBoxLayout(setup_frame)
        setup_row.setContentsMargins(8, 6, 8, 6)
        setup_row.addWidget(self.btn_setup)
        setup_row.addStretch()
        col2.addWidget(setup_frame)

        # Тема оформления
        theme_frame = _section_frame()
        theme_row = QHBoxLayout(theme_frame)
        theme_row.setContentsMargins(8, 6, 8, 6)
        theme_row.addWidget(QLabel("Тема:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Тёмная",  True)
        self.theme_combo.addItem("Светлая", False)
        self.theme_combo.setFixedWidth(160)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        col2.addWidget(theme_frame)

        # Камеры
        cam_frame = _section_frame()
        cam_lay = QVBoxLayout(cam_frame)
        cam_lay.setContentsMargins(8, 8, 8, 8)
        cam_lay.addWidget(self.cameras_widget)
        col2.addWidget(cam_frame)
        col2.addStretch()

        columns.addWidget(self._col1, 1)
        columns.addWidget(self._col2, 1)

        scroll.setWidget(container)
        page_layout.addWidget(scroll)

    @staticmethod
    def _column(title: str) -> QFrame:
        """Рамка секции с заголовком; содержимое добавляется в её layout."""
        frame = QFrame()
        frame.setObjectName("settings_col")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        lbl = QLabel(title)
        lbl.setObjectName("settings_col_title")
        lbl.setStyleSheet(_HEADER_STYLE)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(lbl)
        return frame

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
        # рамки секций — как колонки на экране испытания
        for col in (self._col1, self._col2):
            col.setStyleSheet(
                "QFrame#settings_col { border: 1px solid #777777; border-radius: 4px; }" if dark
                else "QFrame#settings_col { border: 1px solid #b0b0b0; border-radius: 4px; }")
