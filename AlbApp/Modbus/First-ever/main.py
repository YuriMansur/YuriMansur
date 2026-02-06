# main.py
import sys
import asyncio
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

from plc_manager import PLCManager
from gui import MainWindow

# Сбор
def main():

#🔴 НЕОБХОДИМЫЕ ШАГИ (в строгом порядке):
    # 1. Cоздать Qt-приложение
    app = QApplication(sys.argv)

    # 2. Cоздать QEventLoop а адаптер Qt ↔ asynci
    loop = QEventLoop(app)

    # 3. Зарегистрировать QEventLoop в asyncioQEventLoop
    asyncio.set_event_loop(loop)

    # 4. Создать синхронные объекты:
    manager = PLCManager()
    window = MainWindow(manager)
    window.show()

    # 5. Добавить async-задачи
    loop.create_task(manager.start_all())

    # 6. Запустить loop
    with loop: loop.run_forever()


if __name__ == "__main__":
    main()
