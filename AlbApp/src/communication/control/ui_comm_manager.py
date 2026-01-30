from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QLineEdit, QPushButton, QHBoxLayout)
from PyQt6.QtCore import QObject, pyqtSignal as Signal

from PyQt6.QtWidgets import QApplication
import sys
from liveipcontroller import LiveIpController
class ModbusGUIWidget(QWidget):
    """
    Виджет для QStackedWidget.
    Не запускает QApplication и может использоваться как страница.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
    


        layout = QVBoxLayout()
        self.config = None
        # IP и Port
        self.ip_input = QLineEdit()
        self.ip_controller = LiveIpController(self.ip_input, self.config)

        self.port_input = QLineEdit("502")
        layout.addWidget(QLabel("IP:"))
        layout.addWidget(self.ip_input)
        layout.addWidget(QLabel("Port:"))
        layout.addWidget(self.port_input)

        # Start и Count
        h_layout = QHBoxLayout()
        self.start_input = QLineEdit("0")
        self.count_input = QLineEdit("10")
        h_layout.addWidget(QLabel("Start Address:"))
        h_layout.addWidget(self.start_input)
        h_layout.addWidget(QLabel("Count:"))
        h_layout.addWidget(self.count_input)
        layout.addLayout(h_layout)

        # Статус подключения
        self.status_label = QLabel("Disconnected")
        layout.addWidget(self.status_label)

        # Кнопки
        self.connect_btn = QPushButton("Connect")
        self.read_btn = QPushButton("Read Registers")
        layout.addWidget(self.connect_btn)
        layout.addWidget(self.read_btn)

        # Метка для данных
        self.data_label = QLabel("Data: []")
        layout.addWidget(self.data_label)

        self.setLayout(layout)



if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = ModbusGUIWidget()
    gui.show()

    sys.exit(app.exec())