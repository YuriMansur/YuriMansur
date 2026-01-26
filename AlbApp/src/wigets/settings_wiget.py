from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QComboBox, QGroupBox, 
                             QFormLayout, QTextEdit, QPushButton, QHBoxLayout, QTabWidget,
                             QSpinBox, QLineEdit, QCheckBox, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
import json

class SettingsWidget(QWidget):
    protocol_changed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        page3_layout = QVBoxLayout(self)

        # Создаём вкладки
        self.tabs = QTabWidget()
        
        # Вкладка 1: Протокол и конфигурация
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        
        # Группа выбора протокола
        protocol_group = QGroupBox("Протокол связи")
        protocol_layout = QFormLayout()
        
        protocol_label = QLabel("Выберите протокол:")
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["Modbus TCP", "OPC UA"])
        self.protocol_combo.currentTextChanged.connect(self.protocol_changed.emit)
        
        protocol_layout.addRow(protocol_label, self.protocol_combo)
        protocol_group.setLayout(protocol_layout)
        
        tab1_layout.addWidget(protocol_group)
        
        # Группа информации о конфигурации
        config_group = QGroupBox("Информация о конфигурации")
        config_layout = QVBoxLayout()
        
        # Текстовое поле для отображения конфигурации
        self.config_text = QTextEdit()
        self.config_text.setReadOnly(True)
        self.config_text.setMaximumHeight(200)
        self.config_text.setStyleSheet("""
            QTextEdit {
                background-color: #ecf0f1;
                color: #2c3e50;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Courier New', monospace;
                font-size: 10px;
            }
        """)
        config_layout.addWidget(self.config_text)
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        self.refresh_config_btn = QPushButton("🔄 Обновить конфигурацию")
        self.refresh_config_btn.clicked.connect(self.update_config_display)
        buttons_layout.addWidget(self.refresh_config_btn)
        buttons_layout.addStretch()
        
        config_layout.addLayout(buttons_layout)
        config_group.setLayout(config_layout)
        
        tab1_layout.addWidget(config_group)
        tab1_layout.addStretch()
        
        # Вкладка 2: Логи подключений
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        
        logs_group = QGroupBox("Логи подключений")
        logs_layout = QVBoxLayout()
        
        # Текстовое поле для отображения логов
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #00ff00;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Courier New', monospace;
                font-size: 9px;
            }
        """)
        logs_layout.addWidget(self.logs_text)
        
        # Кнопки управления логами
        log_buttons_layout = QHBoxLayout()
        self.refresh_logs_btn = QPushButton("🔄 Обновить логи")
        self.refresh_logs_btn.clicked.connect(self.update_logs_display)
        self.clear_logs_btn = QPushButton("🗑️ Очистить логи")
        self.clear_logs_btn.clicked.connect(self.clear_logs)
        
        log_buttons_layout.addWidget(self.refresh_logs_btn)
        log_buttons_layout.addWidget(self.clear_logs_btn)
        log_buttons_layout.addStretch()
        
        logs_layout.addLayout(log_buttons_layout)
        logs_group.setLayout(logs_layout)
        
        tab2_layout.addWidget(logs_group)
        
        # Вкладка 3: Редактирование конфигурации
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)
        
        edit_group = QGroupBox("Редактирование параметров")
        edit_layout = QFormLayout()
        
        # Modbus TCP параметры
        modbus_label = QLabel("Modbus TCP")
        modbus_label.setStyleSheet("font-weight: bold; color: #3498db;")
        edit_layout.addRow(modbus_label, QLabel())
        
        self.modbus_host = QLineEdit()
        self.modbus_host.setText("127.0.0.1")
        edit_layout.addRow("  Host:", self.modbus_host)
        
        self.modbus_port = QSpinBox()
        self.modbus_port.setRange(1, 65535)
        self.modbus_port.setValue(502)
        edit_layout.addRow("  Port:", self.modbus_port)
        
        self.modbus_timeout = QSpinBox()
        self.modbus_timeout.setRange(1, 60)
        self.modbus_timeout.setValue(5)
        edit_layout.addRow("  Timeout (сек):", self.modbus_timeout)
        
        self.modbus_retries = QSpinBox()
        self.modbus_retries.setRange(0, 10)
        self.modbus_retries.setValue(3)
        edit_layout.addRow("  Retries:", self.modbus_retries)
        
        self.modbus_unit_id = QSpinBox()
        self.modbus_unit_id.setRange(0, 255)
        self.modbus_unit_id.setValue(1)
        edit_layout.addRow("  Unit ID:", self.modbus_unit_id)
        
        self.modbus_enabled = QCheckBox("Включен")
        self.modbus_enabled.setChecked(True)
        edit_layout.addRow("  ", self.modbus_enabled)
        
        # OPC UA параметры
        opcua_label = QLabel("OPC UA")
        opcua_label.setStyleSheet("font-weight: bold; color: #e74c3c; margin-top: 15px;")
        edit_layout.addRow(opcua_label, QLabel())
        
        self.opcua_endpoint = QLineEdit()
        self.opcua_endpoint.setText("opc.tcp://127.0.0.1:4840")
        edit_layout.addRow("  Endpoint URL:", self.opcua_endpoint)
        
        self.opcua_timeout = QSpinBox()
        self.opcua_timeout.setRange(1, 60)
        self.opcua_timeout.setValue(5)
        edit_layout.addRow("  Timeout (сек):", self.opcua_timeout)
        
        self.opcua_retries = QSpinBox()
        self.opcua_retries.setRange(0, 10)
        self.opcua_retries.setValue(3)
        edit_layout.addRow("  Retries:", self.opcua_retries)
        
        self.opcua_enabled = QCheckBox("Включен")
        self.opcua_enabled.setChecked(False)
        edit_layout.addRow("  ", self.opcua_enabled)
        
        edit_group.setLayout(edit_layout)
        tab3_layout.addWidget(edit_group)
        
        # Кнопки сохранения
        save_buttons_layout = QHBoxLayout()
        self.save_config_btn = QPushButton("💾 Сохранить конфигурацию")
        self.save_config_btn.clicked.connect(self.save_configuration)
        self.reload_config_btn = QPushButton("🔄 Загрузить из файла")
        self.reload_config_btn.clicked.connect(self.reload_configuration)
        
        save_buttons_layout.addWidget(self.save_config_btn)
        save_buttons_layout.addWidget(self.reload_config_btn)
        save_buttons_layout.addStretch()
        
        tab3_layout.addLayout(save_buttons_layout)
        tab3_layout.addStretch()
        
        # Добавляем вкладки
        self.tabs.addTab(tab1, "🔧 Конфигурация")
        self.tabs.addTab(tab2, "📋 Логи подключений")
        self.tabs.addTab(tab3, "✏️ Редактирование")
        
        page3_layout.addWidget(self.tabs)
    
    def init_from_config(self):
        """Инициализировать поля из конфигурации (вызывается из MainWindow)"""
        try:
            from communication.protocol_manager import get_protocol_manager
            
            # Получаем менеджер протоколов
            protocol_manager = get_protocol_manager()
            
            # Загружаем конфигурацию
            config = protocol_manager.config.config
            
            # Обновляем поля ввода
            modbus = config.get("modbus_tcp", {})
            self.modbus_host.setText(modbus.get("host", "127.0.0.1"))
            self.modbus_port.setValue(modbus.get("port", 502))
            self.modbus_timeout.setValue(modbus.get("timeout", 5))
            self.modbus_retries.setValue(modbus.get("retries", 3))
            self.modbus_unit_id.setValue(modbus.get("unit_id", 1))
            self.modbus_enabled.setChecked(modbus.get("enabled", True))
            
            opcua = config.get("opcua", {})
            self.opcua_endpoint.setText(opcua.get("endpoint_url", "opc.tcp://127.0.0.1:4840"))
            self.opcua_timeout.setValue(opcua.get("timeout", 5))
            self.opcua_retries.setValue(opcua.get("retries", 3))
            self.opcua_enabled.setChecked(opcua.get("enabled", False))
            
            # Обновляем отображение конфигурации
            self.update_config_display(config)
            
        except Exception as e:
            print(f"Ошибка при инициализации конфигурации: {e}")
    
    def get_selected_protocol(self):
        """Получить выбранный протокол"""
        return self.protocol_combo.currentText()
    
    def update_logs_display(self):
        """Обновить отображение логов подключений"""
        try:
            from communication.connection_logger import get_connection_logger
            logger = get_connection_logger()
            logs_content = logger.read_recent_logs(100)
            self.logs_text.setText(logs_content)
        except Exception as e:
            self.logs_text.setText(f"Ошибка при загрузке логов: {e}")
    
    def clear_logs(self):
        """Очистить логи"""
        try:
            from communication.connection_logger import get_connection_logger
            logger = get_connection_logger()
            logger.clear_logs()
            self.update_logs_display()
        except Exception as e:
            self.logs_text.setText(f"Ошибка при очистке логов: {e}")
    
    def save_configuration(self):
        """Сохранить конфигурацию в файл"""
        try:
            from communication.protocol_manager import get_protocol_manager
            
            # Получаем конфигурацию из полей ввода
            config_data = {
                "modbus_tcp": {
                    "host": self.modbus_host.text(),
                    "port": self.modbus_port.value(),
                    "timeout": self.modbus_timeout.value(),
                    "retries": self.modbus_retries.value(),
                    "unit_id": self.modbus_unit_id.value(),
                    "enabled": self.modbus_enabled.isChecked(),
                    "description": "Modbus TCP конфигурация"
                },
                "opcua": {
                    "endpoint_url": self.opcua_endpoint.text(),
                    "timeout": self.opcua_timeout.value(),
                    "retries": self.opcua_retries.value(),
                    "enabled": self.opcua_enabled.isChecked(),
                    "description": "OPC UA конфигурация",
                    "username": None,
                    "password": None
                }
            }
            
            # Получаем или создаём менеджер протоколов
            protocol_manager = get_protocol_manager()
            result = protocol_manager.config.save_full_config(config_data)
            
            if result:
                QMessageBox.information(self, "Успех", "Конфигурация успешно сохранена!")
                self.update_config_display(config_data)
            else:
                QMessageBox.warning(self, "Ошибка", "Ошибка при сохранении конфигурации")
                
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при сохранении: {e}")
    
    def reload_configuration(self):
        """Загрузить конфигурацию из файла"""
        try:
            from communication.protocol_manager import get_protocol_manager
            
            # Получаем или создаём менеджер протоколов
            protocol_manager = get_protocol_manager()
            
            if protocol_manager.config.reload_config():
                config = protocol_manager.config.config
                
                # Обновляем поля ввода
                modbus = config.get("modbus_tcp", {})
                self.modbus_host.setText(modbus.get("host", "127.0.0.1"))
                self.modbus_port.setValue(modbus.get("port", 502))
                self.modbus_timeout.setValue(modbus.get("timeout", 5))
                self.modbus_retries.setValue(modbus.get("retries", 3))
                self.modbus_unit_id.setValue(modbus.get("unit_id", 1))
                self.modbus_enabled.setChecked(modbus.get("enabled", True))
                
                opcua = config.get("opcua", {})
                self.opcua_endpoint.setText(opcua.get("endpoint_url", "opc.tcp://127.0.0.1:4840"))
                self.opcua_timeout.setValue(opcua.get("timeout", 5))
                self.opcua_retries.setValue(opcua.get("retries", 3))
                self.opcua_enabled.setChecked(opcua.get("enabled", False))
                
                self.update_config_display(config)
                QMessageBox.information(self, "Успех", "Конфигурация загружена!")
            else:
                QMessageBox.warning(self, "Ошибка", "Ошибка при загрузке конфигурации")
                
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при загрузке: {e}")
    
    def set_protocol_manager(self, protocol_manager):
        """Установить менеджер протоколов для взаимодействия с конфигурацией"""
        self._protocol_manager = protocol_manager
    
    def update_config_display(self, config_data: dict = None):
        """
        Обновить отображение конфигурации
        
        Args:
            config_data: Словарь с конфигурацией
        """
        # Проверяем, что config_data является словарём
        if config_data is None or not isinstance(config_data, dict):
            config_data = self.get_default_config()
        
        # Форматируем конфигурацию для отображения
        protocol = self.get_selected_protocol()
        
        config_text = f"""
