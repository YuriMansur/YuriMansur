import sys
import asyncio
from asyncua import Client
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit
)
from PyQt6.QtCore import QThread, pyqtSignal


class OpcReadThread(QThread):
    result = pyqtSignal(str)

    def __init__(self, url, node_id):
        super().__init__()
        self.url = url
        self.node_id = node_id

    def run(self):
        async def _read():
            try:
                async with Client(url=self.url) as client:
                    node = client.get_node(self.node_id)
                    value = await node.read_value()
                    self.result.emit(f"[{self.node_id}] = {value}")
            except Exception as e:
                self.result.emit(f"Ошибка: {e}")

        asyncio.run(_read())


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA Reader")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        for label, placeholder, attr in [
            ("Адрес сервера:", "opc.tcp://localhost:4840", "url_edit"),
            ("Node ID:",       "ns=2;i=2",                 "node_edit"),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            edit = QLineEdit(placeholder)
            row.addWidget(edit)
            setattr(self, attr, edit)
            layout.addLayout(row)

        self.btn = QPushButton("Читать")
        self.btn.clicked.connect(self.read_tag)
        layout.addWidget(self.btn)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120)
        layout.addWidget(self.log)

    def read_tag(self):
        self.btn.setEnabled(False)
        self.log.append("Подключение...")
        t = OpcReadThread(self.url_edit.text(), self.node_edit.text())
        t.result.connect(self._on_result)
        t.finished.connect(lambda: self.btn.setEnabled(True))
        t.start()
        self._thread = t  # keep reference

    def _on_result(self, msg):
        self.log.append(msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
