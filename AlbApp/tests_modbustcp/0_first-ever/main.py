# main.py
import sys
import asyncio
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop
from plc_manager import PLCManager
from gui import MainWindow   

async def start_workers(manager: PLCManager):
    # добавляем PLC после запуска event loop
    await manager.add_plc("PLC1")
    await manager.add_plc("PLC2")

def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    manager = PLCManager()
    window = MainWindow(manager)
    window.show()

    # запускаем worker после старта event loop
    asyncio.ensure_future(start_workers(manager))

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
