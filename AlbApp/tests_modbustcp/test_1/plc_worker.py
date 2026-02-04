# plc_worker.py
import asyncio
from asyncio import Queue


class AsyncPLCWorker:
    def __init__(self, plc_id: str):
        self.plc_id = plc_id
        self.queue: Queue = Queue()
        self._running = True

    async def run(self):
        """Основной цикл worker-а PLC"""
        while self._running:
            future, command = await self.queue.get()

            # Сигнал остановки
            if future is None:
                break

            try:
                # Здесь будет реальный Modbus I/O
                await asyncio.sleep(1)  # симуляция задержки I/O
                result = f"{self.plc_id}: выполнено -> {command}"
                future.set_result(result)

            except Exception as e:
                future.set_exception(e)

    async def request(self, command: str):
        """Отправить команду PLC и получить результат"""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self.queue.put((future, command))
        return await future

    async def stop(self):
        """Остановить worker"""
        self._running = False
        await self.queue.put((None, None))
