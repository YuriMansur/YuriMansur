from PyQt6.QtCore import QThread, pyqtSignal
from opcua import Client, ua

# Словарь соответствия стандартных DataType NodeId → читаемое имя
DATA_TYPE_MAP = {
    ua.NodeId(ua.ObjectIds.Boolean): "Boolean",
    ua.NodeId(ua.ObjectIds.SByte): "SByte",
    ua.NodeId(ua.ObjectIds.Byte): "Byte",
    ua.NodeId(ua.ObjectIds.Int16): "Int16",
    ua.NodeId(ua.ObjectIds.UInt16): "UInt16",
    ua.NodeId(ua.ObjectIds.Int32): "Int32",
    ua.NodeId(ua.ObjectIds.UInt32): "UInt32",
    ua.NodeId(ua.ObjectIds.Int64): "Int64",
    ua.NodeId(ua.ObjectIds.UInt64): "UInt64",
    ua.NodeId(ua.ObjectIds.Float): "Float",
    ua.NodeId(ua.ObjectIds.Double): "Double",
    ua.NodeId(ua.ObjectIds.String): "String",
}

class ScanWorker(QThread):
    log = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(dict)
    progress_value = pyqtSignal(int)

    def __init__(self, endpoint: str):
        super().__init__()
        self.endpoint = endpoint

    def run(self):
        try:
            client = Client(self.endpoint)
            client.connect()
            self.log.emit(f"🔗 Connected to {self.endpoint}")

            root = client.get_root_node()
            self.scanned_nodes = 0
            self.total_nodes = 0
            self._count_nodes(root)
            self.log.emit(f"ℹ Total nodes to scan: {self.total_nodes}")

            result = self._walk(root)
            client.disconnect()
            self.finished.emit(result)
            self.log.emit("✅ Scan finished")
        except Exception as e:
            self.error.emit(str(e))

    def _count_nodes(self, node):
        try:
            children = node.get_children()
        except Exception:
            return 0
        count = 1
        for ch in children:
            count += self._count_nodes(ch)
        self.total_nodes += count
        return count

    def _walk(self, node):
        node_dict = {}
        try:
            name = node.get_browse_name().Name
            nodeid = str(node.nodeid)
            cls_obj = node.get_node_class()
            cls = cls_obj.name

            node_dict["node_id"] = nodeid
            node_dict["node_class"] = cls
            node_dict["browse_name"] = name
            node_dict["children"] = {}

            data_type_name = None
            value = None

            if cls == "Variable":
                # Получаем DataType
                try:
                    dt_node = node.get_data_type()
                    # Пытаемся найти читаемое имя по NodeId
                    data_type_name = DATA_TYPE_MAP.get(dt_node, str(dt_node))
                except Exception:
                    data_type_name = "Unknown"

                # Получаем значение
                try:
                    value = node.get_value()
                except Exception:
                    value = None

                node_dict["data_type"] = data_type_name
                node_dict["value"] = value

            # Обход детей
            try:
                children = node.get_children()
            except Exception:
                children = []

            for child in children:
                child_data = self._walk(child)
                node_dict["children"][child_data["browse_name"]] = child_data

            self.scanned_nodes += 1
            percent = int((self.scanned_nodes / max(1, self.total_nodes)) * 100)
            self.progress_value.emit(percent)

        except Exception:
            pass

        return node_dict
