import sys
import asyncio
from PyQt6.QtWidgets import QApplication
from main_window import MainWindow
from PyQt6.QtWidgets import QApplication

class UiApp(MainWindow):
    def __init__(self):              
        super().__init__()

class CommunicationProtocol:
    def __init__(self):
        pass
    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UiApp()
    window.showMaximized()
    sys.exit(app.exec())
