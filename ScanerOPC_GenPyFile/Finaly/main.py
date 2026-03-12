import sys
import logging
from PyQt6.QtWidgets import QApplication
from gui import OpcUaScanner
from PyQt6.QtGui import QPixmap, QIcon

logging.getLogger("asyncua").setLevel(logging.CRITICAL)



if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = OpcUaScanner()
    win.show()
    sys.exit(app.exec())
