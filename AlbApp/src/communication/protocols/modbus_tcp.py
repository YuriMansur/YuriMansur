import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QThread
import async_timeout
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
from pymodbus.pdu import ExceptionResponse

logger = logging.getLogger(__name__)


@dataclass
class ModbusConfig:
    """Конфигурация Modbus TCP подключения"""
    host: str = "localhost"
    port: int = 502
    unit_id: int = 1
    timeout: float = 10.0
    reconnect_interval: float = 5.0
    max_reconnect_attempts: int = 3

#Поток для выполнения асинхронных операций Modbus
class ModbusWorker(QThread):
    
    
    # Сигналы для связи с GUI
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    data_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    
    def __init__(self, modbus_client):
        super().__init__()
        self.modbus_client = modbus_client
        self.running = False
        self.loop = None

    #Запуск асинхронного цикла событий"""   
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.running = True
        self.loop.run_forever()

    #Остановка потока   
    def stop(self):
        self.running = False
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait()

    # Выполнение корутины в асинхронном цикле событий    
    def execute_async(self, coro):
        if self.loop and self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            return future
        return None

# Основной класс Modbus TCP клиента с поддержкой PyQt
class ModbusTcpClient(QObject):
    """Асинхронный клиент Modbus TCP с поддержкой PyQt"""
    
    # Сигналы для GUI
    connection_changed = pyqtSignal(bool)
    data_updated = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
      
        self.config = ModbusConfig()
        self._client: Optional[AsyncModbusTcpClient] = None
        self._connected = False
        
        # Создаем рабочий поток
        self.worker = ModbusWorker(self)
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.data_received.connect(self._on_data_received)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.status_changed.connect(self._on_status_changed)
        
        # Запускаем поток
        self.worker.start()

    #Обработка сигнала подключения
    def _on_connected(self):
        self._connected = True
        self.connection_changed.emit(True)
        
    def _on_disconnected(self):
        """Обработка сигнала отключения"""
        self._connected = False
        self.connection_changed.emit(False)
        
    def _on_data_received(self, data):
        """Обработка полученных данных"""
        self.data_updated.emit(data)
        
    def _on_error(self, error_msg):
        """Обработка ошибок"""
        self.error_signal.emit(error_msg)
        
    def _on_status_changed(self, status):
        """Обработка изменения статуса"""
        logger.info(f"Статус Modbus: {status}")
        
    @pyqtSlot(str, int, int, float)
    def configure(self, host: str, port: int = 502, unit_id: int = 1, timeout: float = 10.0):
        """Настройка параметров Modbus"""
        self.config.host = host
        self.config.port = port
        self.config.unit_id = unit_id
        self.config.timeout = timeout
        logger.info(f"Modbus сконфигурирован: {host}:{port}, Unit ID: {unit_id}")
        
    @pyqtSlot()
    def connect(self):
        """Подключиться к Modbus серверу (неблокирующий)"""
        self.worker.execute_async(self._async_connect())
        
    async def _async_connect(self) -> bool:
        """Асинхронное подключение"""
        try:
            self.worker.status_changed.emit("Подключение к Modbus...")
            
            async with async_timeout.timeout(self.config.timeout):
                self._client = AsyncModbusTcpClient(
                    host=self.config.host,
                    port=self.config.port,
                    unit_id=self.config.unit_id,
                    timeout=self.config.timeout,
                    retries=3
                )
                
                await self._client.connect()
                
                # Проверяем подключение
                response = await self._client.read_holding_registers(0, 1)
                if isinstance(response, ExceptionResponse):
                    self.worker.error_occurred.emit(f"Modbus exception: {response}")
                    return False
                
                self._connected = True
                self.worker.connected.emit()
                self.worker.status_changed.emit("Modbus подключен")
                return True
                
        except (asyncio.TimeoutError, ConnectionError) as e:
            error_msg = f"Ошибка подключения Modbus: {e}"
            self.worker.error_occurred.emit(error_msg)
            self.worker.status_changed.emit("Ошибка подключения")
            return False
        except Exception as e:
            error_msg = f"Неожиданная ошибка Modbus: {e}"
            self.worker.error_occurred.emit(error_msg)
            return False
    
    @pyqtSlot()
    def disconnect(self):
        """Отключиться от Modbus сервера"""
        self.worker.execute_async(self._async_disconnect())
        
    async def _async_disconnect(self):
        """Асинхронное отключение"""
        if self._client and self._connected:
            self._client.close()
            self._connected = False
            self.worker.disconnected.emit()
            self.worker.status_changed.emit("Modbus отключен")
    
    @pyqtSlot(int, int, str)
    def read_data(self, address: int, count: int = 1, data_type: str = "holding"):
        """Чтение данных с Modbus сервера"""
        self.worker.execute_async(self._async_read_data(address, count, data_type))
        
    async def _async_read_data(self, address: int, count: int, data_type: str):
        """Асинхронное чтение данных"""
        try:
            if not self._connected:
                self.worker.error_occurred.emit("Нет подключения к Modbus")
                return
            
            async with async_timeout.timeout(self.config.timeout):
                if data_type == "coils":
                    response = await self._client.read_coils(address, count)
                    value = response.bits[:count]
                elif data_type == "discrete":
                    response = await self._client.read_discrete_inputs(address, count)
                    value = response.bits[:count]
                elif data_type == "holding":
                    response = await self._client.read_holding_registers(address, count)
                    value = response.registers
                elif data_type == "input":
                    response = await self._client.read_input_registers(address, count)
                    value = response.registers
                else:
                    self.worker.error_occurred.emit(f"Неизвестный тип данных: {data_type}")
                    return
                
                if response.isError() or isinstance(response, ExceptionResponse):
                    self.worker.error_occurred.emit(f"Modbus ошибка: {response}")
                    return
                
                # Отправляем данные в GUI
                data = {
                    'address': address,
                    'type': data_type,
                    'value': value,
                    'timestamp': asyncio.get_event_loop().time()
                }
                self.worker.data_received.emit(data)
                
        except ModbusException as e:
            self.worker.error_occurred.emit(f"Modbus исключение: {e}")
        except asyncio.TimeoutError:
            self.worker.error_occurred.emit("Таймаут чтения Modbus")
        except Exception as e:
            self.worker.error_occurred.emit(f"Ошибка чтения Modbus: {e}")
    
    @pyqtSlot(int, object, str)
    def write_data(self, address: int, value, data_type: str = "coil"):
        """Запись данных на Modbus сервер"""
        self.worker.execute_async(self._async_write_data(address, value, data_type))
        
    async def _async_write_data(self, address: int, value, data_type: str):
        """Асинхронная запись данных"""
        try:
            if not self._connected:
                self.worker.error_occurred.emit("Нет подключения к Modbus")
                return
            
            async with async_timeout.timeout(self.config.timeout):
                if data_type == "coil":
                    response = await self._client.write_coil(address, bool(value))
                elif data_type == "register":
                    response = await self._client.write_register(address, int(value))
                else:
                    self.worker.error_occurred.emit(f"Неизвестный тип записи: {data_type}")
                    return
                
                if response.isError() or isinstance(response, ExceptionResponse):
                    self.worker.error_occurred.emit(f"Modbus ошибка записи: {response}")
                    return
                
                self.worker.status_changed.emit(f"Данные записаны: адрес {address}")
                
        except ModbusException as e:
            self.worker.error_occurred.emit(f"Modbus исключение записи: {e}")
        except Exception as e:
            self.worker.error_occurred.emit(f"Ошибка записи Modbus: {e}")
    
    def is_connected(self) -> bool:
        """Проверка состояния подключения"""
        return self._connected
    
    def cleanup(self):
        """Очистка ресурсов"""
        self.worker.execute_async(self._async_disconnect())
        self.worker.stop()