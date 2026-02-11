"""
Test GUI для CommunicationManager

Простой интерфейс для тестирования Modbus TCP и OPC UA устройств.

ЗАПУСК:
    cd YuriMansur
    python -m AlbApp.unified_backend_package.test_gui
"""

import sys
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QSplitter,
    QTabWidget, QSpinBox, QHeaderView, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

# Добавляем корневую папку в sys.path
_root_dir = Path(__file__).parent.parent.parent  # YuriMansur/
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

from AlbApp.unified_backend_package.communication_manager import CommunicationManager


class TestGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Communication Manager - Test GUI")
        self.setMinimumSize(900, 650)

        self.manager = CommunicationManager()
        self._connect_signals()

        self._build_ui()
        self._setup_refresh_timer()

    # ======================================================================
    # UI BUILD
    # ======================================================================

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        # --- Top: tabs ---
        tabs = QTabWidget()
        tabs.addTab(self._build_device_tab(), "Устройства")
        tabs.addTab(self._build_rw_tab(), "Чтение / Запись")
        splitter.addWidget(tabs)

        # --- Bottom: log ---
        log_group = QGroupBox("Лог событий")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(180)
        log_layout.addWidget(self.log_text)
        splitter.addWidget(log_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

    # ---------- Device tab ----------

    def _build_device_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- Add device form ---
        add_group = QGroupBox("Добавить устройство")
        form = QHBoxLayout(add_group)

        form.addWidget(QLabel("ID:"))
        self.dev_id_input = QLineEdit("PLC1")
        self.dev_id_input.setMaximumWidth(100)
        form.addWidget(self.dev_id_input)

        form.addWidget(QLabel("Тип:"))
        self.dev_type_combo = QComboBox()
        self.dev_type_combo.addItems(["modbus", "opcua"])
        self.dev_type_combo.currentTextChanged.connect(self._on_type_changed)
        form.addWidget(self.dev_type_combo)

        form.addWidget(QLabel("Host / Endpoint:"))
        self.host_input = QLineEdit("127.0.0.1")
        form.addWidget(self.host_input)

        form.addWidget(QLabel("Port:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(502)
        self.port_input.setMaximumWidth(80)
        form.addWidget(self.port_input)

        btn_add = QPushButton("Добавить")
        btn_add.clicked.connect(self._add_device)
        form.addWidget(btn_add)

        layout.addWidget(add_group)

        # --- Device table ---
        self.dev_table = QTableWidget(0, 5)
        self.dev_table.setHorizontalHeaderLabels(
            ["ID", "Тип", "Адрес", "Статус", "Действие"]
        )
        self.dev_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.dev_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        layout.addWidget(self.dev_table)

        # --- Data table ---
        data_group = QGroupBox("Данные (real-time)")
        data_layout = QVBoxLayout(data_group)
        self.data_table = QTableWidget(0, 4)
        self.data_table.setHorizontalHeaderLabels(
            ["Устройство", "Тег / Poll", "Значение", "Время"]
        )
        self.data_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        data_layout.addWidget(self.data_table)
        layout.addWidget(data_group)

        return widget

    # ---------- Read/Write tab ----------

    def _build_rw_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- Tag subscribe ---
        sub_group = QGroupBox("Подписка на тег")
        sub_layout = QHBoxLayout(sub_group)

        sub_layout.addWidget(QLabel("Устройство:"))
        self.sub_dev_combo = QComboBox()
        sub_layout.addWidget(self.sub_dev_combo)

        sub_layout.addWidget(QLabel("Тег:"))
        self.sub_tag_input = QLineEdit("Temperature")
        sub_layout.addWidget(self.sub_tag_input)

        sub_layout.addWidget(QLabel("Reg/Node:"))
        self.sub_config_input = QLineEdit("holding:0:2:float32:1000")
        self.sub_config_input.setToolTip(
            "Modbus: reg_type:address:count:format:interval\n"
            "OPC UA: ns=2;s=Temperature"
        )
        sub_layout.addWidget(self.sub_config_input)

        btn_sub = QPushButton("Подписаться")
        btn_sub.clicked.connect(self._subscribe_tag)
        sub_layout.addWidget(btn_sub)

        layout.addWidget(sub_group)

        # --- Read ---
        read_group = QGroupBox("Чтение")
        read_layout = QHBoxLayout(read_group)

        read_layout.addWidget(QLabel("Устройство:"))
        self.read_dev_combo = QComboBox()
        read_layout.addWidget(self.read_dev_combo)

        read_layout.addWidget(QLabel("Тег:"))
        self.read_tag_input = QLineEdit("Temperature")
        read_layout.addWidget(self.read_tag_input)

        btn_read = QPushButton("Читать")
        btn_read.clicked.connect(self._read_tag)
        read_layout.addWidget(btn_read)

        self.read_result_label = QLabel("---")
        self.read_result_label.setStyleSheet("font-weight: bold; color: #0066cc;")
        read_layout.addWidget(self.read_result_label)

        layout.addWidget(read_group)

        # --- Write ---
        write_group = QGroupBox("Запись")
        write_layout = QHBoxLayout(write_group)

        write_layout.addWidget(QLabel("Устройство:"))
        self.write_dev_combo = QComboBox()
        write_layout.addWidget(self.write_dev_combo)

        write_layout.addWidget(QLabel("Тег:"))
        self.write_tag_input = QLineEdit("Temperature")
        write_layout.addWidget(self.write_tag_input)

        write_layout.addWidget(QLabel("Значение:"))
        self.write_value_input = QLineEdit("0")
        self.write_value_input.setMaximumWidth(100)
        write_layout.addWidget(self.write_value_input)

        btn_write = QPushButton("Записать")
        btn_write.clicked.connect(self._write_tag)
        write_layout.addWidget(btn_write)

        layout.addWidget(write_group)

        # --- Modbus direct register ---
        reg_group = QGroupBox("Modbus - прямые регистры")
        reg_layout = QHBoxLayout(reg_group)

        reg_layout.addWidget(QLabel("Устройство:"))
        self.reg_dev_combo = QComboBox()
        reg_layout.addWidget(self.reg_dev_combo)

        reg_layout.addWidget(QLabel("Тип:"))
        self.reg_type_combo = QComboBox()
        self.reg_type_combo.addItems(["holding", "input", "coil", "discrete"])
        reg_layout.addWidget(self.reg_type_combo)

        reg_layout.addWidget(QLabel("Адрес:"))
        self.reg_addr_input = QSpinBox()
        self.reg_addr_input.setRange(0, 65535)
        reg_layout.addWidget(self.reg_addr_input)

        reg_layout.addWidget(QLabel("Кол-во:"))
        self.reg_count_input = QSpinBox()
        self.reg_count_input.setRange(1, 125)
        self.reg_count_input.setValue(1)
        reg_layout.addWidget(self.reg_count_input)

        btn_read_reg = QPushButton("Читать")
        btn_read_reg.clicked.connect(self._read_register)
        reg_layout.addWidget(btn_read_reg)

        self.reg_result_label = QLabel("---")
        self.reg_result_label.setStyleSheet("font-weight: bold; color: #0066cc;")
        reg_layout.addWidget(self.reg_result_label)

        layout.addWidget(reg_group)

        layout.addStretch()
        return widget

    # ======================================================================
    # SIGNAL CONNECTIONS
    # ======================================================================

    def _connect_signals(self):
        self.manager.device_connected.connect(self._on_device_connected)
        self.manager.device_disconnected.connect(self._on_device_disconnected)
        self.manager.device_error.connect(self._on_device_error)
        self.manager.tag_updated.connect(self._on_tag_updated)
        self.manager.register_updated.connect(self._on_register_updated)

    # ======================================================================
    # ACTIONS
    # ======================================================================

    def _on_type_changed(self, dev_type):
        if dev_type == "modbus":
            self.host_input.setText("127.0.0.1")
            self.port_input.setValue(502)
            self.port_input.setEnabled(True)
        else:
            self.host_input.setText("opc.tcp://127.0.0.1:4840")
            self.port_input.setEnabled(False)

    def _add_device(self):
        dev_id = self.dev_id_input.text().strip()
        dev_type = self.dev_type_combo.currentText()
        host = self.host_input.text().strip()
        port = self.port_input.value()

        if not dev_id or not host:
            return

        if dev_type == "modbus":
            config = {"host": host, "port": port, "device_id": 1}
        else:
            config = {"endpoint": host, "namespace": 2}

        ok = self.manager.add_device(dev_id, dev_type, config)
        if ok:
            self._add_device_row(dev_id, dev_type, host, port)
            self._update_combos()
            self._log(f"Добавлено: {dev_id} ({dev_type}) -> {host}")
        else:
            self._log(f"Ошибка: устройство {dev_id} уже существует")

    def _add_device_row(self, dev_id, dev_type, host, port):
        row = self.dev_table.rowCount()
        self.dev_table.insertRow(row)

        self.dev_table.setItem(row, 0, QTableWidgetItem(dev_id))
        self.dev_table.setItem(row, 1, QTableWidgetItem(dev_type))

        addr = host if dev_type == "opcua" else f"{host}:{port}"
        self.dev_table.setItem(row, 2, QTableWidgetItem(addr))

        status_item = QTableWidgetItem("Отключено")
        status_item.setForeground(QColor("#cc0000"))
        self.dev_table.setItem(row, 3, status_item)

        # Action buttons
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(2, 2, 2, 2)

        btn_connect = QPushButton("Connect")
        btn_connect.setStyleSheet("background-color: #4CAF50; color: white; padding: 2px 8px;")
        btn_connect.clicked.connect(lambda _, d=dev_id: self._connect_device(d))
        btn_layout.addWidget(btn_connect)

        btn_disconnect = QPushButton("Disconnect")
        btn_disconnect.setStyleSheet("background-color: #f44336; color: white; padding: 2px 8px;")
        btn_disconnect.clicked.connect(lambda _, d=dev_id: self._disconnect_device(d))
        btn_layout.addWidget(btn_disconnect)

        btn_remove = QPushButton("X")
        btn_remove.setMaximumWidth(30)
        btn_remove.setStyleSheet("background-color: #888; color: white; padding: 2px;")
        btn_remove.clicked.connect(lambda _, d=dev_id: self._remove_device(d))
        btn_layout.addWidget(btn_remove)

        self.dev_table.setCellWidget(row, 4, btn_widget)

    def _connect_device(self, dev_id):
        self._log(f"Подключение к {dev_id}...")
        self.manager.connect_device(dev_id)

    def _disconnect_device(self, dev_id):
        self._log(f"Отключение от {dev_id}...")
        self.manager.disconnect_device(dev_id)

    def _remove_device(self, dev_id):
        self.manager.remove_device(dev_id, force=True)
        # Remove row from table
        for row in range(self.dev_table.rowCount()):
            item = self.dev_table.item(row, 0)
            if item and item.text() == dev_id:
                self.dev_table.removeRow(row)
                break
        self._update_combos()
        self._log(f"Удалено: {dev_id}")

    def _subscribe_tag(self):
        dev_id = self.sub_dev_combo.currentText()
        tag_name = self.sub_tag_input.text().strip()
        config_str = self.sub_config_input.text().strip()

        if not dev_id or not tag_name:
            return

        # Parse config
        tag_config = self._parse_tag_config(dev_id, config_str)

        ok = self.manager.subscribe_tag(dev_id, tag_name, tag_config)
        if ok:
            self._log(f"Подписка: {dev_id}.{tag_name}")
        else:
            self._log(f"Ошибка подписки: {dev_id}.{tag_name}")

    def _parse_tag_config(self, dev_id, config_str):
        """Parse tag config string into dict."""
        info = self.manager.get_device_info(dev_id)
        if not info:
            return None

        if info["type"] == "modbus":
            # Format: reg_type:address:count:format:interval
            parts = config_str.split(":")
            if len(parts) >= 2:
                return {
                    "reg_type": parts[0] if len(parts) > 0 else "holding",
                    "address": int(parts[1]) if len(parts) > 1 else 0,
                    "count": int(parts[2]) if len(parts) > 2 else 1,
                    "format": parts[3] if len(parts) > 3 else "raw",
                    "interval": int(parts[4]) if len(parts) > 4 else 1000,
                }
        else:
            # OPC UA: node_id string
            return {"node_id": config_str}

        return None

    def _read_tag(self):
        dev_id = self.read_dev_combo.currentText()
        tag_name = self.read_tag_input.text().strip()
        if not dev_id or not tag_name:
            return

        result = self.manager.read_tag(dev_id, tag_name)
        if result is not None:
            self.read_result_label.setText(str(result))
            self._log(f"Чтение: {dev_id}.{tag_name} = {result}")
        else:
            self.read_result_label.setText("(async / None)")
            self._log(f"Чтение: {dev_id}.{tag_name} -> результат через signal")

    def _write_tag(self):
        dev_id = self.write_dev_combo.currentText()
        tag_name = self.write_tag_input.text().strip()
        value_str = self.write_value_input.text().strip()
        if not dev_id or not tag_name:
            return

        # Try to parse value
        try:
            value = float(value_str)
            if value == int(value):
                value = int(value)
        except ValueError:
            value = value_str

        ok = self.manager.write_tag(dev_id, tag_name, value)
        self._log(f"Запись: {dev_id}.{tag_name} = {value} -> {'OK' if ok else 'FAIL'}")

    def _read_register(self):
        dev_id = self.reg_dev_combo.currentText()
        reg_type = self.reg_type_combo.currentText()
        address = self.reg_addr_input.value()
        count = self.reg_count_input.value()
        if not dev_id:
            return

        result = self.manager.read_register(dev_id, reg_type, address, count)
        if result is not None:
            self.reg_result_label.setText(str(result))
            self._log(f"Регистр: {dev_id} {reg_type}[{address}:{count}] = {result}")
        else:
            self.reg_result_label.setText("None")
            self._log(f"Регистр: {dev_id} {reg_type}[{address}:{count}] -> None")

    # ======================================================================
    # SIGNAL HANDLERS
    # ======================================================================

    def _on_device_connected(self, dev_id):
        self._update_device_status(dev_id, "Подключено", "#009900")
        self._log(f"[OK] {dev_id} подключено")

    def _on_device_disconnected(self, dev_id):
        self._update_device_status(dev_id, "Отключено", "#cc0000")
        self._log(f"[--] {dev_id} отключено")

    def _on_device_error(self, dev_id, error):
        self._update_device_status(dev_id, f"Ошибка", "#cc0000")
        self._log(f"[ERR] {dev_id}: {error}")

    def _on_tag_updated(self, dev_id, tag_name, value):
        self._update_data_row(dev_id, tag_name, value)

    def _on_register_updated(self, dev_id, poll_name, data):
        display = data.get("value", data)
        self._update_data_row(dev_id, poll_name, display)

    # ======================================================================
    # HELPERS
    # ======================================================================

    def _update_device_status(self, dev_id, status, color):
        for row in range(self.dev_table.rowCount()):
            item = self.dev_table.item(row, 0)
            if item and item.text() == dev_id:
                status_item = QTableWidgetItem(status)
                status_item.setForeground(QColor(color))
                self.dev_table.setItem(row, 3, status_item)
                break

    def _update_data_row(self, dev_id, tag_name, value):
        now = datetime.now().strftime("%H:%M:%S")

        # Find existing row or create new
        for row in range(self.data_table.rowCount()):
            dev_item = self.data_table.item(row, 0)
            tag_item = self.data_table.item(row, 1)
            if (dev_item and tag_item and
                    dev_item.text() == dev_id and tag_item.text() == tag_name):
                self.data_table.setItem(row, 2, QTableWidgetItem(str(value)))
                self.data_table.setItem(row, 3, QTableWidgetItem(now))
                return

        # New row
        row = self.data_table.rowCount()
        self.data_table.insertRow(row)
        self.data_table.setItem(row, 0, QTableWidgetItem(dev_id))
        self.data_table.setItem(row, 1, QTableWidgetItem(tag_name))
        self.data_table.setItem(row, 2, QTableWidgetItem(str(value)))
        self.data_table.setItem(row, 3, QTableWidgetItem(now))

    def _update_combos(self):
        devices = list(self.manager.get_devices().keys())
        for combo in [self.sub_dev_combo, self.read_dev_combo,
                      self.write_dev_combo, self.reg_dev_combo]:
            current = combo.currentText()
            combo.clear()
            combo.addItems(devices)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _setup_refresh_timer(self):
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(2000)

    def _refresh_data(self):
        """Periodic refresh of all data from manager."""
        all_data = self.manager.get_all_data()
        for dev_id, data in all_data.items():
            for key, value in data.items():
                self._update_data_row(dev_id, key, value)

    def _log(self, msg):
        now = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{now}] {msg}")

    def closeEvent(self, event):
        self.refresh_timer.stop()
        self.manager.stop_all()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = TestGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
