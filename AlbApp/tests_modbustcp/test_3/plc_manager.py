# plc_manager.py
from plc_worker import AsyncPLCWorker

class PLCManager:
    def __init__(self):
        self._plcs: dict[str, AsyncPLCWorker] = {}

    async def add_plc(self, plc_id: str, host: str, port: int = 502, slave: int = 1, poll_interval: float = 2.0):
        """Добавление PLC и запуск worker"""
        worker = AsyncPLCWorker(plc_id, host, port, slave, poll_interval)
        self._plcs[plc_id] = worker
        # запускаем worker (обрабатывает команды + циклический опрос)
        import asyncio
        asyncio.create_task(worker.start())

    async def request(self, plc_id: str, command: tuple):
        if plc_id not in self._plcs:
            raise ValueError(f"PLC '{plc_id}' не зарегистрирован")
        return await self._plcs[plc_id].request(command)

    def get_latest_data(self, plc_id: str):
        """Возвращает последнее циклическое чтение"""
        if plc_id not in self._plcs:
            return None
        return self._plcs[plc_id].latest_data

    async def shutdown(self):
        for worker in self._plcs.values():
            await worker.stop()
