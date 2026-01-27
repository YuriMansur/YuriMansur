import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread
import async_timeout
from asyncua import Client as OpcUaClient
from asyncua.ua import NodeId, Variant, VariantType


logger = logging.getLogger(__name__)


@dataclass
class OpcUaConfig:
    """Конфигурация OPC UA подключения"""
    endpoint: str = "opc.tcp://localhost:4840"
    security_policy: Optional[str] = None
    security_mode: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    timeout: float = 10.0
    reconnect_interval: float = 5.0
    namespace: str = "http://opcfoundation.org/UA/"
    

class OpcUaWorker(QThread):
    """Поток для выполнения асинхронных операций OPC UA"""
    
    # Сигналы для связи с GUI
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    data_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    
    def __init__(self, opcua_client):
        super().__init__()
        self.opcua_client = opcua_client
        self.running = False
        self.loop = None
        
    def run(self):
        """Запуск асинхронного цикла событий"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.running = True
        self.loop.run_forever()
        
    def stop(self):
        """Остановка потока"""
        self.running = False
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait()
        
    def execute_async(self, coro):
        """Выполнить асинхронную корутину из потока"""
        if self.loop and self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            return future
        return None


class OpcUaClientQt(QObject):
    """Асинхронный клиент OPC UA с поддержкой PyQt"""
    
    # Сигналы для GUI
    connection_changed = pyqtSignal(bool)
    data_updated = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = OpcUaConfig()
        self._client: Optional[OpcUaClient] = None
        self._connected = False
        self._namespace_idx = 0
        
        # Создаем рабочий поток
        self.worker = OpcUaWorker(self)
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.data_received.connect(self._on_data_received)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.status_changed.connect(self._on_status_changed)
        
        # Запускаем поток
        self.worker.start()
        
    def _on_connected(self):
        """Обработка сигнала подключения"""
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
        logger.info(f"Статус OPC UA: {status}")
        
    @pyqtSlot(str, str, str, str, str)
    def configure(self, endpoint: str, username: Optional[str] = None, 
                  password: Optional[str] = None, security_policy: Optional[str] = None,
                  security_mode: Optional[str] = None):
        """Настройка параметров OPC UA"""
        self.config.endpoint = endpoint
        self.config.username = username
        self.config.password = password
        self.config.security_policy = security_policy
        self.config.security_mode = security_mode
        logger.info(f"OPC UA сконфигурирован: {endpoint}")
        
    @pyqtSlot()
    def connect(self):
        """Подключиться к OPC UA серверу (неблокирующий)"""
        self.worker.execute_async(self._async_connect())
        
    async def _async_connect(self) -> bool:
        """Асинхронное подключение"""
        try:
            self.worker.status_changed.emit("Подключение к OPC UA...")
            
            async with async_timeout.timeout(self.config.timeout):
                self._client = OpcUaClient(self.config.endpoint)
                
                # Настройка безопасности
                if self.config.security_policy and self.config.security_mode:
                    self._client.set_security(
                        self.config.security_policy,
                        self.config.security_mode,
                        certificate_path=None,
                        private_key_path=None
                    )
                
                # Аутентификация
                if self.config.username and self.config.password:
                    await self._client.set_user(self.config.username)
                    await self._client.set_password(self.config.password)
                
                # Подключаемся
                await self._client.connect()
                
                # Получаем индекс namespace
                self._namespace_idx = await self._client.get_namespace_index(self.config.namespace)
                
                self._connected = True
                self.worker.connected.emit()
                self.worker.status_changed.emit("OPC UA подключен")
                return True
                
        except (asyncio.TimeoutError, ConnectionError) as e:
            error_msg = f"Ошибка подключения OPC UA: {e}"
            self.worker.error_occurred.emit(error_msg)
            self.worker.status_changed.emit("Ошибка подключения")
            return False
        except Exception as e:
            error_msg = f"Неожиданная ошибка OPC UA: {e}"
            self.worker.error_occurred.emit(error_msg)
            return False
    
    @pyqtSlot()
    def disconnect(self):
        """Отключиться от OPC UA сервера"""
        self.worker.execute_async(self._async_disconnect())
        
    async def _async_disconnect(self):
        """Асинхронное отключение"""
        if self._client and self._connected:
            await self._client.disconnect()
            self._connected = False
            self.worker.disconnected.emit()
            self.worker.status_changed.emit("OPC UA отключен")
    
    @pyqtSlot(str)
    def read_node(self, node_id: str):
        """Чтение узла OPC UA"""
        self.worker.execute_async(self._async_read_node(node_id))
        
    async def _async_read_node(self, node_id: str):
        """Асинхронное чтение узла"""
        try:
            if not self._connected:
                self.worker.error_occurred.emit("Нет подключения к OPC UA")
                return
            
            async with async_timeout.timeout(self.config.timeout):
                # Получаем узел
                node = self._client.get_node(node_id)
                
                # Читаем значение и атрибуты
                value = await node.read_value()
                display_name = await node.read_display_name()
                data_type = await node.read_data_type()
                
                # Отправляем данные в GUI
                data = {
                    'node_id': node_id,
                    'display_name': str(display_name.Text),
                    'value': value,
                    'data_type': str(data_type),
                    'timestamp': asyncio.get_event_loop().time()
                }
                self.worker.data_received.emit(data)
                
        except asyncio.TimeoutError:
            self.worker.error_occurred.emit("Таймаут чтения OPC UA")
        except Exception as e:
            self.worker.error_occurred.emit(f"Ошибка чтения OPC UA: {e}")
    
    @pyqtSlot(str, object)
    def write_node(self, node_id: str, value):
        """Запись значения в узел OPC UA"""
        self.worker.execute_async(self._async_write_node(node_id, value))
        
    async def _async_write_node(self, node_id: str, value):
        """Асинхронная запись значения"""
        try:
            if not self._connected:
                self.worker.error_occurred.emit("Нет подключения к OPC UA")
                return
            
            async with async_timeout.timeout(self.config.timeout):
                # Получаем узел
                node = self._client.get_node(node_id)
                
                # Записываем значение
                await node.write_value(value)
                
                self.worker.status_changed.emit(f"Значение записано: {node_id}")
                
        except asyncio.TimeoutError:
            self.worker.error_occurred.emit("Таймаут записи OPC UA")
        except Exception as e:
            self.worker.error_occurred.emit(f"Ошибка записи OPC UA: {e}")
    
    @pyqtSlot(str)
    def browse_node(self, node_id: str = "i=84"):  # i=84 - Objects folder
        """Просмотр дочерних узлов"""
        self.worker.execute_async(self._async_browse_node(node_id))
        
    async def _async_browse_node(self, node_id: str):
        """Асинхронный просмотр узлов"""
        try:
            if not self._connected:
                self.worker.error_occurred.emit("Нет подключения к OPC UA")
                return
            
            async with async_timeout.timeout(self.config.timeout):
                node = self._client.get_node(node_id)
                children = await node.get_children()
                
                nodes_info = []
                for child in children:
                    display_name = await child.read_display_name()
                    node_class = await child.read_node_class()
                    
                    nodes_info.append({
                        'node_id': str(child.nodeid),
                        'display_name': str(display_name.Text),
                        'node_class': str(node_class)
                    })
                
                # Отправляем информацию о узлах
                data = {
                    'parent_node': node_id,
                    'children': nodes_info,
                    'timestamp': asyncio.get_event_loop().time()
                }
                self.worker.data_received.emit(data)
                
        except Exception as e:
            self.worker.error_occurred.emit(f"Ошибка просмотра узлов OPC UA: {e}")
    
    def is_connected(self) -> bool:
        """Проверка состояния подключения"""
        return self._connected
    
    def cleanup(self):
        """Очистка ресурсов"""
        self.worker.execute_async(self._async_disconnect())
        self.worker.stop()