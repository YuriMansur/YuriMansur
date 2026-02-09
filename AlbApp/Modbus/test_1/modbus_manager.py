from typing import Dict, Any, Optional
from plc_worker import AsyncPLCWorker
from regs_convert import ConvertProtocolData
import asyncio
from dataclasses import dataclass

@dataclass
class Variable:
    """Описание переменной для чтения/записи регистров"""
    name: str
    plc_id: str
    address: int
    var_type: str  # "float32", "int32", "uint32", "int16", "uint16", "bit"
    reg_type: str = "holding"  # "holding", "input", "coil", "discrete"
    endianess: str = "ABCD"
    bit: Optional[int] = None  # для битовых переменных

class PLCManager:
    def __init__(self):
        self._plcs: Dict[str, AsyncPLCWorker] = {}
        self._variables: Dict[str, Variable] = {}  # реестр переменных

        # 🔧 ВСЯ КОНФИГУРАЦИЯ ЗДЕСЬ
        self._config = [
            {
                "plc_id": "PLC1",
                "host": "192.168.6.199",
                "device_id": 1,
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
            },
            {
                "plc_id": "PLC2",
                "host": "192.168.1.101",
                "device_id": 2,
                "polls": [
                    {
                        "name": "holding_0_10",
                        "type": "holding",
                        "address": 0,
                        "count": 10,
                        "interval": 3.0,
                    }
                ],
            },
        ]


# ЖИЗНЕННЫЙ ЦИКЛ
    async def start_all(self):
        """Запуск всех PLC из конфигурации"""
        for cfg in self._config:
            worker = AsyncPLCWorker(plc_id=cfg["plc_id"], host=cfg["host"], device_id=cfg["device_id"])

            self._plcs[cfg["plc_id"]] = worker

            # запускаем воркер в фоне
            asyncio.create_task(worker.start(cfg.get("polls")))

    async def shutdown(self):
        for worker in self._plcs.values():
            await worker.stop()

    # ------------------------------------------------------------------
    # УПРАВЛЕНИЕ УСТРОЙСТВАМИ (ДИНАМИЧЕСКОЕ ДОБАВЛЕНИЕ/УДАЛЕНИЕ)
    # ------------------------------------------------------------------

    async def add_device(self, plc_id: str, host: str, device_id: int, polls: list = None, variables: list = None):
        """
        Добавление нового устройства в менеджер

        Args:
            plc_id: уникальный ID контроллера
            host: IP адрес или hostname
            device_id: Modbus device ID (slave ID)
            polls: список конфигураций опроса (опционально)
            variables: список переменных для регистрации (опционально)

        Example:
            await manager.add_device(
                plc_id="PLC1",
                host="192.168.1.100",
                device_id=1,
                polls=[{
                    "name": "holding_0_10",
                    "type": "holding",
                    "address": 0,
                    "count": 10,
                    "interval": 1.0
                }],
                variables=[{
                    "name": "temperature",
                    "address": 100,
                    "var_type": "float32"
                }]
            )
        """
        if plc_id in self._plcs:
            raise ValueError(f"Устройство '{plc_id}' уже существует")

        # Создаем worker
        worker = AsyncPLCWorker(plc_id=plc_id, host=host, device_id=device_id)
        self._plcs[plc_id] = worker

        # Запускаем в фоне
        asyncio.create_task(worker.start(polls or []))

        # Регистрируем переменные, если указаны
        if variables:
            for var_config in variables:
                # Добавляем plc_id к конфигу переменной
                var_config["plc_id"] = plc_id
                self.register_variable(**var_config)

        return worker

    async def remove_device(self, plc_id: str, remove_variables: bool = True):
        """
        Удаление устройства из менеджера

        Args:
            plc_id: ID контроллера для удаления
            remove_variables: удалить связанные переменные (по умолчанию True)
        """
        if plc_id not in self._plcs:
            raise ValueError(f"Устройство '{plc_id}' не найдено")

        # Останавливаем worker
        await self._plcs[plc_id].stop()

        # Удаляем worker
        del self._plcs[plc_id]

        # Удаляем связанные переменные
        if remove_variables:
            vars_to_remove = [name for name, var in self._variables.items() if var.plc_id == plc_id]
            for var_name in vars_to_remove:
                del self._variables[var_name]

    def list_devices(self) -> Dict[str, Dict[str, Any]]:
        """
        Получить список всех устройств

        Returns:
            Словарь с информацией об устройствах
        """
        devices = {}
        for plc_id, worker in self._plcs.items():
            devices[plc_id] = {
                "plc_id": plc_id,
                "host": worker.host,
                "device_id": worker.device_id,
                "connected": worker.client is not None,
                "variables_count": len([v for v in self._variables.values() if v.plc_id == plc_id])
            }
        return devices

    def device_exists(self, plc_id: str) -> bool:
        """Проверить, существует ли устройство"""
        return plc_id in self._plcs

    # ------------------------------------------------------------------
    # НИЗКОУРОВНЕВЫЙ ДОСТУП (ЧИСТЫЙ MODBUS)
    # ------------------------------------------------------------------

    async def request(self, plc_id: str, command: tuple):
        if plc_id not in self._plcs:
            raise ValueError(f"PLC '{plc_id}' не найден")
        return await self._plcs[plc_id].request(command)

    def get_latest_data(self, plc_id: str) -> Dict[str, Any]:
        worker = self._plcs.get(plc_id)
        return worker.latest_data if worker else {}

 

  
