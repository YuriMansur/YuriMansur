import json, re
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QFileDialog, QProgressBar,
    QSplitter, QLabel, QFormLayout, QGroupBox
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QSize
from worker import ScanWorker

BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / "icons"

def make_valid_identifier(name: str) -> str:
    return re.sub(r'\W|^(?=\d)', '_', name)

def export_variables_from_node(node_dict: dict) -> list:
    variables = []
    if node_dict["node_class"] == "Variable":
        variables.append({"name": node_dict["browse_name"], "node_id": node_dict["node_id"]})
    for child in node_dict["children"].values():
        variables.extend(export_variables_from_node(child))
    return variables

def generate_python_module_from_subtree(node_dict: dict) -> str:
    variables = export_variables_from_node(node_dict)
    lines = ["# auto_generated_tags.py", "# Generated OPC UA tags", ""]
    for var in variables:
        var_name = make_valid_identifier(var["name"])
        node_id = var["node_id"]
        lines.append(f'{var_name} = "{node_id}"')
    return "\n".join(lines)

class OpcUaScanner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA Scanner")
        self.resize(1400, 800)

        self.worker = None
        self.scanned_data = None

        self._load_icons()
        self._build_ui()
        self._connect_signals()

    def _load_icons(self):
        self.icons = {
            "Object": QIcon(str(ICON_DIR / "object.svg")),
            "Variable": QIcon(str(ICON_DIR / "variable.svg")),
            "Number": QIcon(str(ICON_DIR / "number.svg")),
            "String": QIcon(str(ICON_DIR / "string.svg")),
            "Bool": QIcon(str(ICON_DIR / "bool.svg")),
        }

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top = QHBoxLayout()
        self.endpoint = QLineEdit("opc.tcp://localhost:4840")
        self.scan_btn = QPushButton("▶ Scan")
        self.save_json = QPushButton("💾 Save JSON")
        self.save_py = QPushButton("🐍 Export Python")
        top.addWidget(self.endpoint)
        top.addWidget(self.scan_btn)
        top.addWidget(self.save_json)
        top.addWidget(self.save_py)
        layout.addLayout(top)

        main_split = QSplitter(Qt.Orientation.Horizontal)
        left_split = QSplitter(Qt.Orientation.Vertical)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name"])
        self.tree.setIconSize(QSize(22, 22))
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        left_split.addWidget(self.tree)
        left_split.addWidget(self.log)
        self.info = self._build_info()

        main_split.addWidget(left_split)
        main_split.addWidget(self.info)

        layout.addWidget(main_split)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

    def _build_info(self):
        box = QGroupBox("Node Inspector")
        form = QFormLayout()

        self.i_name = QLabel("-")
        self.i_nodeid = QLabel("-")
        self.i_class = QLabel("-")
        self.i_ns = QLabel("-")
        self.i_dtype = QLabel("-")
        self.i_dtype_id = QLabel("-")
        self.i_enum = QLabel("-")
        self.i_access = QLabel("-")
        self.i_children = QLabel("-")

        form.addRow("BrowseName:", self.i_name)
        form.addRow("NodeId:", self.i_nodeid)
        form.addRow("NodeClass:", self.i_class)
        form.addRow("Namespace:", self.i_ns)
        form.addRow("DataType:", self.i_dtype)
        form.addRow("DataType NodeId:", self.i_dtype_id)
        form.addRow("Enumeration:", self.i_enum)
        form.addRow("Access:", self.i_access)
        form.addRow("Children:", self.i_children)

        box.setLayout(form)
        return box

    def _connect_signals(self):
        self.scan_btn.clicked.connect(self.start_scan)
        self.tree.itemSelectionChanged.connect(self.show_info)
        self.save_json.clicked.connect(self.save_selected_json)
        self.save_py.clicked.connect(self.export_python)

    def start_scan(self):
        self.tree.clear()
        self.log.clear()
        self.progress.setValue(0)

        self.worker = ScanWorker(self.endpoint.text())
        self.worker.log.connect(self.log.append)
        self.worker.error.connect(lambda e: self.log.append(f"❌ {e}"))
        self.worker.progress_value.connect(self.progress.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, data):
        self.scanned_data = data
        self._build_tree(self.tree.invisibleRootItem(), data)
        self.tree.collapseAll()
        self.progress.setValue(100)

    def _build_tree(self, parent, node):
        item = QTreeWidgetItem([node["browse_name"]])
        item.setData(0, Qt.ItemDataRole.UserRole, node["node_id"])

        cls = node["node_class"]
        dt = node.get("data_type")
        is_enum = node.get("is_enumeration", False)
        access = node.get("access_level")

        if cls == "Object":
            item.setIcon(0, self.icons["Object"])
        elif cls == "Variable":
            if is_enum:
                item.setIcon(0, self.icons["Variable"])
            elif dt == "Boolean":
                item.setIcon(0, self.icons["Bool"])
            elif dt == "String":
                item.setIcon(0, self.icons["String"])
            else:
                item.setIcon(0, self.icons["Number"])

        if access == "RW":
            item.setForeground(0, Qt.GlobalColor.darkGreen)
        elif access == "RO":
            item.setForeground(0, Qt.GlobalColor.darkBlue)

        parent.addChild(item)
        for ch in node["children"].values():
            self._build_tree(item, ch)

    def show_info(self):
        item = self.tree.currentItem()
        if not item or not self.scanned_data:
            return

        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        node = self._find(self.scanned_data, node_id)
        if not node:
            return

        self.i_name.setText(node["browse_name"])
        self.i_nodeid.setText(node["node_id"])
        self.i_class.setText(node["node_class"])
        self.i_ns.setText(node["node_id"].split(";")[0])
        self.i_children.setText(str(len(node["children"])))

        if node["node_class"] == "Variable":
            self.i_dtype.setText(node.get("data_type", ""))
            self.i_dtype_id.setText(node.get("data_type_nodeid", ""))
            self.i_enum.setText("Yes" if node.get("is_enumeration") else "No")
            self.i_access.setText(node.get("access_level", ""))
        else:
            self.i_dtype.setText("-")
            self.i_dtype_id.setText("-")
            self.i_enum.setText("-")
            self.i_access.setText("-")

    def _find(self, node, node_id):
        if node["node_id"] == node_id:
            return node
        for ch in node["children"].values():
            r = self._find(ch, node_id)
            if r:
                return r
        return None

    def save_selected_json(self):
        items = self.tree.selectedItems()
        if not items or not self.scanned_data:
            return

        node_list = []
        for item in items:
            node_id = item.data(0, Qt.ItemDataRole.UserRole)
            node = self._find(self.scanned_data, node_id)
            if node:
                node_list.append(node)

        path, _ = QFileDialog.getSaveFileName(self, "Save JSON", "", "JSON (*.json)")
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            if len(node_list) == 1:
                json.dump(node_list[0], f, indent=2, ensure_ascii=False)
            else:
                json.dump(node_list, f, indent=2, ensure_ascii=False)

    def export_python(self):
        items = self.tree.selectedItems()
        if not items or not self.scanned_data:
            return

        for item in items:
            node_id = item.data(0, Qt.ItemDataRole.UserRole)
            node = self._find(self.scanned_data, node_id)
            if not node:
                continue

            code = generate_python_module_from_subtree(node)
            path, _ = QFileDialog.getSaveFileName(self, "Save Python", "", "Python (*.py)")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(code)
