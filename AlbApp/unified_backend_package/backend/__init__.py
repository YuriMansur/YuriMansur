"""
Legacy Package - Backend'ы для Modbus и OPC UA

Полностью рабочие backend классы для промышленных протоколов.

Компоненты:
- ModbusBackend - backend для Modbus TCP с Extended API
  (read_registers с format, read_bit, write_bit, toggle_bit)
- OpcUaBackend - backend для OPC UA серверов
  (read_node, write_node, subscribe_tag, управление подписками)
- example_extended_api.py - примеры использования Modbus
- README_BACKEND.md - документация
"""

from AlbApp.unified_backend_package.backend.modbus_backend import ModbusBackend
from AlbApp.unified_backend_package.backend.opcua_backend import OpcUaBackend

__all__ = ["ModbusBackend", "OpcUaBackend"]
