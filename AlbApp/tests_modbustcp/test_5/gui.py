# gui.py
import asyncio
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import QTimer

class MainWindow(QWidget):
    def __init__(self, plc_manager):
        super().__init__()
        self.manager = plc_manager

        self.setWindowTitle("PLC Multiple Polling Display PyQt6")

        # PLC1 Labels
        self.label_plc1_0_10 = QLabel("PLC1 holding_0_10: нет данных")
        self.label_plc1_100_5 = QLabel("PLC1 holding_100_5: нет данных")
        # PLC2 Labels
        self.label_plc2_0_10 = QLabel("PLC2 holding_0_10: нет данных")

        self.btn_write1 = QPushButton("Записать 1234 в PLC1 регистр 5")

        layout = QVBoxLayout()
        layout.addWidget(self.label_plc1_0_10)
        layout.addWidget(self.label_plc1_100_5)
        layout.addWidget(self.label_plc2_0_10)
        layout.addWidget(self.btn_write1)
        self.setLayout(layout)

        self.btn_write1.clicked.connect(lambda: asyncio.create_task(self.write_plc1()))

        # QTimer для обновления GUI каждые 0.5 сек
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(500)

    def update_gui(self):
        plc1_data = self.manager.get_latest_data("PLC1")
        plc2_data = self.manager.get_latest_data("PLC2")

        self.label_plc1_0_10.setText(
            f"PLC1 holding_0_10: {plc1_data.get('holding_0_10')}" if plc1_data.get('holding_0_10') else "PLC1 holding_0_10: нет данных"
        )
        self.label_plc1_100_5.setText(
            f"PLC1 holding_100_5: {plc1_data.get('holding_11_5')}" if plc1_data.get('holding_11_5') else "PLC1 holding_11_5: нет данных"
        )
        self.label_plc2_0_10.setText(
            f"PLC2 holding_0_10: {plc2_data.get('holding_0_10')}" if plc2_data.get('holding_0_10') else "PLC2 holding_0_10: нет данных"
        )

    async def write_plc1(self):
        try:
            ok = await self.manager.request("PLC1", ("write_register", 5, 1234))
            if ok:
                self.label_plc1_100_5.setText("PLC1 запись успешна")
        except Exception as e:
            self.label_plc1_100_5.setText(f"PLC1 запись ошибка: {e}")
