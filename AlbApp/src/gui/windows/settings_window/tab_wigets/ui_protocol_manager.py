from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QTextEdit,
    QPushButton,
)
from PyQt6.QtCore import QDateTime
from PyQt6.QtGui import QFont

from protocol_backend.event_bus import bus
from upgradable_qt_widgets.button import OpcUaButton, ButtonMode
from database.influx_logger import InfluxLogger


class Log(QTextEdit):
    """Виджет лога — только для чтения, с цветными строками и автоскроллом."""

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


class ProtocolManagerWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_data = True
        self._build_ui()
        self._connect_bus()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(12, 12, 12, 12)

        # ── Статус соединения ────────────────────────────────────────────
        row_conn = QHBoxLayout()
        self.lbl_connected = QLabel("◌ Подключение...")
        self.lbl_connected.setStyleSheet("color:#f39c12; font-weight:bold;")
        row_conn.addWidget(self.lbl_connected)
        row_conn.addStretch()
        root.addLayout(row_conn)

        # ── Кнопки ───────────────────────────────────────────────────────
        self.btn_control_mode = OpcUaButton(
            off_text  = "Режим",
            on_text   = "Режим ✓",
            off_color = "#e74c3c",
            on_color  = "#2ecc71",
            mode      = ButtonMode.TOGGLE,
        )
        self.btn_forward = OpcUaButton(
            off_text  = "Вперёд",
            off_color = "#2980b9",
            on_color  = "#1abc9c",
            mode      = ButtonMode.HOLD,
        )
        self.btn_backward = OpcUaButton(
            off_text  = "Назад",
            off_color = "#2980b9",
            on_color  = "#1abc9c",
            mode      = ButtonMode.HOLD,
        )
        self.btn_power_on = OpcUaButton(
            off_text  = "Питание вкл",
            on_text   = "Питание вкл ✓",
            off_color = "#d41515",
            on_color  = "#2ecc71",
            mode      = ButtonMode.CLICK,
        )
        self.btn_power_off = OpcUaButton(
            off_text  = "Питание выкл",
            on_text   = "Питание выкл ✓",
            off_color = "#c0392b",
            on_color  = "#3ce761",
            mode      = ButtonMode.CLICK,
        )

        self._all_buttons = [
            self.btn_control_mode,
            self.btn_forward,
            self.btn_backward,
            self.btn_power_on,
            self.btn_power_off,
        ]

        for btn in self._all_buttons:
            btn.setMinimumHeight(36)
            btn.set_online(False)

        # кнопки → bus (команды)
        self.btn_control_mode.state_changed.connect(bus.cmd_control_mode)
        self.btn_forward      .state_changed.connect(bus.cmd_forward)
        self.btn_backward     .state_changed.connect(bus.cmd_backward)
        self.btn_power_on     .state_changed.connect(bus.cmd_power_on)
        self.btn_power_off    .state_changed.connect(bus.cmd_power_off)

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.addWidget(self.btn_control_mode, 0, 0)
        grid.addWidget(self.btn_forward,      0, 1)
        grid.addWidget(self.btn_backward,     1, 0)
        grid.addWidget(self.btn_power_on,     1, 1)
        grid.addWidget(self.btn_power_off,    2, 0)
        root.addLayout(grid)

        # ── Тензодатчики ────────────────────────────────────────────────
        root.addWidget(QLabel("Тензодатчики:"))
        self.tenza_labels: list[QLabel] = []
        self.tenza_grid = QGridLayout()
        self.tenza_grid.setSpacing(4)
        for i in range(16):
            lbl = QLabel(f"[{i}] —")
            lbl.setStyleSheet("color:#aaaaaa; font-family:Consolas;")
            self.tenza_labels.append(lbl)
            self.tenza_grid.addWidget(lbl, i // 4, i % 4)
        root.addLayout(self.tenza_grid)

        # ── Кнопка лога консоли ─────────────────────────────────────────
        self.btn_console_log = QPushButton("⏹ Стоп лог консоли")
        self.btn_console_log.setCheckable(True)
        self.btn_console_log.setChecked(True)
        self.btn_console_log.clicked.connect(self._toggle_console_log)
        root.addWidget(self.btn_console_log)

        # ── Лог ─────────────────────────────────────────────────────────
        self.log = Log()
        root.addWidget(self.log)

    def _connect_bus(self):
        # статус соединения
        bus.server_connected   .connect(lambda srv: self._on_connected(srv))
        bus.server_disconnected.connect(lambda srv: self._on_disconnected(srv))
        bus.server_error       .connect(lambda srv, err: self.log.write(f"[{srv}] ошибка: {err}", "#e74c3c"))
        bus.reconnecting       .connect(lambda srv, sec: self.log.write(f"[{srv}] переподключение через {sec} сек...", "#f39c12"))
        bus.write_completed    .connect(lambda srv, nid, ok: self.log.write(f"[{srv}] запись {nid.split('.')[-1]} {'ок' if ok else 'ошибка'}", "#2ecc71" if ok else "#e74c3c"))
        bus.data_updated       .connect(lambda srv, nid, val: self.log.write(f"[{srv}] {nid} = {val}", "#aaaaaa") if self._log_data else None)

        # массив тензодатчиков
        bus.tenza_array_updated.connect(self._on_tenza_updated)

        # состояния кнопок от PLC
        bus.state_control_mode .connect(self.btn_control_mode.set_active)
        bus.state_forward      .connect(self.btn_forward     .set_active)
        bus.state_backward     .connect(self.btn_backward    .set_active)
        bus.state_power_on     .connect(self.btn_power_on    .set_active)
        bus.state_power_off    .connect(self.btn_power_off   .set_active)

    def _on_connected(self, srv: str):
        self.lbl_connected.setText("● Подключен")
        self.lbl_connected.setStyleSheet("color:#2ecc71; font-weight:bold;")
        for btn in self._all_buttons:
            btn.set_online(True)
        self.log.write(f"[{srv}] подключен", "#2ecc71")

    def _on_tenza_updated(self, values: list):
        for i, lbl in enumerate(self.tenza_labels):
            val = values[i] if i < len(values) else "—"
            lbl.setText(f"[{i}] {val}")

    def _toggle_console_log(self, checked: bool):
        self._log_data = checked
        self.btn_console_log.setText("⏹ Стоп лог консоли" if checked else "▶ Старт лог консоли")

    def _on_disconnected(self, srv: str):
        self.lbl_connected.setText("● Отключен")
        self.lbl_connected.setStyleSheet("color:#e74c3c; font-weight:bold;")
        for btn in self._all_buttons:
            btn.set_online(False)
        self.log.write(f"[{srv}] отключен", "#e74c3c")
