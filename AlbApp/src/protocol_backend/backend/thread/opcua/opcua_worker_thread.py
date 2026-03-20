"""
OpcUaWorkerThread - QThread обертка для AsyncOpcUaWorker

Каждый OPC UA сервер работает в отдельном потоке с собственным asyncio event loop.
Паттерн: PLCWorkerThread (QThread + asyncio)
"""

import asyncio
import threading
from typing import Optional, Dict, Any, List, Callable
from PyQt6.QtCore import QThread, pyqtSignal


class OpcUaWorkerThread(QThread):
    """
    QThread обертка для AsyncOpcUaWorker с собственным asyncio event loop

    ПАТТЕРН:
    ========
    - Каждый OPC UA сервер в отдельном QThread
    - Собственный asyncio event loop в потоке
    - Thread-safe коммуникация через signals
    - Неблокирующие операции для GUI

    SIGNALS:
    ========
    - loop_ready: Event loop готов
    - connected: Успешное подключение
    - disconnected: Отключение
    - connection_error: Ошибка подключения
    - data_updated: Обновление данных от подписок (node_id, value)
    - tag_subscribed: Тег подписан (node_id)
    - tag_unsubscribed: Тег отписан (node_id)
    - read_completed: Чтение завершено (node_id, value)
    - write_completed: Запись завершена (node_id, success)

    ПРИМЕР ИСПОЛЬЗОВАНИЯ:
    =====================
    # Создаем thread
    thread = OpcUaWorkerThread(
        server_id="OPC1",
        endpoint="opc.tcp://192.168.1.10:4840",
        namespace=2
    )

    # Подключаем signals
    thread.connected.connect(lambda: print("Connected!"))
    thread.data_updated.connect(lambda nid, val: print(f"{nid} = {val}"))

    # Запускаем и подключаемся
    thread.loop_ready.connect(lambda: thread.connect_to_server())
    thread.start()

    # Подписываемся на тег
    thread.subscribe_tag("ns=2;s=Temperature", "Temperature")

    # Читаем значение
    thread.read_node("ns=2;s=Pressure")

    # Останавливаем
    thread.stop(blocking=False)
    """

    # ===== SIGNALS =====
    loop_ready = pyqtSignal()               # Event loop готов
    connected = pyqtSignal()                # Успешное подключение
    disconnected = pyqtSignal()             # Отключение
    connection_error = pyqtSignal(str)      # Ошибка подключения
    data_updated = pyqtSignal(str, object)  # (node_id, value)
    tag_subscribed = pyqtSignal(str)        # (node_id)
    tag_unsubscribed = pyqtSignal(str)      # (node_id)
    read_completed = pyqtSignal(str, object)   # (node_id, value)
    write_completed = pyqtSignal(str, bool)    # (node_id, success)
    batch_read_completed = pyqtSignal(dict)    # {node_id: value}
    batch_write_completed = pyqtSignal(dict)   # {node_id: success}
    watchdog_disconnect = pyqtSignal()         # Watchdog обнаружил обрыв
    # Exploration signals
    browse_completed = pyqtSignal(list)        # [{"node_id", "name", "node_class", "children"}]
    node_info_completed = pyqtSignal(dict)     # {"node_id", "value", "source_timestamp", ...}
    method_completed = pyqtSignal(object)      # результат вызова метода (любой тип)
    methods_discovered = pyqtSignal(list)      # [{"node_id", "name"}, ...]
    history_completed = pyqtSignal(str, list)  # (node_id, [{"timestamp", "value", "status"}])
    history_multiple_completed = pyqtSignal(dict)  # {node_id: [{"timestamp", "value", "status"}]}
    event_received = pyqtSignal(dict)          # {"source", "message", "severity", "time", "event_type"}

    def __init__(
        self,
        server_id: str,
        endpoint: str,
        namespace: int = 2,
        timeout: float = 10.0
    ):
        """
        Инициализация OPC UA worker thread

        Args:
            server_id: Уникальный ID сервера
            endpoint: URL сервера (например "opc.tcp://192.168.1.10:4840")
            namespace: Namespace index (по умолчанию 2)
            timeout: Таймаут операций
        """
        super().__init__()

        self.server_id = server_id
        self.endpoint = endpoint
        self.namespace = namespace
        self.timeout = timeout

        # Asyncio event loop (создается в run())
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Worker (создается после запуска event loop)
        self.worker: Optional[Any] = None  # AsyncOpcUaWorker

        # Флаги состояния
        self._connected = False
        self._stopping = False
        self._loop_ready = False
        self._latest_data_lock = threading.Lock()
        self._latest_data: Dict[str, Any] = {}
        self._data_changed_flag = False  # dirty-флаг для has_data_changed()

    # ==========================================================================
    # QTHREAD LIFECYCLE
    # ==========================================================================

    def run(self):
        """
        Основной метод потока - запуск asyncio event loop

        ВАЖНО: Создается НОВЫЙ event loop для изоляции от других потоков
        """
        # Создаем НОВЫЙ event loop в этом потоке
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        # asyncua 1.x имеет баг: в asyncio debug mode падает issubclass()
        # при разборе endpoint'ов сервера. Отключаем явно.
        self.loop.set_debug(False)

        # Импортируем здесь, чтобы избежать проблем с импортами
        from protocol_backend.backend.thread.opcua.worker.opcua_worker import AsyncOpcUaWorker

        # Создаем worker с callback для data_updated
        self.worker = AsyncOpcUaWorker(
            endpoint=self.endpoint,
            namespace=self.namespace,
            timeout=self.timeout,
            on_data_changed=self._on_data_changed
        )

        # Сигнализируем что loop готов
        self._loop_ready = True
        self.loop_ready.emit()

        # Запускаем event loop (блокирует до stop)
        try:
            self.loop.run_forever()
        finally:
            # Cleanup при остановке
            self.loop.close()

    def stop(self, blocking: bool = False):
        """
        Остановить поток

        Args:
            blocking: Блокирующий режим (ждать завершения)
                     False - для GUI (неблокирующий disconnect)
                     True - для closeEvent (корректное завершение)
        """
        if self._stopping:
            return  # Уже останавливаемся

        self._stopping = True

        if self.loop and self.worker:
            # Запускаем shutdown-корутину: сначала disconnect (с эмитом сигнала),
            # потом stop loop. Это гарантирует что loop.stop() вызывается только
            # ПОСЛЕ завершения disconnect, а не параллельно с ним.
            future = asyncio.run_coroutine_threadsafe(
                self._async_shutdown(), self.loop
            )
            if blocking:
                try:
                    future.result(timeout=2.0)
                except Exception:
                    pass

        if blocking:
            self.wait(2000)  # Ждем завершения потока (max 2 сек)
            self.deleteLater()  # Поток уже завершён — безопасно удалять
        else:
            # Удаляем объект только ПОСЛЕ завершения потока.
            # Прямой вызов deleteLater() здесь опасен: Qt может удалить C++
            # объект пока run() ещё выполняется → crash → приложение закрывается.
            self.finished.connect(self.deleteLater)

    def is_loop_ready(self) -> bool:
        """Проверка готовности event loop"""
        return self._loop_ready and self.loop is not None

    # ==========================================================================
    # CONNECTION API
    # ==========================================================================

    def connect_to_server(self):
        """Подключиться к OPC UA серверу (thread-safe)"""
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")

        asyncio.run_coroutine_threadsafe(self._async_connect(), self.loop)

    async def _async_connect(self):
        """Async подключение к серверу"""
        try:
            success = await self.worker.connect()
            if success:
                self._connected = True
                self.connected.emit()
        except Exception as e:
            self.connection_error.emit(str(e))

    def disconnect_from_server(self):
        """Отключиться от сервера (thread-safe)"""
        if not self.is_loop_ready():
            return

        asyncio.run_coroutine_threadsafe(self._async_disconnect(), self.loop)

    async def _async_disconnect(self):
        """Async отключение от сервера"""
        try:
            await self.worker.disconnect()
            self._connected = False
            self.disconnected.emit()
        except Exception as e:
            self.connection_error.emit(str(e))

    async def _async_shutdown(self):
        """
        Корректное завершение: disconnect → emit сигнала → stop loop.

        Используется в stop(). Порядок важен:
          1. worker.disconnect() — закрывает watchdog, subscription, client
          2. disconnected.emit() — GUI/backend получают уведомление
          3. loop.stop() — только после disconnect, не параллельно с ним
        """
        if self._connected:
            try:
                await self.worker.disconnect()
                self._connected = False
                self.disconnected.emit()
            except Exception as e:
                self.connection_error.emit(str(e))
        self.loop.stop()

    # ==========================================================================
    # READ / WRITE API
    # ==========================================================================

    def read_node(self, node_id: str):
        """
        Прочитать значение переменной (thread-safe)

        Args:
            node_id: NodeId (например "ns=2;s=Temperature")
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")

        asyncio.run_coroutine_threadsafe(
            self._async_read_node(node_id), self.loop
        )

    async def _async_read_node(self, node_id: str):
        """Async чтение переменной"""
        try:
            value = await self.worker.read_node(node_id)
            self.read_completed.emit(node_id, value)
        except Exception as e:
            self.connection_error.emit(f"Read error: {e}")

    def write_node(self, node_id: str, value: Any):
        """
        Записать значение переменной (thread-safe)

        Args:
            node_id: NodeId (например "ns=2;s=SetPoint")
            value: Значение для записи
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")

        asyncio.run_coroutine_threadsafe(
            self._async_write_node(node_id, value), self.loop
        )

    async def _async_write_node(self, node_id: str, value: Any):
        """Async запись переменной"""
        try:
            success = await self.worker.write_node(node_id, value)
            self.write_completed.emit(node_id, success)
        except Exception as e:
            self.connection_error.emit(f"Write error: {e}")
            self.write_completed.emit(node_id, False)

    # ==========================================================================
    # SUBSCRIPTION (TAG MANAGEMENT) API
    # ==========================================================================

    def subscribe_tag(self, node_id: str, tag_name: Optional[str] = None):
        """
        Подписаться на изменения тега (thread-safe)

        Args:
            node_id: NodeId (например "ns=2;s=Temperature")
            tag_name: Имя тега (опционально)
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")

        asyncio.run_coroutine_threadsafe(
            self._async_subscribe_tag(node_id, tag_name), self.loop
        )

    async def _async_subscribe_tag(self, node_id: str, tag_name: Optional[str]):
        """Async подписка на тег"""
        try:
            success = await self.worker.subscribe_tag(node_id, tag_name)
            if success:
                self.tag_subscribed.emit(node_id)
        except Exception as e:
            self.connection_error.emit(f"Subscribe error: {e}")

    def unsubscribe_tag(self, node_id: str):
        """
        Отписаться от тега (thread-safe)

        Args:
            node_id: NodeId
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")

        asyncio.run_coroutine_threadsafe(
            self._async_unsubscribe_tag(node_id), self.loop
        )

    async def _async_unsubscribe_tag(self, node_id: str):
        """Async отписка от тега"""
        try:
            success = await self.worker.unsubscribe_tag(node_id)
            if success:
                self.tag_unsubscribed.emit(node_id)
        except Exception as e:
            self.connection_error.emit(f"Unsubscribe error: {e}")

    def subscribe_multiple_tags(self, tags: Dict[str, str]):
        """
        Подписаться на несколько тегов (thread-safe)

        Args:
            tags: Словарь {tag_name: node_id}
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")

        asyncio.run_coroutine_threadsafe(
            self._async_subscribe_multiple_tags(tags), self.loop
        )

    async def _async_subscribe_multiple_tags(self, tags: Dict[str, str]):
        """Async подписка на несколько тегов"""
        try:
            results = await self.worker.subscribe_multiple_tags(tags)
            for tag_name, success in results.items():
                if success:
                    node_id = tags[tag_name]
                    self.tag_subscribed.emit(node_id)
        except Exception as e:
            self.connection_error.emit(f"Subscribe multiple error: {e}")

    # ==========================================================================
    # DATA ACCESS
    # ==========================================================================

    def _on_data_changed(self, node_id: str, value: Any):
        """
        Callback от AsyncOpcUaWorker при изменении данных

        Вызывается в asyncio потоке, эмитит signal для GUI
        """
        # Сохраняем в thread-safe словарь и выставляем dirty-флаг
        with self._latest_data_lock:
            self._latest_data[node_id] = value
            self._data_changed_flag = True

        # Эмитим signal для GUI
        self.data_updated.emit(node_id, value)

    def get_latest_data(self) -> Dict[str, Any]:
        """Получить последние данные от всех тегов (thread-safe)"""
        with self._latest_data_lock:
            return self._latest_data.copy()

    def has_data_changed(self) -> bool:
        """
        Проверить, изменились ли данные с момента последнего вызова.

        Использует dirty-флаг, выставляемый в _on_data_changed().
        Безопасен для любых типов значений (list, dict, numpy и т.д.).

        Returns:
            True если пришли новые данные с последнего вызова.
        """
        with self._latest_data_lock:
            if self._data_changed_flag:
                self._data_changed_flag = False
                return True
        return False

    @property
    def is_connected(self) -> bool:
        """
        Проверка подключения.

        Делегируем в worker.is_connected — он является источником истины,
        в том числе после auto-reconnect когда thread._connected не обновляется.
        """
        if self.worker:
            return self.worker.is_connected
        return self._connected

    def get_subscribed_tags(self) -> List[str]:
        """Получить список подписанных тегов"""
        if not self.worker:
            return []
        return self.worker.get_subscribed_tags()

    # ==========================================================================
    # BATCH READ / WRITE API
    # ==========================================================================

    def read_multiple_nodes(self, node_ids: List[str]):
        """
        Пакетное параллельное чтение нескольких тегов (thread-safe)

        Результат приходит через signal batch_read_completed: {node_id: value}
        Теги с ошибкой чтения будут иметь значение None.

        Args:
            node_ids: Список NodeId ["ns=2;s=Temp", "ns=2;s=Pressure", ...]
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")

        asyncio.run_coroutine_threadsafe(
            self._async_read_multiple_nodes(node_ids), self.loop
        )

    async def _async_read_multiple_nodes(self, node_ids: List[str]):
        try:
            results = await self.worker.read_multiple_nodes(node_ids)
            self.batch_read_completed.emit(results)
        except Exception as e:
            self.connection_error.emit(f"Batch read error: {e}")

    def write_multiple_nodes(self, values: Dict[str, Any]):
        """
        Пакетная параллельная запись нескольких тегов (thread-safe)

        Результат приходит через signal batch_write_completed: {node_id: success}

        Args:
            values: Словарь {node_id: value} для записи
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")

        asyncio.run_coroutine_threadsafe(
            self._async_write_multiple_nodes(values), self.loop
        )

    async def _async_write_multiple_nodes(self, values: Dict[str, Any]):
        try:
            results = await self.worker.write_multiple_nodes(values)
            self.batch_write_completed.emit(results)
        except Exception as e:
            self.connection_error.emit(f"Batch write error: {e}")

    # ==========================================================================
    # POLLING API
    # ==========================================================================

    def start_polling(self, name: str, node_ids: List[str], interval: float = 1.0, sequential: bool = False):
        """
        Запустить именованный цикл опроса тегов (thread-safe).

        Args:
            name      : уникальное имя цикла ("fast", "slow", ...)
            node_ids  : список NodeId для опроса
            interval  : интервал опроса в секундах (по умолчанию 1.0)
            sequential: True — читать узлы строго по порядку (не параллельно)
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")

        asyncio.run_coroutine_threadsafe(
            self.worker.start_polling(name, node_ids, interval, sequential), self.loop
        )

    def stop_polling(self, name: Optional[str] = None):
        """
        Остановить цикл(ы) опроса (thread-safe).

        Args:
            name: имя цикла или None для остановки всех
        """
        if not self.is_loop_ready():
            return

        asyncio.run_coroutine_threadsafe(
            self.worker.stop_polling(name), self.loop
        )

    def get_active_polls(self) -> Dict[str, Dict]:
        """Получить информацию об активных poll loop'ах (синхронный вызов)."""
        if not self.worker:
            return {}
        return self.worker.get_active_polls()

    # ==========================================================================
    # WATCHDOG API
    # ==========================================================================

    def start_watchdog(self, interval: float = 5.0):
        """
        Запустить watchdog — периодическую проверку живости соединения (thread-safe)

        При обнаружении обрыва эмитит:
          - watchdog_disconnect — специфичный сигнал обрыва
          - disconnected        — стандартный сигнал отключения
          - флаг _connected синхронизируется с worker

        Args:
            interval: Интервал проверки в секундах (рекомендуется 3-10)
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")

        asyncio.run_coroutine_threadsafe(
            self._async_start_watchdog(interval), self.loop
        )

    async def _async_start_watchdog(self, interval: float):
        await self.worker.start_watchdog(interval)
        # Запускаем задачу синхронизации: ждём пока watchdog не остановится,
        # затем проверяем — было ли это из-за обрыва или ручного stop_watchdog()
        asyncio.ensure_future(self._sync_watchdog_state())

    async def _sync_watchdog_state(self):
        """
        Ждёт завершения watchdog и синхронизирует _connected флаг thread с worker.

        Watchdog останавливается в двух случаях:
          1. Обрыв связи: worker._connected → False  → эмитим disconnected
          2. Ручной stop_watchdog(): worker._connected остаётся True → ничего не делаем
        """
        # Ждём пока watchdog активен (с мелким шагом чтобы не пропустить момент)
        while self.worker and self.worker.is_watchdog_active:
            await asyncio.sleep(0.5)

        # Watchdog остановился — проверяем причину
        if self.worker and not self.worker.is_connected and self._connected:
            self._connected = False
            self.watchdog_disconnect.emit()
            self.disconnected.emit()

    def stop_watchdog(self):
        """Остановить watchdog (thread-safe)"""
        if not self.is_loop_ready():
            return

        asyncio.run_coroutine_threadsafe(
            self.worker.stop_watchdog(), self.loop
        )

    @property
    def is_watchdog_active(self) -> bool:
        """Проверить активность watchdog"""
        if not self.worker:
            return False
        return self.worker.is_watchdog_active

    # ==========================================================================
    # EXPLORATION API (browse + node_info + methods + history + events)
    # ==========================================================================

    def browse_nodes(self, start_node_id: Optional[str] = None, depth: int = 1):
        """
        Обзор дерева узлов сервера (thread-safe).

        Результат приходит через signal browse_completed(list).

        Args:
            start_node_id: Стартовый узел. None = Objects (корень).
            depth: Глубина рекурсии (1 = только дочерние).
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")
        asyncio.run_coroutine_threadsafe(
            self.async_browse_nodes(start_node_id, depth), self.loop
        )

    async def async_browse_nodes(self, start_node_id: Optional[str], depth: int):
        try:
            result = await self.worker.browse_nodes(start_node_id, depth)
            self.browse_completed.emit(result)
        except Exception as e:
            self.connection_error.emit(f"Browse error: {e}")

    def read_node_info(self, node_id: str):
        """
        Расширенное чтение узла — значение + timestamp + quality + тип (thread-safe).

        Результат приходит через signal node_info_completed(dict).
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")
        asyncio.run_coroutine_threadsafe(
            self.async_read_node_info(node_id), self.loop
        )

    async def async_read_node_info(self, node_id: str):
        try:
            result = await self.worker.read_node_info(node_id)
            self.node_info_completed.emit(result)
        except Exception as e:
            self.connection_error.emit(f"Read node info error: {e}")

    def call_method(self, parent_node_id: str, method_node_id: str, args: Optional[List] = None):
        """
        Вызов OPC UA метода на сервере (thread-safe).

        Результат приходит через signal method_completed(object).

        Args:
            parent_node_id: Адрес Object-узла владельца ("ns=2;s=MyDevice").
            method_node_id: Адрес метода ("ns=2;s=StartPump").
            args: Список аргументов или None.
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")
        asyncio.run_coroutine_threadsafe(
            self.async_call_method(parent_node_id, method_node_id, args), self.loop
        )

    async def async_call_method(self, parent_node_id: str, method_node_id: str, args: Optional[List]):
        try:
            result = await self.worker.call_method(parent_node_id, method_node_id, args)
            self.method_completed.emit(result)
        except Exception as e:
            self.connection_error.emit(f"Method call error: {e}")

    def discover_methods(self, object_node_id: str):
        """
        Обнаружить доступные методы на объекте (thread-safe).

        Результат приходит через signal methods_discovered(list).
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")
        asyncio.run_coroutine_threadsafe(
            self.async_discover_methods(object_node_id), self.loop
        )

    async def async_discover_methods(self, object_node_id: str):
        try:
            result = await self.worker.discover_methods(object_node_id)
            self.methods_discovered.emit(result)
        except Exception as e:
            self.connection_error.emit(f"Discover methods error: {e}")

    def read_history(self, node_id: str, start_time=None, end_time=None, num_values: int = 0):
        """
        Чтение исторических данных тега за период (thread-safe).

        Результат приходит через signal history_completed(node_id, list).

        Args:
            node_id: Адрес узла ("ns=2;s=Temperature").
            start_time: Начало периода UTC (None = час назад).
            end_time:   Конец периода UTC (None = сейчас).
            num_values: Макс. число точек (0 = все).
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")
        asyncio.run_coroutine_threadsafe(
            self.async_read_history(node_id, start_time, end_time, num_values), self.loop
        )

    async def async_read_history(self, node_id: str, start_time, end_time, num_values: int):
        try:
            result = await self.worker.read_history(node_id, start_time, end_time, num_values)
            self.history_completed.emit(node_id, result)
        except Exception as e:
            self.connection_error.emit(f"History read error: {e}")

    def read_history_multiple(self, node_ids: List[str], start_time=None, end_time=None, num_values: int = 0):
        """
        Пакетное чтение истории нескольких тегов параллельно (thread-safe).

        Результат приходит через signal history_multiple_completed(dict).
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")
        asyncio.run_coroutine_threadsafe(
            self.async_read_history_multiple(node_ids, start_time, end_time, num_values), self.loop
        )

    async def async_read_history_multiple(self, node_ids: List[str], start_time, end_time, num_values: int):
        try:
            result = await self.worker.read_history_multiple(node_ids, start_time, end_time, num_values)
            self.history_multiple_completed.emit(result)
        except Exception as e:
            self.connection_error.emit(f"History multiple read error: {e}")

    def subscribe_events(self, source_node_id: Optional[str] = None):
        """
        Подписаться на OPC UA события (аварии, условия) (thread-safe).

        События приходят через signal event_received(dict):
            {"source", "message", "severity", "time", "event_type"}

        Args:
            source_node_id: Источник событий. None = все события сервера.
        """
        if not self.is_loop_ready():
            raise RuntimeError("Event loop not ready")
        asyncio.run_coroutine_threadsafe(
            self.async_subscribe_events(source_node_id), self.loop
        )

    async def async_subscribe_events(self, source_node_id: Optional[str]):
        try:
            await self.worker.subscribe_events(
                source_node_id=source_node_id,
                event_callback=lambda event: self.event_received.emit(event),
            )
        except Exception as e:
            self.connection_error.emit(f"Subscribe events error: {e}")

    def unsubscribe_events(self, source_node_id: Optional[str] = None):
        """Отписаться от событий (thread-safe)."""
        if not self.is_loop_ready():
            return
        asyncio.run_coroutine_threadsafe(
            self.worker.unsubscribe_events(source_node_id), self.loop
        )

    # ==========================================================================
    # STATS
    # ==========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику операций (синхронный вызов, только чтение)

        Returns:
            Dict с полями: reads, writes, read_errors, write_errors,
                           last_read_ms, last_write_ms и др.
        """
        if not self.worker:
            return {}
        return self.worker.get_stats()
