"""
run_opcua_gui.py — точка входа приложения.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from unified_backend_package.server_manager import ServerManager
from unified_backend_package.example_opcua_backend_gui import ExampleWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    manager = ServerManager()
    win = ExampleWindow()

    manager.bind_window(win)
    app.aboutToQuit.connect(manager.stop)

    win.show()
    win.raise_()
    win.activateWindow()

    try:
        import ctypes
        ctypes.windll.user32.SetForegroundWindow(int(win.winId()))
    except Exception:
        pass

    QTimer.singleShot(0, manager.start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
