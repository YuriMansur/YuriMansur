# protocol_manager.py
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from modbus_tcp import AsyncModbusPoller
from other_classes.config_manager import ConfigManager

class ProtocolManager(QObject):
    data_received = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.pollers = {}

    def create_pollers(self):
        cfg = self.config.load("poller_config.json")
        devices = cfg.get("devices", {})

        for device_id, device_cfg in devices.items():
            poller = AsyncModbusPoller(device_id, device_cfg)
            thread = QThread()

            poller.moveToThread(thread)

            thread.started.connect(poller.start)
            poller.data_received.connect(self.data_received)

            thread.finished.connect(poller.deleteLater)
            thread.finished.connect(thread.deleteLater)

            thread.start()
            self.pollers[device_id] = (poller, thread)

    def destroy_all(self):
        for poller, thread in self.pollers.values():
            poller.shutdown()
            thread.quit()
            thread.wait()

        self.pollers.clear()
