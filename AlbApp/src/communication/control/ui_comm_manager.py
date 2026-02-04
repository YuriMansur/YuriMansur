import sys
from PyQt6.QtWidgets import QWidget, QLineEdit, QHBoxLayout, QApplication
from PyQt6.QtCore import Qt
from line_qt_str import IPBuilder  # твой класс IPBuilder


class IPWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Логика IP
        self.ip = IPBuilder()

        # QLineEdit только для отображения
        self.edit = QLineEdit()
        self.edit.setReadOnly(True)
        self.edit.setMaxLength(15)
        self.edit.setPlaceholderText("0.0.0.0")
        self.edit.setText(self.ip.get_ip())

        
        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit)

        self.setFocusProxy(self.edit)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event):
        """
        Перехватываем ввод клавиш и обновляем IPBuilder.
        """
        key = event.key()
        char = event.text()

        # Пока блокируем Backspace
        if key == Qt.Key.Key_Backspace:
            return

        # Разрешаем только цифры
        if char.isdigit():
            if self.ip.add_char(char):
                self.edit.setText(self.ip.get_ip())


if __name__ == "__main__":
    app = QApplication(sys.argv)

    w = IPWidget()
    w.setWindowTitle("IP Input Widget")
    w.resize(200, 40)
    w.show()

    sys.exit(app.exec())
