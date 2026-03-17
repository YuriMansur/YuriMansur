"""
server_manager.py — менеджер OPC UA серверов
=============================================

Все серверы и теги прописаны внутри.
Снаружи только: manager.start() / manager.stop()

Пример в точке входа:
    manager = ServerManager()
    manager.start()
    ...
    manager.stop()
"""

from PyQt6.QtCore import QObject, pyqtSignal

from unified_backend_package.example_opcua_backend import OpcUaController
from unified_backend_package.example_opcua_backend_gui import ExampleWindow
from unified_backend_package.tags import Dev_192_168_6_6_OPC_Tags as Tags


# ═══════════════════════════════════════════════════════════════════════════════
# Конфигурация серверов и тегов — редактировать здесь
# ═══════════════════════════════════════════════════════════════════════════════

_SERVERS = [
    {
        "name"              : "PLC1",
        "endpoint"          : "opc.tcp://192.168.6.6:4840",
        "auto_reconnect"    : True,
        "reconnect_interval": 5,
        "subscribe"         : [Tags.cmdChangeControlMode],
        "read_on_connect"   : [],
        "toggle_node"       : Tags.cmdChangeControlMode,
    },
    # {
    #     "name"    : "PLC2",
    #     "endpoint": "opc.tcp://192.168.6.7:4840",
    #     "subscribe": [Tags.someOtherTag],
    # },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Менеджер
# ═══════════════════════════════════════════════════════════════════════════════

class ServerManager(QObject):
    """
    Управляет всеми OPC UA серверами.
    Конфиг жёстко задан в _SERVERS выше.
    """

    # Агрегированные сигналы от всех серверов
    server_connected    = pyqtSignal(str)
    server_disconnected = pyqtSignal(str)
    server_error        = pyqtSignal(str, str)
    reconnecting        = pyqtSignal(str, int)
    data_updated        = pyqtSignal(str, str, object)
    read_completed      = pyqtSignal(str, str, object)
    write_completed     = pyqtSignal(str, str, bool)

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._controllers: dict[str, OpcUaController] = {}
        self._config: dict[str, dict] = {}
        self._setup()

    # ── Публичный API ─────────────────────────────────────────────────────

    def start(self):
        """Запустить все серверы."""
        for ctrl in self._controllers.values():
            ctrl.start()

    def stop(self):
        """Остановить все серверы."""
        for ctrl in self._controllers.values():
            ctrl.stop()

    def write(self, server_name: str, node_id: str, value):
        """Записать тег на указанном сервере."""
        self._controllers[server_name].write_node(node_id, value)

    def read(self, server_name: str, node_id: str):
        """Прочитать тег на указанном сервере."""
        self._controllers[server_name].read_node(node_id)

    def on_toggle(self, state: bool):
        """Записать состояние бита в сервер с toggle_node."""
        for name, cfg in self._config.items():
            node_id = cfg.get("toggle_node")
            if node_id:
                self.write(name, node_id, int(state))
                return

    def bind_window(self, win: ExampleWindow):
        """Подключить сигналы менеджера к окну и обратно."""
        self.server_connected.connect(win.on_connected)
        self.server_disconnected.connect(win.on_disconnected)
        self.server_error.connect(win.on_error)
        self.reconnecting.connect(win.on_reconnecting)
        self.write_completed.connect(win.on_write_completed)
        self.data_updated.connect(win.on_data_updated)
        win.toggle_requested.connect(self.on_toggle)

    # ── Внутреннее ────────────────────────────────────────────────────────

    def _setup(self):
        """Создать контроллеры по конфигу _SERVERS."""
        for cfg in _SERVERS:
            name = cfg["name"]
            ctrl = OpcUaController(
                endpoint=cfg["endpoint"],
                server_name=name,
                auto_reconnect=cfg.get("auto_reconnect", True),
                reconnect_interval=cfg.get("reconnect_interval", 5),
                parent=self,
            )
            self._config[name] = cfg
            self._controllers[name] = ctrl
            self._wire(ctrl)

    def _wire(self, ctrl: OpcUaController):
        """Пробросить сигналы контроллера наружу и навесить внутреннюю логику."""
        ctrl.server_connected.connect(self._on_connected)
        ctrl.server_disconnected.connect(self.server_disconnected)
        ctrl.server_error.connect(self.server_error)
        ctrl.reconnecting.connect(self.reconnecting)
        ctrl.data_updated.connect(self.data_updated)
        ctrl.read_completed.connect(self.read_completed)
        ctrl.write_completed.connect(self.write_completed)

    def _on_connected(self, srv: str):
        """При подключении — автоматически подписаться и прочитать теги."""
        self.server_connected.emit(srv)
        cfg  = self._config.get(srv, {})
        ctrl = self._controllers[srv]

        for node_id in cfg.get("subscribe", []):
            ctrl.subscribe_tag(node_id)

        read_tags = cfg.get("read_on_connect", [])
        if read_tags:
            ctrl.read_multiple_nodes(read_tags)
