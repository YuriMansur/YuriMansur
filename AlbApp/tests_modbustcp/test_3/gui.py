# gui.py
import asyncio
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import QTimer

class MainWindow(QWidget):
    def __init__(self, plc_manager):
        super().__init__()
        self.manager = plc_manager

        self.setWindowTitle("PLC Cyclic Read Example")

        self.label1 = QLabel("PLC1: нет данных")
        self.label2 = QLabel("PLC2: нет данных")
        self.btn_write1 = QPushButton("Записать 1234 в PLC1 регистр 5")

        layout = QVBoxLayout()
        layout.addWidget(self.label1)
        layout.addWidget(self.label2)
        layout.addWidget(self.btn_write1)
        self.setLayout(layout)

        self.btn_write1.clicked.connect(lambda: asyncio.create_task(self.write_plc1()))

        # QTimer для обновления GUI каждые 0.5 сек
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(500)

    def update_gui(self):
        data1 = self.manager.get_latest_data("PLC1")
        data2 = self.manager.get_latest_data("PLC2")
        self.label1.setText(f"PLC1: {data1}" if data1 else "PLC1: нет данных")
        self.label2.setText(f"PLC2: {data2}" if data2 else "PLC2: нет данных")

    async def write_plc1(self):
        try:
            ok = await self.manager.request("PLC1", ("write_register", 5, 1234))
            if ok:
                self.label1.setText("PLC1: запись успешна")
        except Exception as e:
            self.label1.setText(f"PLC1 запись ошибка: {e}")
