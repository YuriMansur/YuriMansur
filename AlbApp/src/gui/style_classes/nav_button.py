from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

class NavigationButton(QPushButton):
    def __init__(self, text, color):
        super().__init__(text)
        self.color = color
        self._text_color = "#ecf0f1"
        self._underline_color = "#ecf0f1"
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_style(False)
    
    # Обновление стиля в зависимости от состояния активности
    def set_text_color(self, color: str):
        self._text_color = color
        self._underline_color = color
        self.update_style(self.isChecked())

    def update_style(self, active):
        if active:
            style = f"""
                QPushButton {{
                    background-color: {self.color};
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    font-weight: bold;
                    border-bottom: 3px solid {self._underline_color};
                    margin: 0 2px;
                }}
                QPushButton:hover {{
                    background-color: {self.darken_color(self.color)};
                }}
            """
        else:
            style = f"""
                QPushButton {{
                    background-color: transparent;
                    color: {self._text_color};
                    border: none;
                    padding: 10px 20px;
                    margin: 0 2px;
                }}
                QPushButton:hover {{
                    background-color: rgba(128, 128, 128, 0.15);
                    color: {self._text_color};
                    border-bottom: 3px solid {self.color};
                }}
            """
        # Применение стиля   
        self.setStyleSheet(style)

    # Затемнение цвета для hover эффекта
    def darken_color(self, hex_color):
        color = QColor(hex_color)
        return color.darker(120).name()
    
    # Переопределение метода setChecked для обновления стиля при смене состояния
    def setChecked(self, checked):
        super().setChecked(checked)
        self.update_style(checked)