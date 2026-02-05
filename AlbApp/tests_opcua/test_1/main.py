import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel, QCheckBox, QProgressBar
)
from opcua import ua
from worker import ScanWorker
from generator import generate_py

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA Tag Scanner")

        # Endpoint
        self.endpoint = QLineEdit("opc.tcp://DESKTOP-MG010R1:53530/OPCUA/SimulationServer")

        # Фильтр NodeClass
        self.filter_variable = QCheckBox("Variable")
        self.filter_variable.setChecked(True)
        self.filter_object = QCheckBox("Object")
        self.filter_object.setChecked(True)
        self.filter_view = QCheckBox("View")
        self.filter_view.setChecked(False)

        # Namespace фильтр
        self.namespace_label = QLabel("Namespace index (comma-separated, empty=all):")
        self.namespace_input = QLineEdit("")

        # Лог и прогрессбар
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Индикатор бесконечного прогресса

        # Кнопки
        self.btn_scan = QPushButton("Scan")
        self.btn_gen = QPushButton("Generate Python")

        # Layout
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Endpoint:"))
        layout.addWidget(self.endpoint)

        class_layout = QHBoxLayout()
        class_layout.addWidget(self.filter_variable)
        class_layout.addWidget(self.filter_object)
        class_layout.addWidget(self.filter_view)
        layout.addLayout(class_layout)

        layout.addWidget(self.namespace_label)
        layout.addWidget(self.namespace_input)
        layout.addWidget(self.btn_scan)
        layout.addWidget(self.btn_gen)
        layout.addWidget(self.log)
        layout.addWidget(self.progress)

        # Signals
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_gen.clicked.connect(self.generate)

    def start_scan(self):
        node_classes = []
        if self.filter_variable.isChecked():
            node_classes.append(ua.NodeClass.Variable)
        if self.filter_object.isChecked():
            node_classes.append(ua.NodeClass.Object)
        if self.filter_view.isChecked():
            node_classes.append(ua.NodeClass.View)

        ns_text = self.namespace_input.text().strip()
        if ns_text:
            try:
                namespaces = [int(x) for x in ns_text.split(",")]
            except Exception:
                self.log.append("❌ Invalid namespace input")
                return
        else:
            namespaces = None

        self.log.append(f"▶ Scan started: {self.endpoint.text()}")
        self.progress.setRange(0, 0)  # бесконечный прогресс

        self.worker = ScanWorker(
            self.endpoint.text(),
            "tags.json",
            node_classes=node_classes,
            namespaces=namespaces
        )
        self.worker.log.connect(self.log.append)
        self.worker.error.connect(lambda e: self.log.append(f"❌ Error: {e}"))
        self.worker.finished.connect(self.scan_finished)
        self.worker.start()

    def scan_finished(self):
        self.log.append("✅ Scan finished")
        self.progress.setRange(0, 1)
        self.progress.setValue(1)

    def generate(self):
        generate_py("tags.json", "tags.py")
        self.log.append("🐍 Python file generated: tags.py")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = App()
    win.resize(900, 600)
    win.show()
    sys.exit(app.exec())
