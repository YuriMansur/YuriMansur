from PyQt6.QtCore import QThread, pyqtSignal
from scanner import scan
from opcua import ua

class ScanWorker(QThread):
    log = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    progress_value = pyqtSignal(int)

    def __init__(self, endpoint, output_file, node_classes=None, namespaces=None):
        super().__init__()
        self.endpoint = endpoint
        self.output_file = output_file
        self.node_classes = node_classes
        self.namespaces = namespaces

    def run(self):
        try:
            # Простейший прогрессбар: просто логируем каждый найденный тег
            def progress_cb(msg):
                self.log.emit(msg)

            scan(
                self.endpoint,
                self.output_file,
                progress_cb=progress_cb,
                node_classes=self.node_classes,
                namespaces=self.namespaces
            )
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
