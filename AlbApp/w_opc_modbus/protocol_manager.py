"""
Unified Protocol Manager
Централизованная конфигурация Modbus и OPC UA
"""
from typing import Dict, Any, Optional

# Импорты менеджеров
from w_opc_modbus.opcua.modbus_manager import PLCManager
from opc_client import OPCUAManager


class ProtocolManager:
    """
    🔧 ЦЕНТРАЛИЗОВАННАЯ КОНФИГУРАЦИЯ ВСЕХ ПРОТОКОЛОВ

    Здесь вы вручную настраиваете:
    - Modbus устройства, poll loops, переменные
    - OPC UA серверы и переменные
    """

    def __init__(self):
        # ========================================================================
        # 🔴 КОНФИГУРАЦИЯ MODBUS УСТРОЙСТВ
        # ========================================================================
        self.modbus_config = [
            {
                "plc_id": "PLC1",
                "host": "192.168.6.199",
                "device_id": 1,

                # Poll loops для циклического опроса
                "polls": [
                    {
                        "name": "holding_0_10",
                        "type": "holding",
                        "address": 0,
                        "count": 10,
                        "interval": 1.0,
                    },
                    {
                        "name": "holding_100_2",
                        "type": "holding",
                        "address": 100,
                        "count": 2,
                        "interval": 2.0,
                    },
                ],

                # Переменные для чтения/записи регистров
                "variables": [
                    {"name": "temperature", "address": 100, "var_type": "float32", "endianess": "ABCD"},
                    {"name": "pressure", "address": 102, "var_type": "float32", "endianess": "ABCD"},
                    {"name": "setpoint", "address": 110, "var_type": "float32", "endianess": "ABCD"},
                    {"name": "counter", "address": 200, "var_type": "int16"},
                    {"name": "alarm_bit", "address": 300, "var_type": "bit", "bit": 0},
                ],
            },

            # Добавьте ещё устройства по аналогии:
            # {
            #     "plc_id": "PLC2",
            #     "host": "192.168.1.101",
            #     "device_id": 2,
            #     "polls": [...],
            #     "variables": [...],
            # },
        ]

        # ========================================================================
        # 🔴 КОНФИГУРАЦИЯ OPC UA СЕРВЕРОВ
        # ========================================================================
        self.opcua_config = [
            {
                "server_id": "OPCUA_Server1",
                "url": "opc.tcp://192.168.1.200:4840",
                "security_policy": None,  # или "Basic256Sha256"
                "security_mode": None,    # или "SignAndEncrypt"
                "username": None,         # опционально
                "password": None,         # опционально

                # Переменные OPC UA
                "variables": [
                    {"name": "PLC1_temperature", "node_id": "ns=2;s=PLC1.Temperature"},
                    {"name": "PLC1_pressure", "node_id": "ns=2;s=PLC1.Pressure"},
                    {"name": "PLC1_setpoint", "node_id": "ns=2;s=PLC1.Setpoint"},
                ],
            },

            # Добавьте ещё серверы:
            # {
            #     "server_id": "OPCUA_Server2",
            #     "url": "opc.tcp://192.168.1.201:4840",
            #     "variables": [...],
            # },
        ]

        # ========================================================================
        # Инициализация менеджеров (используют конфигурацию выше)
        # ========================================================================
        self.modbus_manager = PLCManager()
        self.opcua_manager = OPCUAManager()

        # Переносим конфигурацию в менеджеры
        self.modbus_manager._config = self.modbus_config
        self.opcua_manager._config = self.opcua_config

        # Единый реестр переменных
        self._variables: Dict[str, dict] = {}

    # ==========================================================================
    # ЗАПУСК И ОСТАНОВКА
    # ==========================================================================

    async def start_all(self):
        """Запуск всех протоколов"""
        # Запускаем Modbus
        await self.modbus_manager.start_all()

        # Запускаем OPC UA
        await self.opcua_manager.connect_all()

        # Регистрируем переменные из обоих менеджеров
        self._register_modbus_variables()
        self._register_opcua_variables()

    async def shutdown(self):
        """Остановка всех протоколов"""
        await self.modbus_manager.shutdown()
        await self.opcua_manager.disconnect_all()

    def _register_modbus_variables(self):
        """Регистрация переменных Modbus в едином реестре"""
        modbus_vars = self.modbus_manager._variables

        for name, var in modbus_vars.items():
            self._variables[f"modbus.{name}"] = {
                "protocol": "modbus",
                "name": name,
                "plc_id": var.plc_id,
                "address": var.address,
                "var_type": var.var_type,
                "reg_type": var.reg_type,
                "endianess": var.endianess,
                "bit": var.bit
            }

    def _register_opcua_variables(self):
        """Регистрация переменных OPC UA в едином реестре"""
        opcua_vars = self.opcua_manager._variables

        for name, var in opcua_vars.items():
            self._variables[f"opcua.{name}"] = {
                "protocol": "opcua",
                "name": name,
                "server_id": var.server_id,
                "node_id": var.node_id
            }

    # ==========================================================================
    # УНИФИЦИРОВАННОЕ ЧТЕНИЕ/ЗАПИСЬ
    # ==========================================================================

    async def read_var(self, name: str) -> Any:
        """
        Чтение переменной (автоопределение протокола)

        Args:
            name: Имя переменной (с префиксом "modbus." или "opcua.")
                  Или без префикса - тогда ищется по обоим протоколам

        Returns:
            Значение переменной
        """
        # Если указан префикс
        if name.startswith("modbus."):
            var_name = name.replace("modbus.", "")
            return await self.modbus_manager.read_var(var_name)

        elif name.startswith("opcua."):
            var_name = name.replace("opcua.", "")
            return await self.opcua_manager.read_var(var_name)

        # Если префикса нет - пробуем найти в реестре
        else:
            if f"modbus.{name}" in self._variables:
                return await self.modbus_manager.read_var(name)
            elif f"opcua.{name}" in self._variables:
                return await self.opcua_manager.read_var(name)
            else:
                raise ValueError(f"Переменная '{name}' не найдена ни в Modbus, ни в OPC UA")

    async def write_var(self, name: str, value: Any):
        """
        Запись переменной (автоопределение протокола)

        Args:
            name: Имя переменной (с префиксом "modbus." или "opcua.")
            value: Значение для записи
        """
        # Если указан префикс
        if name.startswith("modbus."):
            var_name = name.replace("modbus.", "")
            await self.modbus_manager.write_var(var_name, value)

        elif name.startswith("opcua."):
            var_name = name.replace("opcua.", "")
            await self.opcua_manager.write_var(var_name, value)

        # Если префикса нет - пробуем найти
        else:
            if f"modbus.{name}" in self._variables:
                await self.modbus_manager.write_var(name, value)
            elif f"opcua.{name}" in self._variables:
                await self.opcua_manager.write_var(name, value)
            else:
                raise ValueError(f"Переменная '{name}' не найдена")

    def list_variables(self, protocol: Optional[str] = None) -> Dict[str, dict]:
        """
        Получить список всех переменных

        Args:
            protocol: Фильтр по протоколу ("modbus", "opcua" или None для всех)

        Returns:
            Словарь переменных
        """
        if protocol is None:
            return self._variables.copy()
        else:
            return {
                name: var
                for name, var in self._variables.items()
                if var["protocol"] == protocol
            }

    def list_devices(self) -> Dict[str, Dict[str, Any]]:
        """Получить список всех устройств из обоих протоколов"""
        devices = {}

        # OPC UA серверы
        opcua_servers = self.opcua_manager.list_servers()
        for server_id, info in opcua_servers.items():
            devices[f"opcua.{server_id}"] = {
                **info,
                "protocol": "opcua"
            }

        # Modbus устройства
        for cfg in self.modbus_config:
            plc_id = cfg["plc_id"]
            devices[f"modbus.{plc_id}"] = {
                "protocol": "modbus",
                "host": cfg["host"],
                "port": cfg.get("port", 502),
                "device_id": cfg["device_id"],
                "polls_count": len(cfg.get("polls", [])),
                "variables_count": len(cfg.get("variables", []))
            }

        return devices

    # ==========================================================================
    # МЕТОДЫ ОБРАТНОЙ СОВМЕСТИМОСТИ (ДЛЯ GUI)
    # ==========================================================================

    async def request(self, plc_id: str, command: tuple):
        """Прямой запрос - использует Modbus по умолчанию"""
        return await self.modbus_manager.request(plc_id, command)

    def get_latest_data(self, plc_id: str) -> Dict[str, Any]:
        """Получить последние данные опроса - использует Modbus по умолчанию"""
        return self.modbus_manager.get_latest_data(plc_id)

    async def write_4bytes(self, plc_id: str, address: int, value, dtype: str = "float32",
                          endianess: str = "ABCD", reg_type: str = "holdings"):
        """Запись 4-байтного значения - использует Modbus по умолчанию"""
        await self.modbus_manager.write_4bytes(plc_id, address, value, dtype, endianess, reg_type)

    # ==========================================================================
    # СПЕЦИФИЧНЫЕ МЕТОДЫ MODBUS
    # ==========================================================================

    async def modbus_request(self, plc_id: str, command: tuple):
        """Прямой Modbus запрос"""
        return await self.modbus_manager.request(plc_id, command)

    def modbus_get_latest_data(self, plc_id: str) -> Dict[str, Any]:
        """Получить последние данные Modbus опроса"""
        return self.modbus_manager.get_latest_data(plc_id)

    async def modbus_read_4bytes(self, plc_id: str, address: int, dtype: str = "float32",
                                 endianess: str = "ABCD", reg_type: str = "holding"):
        """Чтение 4-байтного значения из Modbus"""
        return await self.modbus_manager.read_4bytes(plc_id, address, dtype, endianess, reg_type)

    async def modbus_write_4bytes(self, plc_id: str, address: int, value, dtype: str = "float32",
                                  endianess: str = "ABCD", reg_type: str = "holdings"):
        """Запись 4-байтного значения в Modbus"""
        await self.modbus_manager.write_4bytes(plc_id, address, value, dtype, endianess, reg_type)

    # ==========================================================================
    # СПЕЦИФИЧНЫЕ МЕТОДЫ OPC UA
    # ==========================================================================

    async def opcua_subscribe(self, var_name: str, callback):
        """Подписка на изменения OPC UA переменной"""
        await self.opcua_manager.subscribe_var(var_name, callback)

    async def opcua_read_multiple(self, var_names: list) -> Dict[str, Any]:
        """Чтение нескольких OPC UA переменных"""
        return await self.opcua_manager.read_multiple(var_names)

    # ==========================================================================
    # УТИЛИТЫ
    # ==========================================================================

    def get_variable_info(self, name: str) -> Optional[dict]:
        """Получить информацию о переменной"""
        # Ищем с префиксом
        if name in self._variables:
            return self._variables[name]

        # Ищем без префикса
        for prefix in ["modbus.", "opcua."]:
            full_name = f"{prefix}{name}"
            if full_name in self._variables:
                return self._variables[full_name]

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Статистика по протоколам"""
        modbus_vars = len(self.list_variables("modbus"))
        opcua_vars = len(self.list_variables("opcua"))

        return {
            "total_variables": len(self._variables),
            "modbus": {
                "devices": len(self.modbus_config),
                "variables": modbus_vars
            },
            "opcua": {
                "servers": len(self.opcua_config),
                "variables": opcua_vars
            }
        }
