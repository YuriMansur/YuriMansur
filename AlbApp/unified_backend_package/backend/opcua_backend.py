"""
OpcUaBackend - API для программного управления множественными OPC UA серверами

═══════════════════════════════════════════════════════════════════════════════
НАЗНАЧЕНИЕ:
═══════════════════════════════════════════════════════════════════════════════
Backend класс для управления OPC UA серверами БЕЗ GUI. Предоставляет API для:
- Добавления/удаления серверов
- Подключения/отключения
- Чтения/записи переменных
- Управления подписками на теги
- Получения данных в реальном времени

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

# Читаем значение
value = backend.read_node("OPC1", "ns=2;s=SetPoint")

# Записываем значение
backend.write_node("OPC1", "ns=2;s=SetPoint", 25.5)

# Получаем данные
data = backend.get_latest_data("OPC1")
print(data)  # {"ns=2;s=Temperature": 23.5, "ns=2;s=Pressure": 101.3}

# Отключаемся
backend.disconnect_server("OPC1")
"""

from typing import Dict, Optional, Callable, Any, List
from PyQt6.QtCore import QObject, pyqtSignal

from AlbApp.unified_backend_package.worker.opcua.opcua_worker_thread import OpcUaWorkerThread


class OpcUaBackend(QObject):
    """
    Backend для управления множественными OPC UA серверами

    ОСОБЕННОСТИ:
    ============
    - Программное управление (без GUI)
    - Каждый сервер в отдельном потоке (изоляция)
    - Thread-safe API
    - Callbacks для событий
    - Управление подписками на теги
    - Real-time данные от подписок

    API:
    ====
    Управление серверами:
        add_server(server_id, endpoint, namespace)
        remove_server(server_id, force=False)
        connect_server(server_id)
        disconnect_server(server_id, blocking=False)
        is_connected(server_id)

    Чтение/запись:
        read_node(server_id, node_id)
        write_node(server_id, node_id, value)

    Управление тегами:
        subscribe_tag(server_id, node_id, tag_name)
        unsubscribe_tag(server_id, node_id)
        subscribe_multiple_tags(server_id, tags)
        get_subscribed_tags(server_id)

    Данные:
        get_latest_data(server_id)
        get_all_data()
    """

    # ===== SIGNALS =====
    server_connected = pyqtSignal(str)  # (server_id)
    server_disconnected = pyqtSignal(str)  # (server_id)
    server_error = pyqtSignal(str, str)  # (server_id, error)
    data_updated = pyqtSignal(str, str, object)  # (server_id, node_id, value)
    tag_subscribed = pyqtSignal(str, str)  # (server_id, node_id)
    tag_unsubscribed = pyqtSignal(str, str)  # (server_id, node_id)
    read_completed = pyqtSignal(str, str, object)  # (server_id, node_id, value)
    write_completed = pyqtSignal(str, str, bool)  # (server_id, node_id, success)

    def __init__(self):
        """Инициализация OPC UA Backend"""
        super().__init__()

        # Словарь серверов {server_id: {"endpoint": str, "namespace": int, "thread": OpcUaWorkerThread, "connected": bool}}
        self.servers: Dict[str, dict] = {}

        # ===== CALLBACKS =====
        self.on_connected: Optional[Callable[[str], None]] = None
        self.on_disconnected: Optional[Callable[[str], None]] = None
        self.on_connection_error: Optional[Callable[[str, str], None]] = None
        self.on_data_updated: Optional[Callable[[str, str, Any], None]] = None
        self.on_tag_subscribed: Optional[Callable[[str, str], None]] = None

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
            bool: True если добавлено

        Example:
            backend.add_server("OPC1", "opc.tcp://192.168.1.10:4840", namespace=2)
        """
        if server_id in self.servers:
            return False  # Сервер с таким ID уже существует

        # Создаем thread для сервера
        thread = OpcUaWorkerThread(
            server_id=server_id,
            endpoint=endpoint,
            namespace=namespace,
            timeout=timeout
        )

        # Подключаем signals
        self._connect_thread_signals(server_id, thread)

        # Сохраняем в словарь
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

        # Проверяем подключение
        if server["connected"] and not force:
            return False  # Сервер подключен, нельзя удалить без force

        # Если force и подключен - отключаем
        if server["connected"] and force:
            self.disconnect_server(server_id, blocking=True)

        # Удаляем из словаря
        del self.servers[server_id]

        return True

    def get_servers(self) -> Dict[str, dict]:
        """Получить все серверы"""
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

        Args:
            server_id: ID сервера

        Returns:
            bool: True если подключение запущено
        """
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]

        if server["connected"]:
            return True  # Уже подключен

        # Запускаем thread если не запущен
        thread = server["thread"]
        if not thread.isRunning():
            # Подключаемся после готовности loop
            thread.loop_ready.connect(lambda: thread.connect_to_server())
            thread.start()
        else:
            # Thread уже запущен, просто подключаемся
            thread.connect_to_server()

        return True

    def disconnect_server(self, server_id: str, blocking: bool = False) -> bool:
        """
        Отключиться от сервера

        Args:
            server_id: ID сервера
            blocking: Блокирующий режим (для closeEvent)

        Returns:
            bool: True если отключение запущено
        """
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]
        thread = server["thread"]

        if not server["connected"]:
            return True  # Уже отключен

        # Останавливаем thread
        thread.stop(blocking=blocking)

        return True

    def connect_all(self):
        """Подключить все серверы"""
        for server_id in self.servers.keys():
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

    def read_node(self, server_id: str, node_id: str) -> Optional[Any]:
        """
        Прочитать значение переменной

        Args:
            server_id: ID сервера
            node_id: NodeId (например "ns=2;s=Temperature")

        Returns:
            Значение переменной (через signal read_completed)
        """
        if server_id not in self.servers:
            return None

        server = self.servers[server_id]

        if not server["connected"]:
            return None

        # Запускаем чтение (результат в signal read_completed)
        thread = server["thread"]
        thread.read_node(node_id)

        return None  # Результат придет через signal

    def write_node(self, server_id: str, node_id: str, value: Any) -> bool:
        """
        Записать значение переменной

        Args:
            server_id: ID сервера
            node_id: NodeId (например "ns=2;s=SetPoint")
            value: Значение

        Returns:
            bool: True если запись запущена (результат в signal write_completed)
        """
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]

        if not server["connected"]:
            return False

        # Запускаем запись (результат в signal write_completed)
        thread = server["thread"]
        thread.write_node(node_id, value)

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
        Подписаться на изменения тега

        Args:
            server_id: ID сервера
            node_id: NodeId (например "ns=2;s=Temperature")
            tag_name: Имя тега (опционально)

        Returns:
            bool: True если подписка запущена
        """
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]

        if not server["connected"]:
            return False

        thread = server["thread"]
        thread.subscribe_tag(node_id, tag_name)

        return True

    def unsubscribe_tag(self, server_id: str, node_id: str) -> bool:
        """
        Отписаться от тега

        Args:
            server_id: ID сервера
            node_id: NodeId

        Returns:
            bool: True если отписка запущена
        """
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]

        if not server["connected"]:
            return False

        thread = server["thread"]
        thread.unsubscribe_tag(node_id)

        return True

    def subscribe_multiple_tags(
        self,
        server_id: str,
        tags: Dict[str, str]
    ) -> bool:
        """
        Подписаться на несколько тегов

        Args:
            server_id: ID сервера
            tags: Словарь {tag_name: node_id}

        Returns:
            bool: True если подписка запущена
        """
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]

        if not server["connected"]:
            return False

        thread = server["thread"]
        thread.subscribe_multiple_tags(tags)

        return True

    def get_subscribed_tags(self, server_id: str) -> List[str]:
        """
        Получить список подписанных тегов

        Args:
            server_id: ID сервера

        Returns:
            Список NodeId подписанных тегов
        """
        if server_id not in self.servers:
            return []

        server = self.servers[server_id]
        thread = server["thread"]

        return thread.get_subscribed_tags()

    # ==========================================================================
    # DATA ACCESS
    # ==========================================================================

    def get_latest_data(self, server_id: str) -> Dict[str, Any]:
        """
        Получить последние данные от сервера

        Args:
            server_id: ID сервера

        Returns:
            Словарь {node_id: value}
        """
        if server_id not in self.servers:
            return {}

        server = self.servers[server_id]
        thread = server["thread"]

        return thread.get_latest_data()

    def get_all_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Получить данные от всех серверов

        Returns:
            Словарь {server_id: {node_id: value}}
        """
        result = {}
        for server_id in self.servers.keys():
            result[server_id] = self.get_latest_data(server_id)

        return result

    # ==========================================================================
    # INTERNAL SIGNAL HANDLERS
    # ==========================================================================

    def _connect_thread_signals(self, server_id: str, thread: OpcUaWorkerThread):
        """Подключить signals от thread к backend"""
        thread.connected.connect(lambda: self._on_server_connected(server_id))
        thread.disconnected.connect(lambda: self._on_server_disconnected(server_id))
        thread.connection_error.connect(lambda err: self._on_server_error(server_id, err))
        thread.data_updated.connect(lambda nid, val: self._on_data_updated(server_id, nid, val))
        thread.tag_subscribed.connect(lambda nid: self._on_tag_subscribed(server_id, nid))
        thread.tag_unsubscribed.connect(lambda nid: self._on_tag_unsubscribed(server_id, nid))
        thread.read_completed.connect(lambda nid, val: self._on_read_completed(server_id, nid, val))
        thread.write_completed.connect(lambda nid, succ: self._on_write_completed(server_id, nid, succ))

    def _on_server_connected(self, server_id: str):
        """Обработчик подключения"""
        if server_id in self.servers:
            self.servers[server_id]["connected"] = True

        if self.on_connected:
            self.on_connected(server_id)

        self.server_connected.emit(server_id)

    def _on_server_disconnected(self, server_id: str):
        """Обработчик отключения"""
        if server_id in self.servers:
            self.servers[server_id]["connected"] = False

        if self.on_disconnected:
            self.on_disconnected(server_id)

        self.server_disconnected.emit(server_id)

    def _on_server_error(self, server_id: str, error: str):
        """Обработчик ошибки"""
        if self.on_connection_error:
            self.on_connection_error(server_id, error)

        self.server_error.emit(server_id, error)

    def _on_data_updated(self, server_id: str, node_id: str, value: Any):
        """Обработчик обновления данных"""
        if self.on_data_updated:
            self.on_data_updated(server_id, node_id, value)

        self.data_updated.emit(server_id, node_id, value)

    def _on_tag_subscribed(self, server_id: str, node_id: str):
        """Обработчик подписки на тег"""
        if self.on_tag_subscribed:
            self.on_tag_subscribed(server_id, node_id)

        self.tag_subscribed.emit(server_id, node_id)

    def _on_tag_unsubscribed(self, server_id: str, node_id: str):
        """Обработчик отписки от тега"""
        self.tag_unsubscribed.emit(server_id, node_id)

    def _on_read_completed(self, server_id: str, node_id: str, value: Any):
        """Обработчик завершения чтения"""
        self.read_completed.emit(server_id, node_id, value)

    def _on_write_completed(self, server_id: str, node_id: str, success: bool):
        """Обработчик завершения записи"""
        self.write_completed.emit(server_id, node_id, success)

    # ==========================================================================
    # LIFECYCLE
    # ==========================================================================

    def stop_all(self):
        """Остановить все серверы"""
        self.disconnect_all(blocking=True)
        self.servers.clear()
