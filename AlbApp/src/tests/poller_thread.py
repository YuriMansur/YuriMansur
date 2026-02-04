from PyQt6.QtCore import QThread
import asyncio
from modbus_poller import ModbusTCP


class ProtocolMnager():

    def __init__(self):
        super().__init__()
   

    def run(self):
        asyncio.run(self.poller.run())

    def stop(self):
        self.poller.stop()

    thread1 = QThread()

    