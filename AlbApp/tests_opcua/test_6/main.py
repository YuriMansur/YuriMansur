import sys
import json
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel,
    QCheckBox, QProgressBar, QTreeWidget,
    QTreeWidgetItem, QSplitter
)
from opcua import ua
from worker import ScanWorker


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA Scanner")
        self.resize(1100, 700)

        self.scanned_data = None

        # ---------- UI ----------
        self.endpoint_edit = QLineEdit(
            "opc.tcp://DESKTOP-MG010R1:53530/OPCUA/SimulationServer"
        )

        self.cb_object = QCheckBox("Object")
        self.cb_object.setChecked(True)
        self.cb_variable = QCheckBox("Variable")
        self.cb_variable.setChecked(True)
        self.cb_view = QCheckBox("View")

        self.btn_scan = QPushButton("▶ Scan")
        self.btn_save_json = QPushButton("💾 Save selected to JSON")
        self.btn_gen_py = QPushButton("🐍 Generate Python for selected")

        self.progress = QProgressBar()
        self.progress.setValue(0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "NodeId"])

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        # ---------- Layout ----------
        top = QVBoxLayout()
        top.addWidget(QLabel("Endpoint:"))
        top.addWidget(self.endpoint_edit)

        flt = QHBoxLayout()
        flt.addWidget(self.cb_object)
        flt.addWidget(self.cb_variable)
        flt.addWidget(self.cb_view)
        top.addLayout(flt)

        btns = QHBoxLayout()
        btns.addWidget(self.btn_scan)
        btns.addWidget(self.btn_save_json)
        btns.addWidget(self.btn_gen_py)
        top.addLayout(btns)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.log)
        splitter.setSizes([450, 250])

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.progress)
        layout.addWidget(splitter)

        # ---------- Signals ----------
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_save_json.clicked.connect(self.save_selected_json)
        self.btn_gen_py.clicked.connect(self.generate_python)

    # ==========================================================
    # Scan
    # ==========================================================
    def start_scan(self):
        self.tree.clear()
        self.log.clear()
        self.progress.setValue(0)

        classes = []
        if self.cb_object.isChecked():
            classes.append(ua.NodeClass.Object)
        if self.cb_variable.isChecked():
            classes.append(ua.NodeClass.Variable)
        if self.cb_view.isChecked():
            classes.append(ua.NodeClass.View)

        self.worker = ScanWorker(
            self.endpoint_edit.text(),
            node_classes=classes
        )
        self.worker.log.connect(self.log.append)
        self.worker.error.connect(lambda e: self.log.append(f"❌ {e}"))
        self.worker.progress_value.connect(self.progress.setValue)
        self.worker.finished.connect(self.scan_finished)
        self.worker.start()

    def scan_finished(self, data: dict):
        self.scanned_data = data
        self.build_tree(self.tree.invisibleRootItem(), data["Objects"])
        self.tree.collapseAll()
        self.log.append("✅ Scan completed")

    # ==========================================================
    # Tree
    # ==========================================================
    def build_tree(self, parent, data: dict):
        for name, node in data.items():
            node_id = node.get("node_id", "")
            cls = node.get("node_class", "Variable")

            icon = "📄"
            if cls == "Object":
                icon = "📁"
            elif cls == "View":
                icon = "🔍"

            item = QTreeWidgetItem([f"{icon} {name}", node_id])
            parent.addChild(item)

            children = {
                k: v for k, v in node.items()
                if isinstance(v, dict) and "node_id" in v
            }
            if children:
                self.build_tree(item, children)

    # ==========================================================
    # Save selected JSON
    # ==========================================================
    def save_selected_json(self):
        item = self.tree.currentItem()
        if not item:
            self.log.append("❌ Select a node")
            return

        def export(item):
            name = item.text(0)[2:]
            out = {
                "node_id": item.text(1),
                "node_class": self.node_class_from_icon(item.text(0))
            }
            for i in range(item.childCount()):
                out[item.child(i).text(0)[2:]] = export(item.child(i))
            return out

        data = export(item)

        with open("selected_node.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.log.append("💾 selected_node.json saved")

    # ==========================================================
    # Generate Python
    # ==========================================================
    def generate_python(self):
        item = self.tree.currentItem()
        if not item:
            self.log.append("❌ Select a node")
            return

        lines = []

        def walk(it, prefix=""):
            name = it.text(0)[2:].replace(" ", "_")
            var = f"{prefix}_{name}" if prefix else name
            lines.append(f'{var} = "{it.text(1)}"')
            for i in range(it.childCount()):
                walk(it.child(i), var)

        walk(item)

        with open("selected_nodes.py", "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        for l in lines:
            self.log.append(f"🐍 {l}")

    # ==========================================================
    def node_class_from_icon(self, text: str) -> str:
        if text.startswith("📁"):
            return "Object"
        if text.startswith("🔍"):
            return "View"
        return "Variable"


# ==============================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = App()
    win.show()
    sys.exit(app.exec())
