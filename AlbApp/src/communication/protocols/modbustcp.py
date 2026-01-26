import asyncio
from PyQt6.QtCore import QObject, pyqtSignal
from pymodbus.client import AsyncModbusTcpClient

class AsyncModbusWorker(QObject):
    # Сигнал для передачи данных в UI (список значений)
    data_received = pyqtSignal(list)
    # Сигнал для передачи ошибок
    error_occurred = pyqtSignal(str)

    def __init__(self, host="127.0.0.1", port=502):
        super().__init__()
        self.host = host
        self.port = port
        self._running = True

    async def run(self):
        client = AsyncModbusTcpClient(self.host, port=self.port)
        await client.connect()
        
        while self._running:
            try:
                if client.connected:
                    # Читаем 10 регистров
                    result = await client.read_holding_registers(address=0, count=10, slave=1)
                    if not result.isError():
                        self.data_received.emit(result.registers)
                    else:
                        self.error_occurred.emit("Ошибка чтения Modbus")
                else:
                    await client.connect()
            except Exception as e:
                self.error_occurred.emit(str(e))
            
            await asyncio.sleep(1) # Интервал опроса
            
        client.close()

    def stop(self):
        self._running = False
