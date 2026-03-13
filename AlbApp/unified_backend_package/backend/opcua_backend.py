"""
OpcUaBackend - API для программного управления множественными OPC UA серверами

═══════════════════════════════════════════════════════════════════════════════
НАЗНАЧЕНИЕ:
═══════════════════════════════════════════════════════════════════════════════
Backend класс для управления OPC UA серверами БЕЗ GUI. Предоставляет API для:
- Добавления/удаления серверов
- Подключения/отключения
- Чтения/записи переменных (одиночных и пакетных)
- Управления подписками на теги
- Watchdog — автоматическое обнаружение обрыва
- Получения статистики и данных в реальном времени

АРХИТЕКТУРА:
============
    ┌──────────────────────────────────────────────┐
    │         User Application (ваш код)           │
    │                                              │
    │  backend = OpcUaBackend()                   │
    │  backend.add_server("OPC1", "opc.tcp://...") │
    │  backend.connect_server("OPC1")             │
    │  backend.subscribe_tag("OPC1", "ns=2;s=T")  │
    └───────────────┬──────────────────────────────┘
                    │
                    ▼
    ┌──────────────────────────────────────────────┐
    │          OpcUaBackend (этот класс)           │
    │                                              │
    │  • Управление словарем серверов             │
    │  • Thread-safe API                          │
    │  • Callbacks для событий                    │
    └───────────────┬──────────────────────────────┘
                    │
            ┌───────┴────────┐
            ▼                ▼
    ┌──────────────┐  ┌──────────────┐
    │OpcUaWorkerThread│ │OpcUaWorkerThread│
    │    (OPC1)    │  │    (OPC2)    │
    │              │  │              │
    │  asyncio     │  │  asyncio     │
    │  event loop  │  │  event loop  │
    └──────────────┘  └──────────────┘

ПРИМЕР ИСПОЛЬЗОВАНИЯ:
====================
from unified_backend_package.legacy import OpcUaBackend

# Создаем backend
backend = OpcUaBackend()

# Callbacks (опционально)
backend.on_connected = lambda srv_id: print(f"{srv_id} connected!")
backend.on_data_updated = lambda srv_id, nid, val: print(f"{srv_id}: {nid}={val}")
backend.on_watchdog_disconnect = lambda srv_id: print(f"{srv_id} connection lost!")

# Добавляем сервер
backend.add_server(
    server_id="OPC1",
    endpoint="opc.tcp://192.168.1.10:4840",
    namespace=2
)

# Подключаемся
backend.connect_server("OPC1")

# Подписываемся на теги
backend.subscribe_tag("OPC1", "ns=2;s=Temperature", "Temperature")
backend.subscribe_tag("OPC1", "ns=2;s=Pressure", "Pressure")

# Читаем одно значение (результат через signal read_completed)
backend.read_node("OPC1", "ns=2;s=SetPoint")

# Читаем несколько сразу (результат через signal batch_read_completed)
backend.read_multiple_nodes("OPC1", ["ns=2;s=Temperature", "ns=2;s=Pressure"])

# Записываем значение (результат через signal write_completed)
backend.write_node("OPC1", "ns=2;s=SetPoint", 25.5)

# Записываем несколько (результат через signal batch_write_completed)
backend.write_multiple_nodes("OPC1", {"ns=2;s=SetPoint": 25.5, "ns=2;s=Mode": 1})

# Watchdog — обнаружение обрыва каждые 5 секунд
backend.start_watchdog("OPC1", interval=5.0)

# Статистика
stats = backend.get_stats("OPC1")
print(stats)  # {"reads": 42, "writes": 5, "read_errors": 0, ...}

# Получаем данные
data = backend.get_latest_data("OPC1")
print(data)  # {"ns=2;s=Temperature": 23.5, "ns=2;s=Pressure": 101.3}

# Отключаемся
backend.disconnect_server("OPC1")
"""

