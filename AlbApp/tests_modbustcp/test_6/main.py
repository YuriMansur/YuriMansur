# main.py
import sys
import asyncio
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop
from gui import MainWindow
from plc_manager import PLCManager

async def start_plcs(manager: PLCManager):
    await manager.add_plc(
        "PLC1", host="192.168.6.199", device_id=1,
        polls=[
            {"name": "holding_0_10", "type": "holding", "address": 0, "count": 10, "interval": 2.0},
            {"name": "holding_100_5", "type": "holding", "address": 100, "count": 5, "interval": 5.0},
        ]
    )
    await manager.add_plc(
        "PLC2", host="192.168.1.101", device_id=2,
        polls=[
            {"name": "holding_0_10", "type": "holding", "address": 0, "count": 10, "interval": 3.0},
        ]
    )

def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    manager = PLCManager()
    window = MainWindow(manager)
    window.show()

    asyncio.ensure_future(start_plcs(manager))

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
