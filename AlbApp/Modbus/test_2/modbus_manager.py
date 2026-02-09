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
                # 📌 ПЕРЕМЕННЫЕ ДЛЯ PLC1
                "variables": [
                    {"name": "temperature", "address": 100, "var_type": "float32"},
                    {"name": "pressure", "address": 102, "var_type": "float32"},
                    {"name": "counter", "address": 200, "var_type": "int16"},
                    {"name": "alarm_bit", "address": 300, "var_type": "bit", "bit": 0},
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
                # 📌 ПЕРЕМЕННЫЕ ДЛЯ PLC2
                "variables": [
                    {"name": "flow_rate", "address": 0, "var_type": "float32"},
                ],
            },
        ]


# ЖИЗНЕННЫЙ ЦИКЛ
    async def start_all(self):
        """Запуск всех PLC из конфигурации"""
        for cfg in self._config:
            plc_id = cfg["plc_id"]

            # Создаем и запускаем worker
            worker = AsyncPLCWorker(plc_id=plc_id, host=cfg["host"], device_id=cfg["device_id"])
            self._plcs[plc_id] = worker
            asyncio.create_task(worker.start(cfg.get("polls")))

            # Регистрируем переменные для этого устройства
            for var_cfg in cfg.get("variables", []):
                var = Variable(
                    name=var_cfg["name"],
                    plc_id=plc_id,
                    address=var_cfg["address"],
                    var_type=var_cfg["var_type"],
                    reg_type=var_cfg.get("reg_type", "holding"),
                    endianess=var_cfg.get("endianess", "ABCD"),
                    bit=var_cfg.get("bit")
                )
                self._variables[var_cfg["name"]] = var

    async def shutdown(self):
        for worker in self._plcs.values():
            await worker.stop()

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
    # РАБОТА С ПЕРЕМЕННЫМИ
    # ------------------------------------------------------------------

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
