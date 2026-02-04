# plc_worker.py
import asyncio
from asyncio import Queue
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

class AsyncPLCWorker:
    def __init__(self, plc_id: str, host: str, port: int = 502, slave: int = 1, poll_interval: float = 1.0):
        self.plc_id = plc_id
        self.host = host
        self.port = port
        self.slave = slave
        self.poll_interval = poll_interval
        self.queue: Queue = Queue()
        self._running = True
        self.latest_data = None  # хранение последнего результата для GUI

    async def run(self):
        """Основной цикл PLC с циклическим чтением и обработкой запросов"""
        async with AsyncModbusTcpClient(self.host, port=self.port) as client:
            while self._running:
                # --- 1. Обработка запросов из очереди ---
                try:
                    future, request = self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    future, request = None, None

                if future is not None:
                    try:
                        cmd, *args = request

                        if cmd == "read_holding":
                            address, count = args
                            result = await client.read_holding_registers(
                                address=address, count=count, device_id=self.slave
                            )
                            if result.isError():
                                raise ModbusException(f"Modbus error: {result}")
                            future.set_result(result.registers)

                        elif cmd == "write_register":
                            address, value = args
                            result = await client.write_register(
                                address=address, value=value, device_id=self.slave
                            )
                            if result.isError():
                                raise ModbusException(f"Modbus write error: {result}")
                            future.set_result(True)

                        else:
                            raise ValueError(f"Неизвестная команда: {cmd}")

                    except Exception as exc:
                        future.set_exception(exc)

                # --- 2. Циклическое чтение для GUI ---
                try:
                    rr = await client.read_holding_registers(address=0, count=10, device_id=self.slave)
                    if not rr.isError():
                        self.latest_data = rr.registers
                except Exception:
                    # Игнорируем ошибки опроса, но сохраняем состояние
                    pass

                await asyncio.sleep(self.poll_interval)

    async def request(self, command: tuple):
        """Отправить запрос в очередь и дождаться ответа"""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self.queue.put((future, command))
        return await future

    async def stop(self):
        self._running = False
        await self.queue.put((None, None))
