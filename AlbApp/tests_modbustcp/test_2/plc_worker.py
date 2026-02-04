# plc_worker.py
import asyncio
from asyncio import Queue
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

class AsyncPLCWorker:
    def __init__(self, plc_id: str, host: str, port: int = 502, slave: int = 1):
        self.plc_id = plc_id
        self.host = host
        self.port = port
        self.slave = slave
        self.queue: Queue = Queue()
        self._running = True

    async def run(self):
        """Цикл обработки запросов через pymodbus AsyncModbusTcpClient"""
        async with AsyncModbusTcpClient(self.host, port=self.port) as client:
            while self._running:
                future, request = await self.queue.get()

                if future is None:
                    break

                try:
                    cmd, *args = request

                    # --- Пример чтения holding-регистров ---
                    if cmd == "read_holding":
                        address, count = args
                        result = await client.read_holding_registers(
                            address=address, count=count, device_id = self.slave
                        )
                        if result.isError():
                            raise ModbusException(f"Modbus error: {result}")
                        future.set_result(result.registers)

                    # --- Пример записи одиночного регистра ---
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

    async def request(self, command: tuple):
        """Отправить запрос в очередь и дождаться ответа"""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self.queue.put((future, command))
        return await future

    async def stop(self):
        """Остановить worker"""
        self._running = False
        await self.queue.put((None, None))
