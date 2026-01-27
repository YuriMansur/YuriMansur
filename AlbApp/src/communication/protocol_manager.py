import logging
from enum import Enum
from typing import Optional, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtWidgets import QMessageBox
from communication.protocols.modbus_tcp import ModbusTcpClient, ModbusConfig
from communication.protocols.opc_ua import OpcUaClientQt, OpcUaConfig

logger = logging.getLogger(__name__)


class ProtocolType(Enum):
    """Типы поддерживаемых протоколов"""
    MODBUS_TCP = "modbus_tcp"
    OPC_UA = "opc_ua"
    NONE = "none"


class ProtocolManager(QObject):
    """Менеджер протоколов для переключения между Modbus TCP и OPC UA"""
    
    # Сигналы для GUI
    protocol_changed = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)
    data_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Текущий активный протокол
        self.current_protocol: ProtocolType = ProtocolType.NONE
        
        # Клиенты протоколов
        self.modbus_client: Optional[ModbusTcpClient] = None
        self.opcua_client: Optional[OpcUaClientQt] = None
        
        # Конфигурации
        self.modbus_config = ModbusConfig()
        self.opcua_config = OpcUaConfig()
        
        # Состояние подключения
        self._connected = False
        
        # Таймер для мониторинга состояния
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._check_connection)
        self.monitor_timer.start(5000)  # Проверка каждые 5 секунд
        
        logger.info("Менеджер протоколов инициализирован")
        
    def _setup_protocol_clients(self):
        """Инициализация клиентов протоколов"""
        try:
            # Инициализация Modbus клиента
            if not self.modbus_client:
                self.modbus_client = ModbusTcpClient(self)
                self.modbus_client.connection_changed.connect(
                    lambda state: self._on_client_connection_changed(ProtocolType.MODBUS_TCP, state)
                )
                self.modbus_client.data_updated.connect(self._on_data_received)
                self.modbus_client.error_signal.connect(self._on_error)
                logger.info("Modbus TCP клиент инициализирован")
                
            # Инициализация OPC UA клиента
            if not self.opcua_client:
                self.opcua_client = OpcUaClientQt(self)
                self.opcua_client.connection_changed.connect(
                    lambda state: self._on_client_connection_changed(ProtocolType.OPC_UA, state)
                )
                self.opcua_client.data_updated.connect(self._on_data_received)
                self.opcua_client.error_signal.connect(self._on_error)
                logger.info("OPC UA клиент инициализирован")
                
        except ImportError as e:
            logger.error(f"Ошибка импорта модулей: {e}")
            self.error_occurred.emit(f"Модуль не установлен: {e}")
        except Exception as e:
            logger.error(f"Ошибка инициализации клиентов: {e}")
            self.error_occurred.emit(f"Ошибка инициализации: {e}")
    
    @pyqtSlot(str)
    def select_protocol(self, protocol_name: str):
        """Выбор активного протокола"""
        try:
            protocol = ProtocolType(protocol_name)
            
            # Если протокол уже выбран
            if protocol == self.current_protocol:
                logger.info(f"Протокол {protocol_name} уже активен")
                return
                
            # Отключаем текущий протокол если подключен
            if self._connected and self.current_protocol != ProtocolType.NONE:
                self._disconnect_current_protocol()
            
            # Устанавливаем новый протокол
            self.current_protocol = protocol
            
            # Инициализируем клиенты если нужно
            self._setup_protocol_clients()
            
            # Отправляем сигнал об изменении протокола
            self.protocol_changed.emit(protocol_name)
            self.status_updated.emit(f"Выбран протокол: {protocol_name}")
            logger.info(f"Протокол изменен на: {protocol_name}")
            
        except ValueError:
            error_msg = f"Неизвестный протокол: {protocol_name}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
    
    @pyqtSlot()
    def connect_protocol(self):
        """Подключение к текущему протоколу"""
        if self.current_protocol == ProtocolType.NONE:
            self.error_occurred.emit("Протокол не выбран")
            return
            
        if self._connected:
            self.status_updated.emit("Уже подключено")
            return
            
        try:
            if self.current_protocol == ProtocolType.MODBUS_TCP and self.modbus_client:
                self.modbus_client.connect()
                self.status_updated.emit("Подключение Modbus TCP...")
                
            elif self.current_protocol == ProtocolType.OPC_UA and self.opcua_client:
                self.opcua_client.connect()
                self.status_updated.emit("Подключение OPC UA...")
                
        except Exception as e:
            error_msg = f"Ошибка подключения: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
    
    @pyqtSlot()
    def disconnect_protocol(self):
        """Отключение от текущего протокола"""
        self._disconnect_current_protocol()
    
    def _disconnect_current_protocol(self):
        """Отключение текущего протокола"""
        try:
            if self.current_protocol == ProtocolType.MODBUS_TCP and self.modbus_client:
                self.modbus_client.disconnect()
                
            elif self.current_protocol == ProtocolType.OPC_UA and self.opcua_client:
                self.opcua_client.disconnect()
                
        except Exception as e:
            logger.error(f"Ошибка отключения: {e}")
    
    def _on_client_connection_changed(self, protocol: ProtocolType, connected: bool):
        """Обработка изменения состояния подключения клиента"""
        # Обновляем состояние только если это текущий протокол
        if protocol == self.current_protocol:
            self._connected = connected
            self.connection_changed.emit(connected)
            
            status = "подключен" if connected else "отключен"
            self.status_updated.emit(f"{protocol.value} {status}")
    
    def _on_data_received(self, data: Dict[str, Any]):
        """Обработка полученных данных"""
        # Добавляем информацию о протоколе в данные
        data['protocol'] = self.current_protocol.value
        self.data_received.emit(data)
    
    def _on_error(self, error_msg: str):
        """Обработка ошибок от клиентов"""
        self.error_occurred.emit(error_msg)
    
    def _check_connection(self):
        """Периодическая проверка соединения"""
        if self.current_protocol != ProtocolType.NONE and self._connected:
            # Можно добавить heartbeat проверку
            pass
    
    @pyqtSlot(str, int, int, float)
    def configure_modbus(self, host: str, port: int = 502, unit_id: int = 1, timeout: float = 10.0):
        """Конфигурация Modbus TCP"""
        if not self.modbus_client:
            self._setup_protocol_clients()
            
        self.modbus_config = ModbusConfig(
            host=host,
            port=port,
            unit_id=unit_id,
            timeout=timeout
        )
        
        if self.modbus_client:
            self.modbus_client.configure(host, port, unit_id, timeout)
            
        logger.info(f"Modbus сконфигурирован: {host}:{port}")
    
    @pyqtSlot(str, str, str, str, str)
    def configure_opcua(self, endpoint: str, username: str = "", 
                        password: str = "", security_policy: str = "",
                        security_mode: str = ""):
        """Конфигурация OPC UA"""
        if not self.opcua_client:
            self._setup_protocol_clients()
            
        self.opcua_config = OpcUaConfig(
            endpoint=endpoint,
            username=username if username else None,
            password=password if password else None,
            security_policy=security_policy if security_policy else None,
            security_mode=security_mode if security_mode else None
        )
        
        if self.opcua_client:
            self.opcua_client.configure(
                endpoint, 
                username if username else None,
                password if password else None,
                security_policy if security_policy else None,
                security_mode if security_mode else None
            )
            
        logger.info(f"OPC UA сконфигурирован: {endpoint}")
    
    @pyqtSlot(int, int, str)
    def read_modbus_data(self, address: int, count: int = 1, data_type: str = "holding"):
        """Чтение данных через Modbus TCP"""
        if self.current_protocol == ProtocolType.MODBUS_TCP and self.modbus_client:
            self.modbus_client.read_data(address, count, data_type)
        else:
            self.error_occurred.emit("Modbus TCP не активен")
    
    @pyqtSlot(int, object, str)
    def write_modbus_data(self, address: int, value, data_type: str = "coil"):
        """Запись данных через Modbus TCP"""
        if self.current_protocol == ProtocolType.MODBUS_TCP and self.modbus_client:
            self.modbus_client.write_data(address, value, data_type)
        else:
            self.error_occurred.emit("Modbus TCP не активен")
    
    @pyqtSlot(str)
    def read_opcua_node(self, node_id: str):
        """Чтение узла OPC UA"""
        if self.current_protocol == ProtocolType.OPC_UA and self.opcua_client:
            self.opcua_client.read_node(node_id)
        else:
            self.error_occurred.emit("OPC UA не активен")
    
    @pyqtSlot(str, object)
    def write_opcua_node(self, node_id: str, value):
        """Запись значения в узел OPC UA"""
        if self.current_protocol == ProtocolType.OPC_UA and self.opcua_client:
            self.opcua_client.write_node(node_id, value)
        else:
            self.error_occurred.emit("OPC UA не активен")
    
    @pyqtSlot(str)
    def browse_opcua_nodes(self, node_id: str = "i=84"):
        """Просмотр узлов OPC UA"""
        if self.current_protocol == ProtocolType.OPC_UA and self.opcua_client:
            self.opcua_client.browse_node(node_id)
        else:
            self.error_occurred.emit("OPC UA не активен")
    
    def get_current_protocol(self) -> str:
        """Получить текущий протокол"""
        return self.current_protocol.value
    
    def is_connected(self) -> bool:
        """Проверка подключения"""
        return self._connected
    
    @pyqtSlot()
    def cleanup(self):
        """Очистка ресурсов"""
        try:
            # Отключаем все протоколы
            self._disconnect_current_protocol()
            
            # Очистка клиентов
            if self.modbus_client:
                self.modbus_client.cleanup()
            if self.opcua_client:
                self.opcua_client.cleanup()
                
            # Остановка таймера
            self.monitor_timer.stop()
            
            logger.info("Менеджер протоколов очищен")
            
        except Exception as e:
            logger.error(f"Ошибка очистки: {e}")