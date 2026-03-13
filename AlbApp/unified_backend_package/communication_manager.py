"""
CommunicationManager - Единый менеджер для управления Modbus TCP и OPC UA устройствами

═══════════════════════════════════════════════════════════════════════════════
НАЗНАЧЕНИЕ:
═══════════════════════════════════════════════════════════════════════════════
Единый интерфейс для работы с множественными устройствами разных протоколов.
Предоставляет:
- Создание и параметрирование устройств (Modbus TCP, OPC UA)
- Управление данными (чтение/запись тегов и регистров)
- Qt signals для обновления данных
- Единый API независимо от протокола

АРХИТЕКТУРА:
============
    ┌──────────────────────────────────────────────┐
    │      CommunicationManager (этот класс)       │
    │                                              │
    │  Единый API для всех устройств:             │
    │  • add_device(id, type, config)             │
    │  • write_tag(device_id, tag, value)         │
    │  • read_tag(device_id, tag)                 │
    │  • subscribe_tag(device_id, tag)            │
    │                                              │
    │  Qt Signals:                                 │
    │  • tag_updated(device_id, tag, value)       │
    │  • register_updated(device_id, poll, data)  │
    └───────────────┬──────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
    ┌─────────────┐     ┌──────────────┐
    │ModbusBackend│     │ OpcUaBackend │
    │             │     │              │
    │  PLC1, PLC2 │     │  OPC1, OPC2  │
    └─────────────┘     └──────────────┘

ПРИМЕР ИСПОЛЬЗОВАНИЯ:
====================
from unified_backend_package.communication_manager import CommunicationManager

# Создаем менеджер
manager = CommunicationManager()

# Добавляем Modbus устройство
manager.add_device("PLC1", "modbus", {
    "host": "192.168.1.1",
    "port": 502,
    "device_id": 1
})

# Добавляем OPC UA устройство
manager.add_device("OPC1", "opcua", {
    "endpoint": "opc.tcp://192.168.1.10:4840",
    "namespace": 2
})

# Подключаем сигналы
manager.tag_updated.connect(lambda dev, tag, val: print(f"{dev}.{tag} = {val}"))
manager.register_updated.connect(lambda dev, poll, data: print(f"{dev}.{poll}: {data}"))

# Подключаем устройства
manager.connect_device("PLC1")
manager.connect_device("OPC1")

# Подписываемся на теги
manager.subscribe_tag("OPC1", "Temperature", {"node_id": "ns=2;s=Temperature"})

# Читаем/пишем данные
value = manager.read_tag("OPC1", "Temperature")
manager.write_tag("OPC1", "SetPoint", 25.5)

# Для Modbus - работа с регистрами через теги
manager.write_register("PLC1", "holding", 100, 42)
manager.read_register("PLC1", "holding", 100, 2, format="float32")
"""

from typing import Dict, Optional, Any
from PyQt6.QtCore import QObject, pyqtSignal

from unified_backend_package.backend.modbus_backend import ModbusBackend
from unified_backend_package.backend.opcua_backend import OpcUaBackend


