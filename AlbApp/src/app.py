import sys
import multiprocessing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))           # src/
sys.path.insert(0, str(Path(__file__).parent.parent))    # AlbApp/

from PyQt6.QtWidgets import QApplication
from gui.windows.main_window import MainWindow
from ipc_bridge import IpcBridge
from worker_process.main import worker_main


class UiApp(MainWindow):
    def __init__(self):
        super().__init__()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # нужно для Windows при сборке в exe

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Очереди IPC между GUI-процессом и рабочим процессом
    live_q = multiprocessing.Queue()  # worker → GUI: live-данные и статус
    cmd_q  = multiprocessing.Queue()  # GUI → worker: команды записи тегов

    # Рабочий процесс: OPC UA + кольцевой буфер + InfluxDB (свой GIL)
    worker = multiprocessing.Process(
        target  = worker_main,
        args    = (live_q, cmd_q),
        daemon  = True,
        name    = "AlbWorker",
    )
    worker.start()

    # Мост: дренирует live_q → bus-сигналы; bus.cmd_* → cmd_q
    bridge = IpcBridge(live_q, cmd_q, parent=app)

    app.aboutToQuit.connect(worker.terminate)

    window = UiApp()
    window.showMaximized()

    sys.exit(app.exec())
