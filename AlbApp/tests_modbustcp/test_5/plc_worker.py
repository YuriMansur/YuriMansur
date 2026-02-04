# plc_worker.py
import asyncio
from asyncio import Queue
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

class AsyncPLCWorker:
    def __init__(self, plc_id: str, host: str, port: int = 502, device_id: int = 1):
        self.plc_id = plc_id
        self.host = host
        self.port = port
        self.device_id = device_id

        self.queue: Queue = Queue()
        self._running = True
        self.latest_data = {}  # ключ = имя опроса, значение = список регистров
        self._poll_tasks = []  # список задач polling

    async def start(self, polls: list):
        """Запуск worker и всех циклических опросов
        polls = [
            {"name": "holding_0_10", "address": 0, "count": 10, "interval": 2.0},
            {"name": "holding_100_5", "address": 100, "count": 5, "interval": 5.0},
        ]
        """
        # создаем задачи циклического опроса
        for poll in polls:
            task = asyncio.create_task(self._poll_loop(poll))
            self._poll_tasks.append(task)

        # запускаем обработку команд из очереди
        await self._command_loop()

    async def _command_loop(self):
        async with AsyncModbusTcpClient(self.host, port=self.port) as client:
            while self._running:
                future, request = await self.queue.get()
                if future is None:
                    break
                try:
                    cmd, *args = request
                    if cmd == "read_holding":
                        address, count = args
                        result = await client.read_holding_registers(
                            address=address, count=count, device_id=self.device_id
                        )
                        if result.isError():
                            raise ModbusException(f"Modbus read error: {result}")
                        future.set_result(result.registers)

                    elif cmd == "write_register":
                        address, value = args
                        result = await client.write_register(
                            address=address, value=value, device_id=self.device_id
                        )
                        if result.isError():
                            raise ModbusException(f"Modbus write error: {result}")
                        future.set_result(True)

                    else:
                        raise ValueError(f"Unknown command: {cmd}")

                except Exception as exc:
                    future.set_exception(exc)

    async def _poll_loop(self, poll: dict):
        """Циклический опрос одного диапазона регистров"""
        name = poll["name"]
        address = poll["address"]
        count = poll["count"]
        interval = poll.get("interval", 2.0)

        async with AsyncModbusTcpClient(self.host, port=self.port) as client:
            while self._running:
                try:
                    rr = await client.read_holding_registers(
                        address=address, count=count, device_id =self.device_id
                    )
                    if not rr.isError():
                        self.latest_data[name] = rr.registers
                except Exception:
                    # игнорируем ошибки опроса
                    pass
                await asyncio.sleep(interval)

    async def request(self, command: tuple):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self.queue.put((future, command))
        return await future

    async def stop(self):
        self._running = False
        await self.queue.put((None, None))
        for task in self._poll_tasks:
            task.cancel()
