import asyncio
from PyQt6.QtCore import QThread, pyqtSignal
from asyncua import Client, ua

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
    ua.NodeId(ua.ObjectIds.Enumeration): "Enumeration",
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
        self.skipped_nodes = 0
        self._stop = False
        self._loop = None

    def stop(self):
        self._stop = True

    # ── QThread entry point ──────────────────────────────────────────────────

    def run(self):
        self._loop = asyncio.new_event_loop()
        self._loop.set_exception_handler(lambda loop, ctx: None)  # suppress background task tracebacks
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_run())
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")
        finally:
            pending = asyncio.all_tasks(self._loop)
            if pending:
                for t in pending:
                    t.cancel()
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()
            self._loop = None

    # ── Main async coroutine ─────────────────────────────────────────────────

    async def _async_run(self):
        endpoint = self.endpoint.strip()
        if not endpoint.startswith("opc.tcp://"):
            endpoint = "opc.tcp://" + endpoint

        scan_ok = False
        try:
            client = Client(url=endpoint, timeout=10)
            client.session_timeout = 3600000
            async with client:
                self.log.emit(f"🔗 Connected to {endpoint}")

                root = client.get_root_node()
                self.log.emit("🔍 Starting tree scan...")

                self._semaphore = asyncio.Semaphore(2)
                result = await self._walk(root)

                if self._stop:
                    self.log.emit(f"⛔ Scan stopped by user ({self.scanned_nodes} nodes scanned)")
                else:
                    scan_ok = True
                    self.finished.emit(result)
                    suffix = f", {self.skipped_nodes} skipped" if self.skipped_nodes else ""
                    self.log.emit(f"✅ Scan finished ({self.scanned_nodes} nodes{suffix})")

        except Exception as e:
            if not scan_ok:
                self.error.emit(f"Не удалось подключиться к {endpoint}\n{type(e).__name__}: {e}")

    # ── Async BFS tree walk ──────────────────────────────────────────────────

    async def _walk(self, root_node):
        root_dict = {}
        current_level = [(root_node, None)]  # (node, parent_children_dict)

        while current_level and not self._stop:
            next_level = []
            await asyncio.gather(
                *[self._process_node(n, p, next_level, root_dict) for n, p in current_level],
                return_exceptions=True,
            )
            current_level = next_level

        return root_dict

    async def _process_node(self, node, parent_children, next_level, root_dict):
        if self._stop:
            return
        async with self._semaphore:
            nodeid = node.nodeid.to_string()
            try:
                name = (await node.read_browse_name()).Name
            except Exception:
                name = nodeid

            try:
                cls = (await node.read_node_class()).name
            except Exception:
                cls = "Unknown"

            node_dict = {
                "browse_name": name,
                "node_id":     nodeid,
                "node_class":  cls,
                "children":    {},
            }

            if cls == "Variable":
                try:
                    dt_node = await node.read_data_type()
                    node_dict["data_type"]        = DATA_TYPE_MAP.get(dt_node, str(dt_node))
                    node_dict["data_type_nodeid"] = dt_node.to_string()
                    node_dict["is_enumeration"]   = dt_node == ua.NodeId(ua.ObjectIds.Enumeration)
                except Exception:
                    node_dict["data_type"]        = "Unknown"
                    node_dict["data_type_nodeid"] = ""
                    node_dict["is_enumeration"]   = False

                try:
                    ua_access = await node.read_user_access_level()
                    node_dict["access_level"] = "RW" if ua_access & ua.AccessLevelType.CurrentWrite else "RO"
                except Exception:
                    node_dict["access_level"] = "Unknown"

            if parent_children is None:
                root_dict.update(node_dict)
            else:
                parent_children[name] = node_dict

            if "|type|" not in nodeid:
                try:
                    children = await node.get_children()
                    for child in children:
                        next_level.append((child, node_dict["children"]))
                except Exception as e:
                    self.log.emit(f"   ⚠ Can't get children of {nodeid} — {type(e).__name__}: {e}")

            self.scanned_nodes += 1
            self.progress_value.emit(self.scanned_nodes)
            if self.scanned_nodes % 100 == 0:
                self.log.emit(
                    f"   ⏳ Scanned {self.scanned_nodes} nodes... "
                    f"(next level: {len(next_level)})"
                )
