"""setup_popup.py — попап «Наладка».

Отдельное немодальное окно для наладочных операций стенда. Открывается кнопкой
«Наладка» из вкладки «Настройки». Пока содержит каркас — наполняется по мере
появления наладочных функций (ручное управление приводом, проверка датчиков и т.п.).
"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt


class SetupPopup(QDialog):
    """Немодальное окно наладки стенда."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Наладка")
        self.setModal(False)
        self.resize(720, 520)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        title = QLabel("Наладка стенда")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        lay.addWidget(title)

        hint = QLabel("Раздел наладочных операций.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #7f8c8d;")
        lay.addWidget(hint)

        lay.addStretch(1)
