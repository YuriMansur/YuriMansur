import sys
import multiprocessing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))           # src/
sys.path.insert(0, str(Path(__file__).parent.parent))    # AlbApp/

from PyQt6.QtCore import QObject, QEvent, QPoint
from PyQt6.QtWidgets import QApplication, QComboBox
from gui.windows.main_window import MainWindow
from ipc_bridge import IpcBridge
from worker_process.main import worker_main


class _ComboPopupDownFilter(QObject):
    """Глобально: все выпадающие списки раскрываются только вниз.

    Qt по умолчанию может раскрыть popup вверх, если снизу мало места. Ловим
    показ popup-контейнера комбобокса и принудительно сдвигаем его под сам
    комбобокс.
    """
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            parent = obj.parent()
            if isinstance(parent, QComboBox):
                below = parent.mapToGlobal(QPoint(0, parent.height()))
                obj.move(obj.x(), below.y())
        return False


class UiApp(MainWindow):
    def __init__(self):
        super().__init__()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # нужно для Windows при сборке в exe

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Все выпадающие списки раскрываются только вниз
    _combo_down_filter = _ComboPopupDownFilter(app)
    app.installEventFilter(_combo_down_filter)

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

    def _shutdown():
        bridge.stop()
        worker.terminate()
        # не ждать фоновые feeder-потоки очередей — иначе процесс висит на выходе
        live_q.cancel_join_thread()
        cmd_q.cancel_join_thread()

    app.aboutToQuit.connect(_shutdown)

    window = UiApp()
    window.showMaximized()

    sys.exit(app.exec())
