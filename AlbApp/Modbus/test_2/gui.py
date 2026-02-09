from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QLineEdit
)
from PyQt6.QtCore import QTimer
import asyncio

READ_TYPES = ["holding", "input", "coil", "discrete"]
WRITE_TYPES = ["holding", "holdings", "coil", "coils"]

class MainWindow(QWidget):
    def __init__(self, plc_manager):
        super().__init__()
        self.manager = plc_manager
        self.setWindowTitle("PLC Multiple Polling GUI")

        layout = QVBoxLayout()

        # Labels для всех poll
        self.labels = {}
        self.add_label(layout, "PLC1", "holding_0_10")
        self.add_label(layout, "PLC1", "holding_100_2")
        self.add_label(layout, "PLC2", "holding_0_10")

        # Выбор PLC и poll
        poll_layout = QHBoxLayout()
        self.poll_plc_combo = QComboBox()
        self.poll_plc_combo.addItems(["PLC1", "PLC2"])
        self.poll_name_combo = QComboBox()
        self.update_poll_names()
        poll_layout.addWidget(self.poll_plc_combo)
        poll_layout.addWidget(self.poll_name_combo)
        layout.addLayout(poll_layout)

        # Чтение
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

        # Запись INT / REGISTERS / COILS
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

        # -----------------------------
        # Новая секция: запись float32
        float_layout = QHBoxLayout()
        self.float_address_input = QLineEdit("0")
        self.float_value_input = QLineEdit("0.0")
        self.float_endian_combo = QComboBox()
        self.float_endian_combo.addItems(["ABCD", "BADC", "CDAB", "DCBA"])
        self.btn_write_float = QPushButton("Записать float32")
        self.btn_write_float.clicked.connect(lambda: asyncio.create_task(self.write_float_command()))
        float_layout.addWidget(QLabel("Адрес"))
        float_layout.addWidget(self.float_address_input)
        float_layout.addWidget(QLabel("Значение"))
        float_layout.addWidget(self.float_value_input)
        float_layout.addWidget(QLabel("Endian"))
        float_layout.addWidget(self.float_endian_combo)
        float_layout.addWidget(self.btn_write_float)
        layout.addLayout(float_layout)

        self.setLayout(layout)

        # Таймер для обновления GUI
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(500)

    # -----------------------------
    # Методы GUI

    def add_label(self, layout, plc_id, poll_name):
        key = f"{plc_id}_{poll_name}"
        label = QLabel(f"{key}: нет данных")
        self.labels[key] = label
        layout.addWidget(label)

    def update_poll_names(self):
        self.poll_name_combo.clear()
        selected_plc = self.poll_plc_combo.currentText()
        data = self.manager.get_latest_data(selected_plc)
        if data:
            self.poll_name_combo.addItems(list(data.keys()))
        else:
            self.poll_name_combo.addItem("Нет poll")

    def update_gui(self):
        for key, label in self.labels.items():
            plc_id, poll_name = key.split("_", 1)
            data = self.manager.get_latest_data(plc_id)
            value = data.get(poll_name) if data else None
            label.setText(f"{key}: {value}" if value is not None else f"{key}: нет данных")

    # -----------------------------
    # Чтение / запись обычных регистров
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
            try:
                value = float(value_text)
            except ValueError:
                if type_ in ["holdings", "coils"]:
                    value = [int(x) for x in value_text.split(",")]
                else:
                    value = int(value_text)
            await self.manager.request("PLC1", ("write", type_, address, 1, value))
            print(f"Write {type_} at {address} -> {value} успешно")
        except Exception as e:
            print(f"Write error: {e}")

    # -----------------------------
    # Новая команда: запись float32
    async def write_float_command(self):
        try:
            address = int(self.float_address_input.text())
            value = float(self.float_value_input.text())
            endianess = self.float_endian_combo.currentText()

            await self.manager.write_4bytes(
                plc_id="PLC1",
                address=address,
                value=value,
                dtype="float32",
                endianess=endianess,
                reg_type="holdings"
            )
            print(f"Записан float32 {value} на адрес {address} с endian {endianess}")
        except Exception as e:
            print(f"Write float error: {e}")
