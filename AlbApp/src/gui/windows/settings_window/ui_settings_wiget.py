from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QComboBox, QGroupBox,
                             QFormLayout, QTextEdit, QPushButton, QHBoxLayout, QTabWidget,
                             QSpinBox, QLineEdit, QCheckBox, QMessageBox)
from PyQt6.QtCore import Qt
import json
from gui.windows.settings_window.tab_wigets.ui_protocol_manager import ProtocolManagerWidget
from gui.windows.settings_window.F_parameters import FWindow

class SettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        page_layout = QVBoxLayout(self)

        # Создаём вкладки
        self.tabs = QTabWidget()
        
        # Вкладка 1: Протокол и конфигурация
        self.protocol_widget = ProtocolManagerWidget()
        tab1 = self.protocol_widget
        
    
        # Вкладка 2: Логи подключений
        self.f_parameters_wiget = FWindow()
        tab2 = self.f_parameters_wiget
        
        
        # Вкладка 3: Редактирование конфигурации
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)
        tab3_layout.addStretch()
        
        # Добавляем вкладки
        self.tabs.addTab(tab1, "🔧 Протоколы и устройства")
        self.tabs.addTab(tab2, "📋 Параметры стенда")
        # self.tabs.addTab(tab3, "✏️ Редактирование")
        
        page_layout.addWidget(self.tabs)
    
    
            
 
   
        
  
        

