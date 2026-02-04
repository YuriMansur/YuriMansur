# gui.py
import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QComboBox, QLineEdit, QHBoxLayout
)
from PyQt6.QtCore import QTimer

READ_TYPES = ["holding", "input", "coil", "discrete"]
WRITE_TYPES = ["holding", "holdings", "coil", "coils"]

class MainWindow(QWidget):
    def __init__(self, plc_manager):
        super().__init__()
        self.manager = plc_manager

        self.setWindowTitle("PLC Multiple Polling PyQt6 - Select Type")

        layout = QVBoxLayout()

        # --- PLC1 Labels ---
        self.label_plc1_0_10 = QLabel("PLC1 holding_0_10: нет данных")
        self.label_plc1_100_5 = QLabel("PLC1 holding_100_5: нет данных")
        layout.addWidget(self.label_plc1_0_10)
        layout.addWidget(self.label_plc1_100_5)

        # --- PLC2 Labels ---
        self.label_plc2_0_10 = QLabel("PLC2 holding_0_10: нет данных")
        layout.addWidget(self.label_plc2_0_10)

        # --- Чтение ---
        read_layout = QHBoxLayout()
        self.read_type_combo = QComboBox()
        self.read_type_combo.addItems(READ_TYPES)
        self.read_address_input = QLineEdit("0")
        self.read_count_input = QLineEdit("1")
        self.btn_read = QPushButton("Читать")
        self.btn_read.clicked.connect(lambda: asyncio.create_task(self.read_command()))
        read_layout.addWidget(self.read_type_combo)
        read_layout.addWidget(self.read_address_input)
        read_layout.addWidget(self.read_count_input)
        read_layout.addWidget(self.btn_read)
        layout.addLayout(read_layout)

        # --- Запись ---
        write_layout = QHBoxLayout()
        self.write_type_combo = QComboBox()
        self.write_type_combo.addItems(WRITE_TYPES)
        self.write_address_input = QLineEdit("0")
        self.write_value_input = QLineEdit("0")
        self.btn_write = QPushButton("Записать")
        self.btn_write.clicked.connect(lambda: asyncio.create_task(self.write_command()))
        write_layout.addWidget(self.write_type_combo)
        write_layout.addWidget(self.write_address_input)
        write_layout.addWidget(self.write_value_input)
        write_layout.addWidget(self.btn_write)
        layout.addLayout(write_layout)

        self.setLayout(layout)

        # Таймер для обновления GUI
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(500)

    def update_gui(self):
        plc1_data = self.manager.get_latest_data("PLC1")
        plc2_data = self.manager.get_latest_data("PLC2")

        self.label_plc1_0_10.setText(f"PLC1 holding_0_10: {plc1_data.get('holding_0_10')}" if plc1_data.get('holding_0_10') else "PLC1 holding_0_10: нет данных")
        self.label_plc1_100_5.setText(f"PLC1 holding_100_5: {plc1_data.get('holding_100_5')}" if plc1_data.get('holding_100_5') else "PLC1 holding_100_5: нет данных")
        self.label_plc2_0_10.setText(f"PLC2 holding_0_10: {plc2_data.get('holding_0_10')}" if plc2_data.get('holding_0_10') else "PLC2 holding_0_10: нет данных")

    async def read_command(self):
        try:
            type_ = self.read_type_combo.currentText()
            address = int(self.read_address_input.text())
            count = int(self.read_count_input.text())
            result = await self.manager.request("PLC1", ("read", type_, address, count))
            print(f"Read result ({type_}): {result}")
        except Exception as e:
            print(f"Read error: {e}")

    async def write_command(self):
        try:
            type_ = self.write_type_combo.currentText()
            address = int(self.write_address_input.text())
            value_text = self.write_value_input.text()
            # value может быть список для "holdings" и "coils"
            if type_ in ["holdings", "coils"]:
                value = [int(x) for x in value_text.split(",")]
            else:
                value = int(value_text)
            await self.manager.request("PLC1", ("write", type_, address, 1, value))
            print(f"Write {type_} at {address} -> {value} успешно")
        except Exception as e:
            print(f"Write error: {e}")
