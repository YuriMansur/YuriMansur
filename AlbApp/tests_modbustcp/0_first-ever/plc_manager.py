# plc_manager.py
import asyncio
from plc_worker import AsyncPLCWorker

class PLCManager:
    def __init__(self):
        self._plcs = {}

    async def add_plc(self, plc_id: str):
        worker = AsyncPLCWorker(plc_id)
        self._plcs[plc_id] = worker
        asyncio.create_task(worker.run())

    async def request(self, plc_id: str, command: str):
        if plc_id not in self._plcs:
            raise ValueError(f"PLC '{plc_id}' не зарегистрирован")
        return await self._plcs[plc_id].request(command)

    async def shutdown(self):
        for worker in self._plcs.values():
            await worker.stop()
