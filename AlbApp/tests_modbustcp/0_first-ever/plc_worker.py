# plc_worker.py
import asyncio
from asyncio import Queue

class AsyncPLCWorker:
    def __init__(self, plc_id: str):
        self.plc_id = plc_id
        self.queue = Queue()
        self._running = True

    async def run(self):
        while self._running:
            future, command = await self.queue.get()
            if future is None:
                break
            # симуляция I/O (Modbus)
            await asyncio.sleep(0.1)
            result = f"{self.plc_id}: выполнено -> {command}"
            future.set_result(result)

    async def request(self, command: str):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self.queue.put((future, command))
        return await future

    async def stop(self):
        self._running = False
        await self.queue.put((None, None))
