import sys, json
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QFileDialog, QProgressBar, QSplitter, QLabel, QFormLayout, QGroupBox
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QSize
from worker import ScanWorker

BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / "icons"

class OpcUaScanner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA Scanner")
        self.resize(1300, 700)
        self.scanned_data = None
        self.worker = None

        self._load_icons()
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        top = QHBoxLayout()
        self.endpoint_edit = QLineEdit("opc.tcp://DESKTOP-MG010R1:53530/OPCUA/SimulationServer")
        self.scan_btn = QPushButton("▶ Scan")
        self.save_json_btn = QPushButton("💾 Save selected → JSON")
        self.save_py_btn = QPushButton("🐍 Generate Python code")
        top.addWidget(self.endpoint_edit)
        top.addWidget(self.scan_btn)
        top.addWidget(self.save_json_btn)
        top.addWidget(self.save_py_btn)
        main_layout.addLayout(top)

        splitter_main = QSplitter(Qt.Orientation.Horizontal)
        left_splitter = QSplitter(Qt.Orientation.Vertical)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "NodeId"])
        self.tree.setIconSize(QSize(24, 24))
        left_splitter.addWidget(self.tree)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        left_splitter.addWidget(self.log)

        left_splitter.setStretchFactor(0, 3)
        left_splitter.setStretchFactor(1, 1)
        splitter_main.addWidget(left_splitter)

        self.info_box = QGroupBox("Tag Parameters")
        info_layout = QFormLayout()
        self.lbl_nodeid = QLabel("")
        self.lbl_browsename = QLabel("")
        self.lbl_nodeclass = QLabel("")
        self.lbl_datatype = QLabel("")
        self.lbl_access = QLabel("")
        info_layout.addRow("NodeId:", self.lbl_nodeid)
        info_layout.addRow("BrowseName:", self.lbl_browsename)
        info_layout.addRow("NodeClass:", self.lbl_nodeclass)
        info_layout.addRow("DataType:", self.lbl_datatype)
        info_layout.addRow("Access:", self.lbl_access)
        self.info_box.setLayout(info_layout)
        splitter_main.addWidget(self.info_box)

        splitter_main.setStretchFactor(0, 3)
        splitter_main.setStretchFactor(1, 1)
        main_layout.addWidget(splitter_main)

        self.progress = QProgressBar()
        main_layout.addWidget(self.progress)

        self.scan_btn.clicked.connect(self.start_scan)
        self.save_json_btn.clicked.connect(self.save_selected_json)
        self.save_py_btn.clicked.connect(self.generate_python_code)
        self.tree.itemSelectionChanged.connect(self.show_tag_info)

    def _load_icons(self):
        self.icons = {
            "Object": QIcon(str(ICON_DIR / "object.svg")),
            "Variable": QIcon(str(ICON_DIR / "variable.svg")),
            "Number": QIcon(str(ICON_DIR / "number.svg")),
            "String": QIcon(str(ICON_DIR / "string.svg")),
            "Bool": QIcon(str(ICON_DIR / "bool.svg")),
        }

    def start_scan(self):
        endpoint = self.endpoint_edit.text().strip()
        if not endpoint.startswith("opc.tcp://"):
            self._log("❌ Invalid endpoint")
            return

        self.tree.clear()
        self.progress.setValue(0)
        self.log.clear()
        self.scanned_data = None

        self.worker = ScanWorker(endpoint)
        self.worker.log.connect(self._log)
        self.worker.error.connect(lambda e: self._log(f"❌ {e}"))
        self.worker.progress_value.connect(self.progress.setValue)
        self.worker.finished.connect(self.scan_finished)
        self.worker.start()

    def scan_finished(self, data):
        self.scanned_data = data
        self.build_tree(self.tree.invisibleRootItem(), data)
        self.tree.collapseAll()
        self._log("✅ Scan completed")
        self.progress.setValue(100)

    def build_tree(self, parent_item, data):
        if not data:
            return
        name = data.get("browse_name", "Unknown")
        nodeid = data.get("node_id", "")
        cls = data.get("node_class", "Variable")
        dt = data.get("data_type")
        access = data.get("access_level", "Unknown")

        item = QTreeWidgetItem([name, nodeid])

        # ---------- Иконки ----------
        if cls == "Object":
            item.setIcon(0, self.icons.get("Object"))
        elif cls == "Variable":
            if dt == "Boolean":
                item.setIcon(0, self.icons.get("Bool"))
            elif dt in ["SByte","Byte","Int16","UInt16","Int32","UInt32","Int64","UInt64","Float","Double"]:
                item.setIcon(0, self.icons.get("Number"))
            elif dt == "String":
                item.setIcon(0, self.icons.get("String"))
            elif dt == "Enumeration":
                item.setIcon(0, self.icons.get("Variable"))
            else:
                item.setIcon(0, self.icons.get("Variable"))
        else:
            item.setIcon(0, self.icons.get(cls, self.icons.get("Variable")))

        # ---------- Цвет по Access Level ----------
        if access == "RW":
            item.setForeground(0, Qt.GlobalColor.green)
        elif access == "RO":
            item.setForeground(0, Qt.GlobalColor.blue)
        else:
            item.setForeground(0, Qt.GlobalColor.black)

        parent_item.addChild(item)

        for child_data in data.get("children", {}).values():
            self.build_tree(item, child_data)

    def show_tag_info(self):
        items = self.tree.selectedItems()
        if not items or not self.scanned_data:
            return
        item = items[0]
        node_id = item.text(1)

        def find_data(node):
            if node.get("node_id") == node_id:
                return node
            for child in node.get("children", {}).values():
                res = find_data(child)
                if res:
                    return res
            return None

        data = find_data(self.scanned_data)
        if not data:
            return

        self.lbl_nodeid.setText(data.get("node_id", ""))
        self.lbl_browsename.setText(data.get("browse_name", ""))
        self.lbl_nodeclass.setText(data.get("node_class", ""))
        self.lbl_datatype.setText(str(data.get("data_type", "")))
        self.lbl_access.setText(str(data.get("access_level", "")))

    def save_selected_json(self):
        items = self.tree.selectedItems()
        if not items or not self.scanned_data:
            self._log("⚠ Nothing selected or no data")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save JSON", "", "JSON (*.json)")
        if not path:
            return

        def export(item):
            node_id = item.text(1)
            def find_data(node):
                if node.get("node_id") == node_id:
                    return node
                for child in node.get("children", {}).values():
                    res = find_data(child)
                    if res:
                        return res
                return None
            return find_data(self.scanned_data)

        data = [export(item) for item in items]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._log(f"💾 Saved JSON: {path}")

    def generate_python_code(self):
        items = self.tree.selectedItems()
        if not items or not self.scanned_data:
            self._log("⚠ Nothing selected or no data")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save Python", "", "Python (*.py)")
        if not path:
            return

        lines = []

        def walk(item, prefix=""):
            name = item.text(0).replace(" ", "_")
            var_name = f"{prefix}_{name}" if prefix else name
            lines.append(f'{var_name} = "{item.text(1)}"')
            for i in range(item.childCount()):
                walk(item.child(i), var_name)

        for item in items:
            walk(item)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        for line in lines:
            self._log(f"🐍 {line}")

    def _log(self, text):
        self.log.append(text)
        


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = OpcUaScanner()
    win.show()
    sys.exit(app.exec())
