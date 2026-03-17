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


def _selectable_label(text: str = "-") -> QLabel:
    """QLabel с возможностью выделения и копирования текста мышью."""
    lbl = QLabel(text)
    lbl.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse |
        Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    lbl.setCursor(Qt.CursorShape.IBeamCursor)
    return lbl


class OpcUaScanner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA Scanner")
        self.resize(1400, 800)

        self.worker = None
        self.scanned_data = None
        self._block_item_changed = False  # защита от рекурсии при каскадном check

        self._load_icons()
        self._build_ui()
        self._connect_signals()

    def _load_icons(self):
        self.icons = {
            "Object":   QIcon(str(ICON_DIR / "object.svg")),
            "Variable": QIcon(str(ICON_DIR / "variable.svg")),
            "Number":   QIcon(str(ICON_DIR / "number.svg")),
            "String":   QIcon(str(ICON_DIR / "string.svg")),
            "Bool":     QIcon(str(ICON_DIR / "bool.svg")),
        }

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ── Верхняя панель: адрес + кнопки управления ─────────────────────────
        top = QHBoxLayout()
        self.endpoint = QLineEdit("opc.tcp://192.168.6.6:4840")
        self.scan_btn = QPushButton("▶ Scan")
        top.addWidget(self.endpoint)
        top.addWidget(self.scan_btn)
        layout.addLayout(top)

        # ── Панель чекбоксов и экспорта ────────────────────────────────────────
        check_bar = QHBoxLayout()

        self.check_all_btn   = QPushButton("☑ Отметить все")
        self.uncheck_all_btn = QPushButton("☐ Снять все")
        self.check_sel_btn   = QPushButton("☑ Отметить выбранные")

        self.save_json = QPushButton("💾 Экспорт JSON")
        self.save_py   = QPushButton("🐍 Экспорт Python")

        check_bar.addWidget(self.check_all_btn)
        check_bar.addWidget(self.uncheck_all_btn)
        check_bar.addWidget(self.check_sel_btn)
        check_bar.addStretch()
        check_bar.addWidget(self.save_json)
        check_bar.addWidget(self.save_py)
        layout.addLayout(check_bar)

        # ── Основная область: дерево / лог / инспектор ────────────────────────
        main_split = QSplitter(Qt.Orientation.Horizontal)
        left_split = QSplitter(Qt.Orientation.Vertical)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Узел / Тег"])
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
        """
        Панель Node Inspector.
        Все поля — QLabel с флагом TextSelectableByMouse,
        поэтому любой текст можно выделить и скопировать.
        """
        box = QGroupBox("Node Inspector  (текст можно выделять и копировать)")
        form = QFormLayout()

        self.i_name      = _selectable_label()
        self.i_nodeid    = _selectable_label()
        self.i_class     = _selectable_label()
        self.i_ns        = _selectable_label()
        self.i_dtype     = _selectable_label()
        self.i_dtype_id  = _selectable_label()
        self.i_enum      = _selectable_label()
        self.i_access    = _selectable_label()
        self.i_children  = _selectable_label()

        form.addRow("BrowseName:",       self.i_name)
        form.addRow("NodeId:",           self.i_nodeid)
        form.addRow("NodeClass:",        self.i_class)
        form.addRow("Namespace:",        self.i_ns)
        form.addRow("DataType:",         self.i_dtype)
        form.addRow("DataType NodeId:",  self.i_dtype_id)
        form.addRow("Enumeration:",      self.i_enum)
        form.addRow("Access:",           self.i_access)
        form.addRow("Children:",         self.i_children)

        box.setLayout(form)
        return box

    def _connect_signals(self):
        self.scan_btn.clicked.connect(self.start_scan)
        self.tree.itemSelectionChanged.connect(self.show_info)
        self.tree.itemChanged.connect(self._on_item_changed)

        self.check_all_btn.clicked.connect(self._check_all)
        self.uncheck_all_btn.clicked.connect(self._uncheck_all)
        self.check_sel_btn.clicked.connect(self._check_selected)

        self.save_json.clicked.connect(self.save_checked_json)
        self.save_py.clicked.connect(self.export_python)

    # ==========================================================================
    # SCAN
    # ==========================================================================

    def start_scan(self):
        if getattr(self, "worker", None) is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()

        self.tree.clear()
        self.log.clear()
        self.progress.setMaximum(0)
        self.progress.setValue(0)
        self.progress.setFormat("Scanning... %v nodes")
        self.scan_btn.setEnabled(False)

        self.worker = ScanWorker(self.endpoint.text())
        self.worker.log.connect(self.log.append)
        self.worker.error.connect(self.on_error)
        self.worker.progress_value.connect(self.progress.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_error(self, message):
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setFormat("Error")
        self.log.append(f"❌ {message}")
        self.scan_btn.setEnabled(True)

    def closeEvent(self, event):
        if getattr(self, "worker", None) is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        event.accept()

    def on_finished(self, data):
        self.scanned_data = data
        self._build_tree(self.tree.invisibleRootItem(), data)
        self.tree.collapseAll()
        self.progress.setMaximum(100)
        self.progress.setValue(100)
        self.progress.setFormat("Done")
        self.scan_btn.setEnabled(True)

    # ==========================================================================
    # TREE BUILD
    # ==========================================================================

    def _build_tree(self, parent, node):
        item = QTreeWidgetItem([node["browse_name"]])
        item.setData(0, Qt.ItemDataRole.UserRole, node["node_id"])

        # Чекбокс на каждом узле
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Unchecked)

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

    # ==========================================================================
    # CHECKBOX LOGIC
    # ==========================================================================

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """
        Каскадное распространение состояния чекбокса на дочерние узлы.
        При изменении родителя — все потомки получают то же состояние.
        """
        if column != 0 or self._block_item_changed:
            return
        self._block_item_changed = True
        self._set_children_check(item, item.checkState(0))
        self._block_item_changed = False

    def _set_children_check(self, item: QTreeWidgetItem, state: Qt.CheckState):
        """Рекурсивно выставить состояние чекбокса всем потомкам."""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_children_check(child, state)

    def _check_all(self):
        """Отметить все узлы дерева."""
        self._block_item_changed = True
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item.setCheckState(0, Qt.CheckState.Checked)
            self._set_children_check(item, Qt.CheckState.Checked)
        self._block_item_changed = False

    def _uncheck_all(self):
        """Снять отметки со всех узлов."""
        self._block_item_changed = True
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self._set_children_check(item, Qt.CheckState.Unchecked)
        self._block_item_changed = False

    def _check_selected(self):
        """Отметить галочками текущие выделенные (подсвеченные) элементы."""
        self._block_item_changed = True
        for item in self.tree.selectedItems():
            item.setCheckState(0, Qt.CheckState.Checked)
            self._set_children_check(item, Qt.CheckState.Checked)
        self._block_item_changed = False

    def _get_checked_items(self) -> list:
        """Собрать все элементы дерева с выставленной галочкой."""
        checked = []

        def collect(item: QTreeWidgetItem):
            if item.checkState(0) == Qt.CheckState.Checked:
                checked.append(item)
            for i in range(item.childCount()):
                collect(item.child(i))

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            collect(root.child(i))
        return checked

    # ==========================================================================
    # INSPECTOR
    # ==========================================================================

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

    # ==========================================================================
    # EXPORT
    # ==========================================================================

    def save_checked_json(self):
        """Сохранить отмеченные галочкой узлы в JSON файл."""
        items = self._get_checked_items()
        if not items or not self.scanned_data:
            self.log.append("⚠ Нет отмеченных узлов для экспорта.")
            return

        node_list = []
        for item in items:
            node_id = item.data(0, Qt.ItemDataRole.UserRole)
            node = self._find(self.scanned_data, node_id)
            if node:
                node_list.append(node)

        path, _ = QFileDialog.getSaveFileName(self, "Сохранить JSON", "", "JSON (*.json)")
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            if len(node_list) == 1:
                json.dump(node_list[0], f, indent=2, ensure_ascii=False)
            else:
                json.dump(node_list, f, indent=2, ensure_ascii=False)

        self.log.append(f"✅ JSON сохранён: {path}  ({len(node_list)} узлов)")

    def export_python(self):
        """Сохранить отмеченные галочкой узлы как Python-файл с константами тегов."""
        items = self._get_checked_items()
        if not items or not self.scanned_data:
            self.log.append("⚠ Нет отмеченных узлов для экспорта.")
            return

        # Собираем все переменные из всех отмеченных поддеревьев
        all_variables = []
        seen_ids = set()
        for item in items:
            node_id = item.data(0, Qt.ItemDataRole.UserRole)
            node = self._find(self.scanned_data, node_id)
            if not node:
                continue
            for var in export_variables_from_node(node):
                if var["node_id"] not in seen_ids:
                    seen_ids.add(var["node_id"])
                    all_variables.append(var)

        if not all_variables:
            self.log.append("⚠ В отмеченных узлах нет переменных (Variable) для экспорта.")
            return

        lines = ["# auto_generated_tags.py", "# Generated OPC UA tags", ""]
        for var in all_variables:
            var_name = make_valid_identifier(var["name"])
            lines.append(f'{var_name} = "{var["node_id"]}"')
        code = "\n".join(lines)

        path, _ = QFileDialog.getSaveFileName(self, "Сохранить Python", "", "Python (*.py)")
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            f.write(code)

        self.log.append(f"✅ Python сохранён: {path}  ({len(all_variables)} переменных)")
