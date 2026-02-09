"""
PLCWorkerThread - QThread обертка для AsyncPLCWorker
Каждый PLC работает в отдельном потоке с собственным asyncio event loop.
Паттерн: OpcUaWorker из src/communication/protocols/opc_ua.py
"""

import asyncio
import threading
from typing import Optional, Dict
from PyQt6.QtCore import QThread, pyqtSignal

from worker.modbus_worker import AsyncPLCWorker


class PLCWorkerThread(QThread):
    """QThread обертка для AsyncPLCWorker с собственным asyncio event loop"""

    # === SIGNALS для коммуникации с GUI ===
    connected = pyqtSignal()  # Успешное подключение
    disconnected = pyqtSignal()  # Отключение
    connection_error = pyqtSignal(str)  # Ошибка подключения
    data_updated = pyqtSignal(str, dict)  # (poll_name, data) - обновление данных из poll
    command_completed = pyqtSignal(object)  # Результат выполнения команды
    command_error = pyqtSignal(str)  # Ошибка выполнения команды

    def __init__(self, plc_id: str, host: str, port: int = 502, device_id: int = 1):
        """
        Инициализация worker thread для PLC

        Args:
            plc_id: Уникальный идентификатор PLC
            host: IP адрес устройства
            port: Modbus TCP порт (по умолчанию 502)
            device_id: Modbus slave ID (по умолчанию 1)
        """
        super().__init__()
        self.plc_id = plc_id
        self.host = host
        self.port = port
        self.device_id = device_id

        # Event loop и worker будут созданы в run()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.worker: Optional[AsyncPLCWorker] = None
        self._connected = False

        # Thread-safe доступ к latest_data
        self._latest_data_lock = threading.Lock()
        self._latest_data: Dict[str, list] = {}

    def run(self):
        """
        Создание event loop в потоке и запуск (паттерн OpcUaWorker)
        Этот метод выполняется в отдельном потоке
        """
        # Создаем новый event loop для этого потока
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Запускаем event loop (блокирующий вызов до stop())
        self.loop.run_forever()

    def stop(self):
        """
        Корректная остановка потока
        Thread-safe метод, вызывается из главного потока
        """
        # Если подключены, сначала отключаемся
        if self._connected and self.worker and self.loop:
            try:
                # Запускаем async disconnect и ждем завершения
                future = asyncio.run_coroutine_threadsafe(
                    self._async_disconnect(), self.loop
                )
                future.result(timeout=5.0)  # Даем 5 секунд на отключение
            except Exception as e:
                # Логируем ошибку, но продолжаем остановку
                print(f"[{self.plc_id}] Ошибка при отключении: {e}")

        # Останавливаем event loop
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

        # Ждем завершения потока
        self.wait()

    # ==========================================================================
    # PUBLIC METHODS (thread-safe, вызываются из GUI потока)
    # ==========================================================================

    def connect_to_plc(self):
        """
        Thread-safe подключение к PLC
        Вызывается из главного потока, выполняется в worker потоке
        """
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._async_connect(), self.loop
            )

    def disconnect_from_plc(self):
        """
        Thread-safe отключение от PLC
        Вызывается из главного потока, выполняется в worker потоке
        """
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._async_disconnect(), self.loop
            )

    def execute_command(self, command: tuple):
        """
        Thread-safe выполнение команды (read/write)

        Args:
            command: tuple вида ("read", type, address, count) или ("write", type, address, count, value)
        """
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._async_execute_command(command), self.loop
            )

    def add_poll(self, poll_config: dict):
        """
        Thread-safe добавление циклического опроса

        Args:
            poll_config: dict с ключами: name, type, address, count, interval
        """
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._async_add_poll(poll_config), self.loop
            )

    def get_latest_data(self) -> dict:
        """
        Thread-safe получение последних данных из polls

        Returns:
            dict: Копия latest_data {poll_name: data}
        """
        with self._latest_data_lock:
            return self._latest_data.copy()

    # ==========================================================================
    # PRIVATE ASYNC METHODS (выполняются в event loop потока)
    # ==========================================================================

    async def _async_connect(self):
        """
        Создание и запуск AsyncPLCWorker
        Выполняется в event loop worker потока
        """
        try:
            # Создаем AsyncPLCWorker
            self.worker = AsyncPLCWorker(
                self.plc_id, self.host, self.port, self.device_id
            )

            # Запускаем worker (создает _command_loop)
            asyncio.create_task(self.worker.start())

            # Даем время на подключение к Modbus (создание соединения в _command_loop)
            await asyncio.sleep(0.5)

            # Отмечаем как подключенный
            self._connected = True

            # Сигнализируем об успешном подключении
            self.connected.emit()

            # Запускаем loop для синхронизации latest_data
            asyncio.create_task(self._sync_latest_data_loop())

        except Exception as e:
            # Сигнализируем об ошибке
            self.connection_error.emit(str(e))

    async def _async_disconnect(self):
        """
        Остановка AsyncPLCWorker
        Выполняется в event loop worker потока
        """
        if self.worker:
            try:
                await self.worker.stop()
                self.worker = None
            except Exception as e:
                print(f"[{self.plc_id}] Ошибка остановки worker: {e}")

        self._connected = False
        self.disconnected.emit()

    async def _async_execute_command(self, command: tuple):
        """
        Выполнение команды read/write через AsyncPLCWorker

        Args:
            command: tuple команды для AsyncPLCWorker.request()
        """
        try:
            if not self.worker:
                self.command_error.emit("Worker не инициализирован")
                return

            # Выполняем команду через worker
            result = await self.worker.request(command)

            # Отправляем результат в GUI
            self.command_completed.emit(result)

        except Exception as e:
            # Отправляем ошибку в GUI
            self.command_error.emit(str(e))

    async def _async_add_poll(self, poll_config: dict):
        """
        Добавление poll loop в AsyncPLCWorker

        Args:
            poll_config: dict с параметрами опроса
        """
        try:
            if not self.worker:
                return

            # Создаем задачу poll_loop
            task = asyncio.create_task(self.worker._poll_loop(poll_config))

            # Добавляем в список задач worker (для отмены при stop)
            self.worker._poll_tasks.append(task)

        except Exception as e:
            print(f"[{self.plc_id}] Ошибка добавления poll: {e}")

    async def _sync_latest_data_loop(self):
        """
        Периодическое копирование latest_data из worker и отправка signals
        Этот loop синхронизирует данные между worker и GUI
        """
        while self._connected:
            if self.worker:
                # Получаем данные от worker
                worker_data = self.worker.latest_data.copy()

                # Обновляем thread-safe копию
                with self._latest_data_lock:
                    self._latest_data = worker_data

                # Отправляем сигналы для каждого poll
                for poll_name, data in worker_data.items():
                    self.data_updated.emit(poll_name, {"data": data})

            # Интервал синхронизации 500мс
            await asyncio.sleep(0.5)
