import sys
import json
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QLineEdit, QLabel, QCheckBox, QProgressBar,
    QTreeWidget, QTreeWidgetItem, QSplitter
)
from opcua import ua
from worker import ScanWorker
from generator import generate_py

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA Tag Scanner")

        # --- Endpoint ---
        self.endpoint = QLineEdit("opc.tcp://DESKTOP-MG010R1:53530/OPCUA/SimulationServer")

        # --- NodeClass фильтры ---
        self.filter_variable = QCheckBox("Variable")
        self.filter_variable.setChecked(True)
        self.filter_object = QCheckBox("Object")
        self.filter_object.setChecked(True)
        self.filter_view = QCheckBox("View")
        self.filter_view.setChecked(False)

        # --- Namespace фильтр ---
        self.namespace_label = QLabel("Namespace index (comma-separated, empty=all):")
        self.namespace_input = QLineEdit("")

        # --- Лог и прогрессбар ---
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.progress = QProgressBar()
        self.progress.setValue(0)

        # --- Дерево тегов ---
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag / Object", "NodeId"])

        # --- Кнопки ---
        self.btn_scan = QPushButton("Scan")
        self.btn_gen = QPushButton("Generate Python")
        self.btn_load = QPushButton("Load Tree from JSON")

        # --- Основной layout ---
        main_layout = QVBoxLayout(self)

        # Верхняя панель для endpoint и фильтров
        top_layout = QVBoxLayout()
        top_layout.addWidget(QLabel("Endpoint:"))
        top_layout.addWidget(self.endpoint)

        class_layout = QHBoxLayout()
        class_layout.addWidget(self.filter_variable)
        class_layout.addWidget(self.filter_object)
        class_layout.addWidget(self.filter_view)
        top_layout.addLayout(class_layout)

        top_layout.addWidget(self.namespace_label)
        top_layout.addWidget(self.namespace_input)

        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_scan)
        btn_layout.addWidget(self.btn_gen)
        btn_layout.addWidget(self.btn_load)
        top_layout.addLayout(btn_layout)

        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.progress)

        # --- Сплиттер для лога и дерева ---
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.log)
        self.splitter.addWidget(self.tree)
        self.splitter.setSizes([200, 400])
        main_layout.addWidget(self.splitter)

        # --- Сигналы ---
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_gen.clicked.connect(self.generate)
        self.btn_load.clicked.connect(self.load_tree)

    # --- Методы ---
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
        self.progress.setValue(0)

        self.worker = ScanWorker(
            self.endpoint.text(),
            "tags.json",
            node_classes=node_classes,
            namespaces=namespaces
        )
        self.worker.log.connect(self.log.append)
        self.worker.error.connect(lambda e: self.log.append(f"❌ Error: {e}"))
        self.worker.progress_value.connect(self.update_progress)
        self.worker.finished.connect(self.scan_finished)
        self.worker.start()

    def update_progress(self, value):
        if self.progress.maximum() < value:
            self.progress.setMaximum(value)
        self.progress.setValue(value)

    def scan_finished(self):
        self.log.append("✅ Scan finished")
        self.load_tree()

    def generate(self):
        generate_py("tags.json", "tags.py")
        self.log.append("🐍 Python file generated: tags.py")

    def load_tree(self):
        """Загрузить и построить рекурсивное дерево с эмодзи и закрытыми ветками"""
        self.tree.clear()
        try:
            with open("tags.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            self.build_tree(self.tree.invisibleRootItem(), data.get("Objects", {}))
            self.log.append("🌳 Full tree loaded (branches closed)")
        except Exception as e:
            self.log.append(f"❌ Failed to load tree: {e}")

    def build_tree(self, parent_item, data):
        """Рекурсивное построение дерева с эмодзи для NodeClass"""
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            node_id = v.get("node_id", "")
            node_class = v.get("node_class", "Variable")

            # Эмодзи
            prefix = ""
            if node_class == "Object":
                prefix = "📁 "
            elif node_class == "Variable":
                prefix = "📄 "
            elif node_class == "View":
                prefix = "🔍 "

            item = QTreeWidgetItem([prefix + k, node_id])
            parent_item.addChild(item)

            children = {kk: vv for kk, vv in v.items() if isinstance(vv, dict)}
            if children:
                self.build_tree(item, children)


# --- Запуск приложения ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = App()
    win.resize(1000, 700)
    win.show()
    sys.exit(app.exec())