class CommunicationManager(QObject):
    """
    Единый менеджер коммуникаций для Modbus TCP и OPC UA

    ОСОБЕННОСТИ:
    ============
    - Единый API для разных протоколов
    - Автоматическая маршрутизация команд к нужному backend
    - Qt signals для всех обновлений данных
    - Абстракция тегов (работает одинаково для Modbus и OPC UA)

    SIGNALS:
    ========
    - tag_updated(device_id, tag_name, value) - обновление тега
    - register_updated(device_id, poll_name, data) - обновление poll (Modbus)
    - device_connected(device_id) - устройство подключено
    - device_disconnected(device_id) - устройство отключено
    - device_error(device_id, error) - ошибка устройства
    """

    # ===== SIGNALS =====
    # Обновления данных
    tag_updated = pyqtSignal(str, str, object)  # (device_id, tag_name, value)
    register_updated = pyqtSignal(str, str, dict)  # (device_id, poll_name, data)

    # События устройств
    device_connected = pyqtSignal(str)  # (device_id)
    device_disconnected = pyqtSignal(str)  # (device_id)
    device_error = pyqtSignal(str, str)  # (device_id, error)

    # События подписок
    tag_subscribed = pyqtSignal(str, str)  # (device_id, tag_name)
    tag_unsubscribed = pyqtSignal(str, str)  # (device_id, tag_name)

    def __init__(self):
        """Инициализация Communication Manager"""
        super().__init__()

        # ===== BACKEND INSTANCES =====
        self.modbus = ModbusBackend()
        self.opcua = OpcUaBackend()

        # ===== DEVICE REGISTRY =====
        # {device_id: {"type": "modbus"|"opcua", "config": dict, "tags": {tag_name: tag_config}}}
        self.devices: Dict[str, dict] = {}

        # ===== TAG MAPPING =====
        # Для Modbus: мапинг тегов на регистры
        # {device_id: {tag_name: {"reg_type": str, "address": int, "format": str}}}
        self.tag_mappings: Dict[str, Dict[str, dict]] = {}

        # ===== ПОДКЛЮЧАЕМ SIGNALS ОТ BACKEND =====
        self._connect_backend_signals()

    # ==========================================================================
    # DEVICE MANAGEMENT
    # ==========================================================================

    def add_device(
        self,
        device_id: str,
        device_type: str,
        config: dict,
        tags: Optional[Dict[str, dict]] = None
    ) -> bool:
        """
        Добавить устройство

        Args:
            device_id: Уникальный ID устройства
            device_type: Тип протокола ("modbus" или "opcua")
            config: Конфигурация устройства
                Modbus: {"host": str, "port": int, "device_id": int}
                OPC UA: {"endpoint": str, "namespace": int}
            tags: Конфигурация тегов (опционально)
                Modbus: {tag_name: {"reg_type": str, "address": int, "format": str}}
                OPC UA: {tag_name: {"node_id": str}}

        Returns:
            bool: True если добавлено

        Example:
            # Modbus
            manager.add_device("PLC1", "modbus", {
                "host": "192.168.1.1",
                "port": 502,
                "device_id": 1
            }, tags={
                "Temperature": {"reg_type": "holding", "address": 0, "format": "float32"},
                "Pressure": {"reg_type": "holding", "address": 2, "format": "float32"}
            })

            # OPC UA
            manager.add_device("OPC1", "opcua", {
                "endpoint": "opc.tcp://192.168.1.10:4840",
                "namespace": 2
            }, tags={
                "Temperature": {"node_id": "ns=2;s=Temperature"},
                "Pressure": {"node_id": "ns=2;s=Pressure"}
            })
        """
        if device_id in self.devices:
            return False  # Устройство уже существует

        device_type = device_type.lower()

        if device_type not in ["modbus", "opcua"]:
            raise ValueError(f"Unsupported device type: {device_type}")

        # Добавляем в соответствующий backend
        if device_type == "modbus":
            success = self.modbus.add_device(
                plc_id=device_id,
                host=config["host"],
                port=config.get("port", 502),
                device_id=config.get("device_id", 1)
            )
        elif device_type == "opcua":
            success = self.opcua.add_server(
                server_id=device_id,
                endpoint=config["endpoint"],
                namespace=config.get("namespace", 2),
                timeout=config.get("timeout", 10.0)
            )
        else:
            return False

        if not success:
            return False

        # Сохраняем в реестр
        self.devices[device_id] = {
            "type": device_type,
            "config": config,
            "tags": tags or {}
        }

        # Сохраняем маппинг тегов для Modbus
        if device_type == "modbus" and tags:
            self.tag_mappings[device_id] = tags

        return True

    def remove_device(self, device_id: str, force: bool = False) -> bool:
        """
        Удалить устройство

        Args:
            device_id: ID устройства
            force: Принудительно удалить (отключить если подключено)

        Returns:
            bool: True если удалено
        """
        if device_id not in self.devices:
            return False

        device = self.devices[device_id]
        device_type = device["type"]

        # Удаляем из backend
        if device_type == "modbus":
            success = self.modbus.remove_device(device_id, force=force)
        elif device_type == "opcua":
            success = self.opcua.remove_server(device_id, force=force)
        else:
            return False

        if success:
            # Удаляем из реестра
            del self.devices[device_id]

            # Удаляем маппинг тегов
            if device_id in self.tag_mappings:
                del self.tag_mappings[device_id]

        return success

    def get_devices(self) -> Dict[str, dict]:
        """Получить все устройства"""
        return self.devices.copy()

    def get_device_info(self, device_id: str) -> Optional[dict]:
        """Получить информацию об устройстве"""
        return self.devices.get(device_id)

    def is_connected(self, device_id: str) -> bool:
        """Проверить подключение устройства"""
        if device_id not in self.devices:
            return False

        device = self.devices[device_id]
        device_type = device["type"]

        if device_type == "modbus":
            return self.modbus.is_connected(device_id)
        elif device_type == "opcua":
            return self.opcua.is_connected(device_id)

        return False

    # ==========================================================================
    # CONNECTION
    # ==========================================================================

    def connect_device(self, device_id: str) -> bool:
        """
        Подключиться к устройству

        Args:
            device_id: ID устройства

        Returns:
            bool: True если подключение запущено
        """
        if device_id not in self.devices:
            return False

        device = self.devices[device_id]
        device_type = device["type"]

        if device_type == "modbus":
            return self.modbus.connect_device(device_id)
        elif device_type == "opcua":
            return self.opcua.connect_server(device_id)

        return False

    def disconnect_device(self, device_id: str, blocking: bool = False) -> bool:
        """
        Отключиться от устройства

        Args:
            device_id: ID устройства
            blocking: Блокирующий режим

        Returns:
            bool: True если отключение запущено
        """
        if device_id not in self.devices:
            return False

        device = self.devices[device_id]
        device_type = device["type"]

        if device_type == "modbus":
            return self.modbus.disconnect_device(device_id, blocking=blocking)
        elif device_type == "opcua":
            return self.opcua.disconnect_server(device_id, blocking=blocking)

        return False

    def connect_all(self):
        """Подключить все устройства"""
        for device_id in self.devices.keys():
            self.connect_device(device_id)

    def disconnect_all(self, blocking: bool = False):
        """Отключить все устройства"""
        for device_id in list(self.devices.keys()):
            self.disconnect_device(device_id, blocking=blocking)

    # ==========================================================================
    # TAG OPERATIONS (UNIFIED API)
    # ==========================================================================

    def subscribe_tag(
        self,
        device_id: str,
        tag_name: str,
        tag_config: Optional[dict] = None
    ) -> bool:
        """
        Подписаться на тег (работает для OPC UA и Modbus polls)

        Args:
            device_id: ID устройства
            tag_name: Имя тега
            tag_config: Конфигурация тега (опционально)
                OPC UA: {"node_id": "ns=2;s=Temperature"}
                Modbus: {"reg_type": "holding", "address": 0, "count": 2, "format": "float32"}

        Returns:
            bool: True если подписка создана

        Example:
            # OPC UA
            manager.subscribe_tag("OPC1", "Temperature", {
                "node_id": "ns=2;s=Temperature"
            })

            # Modbus (через poll)
            manager.subscribe_tag("PLC1", "Temperature", {
                "reg_type": "holding",
                "address": 0,
                "count": 2,
                "format": "float32",
                "interval": 1000
            })
        """
        if device_id not in self.devices:
            return False

        device = self.devices[device_id]
        device_type = device["type"]

        # Используем конфигурацию из устройства если не передана
        if tag_config is None and tag_name in device["tags"]:
            tag_config = device["tags"][tag_name]

        if device_type == "opcua":
            # OPC UA subscription
            node_id = tag_config.get("node_id") if tag_config else f"ns=2;s={tag_name}"
            return self.opcua.subscribe_tag(device_id, node_id, tag_name)

        elif device_type == "modbus":
            # Modbus poll subscription
            if not tag_config:
                return False

            poll_config = {
                "reg_type": tag_config["reg_type"],
                "address": tag_config["address"],
                "count": tag_config.get("count", 1),
                "format": tag_config.get("format", "raw"),
                "interval": tag_config.get("interval", 1000)
            }

            return self.modbus.add_poll(device_id, tag_name, poll_config)

        return False

    def unsubscribe_tag(self, device_id: str, tag_name: str) -> bool:
        """
        Отписаться от тега

        Args:
            device_id: ID устройства
            tag_name: Имя тега

        Returns:
            bool: True если отписка выполнена
        """
        if device_id not in self.devices:
            return False

        device = self.devices[device_id]
        device_type = device["type"]

        if device_type == "opcua":
            # Найти node_id по tag_name
            tag_config = device["tags"].get(tag_name)
            if not tag_config:
                return False
            node_id = tag_config.get("node_id")
            return self.opcua.unsubscribe_tag(device_id, node_id)

        elif device_type == "modbus":
            return self.modbus.remove_poll(device_id, tag_name)

        return False

    def read_tag(self, device_id: str, tag_name: str) -> Optional[Any]:
        """
        Прочитать значение тега

        Args:
            device_id: ID устройства
            tag_name: Имя тега

        Returns:
            Значение тега (через signal для OPC UA, синхронно для Modbus)

        Example:
            # OPC UA - результат через signal tag_updated
            manager.read_tag("OPC1", "Temperature")

            # Modbus - результат через signal register_updated
            manager.read_tag("PLC1", "Temperature")
        """
        if device_id not in self.devices:
            return None

        device = self.devices[device_id]
        device_type = device["type"]

        if device_type == "opcua":
            # OPC UA - читаем node
            tag_config = device["tags"].get(tag_name)
            if not tag_config:
                return None
            node_id = tag_config.get("node_id")
            self.opcua.read_node(device_id, node_id)
            return None  # Результат через signal

        elif device_type == "modbus":
            # Modbus - читаем регистр
            tag_config = self.tag_mappings.get(device_id, {}).get(tag_name)
            if not tag_config:
                return None

            return self.modbus.read_registers(
                plc_id=device_id,
                reg_type=tag_config["reg_type"],
                address=tag_config["address"],
                count=tag_config.get("count", 1),
                format=tag_config.get("format", "raw")
            )

        return None

    def write_tag(self, device_id: str, tag_name: str, value: Any) -> bool:
        """
        Записать значение тега

        Args:
            device_id: ID устройства
            tag_name: Имя тега
            value: Значение для записи

        Returns:
            bool: True если запись запущена

        Example:
            manager.write_tag("OPC1", "SetPoint", 25.5)
            manager.write_tag("PLC1", "Temperature", 23.0)
        """
        if device_id not in self.devices:
            return False

        device = self.devices[device_id]
        device_type = device["type"]

        if device_type == "opcua":
            # OPC UA - пишем в node
            tag_config = device["tags"].get(tag_name)
            if not tag_config:
                return False
            node_id = tag_config.get("node_id")
            return self.opcua.write_node(device_id, node_id, value)

        elif device_type == "modbus":
            # Modbus - пишем в регистр
            tag_config = self.tag_mappings.get(device_id, {}).get(tag_name)
            if not tag_config:
                return False

            return self.modbus.write_registers(
                plc_id=device_id,
                reg_type=tag_config["reg_type"],
                address=tag_config["address"],
                value=value,
                format=tag_config.get("format", "raw")
            )

        return False

    # ==========================================================================
    # REGISTER OPERATIONS (MODBUS-SPECIFIC)
    # ==========================================================================

    def write_register(
        self,
        device_id: str,
        reg_type: str,
        address: int,
        value: Any,
        format: str = "raw"
    ) -> bool:
        """
        Записать регистр Modbus (прямой доступ)

        Args:
            device_id: ID устройства (должен быть Modbus)
            reg_type: Тип регистра ("holding", "coil")
            address: Адрес
            value: Значение
            format: Формат ("raw", "float32", "int32", ...)

        Returns:
            bool: True если запись выполнена
        """
        if device_id not in self.devices:
            return False

        device = self.devices[device_id]
        if device["type"] != "modbus":
            return False

        return self.modbus.write_registers(
            plc_id=device_id,
            reg_type=reg_type,
            address=address,
            value=value,
            format=format
        )

    def read_register(
        self,
        device_id: str,
        reg_type: str,
        address: int,
        count: int = 1,
        format: str = "raw"
    ) -> Optional[Any]:
        """
        Прочитать регистр Modbus (прямой доступ)

        Args:
            device_id: ID устройства (должен быть Modbus)
            reg_type: Тип регистра ("holding", "input", "coil", "discrete")
            address: Адрес
            count: Количество регистров
            format: Формат ("raw", "float32", "int32", ...)

        Returns:
            Значение регистра
        """
        if device_id not in self.devices:
            return None

        device = self.devices[device_id]
        if device["type"] != "modbus":
            return None

        return self.modbus.read_registers(
            plc_id=device_id,
            reg_type=reg_type,
            address=address,
            count=count,
            format=format
        )

    # ==========================================================================
    # DATA ACCESS
    # ==========================================================================

    def get_latest_data(self, device_id: str) -> Dict[str, Any]:
        """
        Получить последние данные от устройства

        Args:
            device_id: ID устройства

        Returns:
            Словарь с данными (формат зависит от типа устройства)
        """
        if device_id not in self.devices:
            return {}

        device = self.devices[device_id]
        device_type = device["type"]

        if device_type == "modbus":
            return self.modbus.get_latest_data(device_id)
        elif device_type == "opcua":
            return self.opcua.get_latest_data(device_id)

        return {}

    def get_all_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Получить данные от всех устройств

        Returns:
            Словарь {device_id: данные}
        """
        result = {}
        for device_id in self.devices.keys():
            result[device_id] = self.get_latest_data(device_id)

        return result

    # ==========================================================================
    # INTERNAL SIGNAL HANDLERS
    # ==========================================================================

    def _connect_backend_signals(self):
        """Подключить signals от backend'ов к CommunicationManager"""

        # ===== MODBUS BACKEND SIGNALS =====
        self.modbus.device_connected.connect(
            lambda dev_id: self.device_connected.emit(dev_id)
        )
        self.modbus.device_disconnected.connect(
            lambda dev_id: self.device_disconnected.emit(dev_id)
        )
        self.modbus.device_error.connect(
            lambda dev_id, err: self.device_error.emit(dev_id, err)
        )
        self.modbus.data_updated.connect(
            lambda dev_id, poll_name, data: self._on_modbus_data_updated(dev_id, poll_name, data)
        )

        # ===== OPC UA BACKEND SIGNALS =====
        self.opcua.server_connected.connect(
            lambda dev_id: self.device_connected.emit(dev_id)
        )
        self.opcua.server_disconnected.connect(
            lambda dev_id: self.device_disconnected.emit(dev_id)
        )
        self.opcua.server_error.connect(
            lambda dev_id, err: self.device_error.emit(dev_id, err)
        )
        self.opcua.data_updated.connect(
            lambda dev_id, node_id, value: self._on_opcua_data_updated(dev_id, node_id, value)
        )
        self.opcua.tag_subscribed.connect(
            lambda dev_id, node_id: self._on_opcua_tag_subscribed(dev_id, node_id)
        )
        self.opcua.tag_unsubscribed.connect(
            lambda dev_id, node_id: self.tag_unsubscribed.emit(dev_id, node_id)
        )

    def _on_modbus_data_updated(self, device_id: str, poll_name: str, data: dict):
        """Обработчик обновления данных Modbus"""
        # Эмитим register_updated
        self.register_updated.emit(device_id, poll_name, data)

        # Также эмитим tag_updated для каждого значения в poll
        # (если poll содержит один регистр - это тег)
        if "value" in data:
            self.tag_updated.emit(device_id, poll_name, data["value"])

    def _on_opcua_data_updated(self, device_id: str, node_id: str, value: Any):
        """Обработчик обновления данных OPC UA"""
        # Найти имя тега по node_id
        tag_name = self._find_tag_name_by_node_id(device_id, node_id)

        # Эмитим tag_updated
        self.tag_updated.emit(device_id, tag_name or node_id, value)

    def _on_opcua_tag_subscribed(self, device_id: str, node_id: str):
        """Обработчик подписки на тег OPC UA"""
        # Найти имя тега по node_id
        tag_name = self._find_tag_name_by_node_id(device_id, node_id)

        # Эмитим tag_subscribed
        self.tag_subscribed.emit(device_id, tag_name or node_id)

    def _find_tag_name_by_node_id(self, device_id: str, node_id: str) -> Optional[str]:
        """Найти имя тега по node_id"""
        if device_id not in self.devices:
            return None

        device = self.devices[device_id]
        tags = device.get("tags", {})

        for tag_name, tag_config in tags.items():
            if tag_config.get("node_id") == node_id:
                return tag_name

        return None

    # ==========================================================================
    # LIFECYCLE
    # ==========================================================================

    def stop_all(self):
        """Остановить все устройства"""
        self.disconnect_all(blocking=True)
        self.modbus.stop_all()
        self.opcua.stop_all()
        self.devices.clear()
        self.tag_mappings.clear()
