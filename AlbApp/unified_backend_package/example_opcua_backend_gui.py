"""
Пример использования OpcUaBackend — GUI версия
===============================================

Повторяет логику example_opcua_backend.py, но с интерфейсом:
  - Все операции вызываются кнопками
  - Результаты отображаются в логе
  - Статус соединения виден визуально

Запуск:
    python -m unified_backend_package.example_opcua_backend_gui
"""

import sys
from pathlib import Path
# Добавляем корень проекта в путь — чтобы работало и через F5, и через python -m
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit, QTextEdit, QFormLayout
)
from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtGui import QFont

from unified_backend_package.backend.opcua_backend import OpcUaBackend


ENDPOINT   = "opc.tcp://192.168.6.6:4840"
NODE_READ  = "ns=2;s=Temperature"
NODE_WRITE = "ns=2;s=Start"
NODE_SUB   = "ns=2;s=Pressure"


# ═══════════════════════════════════════════════════════════════════════════════

class Log(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 9))
        self.setStyleSheet("background:#2b2b2b; color:#f0f0f0;")

    def write(self, msg: str, color: str = "#f0f0f0"):
        ts = QDateTime.currentDateTime().toString("hh:mm:ss.zzz")
        self.append(
            f'<span style="color:#888">[{ts}]</span> '
            f'<span style="color:{color}">{msg}</span>'
        )
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class ExampleWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpcUaBackend — GUI пример")
        self.setMinimumWidth(680)

        self.backend = OpcUaBackend()

        self._build_ui()
        self._connect_signals()

    # ─────────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout()
        root.setSpacing(6)
        root.setContentsMargins(10, 10, 10, 10)

        root.addWidget(self._group_connection())
        root.addWidget(self._group_read_write())
        root.addWidget(self._group_subscriptions())
        root.addWidget(self._group_watchdog())
        root.addWidget(self._group_log())

        w = QWidget()
        w.setLayout(root)
        self.setCentralWidget(w)

    def _group_connection(self) -> QGroupBox:
        box = QGroupBox("1. Подключение")
        form = QFormLayout(box)

        self.le_endpoint = QLineEdit(ENDPOINT)
        form.addRow("Endpoint:", self.le_endpoint)

        row = QHBoxLayout()
        self.lbl_status = QLabel("● Отключен")
        self.lbl_status.setStyleSheet("color:#e74c3c; font-weight:bold;")

        self.btn_connect    = QPushButton("Подключить")
        self.btn_disconnect = QPushButton("Отключить")
        self.btn_disconnect.setEnabled(False)

        self.btn_connect.clicked.connect(self._on_connect)
        self.btn_disconnect.clicked.connect(self._on_disconnect)

        row.addWidget(self.lbl_status)
        row.addStretch()
        row.addWidget(self.btn_connect)
        row.addWidget(self.btn_disconnect)
        form.addRow(row)
        return box

    def _group_read_write(self) -> QGroupBox:
        box = QGroupBox("2. Чтение / запись")
        v = QVBoxLayout(box)

        # Строка ввода node_id
        row_node = QHBoxLayout()
        row_node.addWidget(QLabel("NodeId:"))
        self.le_node = QLineEdit(NODE_READ)
        row_node.addWidget(self.le_node)
        v.addLayout(row_node)

        # Кнопки
        row_btns = QHBoxLayout()
        self.btn_read        = QPushButton("Читать")
        self.btn_write       = QPushButton("Записать 1")
        self.btn_batch_read  = QPushButton("Пакетное чтение")
        self.btn_batch_write = QPushButton("Пакетная запись")

        for btn in (self.btn_read, self.btn_write,
                    self.btn_batch_read, self.btn_batch_write):
            btn.setEnabled(False)
            row_btns.addWidget(btn)

        self.btn_read.clicked.connect(self._on_read)
        self.btn_write.clicked.connect(self._on_write)
        self.btn_batch_read.clicked.connect(self._on_batch_read)
        self.btn_batch_write.clicked.connect(self._on_batch_write)

        v.addLayout(row_btns)
        return box

    def _group_subscriptions(self) -> QGroupBox:
        box = QGroupBox("3. Подписки (push)")
        v = QVBoxLayout(box)

        row_node = QHBoxLayout()
        row_node.addWidget(QLabel("NodeId:"))
        self.le_sub_node = QLineEdit(NODE_SUB)
        row_node.addWidget(self.le_sub_node)
        v.addLayout(row_node)

        row_btns = QHBoxLayout()
        self.btn_subscribe   = QPushButton("Подписаться")
        self.btn_unsubscribe = QPushButton("Отписаться")
        self.btn_show_tags   = QPushButton("Список подписок")

        for btn in (self.btn_subscribe, self.btn_unsubscribe, self.btn_show_tags):
            btn.setEnabled(False)
            row_btns.addWidget(btn)
        row_btns.addStretch()

        self.btn_subscribe.clicked.connect(self._on_subscribe)
        self.btn_unsubscribe.clicked.connect(self._on_unsubscribe)
        self.btn_show_tags.clicked.connect(self._on_show_tags)

        v.addLayout(row_btns)
        return box

    def _group_watchdog(self) -> QGroupBox:
        box = QGroupBox("4. Watchdog / статистика")
        row = QHBoxLayout(box)

        self.btn_watchdog_start = QPushButton("Watchdog старт (5с)")
        self.btn_watchdog_stop  = QPushButton("Watchdog стоп")
        self.btn_stats          = QPushButton("Статистика")

        for btn in (self.btn_watchdog_start, self.btn_watchdog_stop, self.btn_stats):
            btn.setEnabled(False)
            row.addWidget(btn)
        row.addStretch()

        self.btn_watchdog_start.clicked.connect(self._on_watchdog_start)
        self.btn_watchdog_stop.clicked.connect(self._on_watchdog_stop)
        self.btn_stats.clicked.connect(self._on_stats)

        return box

    def _group_log(self) -> QGroupBox:
        box = QGroupBox("Лог событий")
        v = QVBoxLayout(box)
        self.log = Log()
        btn_clear = QPushButton("Очистить")
        btn_clear.setMaximumWidth(90)
        btn_clear.clicked.connect(self.log.clear)
        v.addWidget(self.log)
        v.addWidget(btn_clear, alignment=Qt.AlignmentFlag.AlignRight)
        return box

    # ─────────────────────────────────────────────────────────────────────────
    # Signals
    # ─────────────────────────────────────────────────────────────────────────

    def _connect_signals(self):
        b = self.backend

        b.server_connected.connect(self._on_server_connected)
        b.server_disconnected.connect(self._on_server_disconnected)
        b.server_error.connect(
            lambda srv, err: self.log.write(f"[{srv}] ошибка: {err}", "#e74c3c"))

        b.data_updated.connect(
            lambda srv, nid, val: self.log.write(
                f"[{srv}] push {nid} = {val}", "#3498db"))

        b.read_completed.connect(
            lambda srv, nid, val: self.log.write(
                f"[{srv}] read {nid} = {val}", "#1abc9c"))

        b.write_completed.connect(
            lambda srv, nid, ok: self.log.write(
                f"[{srv}] write {nid} → {'OK' if ok else 'FAIL'}",
                "#2ecc71" if ok else "#e74c3c"))

        b.batch_read_completed.connect(
            lambda srv, res: self.log.write(
                f"[{srv}] batch_read → {res}", "#1abc9c"))

        b.batch_write_completed.connect(
            lambda srv, res: self.log.write(
                f"[{srv}] batch_write → {res}", "#f39c12"))

        b.tag_subscribed.connect(
            lambda srv, nid: self.log.write(
                f"[{srv}] подписка активна: {nid}", "#9b59b6"))

        b.tag_unsubscribed.connect(
            lambda srv, nid: self.log.write(
                f"[{srv}] отписан: {nid}", "#95a5a6"))

        b.watchdog_disconnect.connect(
            lambda srv: self.log.write(
                f"[{srv}] WATCHDOG: соединение потеряно!", "#e67e22"))

    def _on_server_connected(self, srv: str):
        self.lbl_status.setText("● Подключен")
        self.lbl_status.setStyleSheet("color:#2ecc71; font-weight:bold;")
        self.btn_connect.setEnabled(False)
        self.btn_disconnect.setEnabled(True)
        self._set_ops_enabled(True)
        self.log.write(f"[{srv}] подключен", "#2ecc71")

    def _on_server_disconnected(self, srv: str):
        self.lbl_status.setText("● Отключен")
        self.lbl_status.setStyleSheet("color:#e74c3c; font-weight:bold;")
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self._set_ops_enabled(False)
        self.log.write(f"[{srv}] отключен")

    def _set_ops_enabled(self, enabled: bool):
        for btn in (self.btn_read, self.btn_write,
                    self.btn_batch_read, self.btn_batch_write,
                    self.btn_subscribe, self.btn_unsubscribe, self.btn_show_tags,
                    self.btn_watchdog_start, self.btn_watchdog_stop, self.btn_stats):
            btn.setEnabled(enabled)

    # ─────────────────────────────────────────────────────────────────────────
    # Слоты кнопок
    # ─────────────────────────────────────────────────────────────────────────

    def _on_connect(self):
        endpoint = self.le_endpoint.text().strip()
        if not endpoint:
            return
        self.lbl_status.setText("◌ Подключение...")
        self.lbl_status.setStyleSheet("color:#f39c12; font-weight:bold;")
        self.btn_connect.setEnabled(False)
        self.log.write(f"Подключение к {endpoint}...")
        if "PLC1" not in self.backend.servers:
            self.backend.add_server("PLC1", endpoint)
        else:
            # Обновляем endpoint если изменился
            self.backend.servers["PLC1"]["endpoint"] = endpoint
        self.backend.connect_server("PLC1")

    def _on_disconnect(self):
        self.backend.disconnect_server("PLC1", blocking=False)
        self.log.write("Отключение...")

    def _on_read(self):
        node = self.le_node.text().strip()
        if node:
            self.backend.read_node("PLC1", node)
            self.log.write(f"read → {node}")

    def _on_write(self):
        node = self.le_node.text().strip()
        if node:
            self.backend.write_node("PLC1", node, 1)
            self.log.write(f"write {node} ← 1")

    def _on_batch_read(self):
        node = self.le_node.text().strip()
        nodes = [node, NODE_WRITE] if node else [NODE_READ, NODE_WRITE]
        self.backend.read_multiple_nodes("PLC1", nodes)
        self.log.write(f"batch_read → {nodes}")

    def _on_batch_write(self):
        node = self.le_node.text().strip() or NODE_WRITE
        self.backend.write_multiple_nodes("PLC1", {node: 1, "ns=2;s=Reset": 0})
        self.log.write(f"batch_write → {node}, ns=2;s=Reset")

    def _on_subscribe(self):
        node = self.le_sub_node.text().strip()
        if node:
            self.backend.subscribe_tag("PLC1", node)
            self.log.write(f"subscribe → {node}")

    def _on_unsubscribe(self):
        node = self.le_sub_node.text().strip()
        if node:
            self.backend.unsubscribe_tag("PLC1", node)
            self.log.write(f"unsubscribe → {node}")

    def _on_show_tags(self):
        tags = self.backend.get_subscribed_tags("PLC1")
        self.log.write(f"активные подписки: {tags or '(нет)'}")

    def _on_watchdog_start(self):
        self.backend.start_watchdog("PLC1", interval=5.0)
        self.log.write("watchdog запущен (5 сек)")

    def _on_watchdog_stop(self):
        self.backend.stop_watchdog("PLC1")
        self.log.write("watchdog остановлен")

    def _on_stats(self):
        stats = self.backend.get_stats("PLC1")
        if not stats:
            self.log.write("нет данных (не подключён?)")
            return
        self.log.write("--- статистика PLC1 ---")
        for key, val in stats.items():
            self.log.write(f"  {key}: {val}", "#aaaaaa")

    # ─────────────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        # Скрываем окно сразу — пользователь видит что приложение закрылось.
        # Cleanup (disconnect от OPC UA серверов) происходит в фоне.
        self.hide()
        event.ignore()
        self.backend.stop_all()
        QApplication.instance().quit()



def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = ExampleWindow()
    win.show()
    win.raise_()
    win.activateWindow()

    # Windows: принудительно выводим окно на передний план
    # (VSCode блокирует SetForegroundWindow без этого трюка)
    try:
        import ctypes
        hwnd = int(win.winId())
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