from typing import Dict, Optional, Callable, Any, List
from PyQt6.QtCore import QObject, pyqtSignal

from unified_backend_package.backend.worker.opcua.opcua_worker_thread import OpcUaWorkerThread


class OpcUaBackend(QObject):
    """
    Backend для управления множественными OPC UA серверами

    ОСОБЕННОСТИ:
    ============
    - Программное управление (без GUI)
    - Каждый сервер в отдельном потоке (изоляция)
    - Thread-safe API
    - Callbacks для событий
    - Watchdog с синхронизацией флага _connected
    - Пакетное чтение/запись

    API:
    ====
    Управление серверами:
        add_server(server_id, endpoint, namespace, timeout)
        remove_server(server_id, force=False)
        connect_server(server_id)
        disconnect_server(server_id, blocking=False)
        connect_all()
        disconnect_all(blocking=False)
        is_connected(server_id)
        get_servers()

    Чтение/запись:
        read_node(server_id, node_id)
        write_node(server_id, node_id, value)
        read_multiple_nodes(server_id, node_ids)
        write_multiple_nodes(server_id, values)

    Управление тегами:
        subscribe_tag(server_id, node_id, tag_name)
        unsubscribe_tag(server_id, node_id)
        subscribe_multiple_tags(server_id, tags)
        get_subscribed_tags(server_id)

    Watchdog:
        start_watchdog(server_id, interval)
        stop_watchdog(server_id)
        is_watchdog_active(server_id)

    Данные и статистика:
        get_latest_data(server_id)
        get_all_data()
        get_stats(server_id)
    """

    # ===== SIGNALS =====
    # Подключение
    server_connected = pyqtSignal(str)       # (server_id)
    server_disconnected = pyqtSignal(str)    # (server_id)
    server_error = pyqtSignal(str, str)      # (server_id, error)

    # Данные
    data_updated = pyqtSignal(str, str, object)  # (server_id, node_id, value)

    # Теги
    tag_subscribed = pyqtSignal(str, str)    # (server_id, node_id)
    tag_unsubscribed = pyqtSignal(str, str)  # (server_id, node_id)

    # Одиночные операции
    read_completed = pyqtSignal(str, str, object)  # (server_id, node_id, value)
    write_completed = pyqtSignal(str, str, bool)   # (server_id, node_id, success)

    # Пакетные операции
    batch_read_completed = pyqtSignal(str, dict)   # (server_id, {node_id: value})
    batch_write_completed = pyqtSignal(str, dict)  # (server_id, {node_id: success})

    # Watchdog
    watchdog_disconnect = pyqtSignal(str)    # (server_id) — обрыв обнаружен watchdog

    def __init__(self):
        """Инициализация OPC UA Backend"""
        super().__init__()

        # Словарь серверов {server_id: {"endpoint", "namespace", "timeout", "thread", "connected"}}
        self.servers: Dict[str, dict] = {}

        # ===== CALLBACKS =====
        self.on_connected           : Optional[Callable[[str], None]]   = None
        self.on_disconnected        : Optional[Callable[[str], None]] = None
        self.on_connection_error    : Optional[Callable[[str, str], None]] = None
        self.on_data_updated        : Optional[Callable[[str, str, Any], None]] = None
        self.on_tag_subscribed      : Optional[Callable[[str, str], None]] = None
        self.on_watchdog_disconnect : Optional[Callable[[str], None]] = None

    # ==========================================================================
    # SERVER MANAGEMENT
    # ==========================================================================

    def add_server(
        self,
        server_id: str,
        endpoint: str,
        namespace: int = 2,
        timeout: float = 10.0
    ) -> bool:
        """
        Добавить OPC UA сервер

        Args:
            server_id: Уникальный ID сервера
            endpoint: URL сервера (например "opc.tcp://192.168.1.10:4840")
            namespace: Namespace index (по умолчанию 2)
            timeout: Таймаут операций

        Returns:
            bool: True если добавлено, False если server_id уже существует
        """
        if server_id in self.servers:
            return False

        thread = OpcUaWorkerThread(
            server_id=server_id,
            endpoint=endpoint,
            namespace=namespace,
            timeout=timeout
        )

        self._connect_thread_signals(server_id, thread)

        self.servers[server_id] = {
            "endpoint": endpoint,
            "namespace": namespace,
            "timeout": timeout,
            "thread": thread,
            "connected": False
        }

        return True

    def remove_server(self, server_id: str, force: bool = False) -> bool:
        """
        Удалить сервер

        Args:
            server_id: ID сервера
            force: Принудительно удалить (отключить если подключен)

        Returns:
            bool: True если удалено
        """
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]

        if server["connected"] and not force:
            return False

        if server["connected"] and force:
            self.disconnect_server(server_id, blocking=True)

        del self.servers[server_id]
        return True

    def get_servers(self) -> Dict[str, dict]:
        """Получить все серверы (без внутреннего thread объекта)"""
        return {
            srv_id: {
                "endpoint": srv["endpoint"],
                "namespace": srv["namespace"],
                "connected": srv["connected"]
            }
            for srv_id, srv in self.servers.items()
        }

    def is_connected(self, server_id: str) -> bool:
        """Проверить подключение сервера"""
        if server_id not in self.servers:
            return False
        return self.servers[server_id]["connected"]

    # ==========================================================================
    # CONNECTION
    # ==========================================================================

    def connect_server(self, server_id: str) -> bool:
        """
        Подключиться к серверу

        Returns:
            bool: True если подключение запущено (результат через signal server_connected)
        """
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]

        if server["connected"]:
            return True

        thread = server["thread"]
        if not thread.isRunning():
            thread.loop_ready.connect(lambda: thread.connect_to_server())
            thread.start()
        else:
            thread.connect_to_server()

        return True

    def disconnect_server(self, server_id: str, blocking: bool = False) -> bool:
        """
        Отключиться от сервера

        Args:
            blocking: True для closeEvent (ждать завершения),
                      False для GUI (неблокирующий)

        Returns:
            bool: True если отключение запущено
        """
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]

        if not server["connected"]:
            return True

        server["thread"].stop(blocking=blocking)
        return True

    def connect_all(self):
        """Подключить все серверы"""
        for server_id in self.servers:
            if not self.is_connected(server_id):
                self.connect_server(server_id)

    def disconnect_all(self, blocking: bool = False):
        """Отключить все серверы"""
        for server_id in list(self.servers.keys()):
            if self.is_connected(server_id):
                self.disconnect_server(server_id, blocking=blocking)

    # ==========================================================================
    # READ / WRITE
    # ==========================================================================

    def read_node(self, server_id: str, node_id: str) -> bool:
        """
        Прочитать значение переменной

        Результат приходит через signal read_completed(server_id, node_id, value)

        Returns:
            bool: True если запрос отправлен
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False

        thread.read_node(node_id)
        return True

    def write_node(self, server_id: str, node_id: str, value: Any) -> bool:
        """
        Записать значение переменной

        Результат приходит через signal write_completed(server_id, node_id, success)

        Returns:
            bool: True если запрос отправлен
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False

        thread.write_node(node_id, value)
        return True

    def read_multiple_nodes(self, server_id: str, node_ids: List[str]) -> bool:
        """
        Пакетное параллельное чтение нескольких тегов

        Все теги читаются одновременно через asyncio.gather().
        При ошибке одного тега — остальные всё равно читаются, значение → None.

        Результат приходит через signal batch_read_completed(server_id, {node_id: value})

        Args:
            node_ids: Список NodeId ["ns=2;s=Temperature", "ns=2;s=Pressure", ...]

        Returns:
            bool: True если запрос отправлен
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False

        thread.read_multiple_nodes(node_ids)
        return True

    def write_multiple_nodes(self, server_id: str, values: Dict[str, Any]) -> bool:
        """
        Пакетная параллельная запись нескольких тегов

        Все теги пишутся одновременно через asyncio.gather().
        При ошибке одного тега — остальные всё равно записываются.

        Результат приходит через signal batch_write_completed(server_id, {node_id: success})

        Args:
            values: Словарь {node_id: value}

        Returns:
            bool: True если запрос отправлен
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False

        thread.write_multiple_nodes(values)
        return True

    # ==========================================================================
    # SUBSCRIPTION (TAG MANAGEMENT)
    # ==========================================================================

    def subscribe_tag(
        self,
        server_id: str,
        node_id: str,
        tag_name: Optional[str] = None
    ) -> bool:
        """
        Подписаться на изменения тега (push-модель)

        Результат приходит через signal tag_subscribed(server_id, node_id)
        Данные приходят через signal data_updated(server_id, node_id, value)

        Returns:
            bool: True если запрос отправлен
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False

        thread.subscribe_tag(node_id, tag_name)
        return True

    def unsubscribe_tag(self, server_id: str, node_id: str) -> bool:
        """
        Отписаться от тега

        Returns:
            bool: True если запрос отправлен
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False

        thread.unsubscribe_tag(node_id)
        return True

    def subscribe_multiple_tags(self, server_id: str, tags: Dict[str, str]) -> bool:
        """
        Подписаться на несколько тегов

        Args:
            tags: Словарь {tag_name: node_id}

        Returns:
            bool: True если запрос отправлен
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False

        thread.subscribe_multiple_tags(tags)
        return True

    def get_subscribed_tags(self, server_id: str) -> List[str]:
        """Получить список подписанных тегов (NodeId)"""
        thread = self._get_thread(server_id)
        if not thread:
            return []
        return thread.get_subscribed_tags()

    # ==========================================================================
    # WATCHDOG
    # ==========================================================================

    def start_watchdog(self, server_id: str, interval: float = 5.0) -> bool:
        """
        Запустить watchdog — периодическую проверку живости соединения

        При обнаружении обрыва эмитит:
          - signal watchdog_disconnect(server_id)
          - signal server_disconnected(server_id)
          - вызывает callback on_watchdog_disconnect

        Args:
            interval: Интервал проверки в секундах (рекомендуется 3–10)

        Returns:
            bool: True если запрос отправлен
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False

        thread.start_watchdog(interval)
        return True

    def stop_watchdog(self, server_id: str) -> bool:
        """
        Остановить watchdog

        Returns:
            bool: True если запрос отправлен
        """
        thread = self._get_thread(server_id)
        if not thread:
            return False

        thread.stop_watchdog()
        return True

    def is_watchdog_active(self, server_id: str) -> bool:
        """Проверить активность watchdog"""
        thread = self._get_thread(server_id)
        if not thread:
            return False
        return thread.is_watchdog_active

    # ==========================================================================
    # DATA ACCESS
    # ==========================================================================

    def get_latest_data(self, server_id: str) -> Dict[str, Any]:
        """
        Получить последние данные от сервера (из кэша, без запроса к серверу)

        Returns:
            Словарь {node_id: value}
        """
        thread = self._get_thread(server_id)
        if not thread:
            return {}
        return thread.get_latest_data()

    def get_all_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Получить данные от всех серверов

        Returns:
            Словарь {server_id: {node_id: value}}
        """
        return {srv_id: self.get_latest_data(srv_id) for srv_id in self.servers}

    def get_stats(self, server_id: str) -> Dict[str, Any]:
        """
        Получить статистику операций сервера

        Returns:
            Dict с полями: reads, writes, read_errors, write_errors,
                           last_read_ms, last_write_ms и др.
            Пустой dict если сервер не найден.
        """
        thread = self._get_thread(server_id)
        if not thread:
            return {}
        return thread.get_stats()

    # ==========================================================================
    # LIFECYCLE
    # ==========================================================================

    def stop_all(self):
        """Остановить все серверы (блокирующий — для closeEvent)"""
        self.disconnect_all(blocking=True)
        self.servers.clear()

    # ==========================================================================
    # INTERNAL HELPERS
    # ==========================================================================

    def _get_thread(self, server_id: str) -> Optional[OpcUaWorkerThread]:
        """Получить thread по server_id (без проверки подключения)"""
        server = self.servers.get(server_id)
        if not server:
            return None
        return server["thread"]

    def _get_connected_thread(self, server_id: str) -> Optional[OpcUaWorkerThread]:
        """Получить thread только если сервер подключён"""
        server = self.servers.get(server_id)
        if not server or not server["connected"]:
            return None
        return server["thread"]

    # ==========================================================================
    # INTERNAL SIGNAL HANDLERS
    # ==========================================================================

    def _connect_thread_signals(self, server_id: str, thread: OpcUaWorkerThread):
        """Подключить signals от thread к backend"""
        thread.connected.connect(
            lambda: self._on_server_connected(server_id))
        thread.disconnected.connect(
            lambda: self._on_server_disconnected(server_id))
        thread.connection_error.connect(
            lambda err: self._on_server_error(server_id, err))
        thread.data_updated.connect(
            lambda nid, val: self._on_data_updated(server_id, nid, val))
        thread.tag_subscribed.connect(
            lambda nid: self._on_tag_subscribed(server_id, nid))
        thread.tag_unsubscribed.connect(
            lambda nid: self._on_tag_unsubscribed(server_id, nid))
        thread.read_completed.connect(
            lambda nid, val: self._on_read_completed(server_id, nid, val))
        thread.write_completed.connect(
            lambda nid, succ: self._on_write_completed(server_id, nid, succ))
        thread.batch_read_completed.connect(
            lambda results: self._on_batch_read_completed(server_id, results))
        thread.batch_write_completed.connect(
            lambda results: self._on_batch_write_completed(server_id, results))
        thread.watchdog_disconnect.connect(
            lambda: self._on_watchdog_disconnect(server_id))

    def _on_server_connected(self, server_id: str):
        if server_id in self.servers:
            self.servers[server_id]["connected"] = True
        if self.on_connected:
            self.on_connected(server_id)
        self.server_connected.emit(server_id)

    def _on_server_disconnected(self, server_id: str):
        if server_id in self.servers:
            self.servers[server_id]["connected"] = False
        if self.on_disconnected:
            self.on_disconnected(server_id)
        self.server_disconnected.emit(server_id)

    def _on_server_error(self, server_id: str, error: str):
        if self.on_connection_error:
            self.on_connection_error(server_id, error)
        self.server_error.emit(server_id, error)

    def _on_data_updated(self, server_id: str, node_id: str, value: Any):
        if self.on_data_updated:
            self.on_data_updated(server_id, node_id, value)
        self.data_updated.emit(server_id, node_id, value)

    def _on_tag_subscribed(self, server_id: str, node_id: str):
        if self.on_tag_subscribed:
            self.on_tag_subscribed(server_id, node_id)
        self.tag_subscribed.emit(server_id, node_id)

    def _on_tag_unsubscribed(self, server_id: str, node_id: str):
        self.tag_unsubscribed.emit(server_id, node_id)

    def _on_read_completed(self, server_id: str, node_id: str, value: Any):
        self.read_completed.emit(server_id, node_id, value)

    def _on_write_completed(self, server_id: str, node_id: str, success: bool):
        self.write_completed.emit(server_id, node_id, success)

    def _on_batch_read_completed(self, server_id: str, results: dict):
        self.batch_read_completed.emit(server_id, results)

    def _on_batch_write_completed(self, server_id: str, results: dict):
        self.batch_write_completed.emit(server_id, results)

    def _on_watchdog_disconnect(self, server_id: str):
        if self.on_watchdog_disconnect:
            self.on_watchdog_disconnect(server_id)
        self.watchdog_disconnect.emit(server_id)
