# plc_manager.py
from plc_worker import AsyncPLCWorker
import asyncio

class PLCManager:
    def __init__(self):
        self._plcs: dict[str, AsyncPLCWorker] = {}

    async def add_plc(self, plc_id: str, host: str, device_id: int = 1, polls: list = None):
        """
        Добавление PLC с несколькими циклическими опросами
        polls = [
            {"name": "holding_0_10", "address": 0, "count": 10, "interval": 2.0},
            {"name": "holding_100_5", "address": 100, "count": 5, "interval": 5.0},
        ]
        """
        if polls is None:
            polls = []

        worker = AsyncPLCWorker(plc_id, host, device_id=device_id)
        self._plcs[plc_id] = worker
        asyncio.create_task(worker.start(polls))

    async def request(self, plc_id: str, command: tuple):
        if plc_id not in self._plcs:
            raise ValueError(f"PLC '{plc_id}' не зарегистрирован")
        return await self._plcs[plc_id].request(command)

    def get_latest_data(self, plc_id: str):
        if plc_id not in self._plcs:
            return {}
        return self._plcs[plc_id].latest_data

    async def shutdown(self):
        for worker in self._plcs.values():
            await worker.stop()
