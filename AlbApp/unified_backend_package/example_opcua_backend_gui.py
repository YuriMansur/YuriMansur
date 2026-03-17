"""
GUI для OpcUaController
========================

Только UI: кнопки, поля ввода, лог, сигналы.
Вся логика подключения — в example_opcua_backend.OpcUaController.

Запуск:
    python -m unified_backend_package.example_opcua_backend_gui
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit, QTextEdit, QFormLayout,
)
from PyQt6.QtCore import Qt, QDateTime, QTimer
from PyQt6.QtGui import QFont

from unified_backend_package.example_opcua_backend import (
    OpcUaController, NODE_READ, NODE_WRITE, NODE_SUB, ENDPOINT,
)


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

        self.ctrl = OpcUaController(
            endpoint=ENDPOINT,
            auto_reconnect=True,
            reconnect_interval=5,
        )

        self._build_ui()
        self._connect_signals()

        # Запускаем подключение после отрисовки окна
        QTimer.singleShot(0, self.ctrl.start)

    # ─────────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout()
        root.setSpacing(6)
        root.setContentsMargins(10, 10, 10, 10)

        root.addWidget(self._group_status())
        root.addWidget(self._group_read_write())
        root.addWidget(self._group_subscriptions())
        root.addWidget(self._group_watchdog())
        root.addWidget(self._group_log())

        w = QWidget()
        w.setLayout(root)
        self.setCentralWidget(w)

    def _group_status(self) -> QGroupBox:
        box = QGroupBox("Соединение")
        form = QFormLayout(box)

        row_status = QHBoxLayout()
        self.lbl_status = QLabel("◌ Подключение...")
        self.lbl_status.setStyleSheet("color:#f39c12; font-weight:bold;")
        row_status.addWidget(self.lbl_status)
        row_status.addStretch()
        form.addRow(row_status)

        return box

    def _group_read_write(self) -> QGroupBox:
        box = QGroupBox("1. Чтение / запись")
        v = QVBoxLayout(box)

        row_node = QHBoxLayout()
        row_node.addWidget(QLabel("NodeId:"))
        self.le_node = QLineEdit(NODE_READ[0])
        row_node.addWidget(self.le_node)
        v.addLayout(row_node)

        row_btns = QHBoxLayout()
        self.btn_read        = QPushButton("Читать")
        self.btn_write       = QPushButton("Записать 1")
        self.btn_batch_read  = QPushButton("Пакетное чтение")
        self.btn_batch_write = QPushButton("Пакетная запись")

        for btn in (self.btn_read, self.btn_write,
                    self.btn_batch_read, self.btn_batch_write):
            btn.setEnabled(False)
            row_btns.addWidget(btn)

        self.btn_read.clicked.connect(
            lambda: self.ctrl.read_node(self.le_node.text().strip()))
        self.btn_write.clicked.connect(
            lambda: self.ctrl.write_node(self.le_node.text().strip(), 1))
        self.btn_batch_read.clicked.connect(self._on_batch_read)
        self.btn_batch_write.clicked.connect(self._on_batch_write)

        v.addLayout(row_btns)
        return box

    def _group_subscriptions(self) -> QGroupBox:
        box = QGroupBox("2. Подписки (push)")
        v = QVBoxLayout(box)

        row_node = QHBoxLayout()
        row_node.addWidget(QLabel("NodeId:"))
        self.le_sub_node = QLineEdit(NODE_SUB[0])
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

        self.btn_subscribe.clicked.connect(
            lambda: self.ctrl.subscribe_tag(self.le_sub_node.text().strip()))
        self.btn_unsubscribe.clicked.connect(
            lambda: self.ctrl.unsubscribe_tag(self.le_sub_node.text().strip()))
        self.btn_show_tags.clicked.connect(
            lambda: self.log.write(
                f"активные подписки: {self.ctrl.get_subscribed_tags() or '(нет)'}"))

        v.addLayout(row_btns)
        return box

    def _group_watchdog(self) -> QGroupBox:
        box = QGroupBox("3. Watchdog / статистика")
        row = QHBoxLayout(box)

        self.btn_watchdog_start = QPushButton("Watchdog старт (5с)")
        self.btn_watchdog_stop  = QPushButton("Watchdog стоп")
        self.btn_stats          = QPushButton("Статистика")

        for btn in (self.btn_watchdog_start, self.btn_watchdog_stop, self.btn_stats):
            btn.setEnabled(False)
            row.addWidget(btn)
        row.addStretch()

        self.btn_watchdog_start.clicked.connect(
            lambda: self.ctrl.start_watchdog(interval=5.0))
        self.btn_watchdog_stop.clicked.connect(self.ctrl.stop_watchdog)
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
    # Сигналы контроллера → обновление UI
    # ─────────────────────────────────────────────────────────────────────────

    def _connect_signals(self):
        c = self.ctrl

        c.server_connected.connect(self._on_connected)
        c.server_disconnected.connect(self._on_disconnected)
        c.reconnecting.connect(
            lambda srv, sec: self.log.write(
                f"[{srv}] переподключение через {sec} сек...", "#f39c12"))
        c.server_error.connect(
            lambda srv, err: self.log.write(f"[{srv}] ошибка: {err}", "#e74c3c"))

        c.data_updated.connect(
            lambda srv, nid, val: self.log.write(
                f"[{srv}] push {nid} = {val}", "#3498db"))
        c.read_completed.connect(
            lambda srv, nid, val: self.log.write(
                f"[{srv}] read {nid} = {val}", "#1abc9c"))
        c.write_completed.connect(
            lambda srv, nid, ok: self.log.write(
                f"[{srv}] write {nid} → {'OK' if ok else 'FAIL'}",
                "#2ecc71" if ok else "#e74c3c"))
        c.batch_read_completed.connect(
            lambda srv, res: self.log.write(
                f"[{srv}] batch_read → {res}", "#1abc9c"))
        c.batch_write_completed.connect(
            lambda srv, res: self.log.write(
                f"[{srv}] batch_write → {res}", "#f39c12"))
        c.tag_subscribed.connect(
            lambda srv, nid: self.log.write(
                f"[{srv}] подписка активна: {nid}", "#9b59b6"))
        c.tag_unsubscribed.connect(
            lambda srv, nid: self.log.write(
                f"[{srv}] отписан: {nid}", "#95a5a6"))
        c.watchdog_disconnect.connect(
            lambda srv: self.log.write(
                f"[{srv}] WATCHDOG: соединение потеряно!", "#e67e22"))

    def _on_connected(self, srv: str):
        self.lbl_status.setText("● Подключен")
        self.lbl_status.setStyleSheet("color:#2ecc71; font-weight:bold;")
        self._set_ops_enabled(True)
        self.log.write(f"[{srv}] подключен", "#2ecc71")

    def _on_disconnected(self, srv: str):
        self.lbl_status.setText("● Отключен")
        self.lbl_status.setStyleSheet("color:#e74c3c; font-weight:bold;")
        self._set_ops_enabled(False)
        self.log.write(f"[{srv}] отключен")

    def _set_ops_enabled(self, enabled: bool):
        for btn in (self.btn_read, self.btn_write,
                    self.btn_batch_read, self.btn_batch_write,
                    self.btn_subscribe, self.btn_unsubscribe, self.btn_show_tags,
                    self.btn_watchdog_start, self.btn_watchdog_stop, self.btn_stats):
            btn.setEnabled(enabled)

    # ─────────────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    # Сложные слоты кнопок
    # ─────────────────────────────────────────────────────────────────────────

    def _on_batch_read(self):
        node = self.le_node.text().strip()
        nodes = [node, NODE_WRITE[0]] if node else [NODE_READ[0], NODE_WRITE[0]]
        self.ctrl.read_multiple_nodes(nodes)

    def _on_batch_write(self):
        node = self.le_node.text().strip() or NODE_WRITE[0]
        self.ctrl.write_multiple_nodes({node: 1, "ns=2;s=Reset": 0})

    def _on_stats(self):
        stats = self.ctrl.get_stats()
        if not stats:
            self.log.write("нет данных (не подключён?)")
            return
        self.log.write("--- статистика PLC1 ---")
        for key, val in stats.items():
            self.log.write(f"  {key}: {val}", "#aaaaaa")

    # ─────────────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self.hide()
        event.ignore()
        self.ctrl.stop()
        QApplication.instance().quit()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = ExampleWindow()
    win.show()
    win.raise_()
    win.activateWindow()

    try:
        import ctypes
        ctypes.windll.user32.SetForegroundWindow(int(win.winId()))
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
