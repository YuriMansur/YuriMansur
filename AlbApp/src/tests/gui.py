import sys
import queue

from PyQt6.QtWidgets import (
    QApplication, QWidget,
    QVBoxLayout, QLabel, QPushButton
)
from PyQt6.QtCore import QTimer

from poller_thread import PollerThread


class ManagerGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Modbus Manager (PyQt6)")

        self.queue = queue.Queue()
        self.poller = PollerThread(
            host="192.168.6.199",
            port=502,
            unit_id=1,
            out_queue=self.queue
        )

        self.label = QLabel("Нет данных")
        self.start_btn = QPushButton("Старт")
        self.stop_btn = QPushButton("Стоп")

        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        self.setLayout(layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_data)
        self.timer.start(200)

    def start(self):
        if not self.poller.is_alive():
            self.poller.start()

    def stop(self):
        self.poller.stop()

    def update_data(self):
        while not self.queue.empty():
            msg = self.queue.get()

            if "registers" in msg:
                self.label.setText(f"Регистры: {msg['registers']}")
            elif "error" in msg:
                self.label.setText(f"Ошибка: {msg['error']}")

    def closeEvent(self, event):
        self.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ManagerGUI()
    win.show()
    sys.exit(app.exec())
