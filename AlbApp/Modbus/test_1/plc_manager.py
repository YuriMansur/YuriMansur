from typing import Dict, Any
from plc_worker import AsyncPLCWorker
from regs_convert import ConvertProtocolData
import asyncio

class PLCManager:
    def __init__(self):
        self._plcs: Dict[str, AsyncPLCWorker] = {}

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
