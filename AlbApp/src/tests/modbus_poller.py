import asyncio
import sys
from typing import Union, List, Dict, Any
from enum import Enum
from dataclasses import dataclass
from pymodbus.client import AsyncModbusTcpClient
from pymodbus import FramerType, ModbusException




# Перечисление для чтения
class ReadRegisterType(Enum):
    HOLDING = "holding"
    INPUT = "input"
    COIL = "coil"
    DISCRETE = "discrete"

# Перечисления для записи
class WriteRegisterType(Enum):
    HOLDING = "holding"
    COIL = "coil"

# Класс данных для чтения
@dataclass
class ReadTask:
    tag: str = None
    address: int
    count: int
    register_type : ReadRegisterType
    poll_interval: float = 1.0

# Класс данных для записи
@dataclass
class WriteTask:
    tag: str = None
    address: int
    register_type: WriteRegisterType
    value: Union[bool, int]  # Для одиночной записи
    values: List[int] = None  # Для множественной записи


    
# Класс для чтения/записи
class ModbusTCP:
    def __init__(self, host: str, port: int, device_id: int, out_queue):
        self.host = host
        self.port = port
        self.device_id = device_id
        self.out_queue = out_queue
        self._running = True
        self._tasks: Dict[str, ReadTask] = {}  # Хранилище задач по тегам
        self._active_poll_tasks: Dict[str, asyncio.Task] = {}  # Активные задачи опроса
        self._client: AsyncModbusTcpClient = None

# Подключение к устройству
    async def connect(self):
        try:  
            self._client = AsyncModbusTcpClient(framer = FramerType.SOCKET, host = self.ip, port = self.port)
            await self._client.connect()
            if not self._client.connected:
                    self.out_queue.put({"error": "Modbus connection failed"})
        except ModbusException as exc:
            self.out_queue.put({"error": f"Connection error: {str(exc)}"})

# Отключение от устройства
    async def disconnect(self):       
        if self._client:
            self._client.close()
            await asyncio.sleep(0.1)

# Запуск цикла опроса 
    async def poll_loop(self, task: ReadTask):  
        while self._running and task.tag in self._tasks and self._client and self._client.connected: 
            try:
                result = qw._read_registers(task) 
                if not result.
                    self.out_queue.put({
                        "tag": task.tag,
                        "type": task.register_type.value,
                        "address": task.address,
                        "registers": result.registers,
                        "timestamp": asyncio.get_event_loop().time()
                    })
                else:
                    self.out_queue.put({
                        "error": str(result),
                        "tag": task.tag
                    })
            except Exception as e:
                self.out_queue.put({
                    "error": f"Poll error for '{task.tag}': {str(e)}",
                    "tag": task.tag
                })
        await asyncio.sleep(task.poll_interval)


# Остановка цикла
    def stop(self):
        self._running = False

# Чтение регистров
    async def _read_registers(self, task: ReadTask):
        match task.register_type:
            case ReadRegisterType.HOLDING:
                return await self._client.read_holding_registers(task.address, task.count, self.device_id)
            case ReadRegisterType.INPUT:
                     return await self._client.read_input_registers(task.address, task.count, self.device_id)
            case ReadRegisterType.COIL:
                return await self._client.read_coils(task.address, task.count, self.device_id)
            case ReadRegisterType.DISCRETE:
                return await self._client.read_discrete_inputs(task.address, task.count, self.device_id)
            case _ : 
                return await self._client.read_holding_registers(task.address, task.count, self.device_id)

# Запись регистров
    async def _write_registers(self, task: WriteTask):
        match task.register_type:
            case WriteRegisterType.COIL:
                if isinstance(task.value, bool):
                   return await self._client.write_coil(task.address, task.value, self.device_id)
                elif isinstance(task.value, list[bool]):
                    return await self._client.write_coils(task.address, task.value, self.device_id)
            case WriteRegisterType.HOLDING:
                if isinstance(task.value, int):
                    return await self._client.w (task.address, task.value, self.device_id)
                elif isinstance(task.value, list[int]):
                    return await self._client.write_registers(task.address, task.value, self.device_id)
            case _ :  
                if isinstance(task.value, int):
                    return await self._client.write_register(task.address, task.value, self.device_id)
                elif isinstance(task.value, list[int]):
                    return await self._client.write_registers(task.address, task.value, self.device_id)   














































































































    # async def run(self):
    #     async with AsyncModbusTcpClient(framer = FramerType.SOCKET, host = self.host, port = self.port) as client:

    #         if not client.connected:
    #             self.out_queue.put({"error": "Modbus connection failed"})
    #             return
            

    #         while self._running:
    #             result = await client.read_holding_registers(address = 0, count = 10,device_id = self.unit_id)

    #             if not result.isError():
    #                 self.out_queue.put({"registers": result.registers})
    #             else:
    #                 self.out_queue.put({"error": str(result)})

    #             await asyncio.sleep(1)
        
    # def stop(self):
    #     self._running = False
