from PyQt6.QtCore import QThread, pyqtSignal
from opcua import Client, ua

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
    ua.NodeId(ua.ObjectIds.Enumeration): "Enumeration"
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
            endpoint = self.endpoint.strip()
            if not endpoint.startswith("opc.tcp://"):
                endpoint = "opc.tcp://" + endpoint

            client = Client(endpoint)
            client.connect()
            self.log.emit(f"🔗 Connected to {endpoint}")

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
            nodeid = node.nodeid.to_string()  # ← КОРРЕКТНЫЙ NodeId
            cls = node.get_node_class().name

            node_dict["browse_name"] = name
            node_dict["node_id"] = nodeid
            node_dict["node_class"] = cls
            node_dict["children"] = {}

            if cls == "Variable":
                try:
                    dt_node = node.get_data_type()
                    node_dict["data_type"] = DATA_TYPE_MAP.get(dt_node, str(dt_node))
                    node_dict["data_type_nodeid"] = dt_node.to_string()
                    node_dict["is_enumeration"] = dt_node == ua.NodeId(ua.ObjectIds.Enumeration)
                except Exception:
                    node_dict["data_type"] = "Unknown"
                    node_dict["data_type_nodeid"] = ""
                    node_dict["is_enumeration"] = False

                try:
                    ua_access = node.get_user_access_level()
                    node_dict["access_level"] = "RW" if ua_access & ua.AccessLevel.CurrentWrite else "RO"
                except Exception:
                    node_dict["access_level"] = "Unknown"

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
