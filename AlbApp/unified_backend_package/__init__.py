"""
Unified Backend Package - Modbus + OPC UA Backend

Полностью автономный пакет для работы с промышленными протоколами.

Компоненты:
    backend/               - ModbusBackend и OpcUaBackend
    worker/                - worker threads для протоколов
    gui/                   - графические интерфейсы
    communication_manager  - единый менеджер для всех устройств

Использование:

1. Через CommunicationManager (рекомендуется):
    from AlbApp.unified_backend_package import CommunicationManager

    manager = CommunicationManager()

    # Добавляем устройства любого типа
    manager.add_device("PLC1", "modbus", {...})
    manager.add_device("OPC1", "opcua", {...})

    # Единый API для всех
    manager.connect_device("PLC1")
    manager.write_tag("PLC1", "Temperature", 25.5)

    # Qt signals
    manager.tag_updated.connect(handler)

2. Через отдельные backend'ы:
    from AlbApp.unified_backend_package import ModbusBackend, OpcUaBackend

    modbus = ModbusBackend()
    opcua = OpcUaBackend()
"""

from AlbApp.unified_backend_package.backend import ModbusBackend, OpcUaBackend
from AlbApp.unified_backend_package.communication_manager import CommunicationManager

__version__ = "1.0.0"
__all__ = [
    "ModbusBackend",
    "OpcUaBackend",
    "CommunicationManager",
]
