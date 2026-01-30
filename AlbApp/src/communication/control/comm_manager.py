import os
import json
from PyQt6.QtCore import QObject, QThread, pyqtSignal
# from protocols.modbus.modbus_tcp import ModbusPoller
from other_classes.config_manager import ConfigManager

class ProtocolManager(QObject): 
    def __init__(self):
        super().__init__()
        self.config = ConfigManager()




    
    def create_poller(self):
        # self.poller = ModbusPoller()        # Создаём объект poller
        self.poller_thread = QThread()      # Создаём поток

        # Переносим poller в отдельный поток
        self.poller.moveToThread(self.poller_thread)

        # Корректное удаление при завершении потока
        self.poller_thread.finished.connect(self.poller.deleteLater)
        self.poller_thread.finished.connect(self.poller_thread.deleteLater)

        # Проброс сигналов poller в GUI
        self.poller.data_received.connect(self.on_data)
        self.poller.connection_status.connect(self.on_connection)

        # Стартуем потокщ
        self.poller_thread.start()


    def destroy_poller(self):
        if hasattr(self, "poller") and self.poller:
            self.poller.shutdown()      # Останавливаем таймер и закрываем Modbus
            self.poller_thread.quit()   # Сигнал потоку о завершении
            self.poller_thread.wait()   # Ждём завершения потока
            self.poller = None
            self.poller_thread = None
            
if __name__ == "__main__":
    app = QApplication(sys.argv)
    manager = ProtocolManager()
    window = UiApp()
    window.showMaximized()
    sys.exit(app.exec())