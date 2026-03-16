"""
Пример использования AsyncOpcUaWorker (чистый asyncio, без Qt)
===============================================================

Демонстрирует:
  1. Подключение / отключение
  2. Чтение тега
  3. Запись тега
  4. Подписка на теги (push)
  5. Пакетное чтение / запись
  6. Watchdog
  7. Статистика

Запуск:
    python -m unified_backend_package.example_opcua_backend
"""

import sys
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unified_backend_package.backend.worker.opcua.opcua_worker import AsyncOpcUaWorker


ENDPOINT   = "opc.tcp://192.168.6.6:4840"
NODE_READ  = "ns=2;s=Temperature"
NODE_WRITE = "ns=2;s=Start"
NODE_SUB   = "ns=2;s=Pressure"


async def main():

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Создание и подключение
    # ─────────────────────────────────────────────────────────────────────────

    def on_data_changed(node_id: str, value):
        """Callback — вызывается при каждом изменении подписанного тега."""
        print(f"  push {node_id} = {value}")

    worker = AsyncOpcUaWorker(
        endpoint=ENDPOINT,
        namespace=2,
        timeout=10.0,
        on_data_changed=on_data_changed,
    )

    print(f"Подключение к {ENDPOINT}...")
    ok = await worker.connect()
    if not ok:
        print("Не удалось подключиться")
        return
    print("Подключен\n")

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Чтение тега
    # ─────────────────────────────────────────────────────────────────────────

    value = await worker.read_node(NODE_READ)
    print(f"read  {NODE_READ} = {value}")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Запись тега
    # ─────────────────────────────────────────────────────────────────────────

    await worker.write_node(NODE_WRITE, 1)
    print(f"write {NODE_WRITE} = 1")

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Пакетное чтение / запись
    # ─────────────────────────────────────────────────────────────────────────

    results = await worker.read_multiple_nodes([NODE_READ, NODE_WRITE])
    print(f"batch_read  → {results}")

    results = await worker.write_multiple_nodes({NODE_WRITE: 0, "ns=2;s=Reset": 1})
    print(f"batch_write → {results}")

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Подписка на теги (push)
    #    on_data_changed будет вызываться при каждом изменении значения на сервере
    # ─────────────────────────────────────────────────────────────────────────

    await worker.subscribe_tag(NODE_SUB, tag_name="Pressure")
    print(f"\nПодписка на {NODE_SUB} активна — ждём 5 секунд изменений...")
    await asyncio.sleep(5)

    await worker.unsubscribe_tag(NODE_SUB)
    print("Отписались")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Watchdog — фоновая задача проверки живости соединения
    #    При обрыве watchdog останавливается и запускает auto-reconnect
    #    (если auto_reconnect=True при создании воркера).
    # ─────────────────────────────────────────────────────────────────────────

    await worker.start_watchdog(interval=5.0)
    print("\nWatchdog запущен")

    await asyncio.sleep(2)

    await worker.stop_watchdog()
    print("Watchdog остановлен")

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Статистика
    # ─────────────────────────────────────────────────────────────────────────

    stats = worker.get_stats()
    print("\n--- Статистика ---")
    for key, val in stats.items():
        print(f"  {key}: {val}")

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Отключение
    # ─────────────────────────────────────────────────────────────────────────

    await worker.disconnect()
    print("\nОтключен")


if __name__ == "__main__":
    asyncio.run(main())
