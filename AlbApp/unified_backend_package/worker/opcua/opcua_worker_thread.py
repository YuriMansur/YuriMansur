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
    loop_ready = pyqtSignal()  # Event loop готов
    connected = pyqtSignal()  # Успешное подключение
    disconnected = pyqtSignal()  # Отключение
    connection_error = pyqtSignal(str)  # Ошибка подключения
    data_updated = pyqtSignal(str, object)  # (node_id, value)
    tag_subscribed = pyqtSignal(str)  # (node_id)
    tag_unsubscribed = pyqtSignal(str)  # (node_id)
    read_completed = pyqtSignal(str, object)  # (node_id, value)
    write_completed = pyqtSignal(str, bool)  # (node_id, success)

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

        # Импортируем здесь, чтобы избежать проблем с импортами
        from AlbApp.unified_backend_package.worker.opcua.opcua_worker import AsyncOpcUaWorker

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
            # Отключаемся от сервера (если подключены)
            if self._connected:
                future = asyncio.run_coroutine_threadsafe(
                    self.worker.disconnect(), self.loop
                )
                if blocking:
                    try:
                        future.result(timeout=5.0)
                    except Exception:
                        pass

            # Останавливаем event loop
            self.loop.call_soon_threadsafe(self.loop.stop)

        if blocking:
            self.wait(5000)  # Ждем завершения потока (max 5 сек)

        # Планируем удаление потока
        self.deleteLater()

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
        # Сохраняем в thread-safe словарь
        with self._latest_data_lock:
            self._latest_data[node_id] = value

        # Эмитим signal для GUI
        self.data_updated.emit(node_id, value)

    def get_latest_data(self) -> Dict[str, Any]:
        """Получить последние данные от всех тегов (thread-safe)"""
        with self._latest_data_lock:
            return self._latest_data.copy()

    def has_data_changed(self) -> bool:
        """
        Проверить, изменились ли данные

        Returns:
            bool: True если есть новые данные
        """
        if not self.worker:
            return False

        with self._latest_data_lock:
            current_hash = hash(frozenset(self._latest_data.items()))

        # Сравниваем с предыдущим hash
        if not hasattr(self, '_prev_hash'):
            self._prev_hash = current_hash
            return True

        if current_hash != self._prev_hash:
            self._prev_hash = current_hash
            return True

        return False

    @property
    def is_connected(self) -> bool:
        """Проверка подключения"""
        return self._connected

    def get_subscribed_tags(self) -> List[str]:
        """Получить список подписанных тегов"""
        if not self.worker:
            return []
        return self.worker.get_subscribed_tags()
