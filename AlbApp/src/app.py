import sys
from PyQt6.QtWidgets import QApplication
from gui.windows.main_window import MainWindow
from PyQt6.QtWidgets import QApplication
# from communication.control.comm_manager import ProtocolManager

class UiApp(MainWindow):
    def __init__(self):              
        super().__init__()
  
if __name__ == "__main__":
    app = QApplication(sys.argv)
    # manager = ProtocolManager()
    window = UiApp()
    window.showMaximized()
    sys.exit(app.exec())

