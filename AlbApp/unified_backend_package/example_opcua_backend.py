"""
OpcUaController — логика подключения и работы с OPC UA сервером
===============================================================

Содержит всю логику:
  - Авто-подключение при старте
  - Авто-переподключение при обрыве
  - Все операции (read/write/subscribe/watchdog/stats)

Используется из example_opcua_backend_gui.py (GUI — только кнопки и сигналы).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from unified_backend_package.backend.opcua_backend import OpcUaBackend
from unified_backend_package.tags import Temperature, Start, Pressure


ENDPOINT   = "opc.tcp://192.168.6.6:4840"
NODE_READ  = (Temperature,)
NODE_WRITE = (Start,)
NODE_SUB   = (Pressure,)


class OpcUaController(QObject):
    """
    Контроллер OPC UA соединения.

    Инициирует подключение при старте, автоматически переподключается
    при обрыве. Все операции делегируются OpcUaBackend.

    Сигналы пробрасываются наружу — GUI подписывается на них напрямую.
    """

    # ── Статус соединения ──────────────────────────────────────────────────
    server_connected    = pyqtSignal(str)           # srv_name
    server_disconnected = pyqtSignal(str)           # srv_name
    server_error        = pyqtSignal(str, str)      # srv_name, error_msg
    reconnecting        = pyqtSignal(str, int)      # srv_name, interval_sec

    # ── Данные ────────────────────────────────────────────────────────────
    data_updated          = pyqtSignal(str, str, object)  # srv, node_id, value
    read_completed        = pyqtSignal(str, str, object)  # srv, node_id, value
    write_completed       = pyqtSignal(str, str, bool)    # srv, node_id, ok
    batch_read_completed  = pyqtSignal(str, object)       # srv, results
    batch_write_completed = pyqtSignal(str, object)       # srv, results

    # ── Подписки ──────────────────────────────────────────────────────────
    tag_subscribed   = pyqtSignal(str, str)   # srv, node_id
    tag_unsubscribed = pyqtSignal(str, str)   # srv, node_id

    # ── Watchdog ──────────────────────────────────────────────────────────
    watchdog_disconnect = pyqtSignal(str)     # srv

    # ──────────────────────────────────────────────────────────────────────

    def __init__(
        self,
        endpoint            : str       = ENDPOINT,
        server_name         : str       = "PLC1",
        auto_reconnect      : bool      = True,
        reconnect_interval  : int       = 5,
        parent              : QObject   = None,
    ):
        """
        Инициализация OpcUaController.

        Args:
            endpoint           : адрес OPC UA сервера (opc.tcp://host:port)
            server_name        : имя сервера внутри backend (произвольный ключ)
            auto_reconnect     : авто-переподключение при обрыве соединения
            reconnect_interval : интервал между попытками переподключения (сек)
            parent             : родительский QObject (для Qt-иерархии)
        """
        super().__init__(parent)
        # Адрес OPC UA сервера (может быть любым, главное, чтобы сервер был доступен по этому адресу):
        self.endpoint           = endpoint
        # Имя сервера (может быть любым, используется для идентификации в backend и GUI):
        self.server_name        = server_name
        # Авто-переподключение при обрыве:
        self.auto_reconnect     = auto_reconnect
        # При обрыве, если auto_reconnect=True, то будем пытаться переподключиться каждые reconnect_interval секунд:
        self.reconnect_interval = reconnect_interval
        # Объявляем backend (вся логика работы с OPC UA внутри него):
        self._backend           = OpcUaBackend()
        # Объявляем таймер переподключения (используем для авто-переподключения при обрыве):
        self._reconnect_timer   = QTimer(self)
        # Таймер переподключения (неоднократный):
        self._reconnect_timer.setSingleShot(False)
        # При срабатывании пытаемся переподключиться:
        self._reconnect_timer.timeout.connect(self._try_reconnect)
        # Пробрасываем сигналы из backend наружу (GUI подписывается на эти сигналы):
        self._wire_backend_signals()

    # ── Публичный API ──────────────────────────────────────────────────────

    def start(self):
        """Запустить подключение (вызывается один раз при старте приложения)."""
        self._backend.add_server(self.server_name, self.endpoint)
        self._do_connect()

    def stop(self):
        """Остановить всё (вызывается при закрытии приложения)."""
        self._reconnect_timer.stop()
        self._backend.stop_all()

    # ── Операции (делегируются в backend) ─────────────────────────────────

    def read_node(self, node_id: str):
        """Прочитать значение одного тега."""
        self._backend.read_node(self.server_name, node_id)

    def write_node(self, node_id: str, value):
        """Записать значение в один тег."""
        self._backend.write_node(self.server_name, node_id, value)

    def read_multiple_nodes(self, nodes: list):
        """Пакетное чтение нескольких тегов."""
        self._backend.read_multiple_nodes(self.server_name, nodes)

    def write_multiple_nodes(self, nodes: dict):
        """Пакетная запись нескольких тегов {node_id: value}."""
        self._backend.write_multiple_nodes(self.server_name, nodes)

    def subscribe_tag(self, node_id: str):
        """Подписаться на изменения тега (push)."""
        self._backend.subscribe_tag(self.server_name, node_id)

    def unsubscribe_tag(self, node_id: str):
        """Отписаться от изменений тега."""
        self._backend.unsubscribe_tag(self.server_name, node_id)

    def get_subscribed_tags(self) -> list:
        """Вернуть список активных подписок."""
        return self._backend.get_subscribed_tags(self.server_name)

    def start_polling(self, name: str, node_ids: list, interval: float = 1.0):
        """Запустить именованный цикл опроса тегов."""
        self._backend.start_polling(self.server_name, name, node_ids, interval)

    def stop_polling(self, name: str = None):
        """Остановить цикл(ы) опроса (None = все)."""
        self._backend.stop_polling(self.server_name, name)

    def get_active_polls(self) -> dict:
        """Вернуть информацию об активных poll loop'ах."""
        return self._backend.get_active_polls(self.server_name)

    def start_watchdog(self, interval: float = 5.0):
        """Запустить watchdog — фоновую проверку живости соединения."""
        self._backend.start_watchdog(self.server_name, interval=interval)

    def stop_watchdog(self):
        """Остановить watchdog."""
        self._backend.stop_watchdog(self.server_name)

    def get_stats(self) -> dict:
        """Вернуть статистику соединения и операций."""
        return self._backend.get_stats(self.server_name)

    # ── Внутренняя логика ──────────────────────────────────────────────────

    def _wire_backend_signals(self):
        """Подключить сигналы backend к локальным слотам и пробросить наружу."""
        b = self._backend
        b.server_connected.connect(self._on_connected)
        b.server_disconnected.connect(self._on_disconnected)
        b.server_error.connect(self.server_error)
        b.data_updated.connect(self.data_updated)
        b.read_completed.connect(self.read_completed)
        b.write_completed.connect(self.write_completed)
        b.batch_read_completed.connect(self.batch_read_completed)
        b.batch_write_completed.connect(self.batch_write_completed)
        b.tag_subscribed.connect(self.tag_subscribed)
        b.tag_unsubscribed.connect(self.tag_unsubscribed)
        b.watchdog_disconnect.connect(self.watchdog_disconnect)

    def _do_connect(self):
        """Инициировать подключение к серверу."""
        if self.server_name not in self._backend.servers:
            self._backend.add_server(self.server_name, self.endpoint)
        self._backend.connect_server(self.server_name)

    def _on_connected(self, srv: str):
        """Обработать успешное подключение — остановить таймер и пробросить сигнал."""
        self._reconnect_timer.stop()
        self.server_connected.emit(srv)

    def _on_disconnected(self, srv: str):
        """Обработать отключение — запустить таймер авто-переподключения если нужно."""
        self.server_disconnected.emit(srv)
        if self.auto_reconnect:
            self._reconnect_timer.start(self.reconnect_interval * 1000)
            self.reconnecting.emit(srv, self.reconnect_interval)

    def _try_reconnect(self):
        """Попытка переподключения по таймеру."""
        if not self.auto_reconnect:
            self._reconnect_timer.stop()
            return
        self._do_connect()
