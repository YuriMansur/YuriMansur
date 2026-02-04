# plc_worker.py
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
        self.latest_data = {}  # хранение последних данных для GUI
        self._poll_tasks = []

    async def start(self, polls: list = None):
        """Запуск worker и циклических опросов"""
        if polls:
            for poll in polls:
                task = asyncio.create_task(self._poll_loop(poll))
                self._poll_tasks.append(task)
        await self._command_loop()

    async def _command_loop(self):
        async with AsyncModbusTcpClient(self.host, port=self.port) as client:
            while self._running:
                future, request = await self.queue.get()
                if future is None:
                    break
                try:
                    cmd, type_, address, count, *args = request

                    # --- Чтение ---
                    if cmd == "read":
                        if type_ == "holding":
                            result = await client.read_holding_registers(address, count, device_id=self.device_id)
                        elif type_ == "input":
                            result = await client.read_input_registers(address, count, device_id=self.device_id)
                        elif type_ == "coil":
                            result = await client.read_coils(address, count, device_id=self.device_id)
                        elif type_ == "discrete":
                            result = await client.read_discrete_inputs(address, count, device_id=self.device_id)
                        else:
                            raise ValueError(f"Unknown read type: {type_}")

                        if result.isError():
                            raise ModbusException(f"Modbus read error: {result}")
                        future.set_result(result.registers if hasattr(result, 'registers') else result.bits)

                    # --- Запись ---
                    elif cmd == "write":
                        value = args[0]
                        if type_ == "holding":
                            result = await client.write_register(address, value, device_id=self.device_id)
                        elif type_ == "holdings":
                            result = await client.write_registers(address, value, device_id=self.device_id)
                        elif type_ == "coil":
                            result = await client.write_coil(address, value, device_id=self.device_id)
                        elif type_ == "coils":
                            result = await client.write_coils(address, value, device_id=self.device_id)
                        else:
                            raise ValueError(f"Unknown write type: {type_}")

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
        type_ = poll.get("type", "holding")

        async with AsyncModbusTcpClient(self.host, port=self.port) as client:
            while self._running:
                try:
                    if type_ == "holding":
                        rr = await client.read_holding_registers(address, count, device_id=self.device_id)
                        if not rr.isError():
                            self.latest_data[name] = rr.registers
                    elif type_ == "input":
                        rr = await client.read_input_registers(address, count, device_id=self.device_id)
                        if not rr.isError():
                            self.latest_data[name] = rr.registers
                    elif type_ == "coil":
                        rr = await client.read_coils(address, count, device_id=self.device_id)
                        if not rr.isError():
                            self.latest_data[name] = rr.bits
                    elif type_ == "discrete":
                        rr = await client.read_discrete_inputs(address, count, device_id=self.device_id)
                        if not rr.isError():
                            self.latest_data[name] = rr.bits
                except Exception:
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