════════════════════════════════════════════════════════════════════════════════
                        ТЕКУЩАЯ КОНФИГУРАЦИЯ
════════════════════════════════════════════════════════════════════════════════

ВЫБРАННЫЙ ПРОТОКОЛ: {protocol}

"""
        
        if protocol == "Modbus TCP":
            modbus_config = config_data.get("modbus_tcp", {})
            config_text += f"""ПАРАМЕТРЫ MODBUS TCP:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • Host:           {modbus_config.get('host', 'N/A')}
  • Port:           {modbus_config.get('port', 'N/A')}
  • Unit ID:        {modbus_config.get('unit_id', 'N/A')}
  • Timeout:        {modbus_config.get('timeout', 'N/A')} сек
  • Retries:        {modbus_config.get('retries', 'N/A')}
  • Статус:         {'✓ Включен' if modbus_config.get('enabled', False) else '✗ Отключен'}
"""
        
        elif protocol == "OPC UA":
            opcua_config = config_data.get("opcua", {})
            config_text += f"""ПАРАМЕТРЫ OPC UA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • Endpoint URL:   {opcua_config.get('endpoint_url', 'N/A')}
  • Security:       {opcua_config.get('security_policy', 'N/A')}
  • Timeout:        {opcua_config.get('timeout', 'N/A')} сек
  • Retries:        {opcua_config.get('retries', 'N/A')}
  • Username:       {opcua_config.get('username', 'Anonymous')}
  • Статус:         {'✓ Включен' if opcua_config.get('enabled', False) else '✗ Отключен'}
