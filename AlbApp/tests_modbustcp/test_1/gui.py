# gui.py
import asyncio
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from plc_manager import PLCManager


class MainWindow(QWidget):
    def __init__(self, plc_manager: PLCManager):
        super().__init__()
        self.manager = plc_manager

        self.setWindowTitle("PLC Control")

        self.label = QLabel("Готово")
        self.btn_plc1 = QPushButton("PLC 1")
        self.btn_plc2 = QPushButton("PLC 2")

        layout = QVBoxLayout()
        layout.addWidget(self.btn_plc1)
        layout.addWidget(self.btn_plc2)
        layout.addWidget(self.label)
        self.setLayout(layout)

        # Подключаем кнопки к асинхронным вызовам
        self.btn_plc1.clicked.connect(
            lambda: asyncio.create_task(self.call_plc("PLC1"))
        )
        self.btn_plc2.clicked.connect(
            lambda: asyncio.create_task(self.call_plc("PLC2"))
        )

    async def call_plc(self, plc_id: str):
        self.label.setText(f"Запрос к {plc_id}...")
        try:
            result = await self.manager.request(plc_id, "read holding registers")
            self.label.setText(result)
        except Exception as e:
            self.label.setText(f"Ошибка: {e}")
