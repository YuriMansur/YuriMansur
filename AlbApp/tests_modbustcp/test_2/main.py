# main.py
import sys
import asyncio
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop
from gui import MainWindow
from plc_manager import PLCManager

async def start_plcs(manager: PLCManager):
    # пример нескольких PLC
    await manager.add_plc("PLC1", host="192.168.6.199", port=502, slave=1)
    await manager.add_plc("PLC2", host="192.168.1.101", port=502, slave=1)

def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    manager = PLCManager()
    window = MainWindow(manager)
    window.show()

    # запускаем регистратор PLC после старта loop
    asyncio.ensure_future(start_plcs(manager))

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
