import asyncio
from plc_worker import AsyncPLCWorker

class PLCManager:
    def __init__(self):
        self._plcs: dict[str, AsyncPLCWorker] = {}

        # 🔧 ВСЯ КОНФИГУРАЦИЯ ЗДЕСЬ
        self._config = [
            {
                "plc_id": "PLC1",
                "host": "192.168.6.199",
                "device_id": 1,
                "polls": [
                    {
                        "name": "holding_0_10",
                        "type": "holding",
                        "address": 0,
                        "count": 10,
                        "interval": 1.0,
                    },
                    {
                        "name": "holding_100_5",
                        "type": "holding",
                        "address": 100,
                        "count": 5,
                        "interval": 2.0,
                    },
                ],
            },
            {
                "plc_id": "PLC2",
                "host": "192.168.1.101",
                "device_id": 2,
                "polls": [
                    {
                        "name": "holding_0_10",
                        "type": "holding",
                        "address": 0,
                        "count": 10,
                        "interval": 3.0,
                    }
                ],
            },
        ]

    async def start_all(self):
        """Запуск всех PLC из конфигурации"""
        for cfg in self._config:
            worker = AsyncPLCWorker(
                plc_id=cfg["plc_id"],
                host=cfg["host"],
                device_id=cfg["device_id"],
            )

            self._plcs[cfg["plc_id"]] = worker

            # ❗ ВАЖНО: запускаем воркер в фоне
            asyncio.create_task(worker.start(cfg["polls"]))

    async def request(self, plc_id: str, command: tuple):
        if plc_id not in self._plcs:
            raise ValueError(f"PLC '{plc_id}' не найден")
        return await self._plcs[plc_id].request(command)

    def get_latest_data(self, plc_id: str):
        worker = self._plcs.get(plc_id)
        return worker.latest_data if worker else {}

    async def shutdown(self):
        for worker in self._plcs.values():
            await worker.stop()