# Чтение 32 битных 
    async def read_4bytes(self, plc_id: str, address: int, dtype: str = "float32", endianess: str = "ABCD", reg_type: str = "holding"):

        regs = await self.request(plc_id, ("read", reg_type, address, 2))

        return ConvertProtocolData.convert_4bytes(data = regs, dtype = dtype, endianess = endianess,)

# Запись 32 битных 
    async def write_4bytes(self, plc_id: str, address: int, value, dtype: str = "float32", endianess: str = "ABCD", reg_type: str = "holdings",):

        regs = ConvertProtocolData.convert_4bytes(data = value, dtype = dtype, endianess = endianess)

        await self.request(plc_id,("write", reg_type, address, 2, regs))


# Чтение битов
    async def read_bit(self, plc_id: str, address: int, bit: int, reg_type: str = "holding") -> int:

        regs = await self.request(plc_id, ("read", reg_type, address, 1))

        return ConvertProtocolData.register_bits(reg_or_bits = regs[0], bit = bit)
    
# Запись битов
    async def write_bit(self, plc_id: str, address: int, bit: int, value: int, reg_type: str = "holding",):

        regs = await self.request(plc_id,("read", reg_type, address, 1))

        bits = ConvertProtocolData.register_bits(regs[0])

        bits[bit] = 1 if value else 0

        new_reg = ConvertProtocolData.register_bits(bits)

        await self.request(plc_id,("write", reg_type, address, 1, new_reg))

    # ------------------------------------------------------------------
    # РАБОТА С ПЕРЕМЕННЫМИ (ВЫСОКОУРОВНЕВЫЙ ДОСТУП)
    # ------------------------------------------------------------------

    def register_variable(self, name: str, plc_id: str, address: int, var_type: str,
                         reg_type: str = "holding", endianess: str = "ABCD", bit: Optional[int] = None):
        """
        Регистрация переменной для чтения/записи

        Args:
            name: имя переменной (уникальное)
            plc_id: ID контроллера
            address: адрес регистра
            var_type: тип данных ("float32", "int32", "uint32", "int16", "uint16", "bit")
            reg_type: тип регистра ("holding", "input", "coil", "discrete")
            endianess: порядок байтов для 32-бит ("ABCD", "CDAB", "BADC", "DCBA")
            bit: номер бита (для var_type="bit")
        """
        variable = Variable(
            name=name,
            plc_id=plc_id,
            address=address,
            var_type=var_type,
            reg_type=reg_type,
            endianess=endianess,
            bit=bit
        )
        self._variables[name] = variable
        return variable

    def register_variables_batch(self, variables: list):
        """
        Регистрация нескольких переменных

        Args:
            variables: список словарей с параметрами переменных
        """
        for var_config in variables:
            self.register_variable(**var_config)

    def register_device_variables(self, plc_id: str, variables: list):
        """
        Регистрация переменных для конкретного устройства

        Args:
            plc_id: ID контроллера
            variables: список словарей с параметрами переменных (без plc_id)

        Example:
            manager.register_device_variables("PLC1", [
                {"name": "temp1", "address": 0, "var_type": "float32"},
                {"name": "temp2", "address": 2, "var_type": "float32"},
            ])
        """
        if plc_id not in self._plcs:
            raise ValueError(f"Устройство '{plc_id}' не найдено")

        for var_config in variables:
            var_config["plc_id"] = plc_id
            self.register_variable(**var_config)

    def unregister_variable(self, name: str):
        """
        Удаление переменной из реестра

        Args:
            name: имя переменной для удаления
        """
        if name in self._variables:
            del self._variables[name]
        else:
            raise ValueError(f"Переменная '{name}' не найдена")

    def get_device_variables(self, plc_id: str) -> Dict[str, Variable]:
        """
        Получить все переменные конкретного устройства

        Args:
            plc_id: ID контроллера

        Returns:
            Словарь переменных устройства
        """
        return {name: var for name, var in self._variables.items() if var.plc_id == plc_id}

    async def read_var(self, name: str):
        """
        Чтение значения переменной по имени

        Args:
            name: имя зарегистрированной переменной

        Returns:
            Значение переменной
        """
        if name not in self._variables:
            raise ValueError(f"Переменная '{name}' не зарегистрирована")

        var = self._variables[name]

        # Для битовых переменных
        if var.var_type == "bit":
            if var.bit is None:
                raise ValueError(f"Для переменной '{name}' типа 'bit' не указан номер бита")
            return await self.read_bit(var.plc_id, var.address, var.bit, var.reg_type)

        # Для 16-битных переменных
        elif var.var_type in ["int16", "uint16"]:
            regs = await self.request(var.plc_id, ("read", var.reg_type, var.address, 1))
            return regs[0] if var.var_type == "uint16" else ConvertProtocolData.to_signed_16(regs[0])

        # Для 32-битных переменных
        elif var.var_type in ["float32", "int32", "uint32"]:
            return await self.read_4bytes(var.plc_id, var.address, var.var_type, var.endianess, var.reg_type)

        else:
            raise ValueError(f"Неподдерживаемый тип переменной: {var.var_type}")

    async def write_var(self, name: str, value):
        """
        Запись значения переменной по имени

        Args:
            name: имя зарегистрированной переменной
            value: значение для записи
        """
        if name not in self._variables:
            raise ValueError(f"Переменная '{name}' не зарегистрирована")

        var = self._variables[name]

        # Для битовых переменных
        if var.var_type == "bit":
            if var.bit is None:
                raise ValueError(f"Для переменной '{name}' типа 'bit' не указан номер бита")
            await self.write_bit(var.plc_id, var.address, var.bit, value, var.reg_type)

        # Для 16-битных переменных
        elif var.var_type in ["int16", "uint16"]:
            reg_value = int(value) & 0xFFFF
            await self.request(var.plc_id, ("write", var.reg_type, var.address, 1, [reg_value]))

        # Для 32-битных переменных
        elif var.var_type in ["float32", "int32", "uint32"]:
            await self.write_4bytes(var.plc_id, var.address, value, var.var_type, var.endianess, var.reg_type)

        else:
            raise ValueError(f"Неподдерживаемый тип переменной: {var.var_type}")

    def get_variable_info(self, name: str) -> Optional[Variable]:
        """Получить информацию о переменной"""
        return self._variables.get(name)

    def list_variables(self) -> Dict[str, Variable]:
        """Получить список всех зарегистрированных переменных"""
        return self._variables.copy()
