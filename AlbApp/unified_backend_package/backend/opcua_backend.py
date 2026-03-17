"""
OpcUaBackend — программный API для управления множественными OPC UA серверами
==============================================================================

АРХИТЕКТУРА:
============
    ┌─────────────────────────────────────────┐
    │         User Application (ваш код)      │
    │                                         │
    │  backend = OpcUaBackend()               │
    │  backend.add_server("S1", endpoint)     │
    │  backend.connect_server("S1")           │
    │  backend.start_polling("S1", ...)       │
    └──────────────────┬──────────────────────┘
                       │
                       ▼
    ┌─────────────────────────────────────────┐
    │          OpcUaBackend (этот класс)      │
    │                                         │
    │  • Управление словарём серверов         │
    │  • Делегирование в OpcUaWorkerThread    │
    │  • Форвардинг Qt signals                │
    │  • Callbacks для событий                │
    └──────────┬──────────────┬───────────────┘
               │              │
               ▼              ▼
    ┌────────────────┐  ┌────────────────┐
    │OpcUaWorkerThread│  │OpcUaWorkerThread│
    │   (Server 1)   │  │   (Server 2)   │
    │  asyncio loop  │  │  asyncio loop  │
    └────────────────┘  └────────────────┘

ПОТОК ДАННЫХ (polling/subscription):
=====================================
    OpcUaBackend.start_polling(server_id, name, node_ids, interval)
        └─► OpcUaWorkerThread.start_polling(name, node_ids, interval)
                └─► asyncio: LifecycleMixin._poll_loop()
                        └─► worker.read_multiple_nodes()  ← asyncio.gather
                                └─► on_data_changed(node_id, value)
                                        └─► thread.data_updated.emit()
                                                └─► backend.data_updated.emit(server_id, ...)

CALLBACKS:
==========
Пользователь может установить функции для обработки событий без Qt:
    backend.on_connected           = lambda server_id: ...
    backend.on_disconnected        = lambda server_id: ...
    backend.on_connection_error    = lambda server_id, error: ...
    backend.on_data_updated        = lambda server_id, node_id, value: ...
    backend.on_tag_subscribed      = lambda server_id, node_id: ...
    backend.on_watchdog_disconnect = lambda server_id: ...

ПРИМЕР ИСПОЛЬЗОВАНИЯ:
=====================
    backend = OpcUaBackend()
    backend.on_connected = lambda s: print(f"{s} connected!")
    backend.data_updated.connect(lambda s, n, v: print(f"{s}|{n}={v}"))

    backend.add_server("PLC1", "opc.tcp://192.168.1.10:4840", namespace=2)
    backend.connect_server("PLC1")

    # После подключения (через сигнал server_connected):
    backend.start_polling("PLC1", "fast", ["ns=2;s=Temp", "ns=2;s=Press"], interval=0.2)
    backend.start_polling("PLC1", "slow", ["ns=2;s=Status"], interval=5.0)
    backend.start_watchdog("PLC1", interval=5.0)

    # При завершении:
    backend.stop_all()
"""

from typing import Dict, Optional, Callable, Any, List
from PyQt6.QtCore import QObject, pyqtSignal
from unified_backend_package.backend.worker.opcua.opcua_worker_thread import OpcUaWorkerThread