"""
        
        # Добавляем информацию о переподключении
        reconnect_config = config_data.get("reconnection", {})
        config_text += f"""
ПЕРЕПОДКЛЮЧЕНИЕ:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • Автоматическое: {'✓ Да' if reconnect_config.get('auto_reconnect', False) else '✗ Нет'}
  • Интервал:       {reconnect_config.get('reconnect_interval', 'N/A')} сек
  • Макс попыток:   {reconnect_config.get('max_reconnect_attempts', 'N/A')}

════════════════════════════════════════════════════════════════════════════════
"""
        
        self.config_text.setText(config_text)
    
    def get_default_config(self) -> dict:
        """Получить конфигурацию по умолчанию"""
        return {
            "modbus_tcp": {
                "host": "127.0.0.1",
                "port": 502,
                "timeout": 5,
                "retries": 3,
                "unit_id": 1,
                "enabled": True
            },
            "opcua": {
                "endpoint_url": "opc.tcp://127.0.0.1:4840",
                "security_policy": "None",
                "timeout": 5,
                "retries": 3,
                "username": "Anonymous",
                "enabled": False
            },
            "reconnection": {
                "auto_reconnect": True,
                "reconnect_interval": 5,
                "max_reconnect_attempts": 10
            }
        }
    
    def set_config(self, config_data: dict):
        """
        Установить конфигурацию для отображения
        
        Args:
            config_data: Словарь с конфигурацией
        """
        self.update_config_display(config_data)