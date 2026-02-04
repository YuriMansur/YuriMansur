# plc_manager.py
import asyncio
from plc_worker import AsyncPLCWorker

class PLCManager:
    def __init__(self):
        self._plcs: dict[str, AsyncPLCWorker] = {}

    async def add_plc(self, plc_id: str, host: str, port: int = 502, slave: int = 1):
        """Добавить PLC и запустить worker"""
        worker = AsyncPLCWorker(plc_id, host, port, slave)
        self._plcs[plc_id] = worker
        asyncio.create_task(worker.run())

    async def request(self, plc_id: str, command: tuple):
        if plc_id not in self._plcs:
            raise ValueError(f"PLC '{plc_id}' не зарегистрирован")
        return await self._plcs[plc_id].request(command)

    def get_latest_data(self, plc_id: str):
        """Получить последнее циклическое чтение для GUI"""
        if plc_id not in self._plcs:
            return None
        return self._plcs[plc_id].latest_data

    async def shutdown(self):
        for worker in self._plcs.values():
            await worker.stop()
