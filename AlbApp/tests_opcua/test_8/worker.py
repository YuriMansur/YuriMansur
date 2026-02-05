from PyQt6.QtCore import QThread, pyqtSignal
from opcua import Client, ua

# Стандартные NodeId → читаемое имя DataType
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
    ua.NodeId(ua.ObjectIds.Enumeration): "Enumeration"  # Enumeration через ObjectIds
}

class ScanWorker(QThread):
    log = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(dict)
    progress_value = pyqtSignal(int)

    def __init__(self, endpoint: str):
        super().__init__()
        self.endpoint = endpoint
        self.scanned_nodes = 0
        self.total_nodes = 0

    def run(self):
        try:
            client = Client(self.endpoint)
            client.connect()
            self.log.emit(f"🔗 Connected to {self.endpoint}")

            root = client.get_root_node()
            self.total_nodes = self._count_nodes(root)
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
            return 1
        count = 1
        for ch in children:
            count += self._count_nodes(ch)
        return count

    def _walk(self, node):
        node_dict = {}
        try:
            name = node.get_browse_name().Name
            nodeid = str(node.nodeid)
            cls = node.get_node_class().name

            node_dict["node_id"] = nodeid
            node_dict["browse_name"] = name
            node_dict["node_class"] = cls
            node_dict["children"] = {}

            data_type_name = None
            access = "Unknown"

            if cls == "Variable":
                try:
                    dt_node = node.get_data_type()
                    data_type_name = DATA_TYPE_MAP.get(dt_node, str(dt_node))
                except Exception:
                    data_type_name = "Unknown"

                try:
                    ua_access = node.get_user_access_level()
                    if ua_access & ua.AccessLevel.CurrentWrite:
                        access = "RW"
                    elif ua_access & ua.AccessLevel.CurrentRead:
                        access = "RO"
                    else:
                        access = "Unknown"
                except Exception:
                    access = "Unknown"

                node_dict["data_type"] = data_type_name
                node_dict["access_level"] = access

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
