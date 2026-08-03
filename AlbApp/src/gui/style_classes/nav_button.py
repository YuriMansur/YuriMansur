from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QIcon

from gui.icons import make_icon

class NavigationButton(QPushButton):
    ICON_PX = 18

    def __init__(self, text, color, icon_kind: str = None):
        super().__init__(text)
        self.color = color
        self._icon_kind = icon_kind
        self._text_color = "#ecf0f1"
        self._underline_color = "#ecf0f1"
        self.setFixedHeight(40)
        self.setIconSize(QSize(self.ICON_PX, self.ICON_PX))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_style(False)

    def _repaint_icon(self, active: bool):
        """Значок в цвет надписи: на активной кнопке белый, иначе цвет темы."""
        if not self._icon_kind:
            return
        color = "#ffffff" if active else self._text_color
        self.setIcon(QIcon(make_icon(self._icon_kind, color, self.ICON_PX)))
    
    # Обновление стиля в зависимости от состояния активности
    def set_text_color(self, color: str):
        self._text_color = color
        self._underline_color = color
        self.update_style(self.isChecked())

    def update_style(self, active):
        self._repaint_icon(active)
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