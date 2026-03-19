import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))           # src/
sys.path.insert(0, str(Path(__file__).parent.parent))    # AlbApp/

from PyQt6.QtWidgets import QApplication
from gui.windows.main_window import MainWindow
from protocol_backend.server_manager import ServerManager
from database.influx_logger import InfluxLogger


class UiApp(MainWindow):
    def __init__(self):
        super().__init__()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    manager    = ServerManager(parent=app)
    db_logger  = InfluxLogger(parent=app)
    app.aboutToQuit.connect(manager.stop)
    app.aboutToQuit.connect(db_logger.close)

    window = UiApp()
    window.showMaximized()

    sys.exit(app.exec())
