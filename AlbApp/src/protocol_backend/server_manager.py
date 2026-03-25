import re
from datetime import datetime, timezone
from PyQt6.QtCore import QObject, QTimer
from protocol_backend.backend.opcua_backend import OpcUaBackend
from protocol_backend.event_bus import bus
from protocol_backend.tags.tags import Dev_192_168_6_6_OPC_Tags as Tags


# ── Теги PLC1 ─────────────────────────────────────────────────────────────────
_PLC1_TAGS = [
    Tags.cmdChangeControlMode,
    Tags.cmdForwardJogging,
    Tags.cmdBackwardJogging,
    Tags.cmdPowerOn,
    Tags.cmdPowerOff,
    Tags.nowSetpoint,       # подписка на текущую уставку
]

# ── Конфигурация серверов ─────────────────────────────────────────────────────
_SERVERS = [
    {
        "name"              : "PLC1",
        "endpoint"          : "opc.tcp://192.168.6.6:4840",
        "auto_reconnect"    : True,
        "reconnect_interval": 5,
        "subscribe"         : _PLC1_TAGS,  # подписка + начальное чтение при подключении
        "polls"             : [
            {"name": "arrays", "nodes": [Tags.cc, Tags.displacementSensorArr, Tags.tenzaSensorDataArr], "interval": 0.1, "sequential": True},
        ],
    },
]


class ServerManager(QObject):
    """Управляет OPC UA серверами. Общается с GUI через event_bus."""

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._backend = OpcUaBackend()
        self._timers: dict[str, QTimer] = {}
        self._config: dict[str, dict] = {}
        self._setup()

        # Команды от GUI → запись тега на PLC
        bus.cmd_control_mode.connect(lambda v: self._write("PLC1", Tags.cmdChangeControlMode, int(v)))
        bus.cmd_forward     .connect(lambda v: self._write("PLC1", Tags.cmdForwardJogging,    int(v)))
        bus.cmd_backward    .connect(lambda v: self._write("PLC1", Tags.cmdBackwardJogging,   int(v)))
        bus.cmd_power_on    .connect(lambda v: self._write("PLC1", Tags.cmdPowerOn,           int(v)))
        bus.cmd_power_off   .connect(lambda v: self._write("PLC1", Tags.cmdPowerOff,          int(v)))

        QTimer.singleShot(0, self.start)  # старт после запуска event loop

    # ── Публичный API ─────────────────────────────────────────────────────────

    def start(self):
        """Подключиться ко всем серверам."""
        for name in self._config:
            self._backend.connect_server(name)

    def stop(self):
        """Отключиться от всех серверов (вызывается при закрытии приложения)."""
        import logging
        logging.getLogger("asyncua").setLevel(logging.CRITICAL)
        for timer in self._timers.values():
            timer.stop()
        self._backend.stop_all()

    def _write(self, srv: str, node_id: str, value):
        self._backend.write_node(srv, node_id, value)

    # ── Инициализация ─────────────────────────────────────────────────────────

    def _setup(self):
        """Зарегистрировать серверы и подключить сигналы backend."""
        for cfg in _SERVERS:
            name = cfg["name"]
            self._config[name] = cfg
            self._backend.add_server(name, cfg["endpoint"])
            # Таймер авто-переподключения (запускается в _on_disconnected)
            timer = QTimer(self)
            timer.setSingleShot(False)
            timer.timeout.connect(lambda n=name: self._try_reconnect(n))
            self._timers[name] = timer
        self._wire_signals()

    def _wire_signals(self):
        """Пробросить сигналы backend в шину событий."""
        b = self._backend
        b.server_connected    .connect(self._on_connected)
        b.server_disconnected .connect(self._on_disconnected)
        b.server_error        .connect(bus.server_error)
        b.data_updated        .connect(self._on_data_received)   # подписка
        b.read_completed      .connect(self._on_data_received)   # одиночное чтение
        b.write_completed     .connect(self._on_write_completed)
        b.batch_read_completed.connect(self._on_batch_read)      # начальное чтение при подключении

    # ── Обработчики событий backend ───────────────────────────────────────────

    def _on_connected(self, srv: str):
        """Подключились: остановить таймер реконнекта, подписаться, прочитать начальные значения."""
        self._timers[srv].stop()
        bus.server_connected.emit(srv)
        cfg = self._config.get(srv, {})
        subscribe_tags = cfg.get("subscribe", [])
        for node_id in subscribe_tags:
            self._backend.subscribe_tag(srv, node_id)
        if subscribe_tags:
            self._backend.read_multiple_nodes(srv, subscribe_tags)  # начальное состояние кнопок
        for poll in cfg.get("polls", []):
            self._backend.start_polling(srv, poll["name"], poll["nodes"], poll["interval"], poll.get("sequential", False))

    def _on_disconnected(self, srv: str):
        """Отключились: запустить таймер авто-переподключения."""
        bus.server_disconnected.emit(srv)
        cfg = self._config.get(srv, {})
        if cfg.get("auto_reconnect", True):
            interval = cfg.get("reconnect_interval", 5)
            self._timers[srv].start(interval * 1000)
            bus.reconnecting.emit(srv, interval)

    def _try_reconnect(self, name: str):
        self._backend.connect_server(name)

    def _on_write_completed(self, srv: str, node_id: str, success: bool):
        """После записи — читаем тег обратно для получения подтверждённого состояния."""
        bus.write_completed.emit(srv, node_id, success)
        if success:
            self._backend.read_node(srv, node_id)

    def _on_batch_read(self, srv: str, results: dict):
        """Результат начального чтения — передаём каждое значение как обычное обновление."""
        for node_id, value in results.items():
            if value is not None:
                self._on_data_received(srv, node_id, value)

    # ── Маршрутизация входящих данных ─────────────────────────────────────────

    def _on_data_received(self, srv: str, nid: str, val):
        """Единая точка входа для всех данных от PLC (подписка / чтение)."""
        nid = self._normalize_nid(nid)
        bus.data_updated.emit(srv, nid, val)
        self._emit_state(nid, val)

    @staticmethod
    def _normalize_nid(nid: str) -> str:
        """Привести NodeId к формату ns=X;s=... если пришёл объект asyncua NodeId."""
        if not nid.startswith("NodeId("):
            return nid
        m_ns = re.search(r"NamespaceIndex=(\d+)", nid)
        m_id = re.search(r"Identifier='([^']+)'", nid)
        if m_ns and m_id:
            return f"ns={m_ns.group(1)};s={m_id.group(1)}"
        return nid

    # Маппинг тег → сигнал шины состояния GUI
    _STATE_MAP = {
        Tags.cmdChangeControlMode: lambda v: bus.state_control_mode .emit(bool(v)),
        Tags.cmdForwardJogging:    lambda v: bus.state_forward       .emit(bool(v)),
        Tags.cmdBackwardJogging:   lambda v: bus.state_backward      .emit(bool(v)),
        Tags.cmdPowerOn:           lambda v: bus.state_power_on      .emit(bool(v)),
        Tags.cmdPowerOff:          lambda v: bus.state_power_off     .emit(bool(v)),
        Tags.tenzaSensorDataArr:   lambda v: bus.tenza_array_updated .emit(list(v) if v else []),
        Tags.nowSetpoint:          lambda v: bus.nowSetpoint_points  .emit(
            [datetime.now(timezone.utc).timestamp()], [float(v)]
        ),
    }

    def _emit_state(self, nid: str, val):
        """Испустить state-сигнал шины для соответствующей кнопки GUI."""
        emitter = self._STATE_MAP.get(nid)
        if emitter:
            emitter(val)
