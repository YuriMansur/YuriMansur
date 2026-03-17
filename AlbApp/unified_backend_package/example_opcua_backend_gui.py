"""
example_opcua_backend_gui.py — минималистичный GUI для управления битом.

GUI ничего не знает о контроллере и тегах.
Все подключения сигналов — снаружи, в run_opcua_gui.py.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit,
)
from PyQt6.QtCore import QDateTime, pyqtSignal
from PyQt6.QtGui import QFont


# Виджет лога
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

# Главное окно
class ExampleWindow(QMainWindow):
    # Сигнал: пользователь нажал кнопку — снаружи решат что записать
    toggle_requested = pyqtSignal(bool)  # True = включить, False = выключить

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA — управление битом")
        self.setMinimumWidth(400)

        self._bit_state = False

        self._build_ui()


    # UI
    def _build_ui(self):
        root = QVBoxLayout()
        root.setSpacing(10)
        root.setContentsMargins(12, 12, 12, 12)

        # ── Статус соединения ────────────────────────────────────────────
        row_conn = QHBoxLayout()
        self.lbl_connected = QLabel("◌ Подключение...")
        self.lbl_connected.setStyleSheet("color:#f39c12; font-weight:bold;")
        row_conn.addWidget(self.lbl_connected)
        row_conn.addStretch()
        root.addLayout(row_conn)

        # ── Лампочка + кнопка ───────────────────────────────────────────
        row_bit = QHBoxLayout()

        self.lbl_bit = QLabel("⬤")
        self.lbl_bit.setFont(QFont("Arial", 28))
        self.lbl_bit.setStyleSheet("color:#555555;")
        row_bit.addWidget(self.lbl_bit)

        self.btn_toggle = QPushButton("Включить")
        self.btn_toggle.setMinimumHeight(48)
        self.btn_toggle.setEnabled(False)
        self.btn_toggle.clicked.connect(self._on_toggle_clicked)
        row_bit.addWidget(self.btn_toggle, stretch=1)

        root.addLayout(row_bit)

        # ── Лог ─────────────────────────────────────────────────────────
        self.log = Log()
        root.addWidget(self.log)

        w = QWidget()
        w.setLayout(root)
        self.setCentralWidget(w)

    # ───────────────────────────────────────────────────────────────────────
    # Слоты (вызываются снаружи через connect)
    # ───────────────────────────────────────────────────────────────────────

    def on_connected(self, srv: str):
        self.lbl_connected.setText("● Подключен")
        self.lbl_connected.setStyleSheet("color:#2ecc71; font-weight:bold;")
        self.btn_toggle.setEnabled(True)
        self.log.write(f"[{srv}] подключен", "#2ecc71")

    def on_disconnected(self, srv: str):
        self.lbl_connected.setText("● Отключен")
        self.lbl_connected.setStyleSheet("color:#e74c3c; font-weight:bold;")
        self.btn_toggle.setEnabled(False)
        self.lbl_bit.setStyleSheet("color:#555555;")
        self.log.write(f"[{srv}] отключен")

    def on_error(self, srv: str, err: str):
        self.log.write(f"[{srv}] ошибка: {err}", "#e74c3c")

    def on_reconnecting(self, srv: str, sec: int):
        self.log.write(f"[{srv}] переподключение через {sec} сек...", "#f39c12")

    def on_write_completed(self, srv: str, _nid: str, ok: bool):
        if ok:
            self._bit_state = not self._bit_state
            self._update_lamp(self._bit_state)
            self.btn_toggle.setText("Выключить" if self._bit_state else "Включить")
            self.log.write(f"[{srv}] бит → {'1' if self._bit_state else '0'}", "#2ecc71")
        else:
            self.log.write(f"[{srv}] ошибка записи!", "#e74c3c")

    def on_data_updated(self, _srv: str, _nid: str, val):
        self._bit_state = bool(val)
        self._update_lamp(self._bit_state)
        self.btn_toggle.setText("Выключить" if self._bit_state else "Включить")

    # ───────────────────────────────────────────────────────────────────────

    def _on_toggle_clicked(self):
        self.toggle_requested.emit(not self._bit_state)

    def _update_lamp(self, state: bool):
        self.lbl_bit.setStyleSheet("color:#2ecc71;" if state else "color:#e74c3c;")
