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
        self.latest_data = {}  # {poll_name: list of values}
        self._poll_tasks = []

    async def start(self, polls: list = None):
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
                        result = await self._read_modbus(client, type_, address, count)
                        future.set_result(result)

                    # --- Запись ---
                    elif cmd == "write":
                        value = args[0]
                        result = await self._write_modbus(client, type_, address, value)
                        future.set_result(result)

                    else:
                        raise ValueError(f"Unknown command: {cmd}")

                except Exception as exc:
                    future.set_exception(exc)

    async def _read_modbus(self, client, type_, address, count):
        if type_ == "holding":
            rr = await client.read_holding_registers(address=address, count=count, device_id=self.device_id)
            return rr.registers
        elif type_ == "input":
            rr = await client.read_input_registers(address=address, count=count, device_id=self.device_id)
            return rr.registers
        elif type_ == "coil":
            rr = await client.read_coils(address=address, count=count, device_id=self.device_id)
            return rr.bits
        elif type_ == "discrete":
            rr = await client.read_discrete_inputs(address=address, count=count, device_id=self.device_id)
            return rr.bits
        else:
            raise ValueError(f"Unknown read type: {type_}")

    async def _write_modbus(self, client, type_, address, value):
        if type_ == "holding":
            rr = await client.write_register(address=address, value=value, device_id=self.device_id)
        elif type_ == "holdings":
            rr = await client.write_registers(address=address, values=value, device_id=self.device_id)
        elif type_ == "coil":
            rr = await client.write_coil(address=address, value=value, device_id=self.device_id)
        elif type_ == "coils":
            rr = await client.write_coils(address=address, values=value, device_id=self.device_id)
        else:
            raise ValueError(f"Unknown write type: {type_}")
        return True

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
                    self.latest_data[name] = await self._read_modbus(client, type_, address, count)
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
