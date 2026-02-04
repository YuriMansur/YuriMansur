# gui.py
import asyncio
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel

class MainWindow(QWidget):
    def __init__(self, plc_manager):
        super().__init__()
        self.manager = plc_manager

        self.setWindowTitle("PLC Control with PyModbus")

        self.label = QLabel("Готово")
        self.btn_read1 = QPushButton("Читать PLC1")
        self.btn_write1 = QPushButton("Писать PLC1")

        layout = QVBoxLayout()
        layout.addWidget(self.btn_read1)
        layout.addWidget(self.btn_write1)
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.btn_read1.clicked.connect(
            lambda: asyncio.create_task(self.call_read("PLC1"))
        )
        self.btn_write1.clicked.connect(
            lambda: asyncio.create_task(self.call_write("PLC1"))
        )

    async def call_read(self, plc_id: str):
        self.label.setText(f"Чтение {plc_id}...")
        try:
            registers = await self.manager.request(plc_id, ("read_holding", 0, 10))
            self.label.setText(f"{plc_id} данные: {registers}")
        except Exception as e:
            self.label.setText(f"Ошибка чтения: {e}")

    async def call_write(self, plc_id: str):
        self.label.setText(f"Запись в {plc_id}...")
        try:
            ok = await self.manager.request(plc_id, ("write_register", 5, 1234))
            self.label.setText(f"{plc_id} запись: {'OK' if ok else 'FAIL'}")
        except Exception as e:
            self.label.setText(f"Ошибка записи: {e}")
