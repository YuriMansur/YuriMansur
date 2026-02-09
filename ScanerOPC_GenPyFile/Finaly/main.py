import sys
from PyQt6.QtWidgets import QApplication
from gui import OpcUaScanner
from PyQt6.QtGui import QPixmap, QIcon



if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = OpcUaScanner()
    win.show()
    sys.exit(app.exec())
