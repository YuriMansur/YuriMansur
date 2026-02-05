from PyQt6.QtCore import QThread, pyqtSignal
from opcua import Client, ua

class ScanWorker(QThread):
    log = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(dict)   # ⬅ возвращаем данные
    progress_value = pyqtSignal(int)

    def __init__(self, endpoint, node_classes=None):
        super().__init__()
        self.endpoint = endpoint
        self.node_classes = node_classes or []

    def run(self):
        try:
            client = Client(self.endpoint)
            client.connect()
            self.log.emit("🔗 Connected")

            objects = client.get_objects_node()
            result = {}

            count = 0

            def walk(node, out):
                nonlocal count
                for child in node.get_children():
                    try:
                        cls = child.get_node_class()
                        if self.node_classes and cls not in self.node_classes:
                            continue

                        name = child.get_browse_name().Name
                        node_id = str(child.nodeid)

                        out[name] = {
                            "node_id": node_id,
                            "node_class": cls.name
                        }

                        count += 1
                        self.progress_value.emit(count)

                        walk(child, out[name])

                    except Exception:
                        continue

            walk(objects, result)
            client.disconnect()

            self.finished.emit({"Objects": result})
            self.log.emit("✅ Scan finished")

        except Exception as e:
            self.error.emit(str(e))
