# plc_worker.py
import asyncio
from asyncio import Queue
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

class AsyncPLCWorker:
    def __init__(self, plc_id: str, host: str, port: int = 502, slave: int = 1, poll_interval: float = 2.0):
        self.plc_id = plc_id
        self.host = host
        self.port = port
        self.slave = slave
        self.poll_interval = poll_interval

        self.queue: Queue = Queue()
        self._running = True
        self.latest_data = None

        self._poll_task = None  # задача для циклического опроса

    async def start(self):
        """Запустить worker и циклический опрос"""
        self._poll_task = asyncio.create_task(self._poll_loop())
        await self._command_loop()

    async def _command_loop(self):
        """Обработка команд из очереди"""
        async with AsyncModbusTcpClient(self.host, port=self.port) as client:
            while self._running:
                future, request = await self.queue.get()
                if future is None:
                    break

                try:
                    cmd, *args = request

                    if cmd == "read_holding":
                        address, count = args
                        result = await client.read_holding_registers(address, count, device_id=self.slave)
                        if result.isError():
                            raise ModbusException(f"Modbus read error: {result}")
                        future.set_result(result.registers)

                    elif cmd == "write_register":
                        address, value = args
                        result = await client.write_register(address, value, device_id=self.slave)
                        if result.isError():
                            raise ModbusException(f"Modbus write error: {result}")
                        future.set_result(True)

                    else:
                        raise ValueError(f"Unknown command: {cmd}")

                except Exception as exc:
                    future.set_exception(exc)

    async def _poll_loop(self):
        """Циклическое чтение holding регистров для GUI"""
        async with AsyncModbusTcpClient(self.host, port=self.port) as client:
            while self._running:
                try:
                    rr = await client.read_holding_registers(address=0, count=10, device_id=self.slave)
                    if not rr.isError():
                        self.latest_data = rr.registers
                except Exception:
                    # Игнорируем ошибки, опрос продолжается
                    pass
                await asyncio.sleep(self.poll_interval)

    async def request(self, command: tuple):
        """Отправка команды в очередь и ожидание результата"""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self.queue.put((future, command))
        return await future

    async def stop(self):
        """Остановка worker и poll задачи"""
        self._running = False
        await self.queue.put((None, None))
        if self._poll_task:
            self._poll_task.cancel()