class OpcUaBackend(QObject):
    """
    Backend для управления множественными OPC UA серверами.

    Предоставляет thread-safe API поверх OpcUaWorkerThread:
    каждый сервер работает в своём QThread с собственным asyncio event loop.

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

    Подписки на теги (push-модель):
        subscribe_tag(server_id, node_id, tag_name)
        unsubscribe_tag(server_id, node_id)
        subscribe_multiple_tags(server_id, tags)
        get_subscribed_tags(server_id)

    Циклический опрос (poll-модель):
        start_polling(server_id, name, node_ids, interval)
        stop_polling(server_id, name)
        get_active_polls(server_id)

    Watchdog:
        start_watchdog(server_id, interval)
        stop_watchdog(server_id)
        is_watchdog_active(server_id)

    Exploration (browse / node_info / methods / history / events):
        browse_nodes(server_id, start_node_id, depth)
        read_node_info(server_id, node_id)
        call_method(server_id, parent_node_id, method_node_id, args)
        discover_methods(server_id, object_node_id)
        read_history(server_id, node_id, start_time, end_time, num_values)
        read_history_multiple(server_id, node_ids, ...)
        subscribe_events(server_id, source_node_id)
        unsubscribe_events(server_id, source_node_id)

    Данные и статистика:
        get_latest_data(server_id)
        get_all_data()
        get_stats(server_id)
    """

    # ===== SIGNALS =====

    # Подключение / отключение / ошибка
    server_connected    = pyqtSignal(str)       # (server_id) — успешное подключение
    server_disconnected = pyqtSignal(str)       # (server_id) — отключение (норм. или обрыв)
    server_error        = pyqtSignal(str, str)  # (server_id, error_str) — ошибка соединения

    # Данные реального времени (от подписок и polling)
    data_updated = pyqtSignal(str, str, object)  # (server_id, node_id, value)

    # Управление тегами
    tag_subscribed   = pyqtSignal(str, str)  # (server_id, node_id) — подписка оформлена
    tag_unsubscribed = pyqtSignal(str, str)  # (server_id, node_id) — подписка снята

    # Одиночные read/write
    read_completed  = pyqtSignal(str, str, object)  # (server_id, node_id, value)
    write_completed = pyqtSignal(str, str, bool)    # (server_id, node_id, success)

    # Пакетные read/write
    batch_read_completed  = pyqtSignal(str, dict)  # (server_id, {node_id: value})
    batch_write_completed = pyqtSignal(str, dict)  # (server_id, {node_id: success})

    # Watchdog
    watchdog_disconnect = pyqtSignal(str)  # (server_id) — обрыв обнаружен watchdog'ом

    # Exploration (browse / node_info / methods / history / events)
    browse_completed           = pyqtSignal(str, list)   # (server_id, nodes_list)
    node_info_completed        = pyqtSignal(str, dict)   # (server_id, info_dict)
    method_completed           = pyqtSignal(str, object) # (server_id, result)
    methods_discovered         = pyqtSignal(str, list)   # (server_id, methods_list)
    history_completed          = pyqtSignal(str, str, list)  # (server_id, node_id, data)
    history_multiple_completed = pyqtSignal(str, dict)   # (server_id, {node_id: data})
    event_received             = pyqtSignal(str, dict)   # (server_id, event_dict)

    # ==========================================================================

    def __init__(self):
        """Инициализация backend. Серверы добавляются через add_server()."""
        super().__init__()

        # Словарь серверов: {server_id: {"endpoint", "namespace", "timeout", "thread"}}
        # "thread" = None до первого connect_server(); создаётся/пересоздаётся там.
        self.servers: Dict[str, dict] = {}

        # ===== CALLBACKS (альтернатива Qt signals для non-GUI кода) =====
        self.on_connected           : Optional[Callable[[str], None]]          = None
        self.on_disconnected        : Optional[Callable[[str], None]]          = None
        self.on_connection_error    : Optional[Callable[[str, str], None]]     = None
        self.on_data_updated        : Optional[Callable[[str, str, Any], None]] = None
        self.on_tag_subscribed      : Optional[Callable[[str, str], None]]     = None
        self.on_watchdog_disconnect : Optional[Callable[[str], None]]          = None

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
        Зарегистрировать OPC UA сервер (БЕЗ подключения).

        Thread создаётся только при первом вызове connect_server(),
        что позволяет добавлять серверы заранее и подключаться позже.

        Args:
            server_id : Уникальный строковый ключ ("PLC1", "SCADA", ...)
            endpoint  : URL сервера ("opc.tcp://192.168.1.10:4840")
            namespace : Namespace index для тегов (по умолчанию 2)
            timeout   : Таймаут операций connect/read/write в секундах

        Returns:
            True  — сервер добавлен
            False — server_id уже зарегистрирован
        """
        if server_id in self.servers:
            return False

        self.servers[server_id] = {
            "endpoint":  endpoint,
            "namespace": namespace,
            "timeout":   timeout,
            "thread":    None,   # будет создан в connect_server()
        }
        return True

    def remove_server(self, server_id: str, force: bool = False) -> bool:
        """
        Удалить сервер из backend.

        Args:
            server_id : ID сервера
            force     : True — отключить перед удалением если подключён;
                        False — отказать если подключён

        Returns:
            True  — сервер удалён
            False — сервер не найден, или подключён и force=False
        """
        if server_id not in self.servers:
            return False

        if self.is_connected(server_id):
            if not force:
                return False
            # Блокирующий disconnect гарантирует остановку thread
            # ДО удаления записи из словаря (иначе сигналы thread
            # попадут в _on_server_disconnected уже после del)
            self.disconnect_server(server_id, blocking=True)

        del self.servers[server_id]
        return True

    def get_servers(self) -> Dict[str, dict]:
        """
        Получить список всех зарегистрированных серверов.

        Returns:
            {server_id: {"endpoint": str, "namespace": int, "connected": bool}}
            Внутренний объект thread не включается.
        """
        return {
            srv_id: {
                "endpoint":  srv["endpoint"],
                "namespace": srv["namespace"],
                "connected": self.is_connected(srv_id),  # актуальный статус через thread
            }
            for srv_id, srv in self.servers.items()
        }

    def is_connected(self, server_id: str) -> bool:
        """
        Проверить актуальный статус подключения сервера.

        Делегирует в thread.is_connected — источник истины.
        Это важно после auto-reconnect: worker восстанавливает соединение
        внутри asyncio loop напрямую, не через _async_connect,
        поэтому backend не получает повторный сигнал connected.
        thread.is_connected всегда отражает реальное состояние worker'а.

        Returns:
            True  — подключён
            False — не подключён, сервер не найден, или Qt-объект thread уже удалён
        """
        server = self.servers.get(server_id)
        if not server:
            return False
        thread = server.get("thread")
        if thread:
            try:
                return thread.is_connected
            except RuntimeError:
                pass  # C++ объект Qt уже удалён через deleteLater()
        return False

    # ==========================================================================
    # CONNECTION
    # ==========================================================================

    def connect_server(self, server_id: str) -> bool:
        """
        Запустить подключение к серверу (неблокирующий).

        Если thread не существует или уже удалён (после предыдущего disconnect) —
        создаёт новый OpcUaWorkerThread, подключает все signals и запускает поток.
        Если поток уже запущен и просто не подключён — отправляет connect_to_server().

        Результат подключения приходит через signal server_connected(server_id)
        или server_error(server_id, error).

        Returns:
            True  — запрос отправлен (или уже подключён)
            False — server_id не зарегистрирован
        """
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]

        if self.is_connected(server_id):
            return True  # Уже подключён

        # Проверяем жив ли старый thread.
        # После disconnect thread уничтожается через deleteLater() —
        # Python-обёртка бросает RuntimeError при любом обращении к C++ объекту.
        thread = server.get("thread")
        try:
            is_running = thread.isRunning() if thread else False
        except RuntimeError:
            is_running = False
            thread = None

        if not is_running:
            # Thread отсутствует, ещё не запускался, или удалён — создаём новый.
            # loop_ready подключается первым: connect_to_server() вызывается
            # только после того, как asyncio event loop полностью готов.
            thread = OpcUaWorkerThread(
                server_id=server_id,
                endpoint=server["endpoint"],
                namespace=server["namespace"],
                timeout=server["timeout"]
            )
            self._connect_thread_signals(server_id, thread)
            server["thread"] = thread
            thread.loop_ready.connect(lambda: thread.connect_to_server())
            thread.start()
        else:
            # Поток уже работает (loop готов) — просто подключаемся
            thread.connect_to_server()

        return True

    def disconnect_server(self, server_id: str, blocking: bool = False) -> bool:
        """
        Отключиться от сервера.

        Args:
            blocking : False — неблокирующий (для GUI, disconnect в фоне)
                       True  — блокирующий (для closeEvent, ждём остановки thread)

        Returns:
            True  — запрос отправлен (или уже отключён)
            False — server_id не найден
        """
        if server_id not in self.servers:
            return False

        if not self.is_connected(server_id):
            return True  # Уже отключён

        self.servers[server_id]["thread"].stop(blocking=blocking)
        return True

    def connect_all(self):
        """Подключить все зарегистрированные серверы (которые ещё не подключены)."""
        for server_id in self.servers:
            if not self.is_connected(server_id):
                self.connect_server(server_id)

    def disconnect_all(self, blocking: bool = False):
        """
        Отключить все подключённые серверы.

        При blocking=True все потоки останавливаются параллельно (stop без wait),
        затем ждём завершения каждого — итоговое время = max(одного), не сумма.

        Args:
            blocking : False — отправить stop всем и вернуться
                       True  — дождаться остановки каждого потока (max 2 сек на каждый)
        """
        threads = []
        for server_id in list(self.servers.keys()):
            server = self.servers.get(server_id)
            if server and self.is_connected(server_id):
                server["thread"].stop(blocking=False)  # Запускаем все сразу
                threads.append(server["thread"])

        if blocking:
            for thread in threads:
                try:
                    thread.wait(2000)  # Ждём завершения потока (max 2 сек)
                except RuntimeError:
                    pass  # Thread уже удалён через deleteLater()

    # ==========================================================================
    # READ / WRITE
    # ==========================================================================

    def read_node(self, server_id: str, node_id: str) -> bool:
        """
        Прочитать значение одного узла (асинхронный запрос).

        Результат приходит через signal read_completed(server_id, node_id, value).
        При ошибке — server_error(server_id, error).

        Args:
            server_id : ID сервера
            node_id   : NodeId узла ("ns=2;s=Temperature")

        Returns:
            True  — запрос поставлен в очередь asyncio loop
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.read_node(node_id)
        return True

    def write_node(self, server_id: str, node_id: str, value: Any) -> bool:
        """
        Записать значение одного узла (асинхронный запрос).

        Результат приходит через signal write_completed(server_id, node_id, success).
        При ошибке — server_error(server_id, error) + write_completed(..., False).

        Args:
            server_id : ID сервера
            node_id   : NodeId узла ("ns=2;s=SetPoint")
            value     : Значение; тип должен совпадать с типом узла на сервере

        Returns:
            True  — запрос поставлен в очередь
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.write_node(node_id, value)
        return True

    def read_multiple_nodes(self, server_id: str, node_ids: List[str]) -> bool:
        """
        Пакетное параллельное чтение нескольких узлов (asyncio.gather).

        Все теги читаются одновременно — время ≈ max(одного запроса), не сумма.
        При ошибке отдельного тега остальные читаются, ошибочное значение → None.

        Результат: signal batch_read_completed(server_id, {node_id: value}).

        Args:
            server_id : ID сервера
            node_ids  : Список NodeId ["ns=2;s=Temp", "ns=2;s=Pressure", ...]

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.read_multiple_nodes(node_ids)
        return True

    def write_multiple_nodes(self, server_id: str, values: Dict[str, Any]) -> bool:
        """
        Пакетная параллельная запись нескольких узлов (asyncio.gather).

        Все теги пишутся одновременно. При ошибке одного — остальные записываются.

        Результат: signal batch_write_completed(server_id, {node_id: success}).

        Args:
            server_id : ID сервера
            values    : Словарь {node_id: value}

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.write_multiple_nodes(values)
        return True

    # ==========================================================================
    # SUBSCRIPTION (TAG MANAGEMENT)  — push-модель
    # ==========================================================================

    def subscribe_tag(
        self,
        server_id: str,
        node_id: str,
        tag_name: Optional[str] = None
    ) -> bool:
        """
        Подписаться на изменения тега (OPC UA DataChange Subscription).

        Сервер сам присылает новое значение при каждом изменении — poll не нужен.
        Подходит для критичных тегов с быстрыми изменениями.

        Результат подписки: signal tag_subscribed(server_id, node_id).
        Данные при изменении: signal data_updated(server_id, node_id, value).

        Args:
            server_id : ID сервера
            node_id   : NodeId тега ("ns=2;s=Temperature")
            tag_name  : Человекочитаемое имя (опционально, для отладки)

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.subscribe_tag(node_id, tag_name)
        return True

    def unsubscribe_tag(self, server_id: str, node_id: str) -> bool:
        """
        Отписаться от тега.

        Результат: signal tag_unsubscribed(server_id, node_id).

        Args:
            server_id : ID сервера
            node_id   : NodeId тега

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.unsubscribe_tag(node_id)
        return True

    def subscribe_multiple_tags(self, server_id: str, tags: Dict[str, str]) -> bool:
        """
        Подписаться на несколько тегов за один вызов.

        Для каждого успешно подписанного тега придёт
        signal tag_subscribed(server_id, node_id).

        Args:
            server_id : ID сервера
            tags      : Словарь {tag_name: node_id}

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.subscribe_multiple_tags(tags)
        return True

    def get_subscribed_tags(self, server_id: str) -> List[str]:
        """
        Получить список NodeId всех активных подписок сервера (синхронный).

        Читает прямо из worker.subscribed_tags — без round-trip к OPC UA серверу.

        Returns:
            Список NodeId или [] если сервер не найден / не запущен
        """
        thread = self._get_thread(server_id)
        if not thread:
            return []
        return thread.get_subscribed_tags()

    # ==========================================================================
    # WATCHDOG — heartbeat-проверка живости соединения
    # ==========================================================================

    def start_watchdog(self, server_id: str, interval: float = 5.0) -> bool:
        """
        Запустить watchdog — периодическую heartbeat-проверку соединения.

        Читает ServerStatus.CurrentTime (i=2258) каждые N секунд.
        Это самый лёгкий запрос, доступный на любом OPC UA сервере.
        При обрыве — немедленно запускает auto-reconnect (если включён).

        При обнаружении обрыва эмитит:
          - watchdog_disconnect(server_id) — специфичный сигнал
          - server_disconnected(server_id) — стандартный сигнал отключения
          - вызывает callback on_watchdog_disconnect

        Args:
            server_id : ID сервера
            interval  : Интервал проверки в секундах (рекомендуется 3–10)

        Returns:
            True  — watchdog запущен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.start_watchdog(interval)
        return True

    def stop_watchdog(self, server_id: str) -> bool:
        """
        Остановить watchdog.

        Можно вызвать даже если сервер не подключён
        (например, при cleanup до disconnect).

        Returns:
            True  — запрос отправлен
            False — сервер не найден
        """
        thread = self._get_thread(server_id)
        if not thread:
            return False
        thread.stop_watchdog()
        return True

    def is_watchdog_active(self, server_id: str) -> bool:
        """
        Проверить активность watchdog (синхронный).

        Returns:
            True  — watchdog запущен и работает
            False — остановлен, или сервер не найден
        """
        thread = self._get_thread(server_id)
        if not thread:
            return False
        return thread.is_watchdog_active

    # ==========================================================================
    # POLLING API — циклический опрос массива тегов
    # ==========================================================================

    def start_polling(
        self,
        server_id: str,
        name: str,
        node_ids: List[str],
        interval: float = 1.0
    ) -> bool:
        """
        Запустить именованный цикл периодического опроса тегов.

        Каждую итерацию читает все теги параллельно (asyncio.gather),
        результаты приходят через signal data_updated(server_id, node_id, value).

        Можно запустить несколько циклов с разными интервалами:
            start_polling("PLC1", "fast", critical_tags, interval=0.2)
            start_polling("PLC1", "slow", status_tags,   interval=5.0)

        При обрыве соединения цикл останавливается и запускает auto-reconnect.
        После восстановления — цикл автоматически восстанавливается.

        Args:
            server_id : ID сервера
            name      : Уникальное имя цикла ("fast", "slow", "diagnostics", ...)
            node_ids  : Список NodeId для опроса
            interval  : Интервал опроса в секундах (по умолчанию 1.0)

        Returns:
            True  — цикл запущен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.start_polling(name, node_ids, interval)
        return True

    def stop_polling(self, server_id: str, name: Optional[str] = None) -> bool:
        """
        Остановить цикл(ы) опроса.

        Можно вызвать даже если сервер не подключён
        (например, перед disconnect для корректного cleanup).

        Args:
            server_id : ID сервера
            name      : Имя конкретного цикла; None — остановить все циклы

        Returns:
            True  — запрос отправлен
            False — сервер не найден
        """
        thread = self._get_thread(server_id)
        if not thread:
            return False
        thread.stop_polling(name)
        return True

    def get_active_polls(self, server_id: str) -> Dict[str, Dict]:
        """
        Получить информацию об активных циклах опроса (синхронный).

        Читает напрямую из worker._poll_loops — без asyncio round-trip.

        Returns:
            {name: {"nodes": [node_id, ...], "interval": float}}
            Пустой dict если сервер не найден или нет активных циклов
        """
        thread = self._get_thread(server_id)
        if not thread:
            return {}
        return thread.get_active_polls()

    # ==========================================================================
    # EXPLORATION API — исследование OPC UA сервера
    # ==========================================================================

    def browse_nodes(
        self,
        server_id: str,
        start_node_id: Optional[str] = None,
        depth: int = 1
    ) -> bool:
        """
        Обзор дерева узлов сервера.

        Позволяет найти доступные переменные и объекты без знания NodeId заранее.
        По умолчанию начинает с Objects (i=85) — корня пользовательских данных.

        Результат: signal browse_completed(server_id, nodes)
            nodes = [{"node_id": str, "name": str, "node_class": str,
                      "children": [...]}, ...]

        Args:
            server_id     : ID сервера
            start_node_id : Стартовый узел (None = Objects — корень)
            depth         : Глубина рекурсии (1 = только дочерние)

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.browse_nodes(start_node_id, depth)
        return True

    def read_node_info(self, server_id: str, node_id: str) -> bool:
        """
        Расширенное чтение узла: значение + timestamp + quality + тип данных.

        В отличие от read_node() (только значение) возвращает полную структуру DataValue.

        Результат: signal node_info_completed(server_id, info)
            info = {"node_id", "value", "source_timestamp", "server_timestamp",
                    "status_code", "data_type"}

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.read_node_info(node_id)
        return True

    def call_method(
        self,
        server_id: str,
        parent_node_id: str,
        method_node_id: str,
        args: Optional[List] = None
    ) -> bool:
        """
        Вызвать OPC UA метод на сервере (Remote Procedure Call).

        OPC UA Method — функция на сервере: StartPump(), ResetAlarm(), SetTemperature().
        Метод принадлежит Object-узлу: parent — объект, method — сам метод.

        Результат: signal method_completed(server_id, result)
            result = возвращаемое значение метода или None для void-методов

        Args:
            server_id      : ID сервера
            parent_node_id : NodeId Object-узла владельца ("ns=2;s=Pump1")
            method_node_id : NodeId метода ("ns=2;s=Start")
            args           : Список аргументов или None
                             Пример: [ua.Variant(250.0, ua.VariantType.Float)]

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.call_method(parent_node_id, method_node_id, args)
        return True

    def discover_methods(self, server_id: str, object_node_id: str) -> bool:
        """
        Обнаружить все доступные методы на объекте.

        Результат: signal methods_discovered(server_id, methods)
            methods = [{"node_id": str, "name": str}, ...]

        Args:
            server_id      : ID сервера
            object_node_id : NodeId Object-узла ("ns=2;s=MyDevice")

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.discover_methods(object_node_id)
        return True

    def read_history(
        self,
        server_id: str,
        node_id: str,
        start_time=None,
        end_time=None,
        num_values: int = 0
    ) -> bool:
        """
        Чтение исторических данных тега за период (Historian).

        Требует Historizing=True на узле и наличия historian'а на сервере
        (поддерживают: Kepware, Prosys, Unified Automation).

        Результат: signal history_completed(server_id, node_id, data)
            data = [{"timestamp": datetime, "value": Any, "status": str}, ...]

        Args:
            server_id  : ID сервера
            node_id    : NodeId тега ("ns=2;s=Temperature")
            start_time : Начало периода UTC (None = час назад)
            end_time   : Конец периода UTC   (None = сейчас)
            num_values : Макс. число точек (0 = всё, лимит на стороне сервера)

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.read_history(node_id, start_time, end_time, num_values)
        return True

    def read_history_multiple(
        self,
        server_id: str,
        node_ids: List[str],
        start_time=None,
        end_time=None,
        num_values: int = 0
    ) -> bool:
        """
        Пакетное параллельное чтение истории нескольких тегов (asyncio.gather).

        Все теги читаются одновременно.
        При ошибке одного — в результате будет пустой список [].

        Результат: signal history_multiple_completed(server_id, results)
            results = {node_id: [{"timestamp", "value", "status"}, ...]}

        Args:
            server_id  : ID сервера
            node_ids   : Список NodeId
            start_time : Начало периода UTC (None = час назад)
            end_time   : Конец периода UTC   (None = сейчас)
            num_values : Макс. число точек на тег (0 = все)

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.read_history_multiple(node_ids, start_time, end_time, num_values)
        return True

    def subscribe_events(
        self,
        server_id: str,
        source_node_id: Optional[str] = None
    ) -> bool:
        """
        Подписаться на OPC UA события (аварии, условия, уведомления).

        OPC UA Events — push-уведомления от сервера о системных событиях
        (аварийные сигналы, изменения состояний, действия оператора).

        События приходят через signal event_received(server_id, event):
            event = {"source", "message", "severity", "time", "event_type"}

        Args:
            server_id      : ID сервера
            source_node_id : Источник событий (None = все события сервера)

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.subscribe_events(source_node_id)
        return True

    def unsubscribe_events(
        self,
        server_id: str,
        source_node_id: Optional[str] = None
    ) -> bool:
        """
        Отписаться от OPC UA событий.

        Args:
            server_id      : ID сервера
            source_node_id : Тот же source что был передан в subscribe_events()

        Returns:
            True  — запрос отправлен
            False — сервер не подключён
        """
        thread = self._get_connected_thread(server_id)
        if not thread:
            return False
        thread.unsubscribe_events(source_node_id)
        return True

    # ==========================================================================
    # DATA ACCESS
    # ==========================================================================

    def get_latest_data(self, server_id: str) -> Dict[str, Any]:
        """
        Получить последние известные значения всех тегов сервера (из кэша).

        Возвращает данные без обращения к OPC UA серверу —
        кэш обновляется автоматически через подписки и polling.

        Returns:
            {node_id: value} — снимок кэша на момент вызова
            {} если сервер не найден или thread не запущен
        """
        thread = self._get_thread(server_id)
        if not thread:
            return {}
        return thread.get_latest_data()

    def get_all_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Получить кэшированные данные от всех зарегистрированных серверов.

        Returns:
            {server_id: {node_id: value}}
        """
        return {srv_id: self.get_latest_data(srv_id) for srv_id in self.servers}

    def get_stats(self, server_id: str) -> Dict[str, Any]:
        """
        Получить статистику операций сервера (синхронный).

        Читает из worker._stats без round-trip к OPC UA серверу.

        Returns:
            Dict с полями: reads, writes, read_errors, write_errors,
                           reconnects, last_read_ms, last_write_ms, ...
            {} если сервер не найден или thread не запущен
        """
        thread = self._get_thread(server_id)
        if not thread:
            return {}
        return thread.get_stats()

    # ==========================================================================
    # LIFECYCLE
    # ==========================================================================

    def stop_all(self):
        """
        Остановить все серверы и очистить backend (блокирующий).

        ВАЖНО: вызывать при закрытии приложения (closeEvent) для корректного
        завершения всех asyncio loop'ов и OPC UA соединений.
        После вызова backend не пригоден для повторного использования.
        """
        self.disconnect_all(blocking=True)
        self.servers.clear()

    # ==========================================================================
    # INTERNAL HELPERS
    # ==========================================================================

    def _get_thread(self, server_id: str) -> Optional[OpcUaWorkerThread]:
        """
        Получить thread по server_id без проверки статуса подключения.

        Используется для операций, допустимых даже в отключённом состоянии:
        stop_watchdog, stop_polling, get_subscribed_tags, get_stats и т.д.

        Returns:
            OpcUaWorkerThread или None если сервер не найден / thread не создан
        """
        server = self.servers.get(server_id)
        if not server:
            return None
        return server.get("thread")

    def _get_connected_thread(self, server_id: str) -> Optional[OpcUaWorkerThread]:
        """
        Получить thread только если сервер подключён.

        Используется для всех операций, требующих активного соединения:
        read_node, write_node, subscribe_tag, browse_nodes и т.д.

        Проверяет через is_connected() → thread.is_connected (источник истины),
        что корректно отражает состояние после auto-reconnect.

        Returns:
            OpcUaWorkerThread если подключён, иначе None
        """
        if not self.is_connected(server_id):
            return None
        return self.servers[server_id]["thread"]

    # ==========================================================================
    # INTERNAL SIGNAL HANDLERS
    # ==========================================================================

    def _connect_thread_signals(self, server_id: str, thread: OpcUaWorkerThread):
        """
        Подключить все signals от OpcUaWorkerThread к backend.

        Вызывается один раз при создании нового thread в connect_server().
        server_id захватывается через замыкание (lambda) — каждый thread
        знает свой server_id и правильно помечает данные при форвардинге.
        """
        # Подключение / отключение / ошибка
        thread.connected.connect(
            lambda: self._on_server_connected(server_id))
        thread.disconnected.connect(
            lambda: self._on_server_disconnected(server_id))
        thread.connection_error.connect(
            lambda err: self._on_server_error(server_id, err))

        # Данные от подписок и polling
        thread.data_updated.connect(
            lambda nid, val: self._on_data_updated(server_id, nid, val))

        # Теги
        thread.tag_subscribed.connect(
            lambda nid: self._on_tag_subscribed(server_id, nid))
        thread.tag_unsubscribed.connect(
            lambda nid: self._on_tag_unsubscribed(server_id, nid))

        # Одиночные read/write
        thread.read_completed.connect(
            lambda nid, val: self._on_read_completed(server_id, nid, val))
        thread.write_completed.connect(
            lambda nid, succ: self._on_write_completed(server_id, nid, succ))

        # Пакетные read/write
        thread.batch_read_completed.connect(
            lambda results: self._on_batch_read_completed(server_id, results))
        thread.batch_write_completed.connect(
            lambda results: self._on_batch_write_completed(server_id, results))

        # Watchdog
        thread.watchdog_disconnect.connect(
            lambda: self._on_watchdog_disconnect(server_id))

        # Exploration — добавляем server_id к каждому сигналу thread
        thread.browse_completed.connect(
            lambda res:       self.browse_completed.emit(server_id, res))
        thread.node_info_completed.connect(
            lambda res:       self.node_info_completed.emit(server_id, res))
        thread.method_completed.connect(
            lambda res:       self.method_completed.emit(server_id, res))
        thread.methods_discovered.connect(
            lambda res:       self.methods_discovered.emit(server_id, res))
        thread.history_completed.connect(
            lambda nid, res:  self.history_completed.emit(server_id, nid, res))
        thread.history_multiple_completed.connect(
            lambda res:       self.history_multiple_completed.emit(server_id, res))
        thread.event_received.connect(
            lambda ev:        self.event_received.emit(server_id, ev))

    def _on_server_connected(self, server_id: str):
        """Вызывается при успешном подключении thread к серверу."""
        if self.on_connected:
            self.on_connected(server_id)
        self.server_connected.emit(server_id)

    def _on_server_disconnected(self, server_id: str):
        """Вызывается при отключении (нормальном или по обрыву)."""
        if self.on_disconnected:
            self.on_disconnected(server_id)
        self.server_disconnected.emit(server_id)

    def _on_server_error(self, server_id: str, error: str):
        """Вызывается при ошибке подключения или операции."""
        if self.on_connection_error:
            self.on_connection_error(server_id, error)
        self.server_error.emit(server_id, error)

    def _on_data_updated(self, server_id: str, node_id: str, value: Any):
        """Вызывается при изменении значения тега (подписка или polling)."""
        if self.on_data_updated:
            self.on_data_updated(server_id, node_id, value)
        self.data_updated.emit(server_id, node_id, value)

    def _on_tag_subscribed(self, server_id: str, node_id: str):
        """Вызывается при успешном оформлении подписки на тег."""
        if self.on_tag_subscribed:
            self.on_tag_subscribed(server_id, node_id)
        self.tag_subscribed.emit(server_id, node_id)

    def _on_tag_unsubscribed(self, server_id: str, node_id: str):
        """Вызывается при успешной отписке от тега."""
        self.tag_unsubscribed.emit(server_id, node_id)

    def _on_read_completed(self, server_id: str, node_id: str, value: Any):
        """Вызывается при завершении одиночного чтения."""
        self.read_completed.emit(server_id, node_id, value)

    def _on_write_completed(self, server_id: str, node_id: str, success: bool):
        """Вызывается при завершении одиночной записи."""
        self.write_completed.emit(server_id, node_id, success)

    def _on_batch_read_completed(self, server_id: str, results: dict):
        """Вызывается при завершении пакетного чтения."""
        self.batch_read_completed.emit(server_id, results)

    def _on_batch_write_completed(self, server_id: str, results: dict):
        """Вызывается при завершении пакетной записи."""
        self.batch_write_completed.emit(server_id, results)

    def _on_watchdog_disconnect(self, server_id: str):
        """Вызывается когда watchdog обнаружил обрыв соединения."""
        if self.on_watchdog_disconnect:
            self.on_watchdog_disconnect(server_id)
        self.watchdog_disconnect.emit(server_id)
