# gui_main.py
import sys
import logging
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QComboBox, QLineEdit,
    QSpinBox, QDoubleSpinBox, QCheckBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QMessageBox, QSplitter,
    QFormLayout, QGridLayout, QStatusBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QPalette, QColor
import pyqtgraph as pg
import numpy as np

from modbus_tcp import RealTimeData  # Импортируем ваш класс работы с Modbus


class SensorDisplayWidget(QWidget):
    """Виджет для отображения текущих значений датчиков"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QGridLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Стилизация
        value_font = QFont("Arial", 16, QFont.Weight.Bold)
        unit_font = QFont("Arial", 10)
        label_font = QFont("Arial", 10, QFont.Weight.Bold)
        
        # Момент кручения
        self.tension_label = QLabel("Момент кручения:")
        self.tension_label.setFont(label_font)
        self.tension_value = QLabel("0.00")
        self.tension_value.setFont(value_font)
        self.tension_value.setStyleSheet("color: blue;")
        self.tension_unit = QLabel("Н·м")
        self.tension_unit.setFont(unit_font)
        
        tension_layout = QHBoxLayout()
        tension_layout.addWidget(self.tension_value)
        tension_layout.addWidget(self.tension_unit)
        tension_layout.addStretch()
        
        # Угол поворота
        self.angle_label = QLabel("Угол поворота:")
        self.angle_label.setFont(label_font)
        self.angle_value = QLabel("0.00")
        self.angle_value.setFont(value_font)
        self.angle_value.setStyleSheet("color: green;")
        self.angle_unit = QLabel("°")
        self.angle_unit.setFont(unit_font)
        
        angle_layout = QHBoxLayout()
        angle_layout.addWidget(self.angle_value)
        angle_layout.addWidget(self.angle_unit)
        angle_layout.addStretch()
        
        # Скорость нарастания
        self.velocity_label = QLabel("Скорость нарастания:")
        self.velocity_label.setFont(label_font)
        self.velocity_value = QLabel("0.00")
        self.velocity_value.setFont(value_font)
        self.velocity_value.setStyleSheet("color: red;")
        self.velocity_unit = QLabel("Н·м/с")
        self.velocity_unit.setFont(unit_font)
        
        velocity_layout = QHBoxLayout()
        velocity_layout.addWidget(self.velocity_value)
        velocity_layout.addWidget(self.velocity_unit)
        velocity_layout.addStretch()
        
        # Статус соединения
        self.connection_label = QLabel("Статус Modbus:")
        self.connection_label.setFont(label_font)
        self.connection_status = QLabel("Нет соединения")
        self.connection_status.setFont(QFont("Arial", 10))
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        
        # Размещение в сетке
        layout.addWidget(self.tension_label, 0, 0)
        layout.addLayout(tension_layout, 0, 1)
        layout.addWidget(self.angle_label, 1, 0)
        layout.addLayout(angle_layout, 1, 1)
        layout.addWidget(self.velocity_label, 2, 0)
        layout.addLayout(velocity_layout, 2, 1)
        layout.addWidget(self.connection_label, 3, 0)
        layout.addWidget(self.connection_status, 3, 1)
        
        layout.setColumnStretch(1, 1)
        self.setLayout(layout)
        
    def update_values(self, tension: float, angle: float, velocity: float):
        """Обновление значений датчиков"""
        self.tension_value.setText(f"{tension:.2f}")
        self.angle_value.setText(f"{angle:.2f}")
        self.velocity_value.setText(f"{velocity:.2f}")
        
    def update_connection_status(self, connected: bool):
        """Обновление статуса соединения"""
        if connected:
            self.connection_status.setText("Соединение установлено")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.connection_status.setText("Нет соединения")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")


class ControlPanelWidget(QWidget):
    """Панель управления Modbus параметрами"""
    
    # Сигналы для отправки команд в Modbus
    control_command = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Группа управления соединением
        connection_group = QGroupBox("Соединение Modbus")
        connection_layout = QFormLayout()
        
        self.host_edit = QLineEdit("127.0.0.1")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(502)
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(0.1, 10.0)
        self.timeout_spin.setValue(1.0)
        self.timeout_spin.setSuffix(" с")
        
        self.connect_btn = QPushButton("Подключиться")
        self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.disconnect_btn = QPushButton("Отключиться")
        self.disconnect_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.disconnect_btn.setEnabled(False)
        
        connection_layout.addRow("Хост:", self.host_edit)
        connection_layout.addRow("Порт:", self.port_spin)
        connection_layout.addRow("Таймаут:", self.timeout_spin)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.connect_btn)
        btn_layout.addWidget(self.disconnect_btn)
        connection_layout.addRow("", btn_layout)
        
        connection_group.setLayout(connection_layout)
        
        # Группа управления ПИД-регулятором
        pid_group = QGroupBox("ПИД-регулятор")
        pid_layout = QFormLayout()
        
        self.kp_spin = QDoubleSpinBox()
        self.kp_spin.setRange(0.0, 100.0)
        self.kp_spin.setValue(1.0)
        self.kp_spin.setDecimals(4)
        
        self.ki_spin = QDoubleSpinBox()
        self.ki_spin.setRange(0.0, 100.0)
        self.ki_spin.setValue(0.1)
        self.ki_spin.setDecimals(4)
        
        self.kd_spin = QDoubleSpinBox()
        self.kd_spin.setRange(0.0, 100.0)
        self.kd_spin.setValue(0.01)
        self.kd_spin.setDecimals(4)
        
        self.pid_apply_btn = QPushButton("Применить коэффициенты")
        self.pid_apply_btn.setStyleSheet("background-color: #2196F3; color: white;")
        
        pid_layout.addRow("Kp:", self.kp_spin)
        pid_layout.addRow("Ki:", self.ki_spin)
        pid_layout.addRow("Kd:", self.kd_spin)
        pid_layout.addRow("", self.pid_apply_btn)
        
        pid_group.setLayout(pid_layout)
        
        # Группа управления уставками
        setpoint_group = QGroupBox("Управляющие уставки")
        setpoint_layout = QFormLayout()
        
        self.tension_setpoint_spin = QDoubleSpinBox()
        self.tension_setpoint_spin.setRange(-100.0, 100.0)
        self.tension_setpoint_spin.setValue(0.0)
        self.tension_setpoint_spin.setSuffix(" Н·м")
        
        self.velocity_setpoint_spin = QDoubleSpinBox()
        self.velocity_setpoint_spin.setRange(-100.0, 100.0)
        self.velocity_setpoint_spin.setValue(0.0)
        self.velocity_setpoint_spin.setSuffix(" Н·м/с")
        
        self.setpoint_apply_btn = QPushButton("Установить уставки")
        self.setpoint_apply_btn.setStyleSheet("background-color: #FF9800; color: white;")
        
        setpoint_layout.addRow("Уставка момента:", self.tension_setpoint_spin)
        setpoint_layout.addRow("Уставка скорости:", self.velocity_setpoint_spin)
        setpoint_layout.addRow("", self.setpoint_apply_btn)
        
        setpoint_group.setLayout(setpoint_layout)
        
        # Группа дискретных управлений
        digital_group = QGroupBox("Дискретные управления")
        digital_layout = QVBoxLayout()
        
        self.start_btn = QPushButton("Старт")
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.stop_btn = QPushButton("Стоп")
        self.stop_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        self.reset_btn = QPushButton("Сброс")
        self.reset_btn.setStyleSheet("background-color: #FF9800; color: white;")
        
        digital_layout.addWidget(self.start_btn)
        digital_layout.addWidget(self.stop_btn)
        digital_layout.addWidget(self.reset_btn)
        
        digital_group.setLayout(digital_layout)
        
        # Добавление всех групп
        layout.addWidget(connection_group)
        layout.addWidget(pid_group)
        layout.addWidget(setpoint_group)
        layout.addWidget(digital_group)
        layout.addStretch()
        
        self.setLayout(layout)
        
        # Подключение сигналов
        self.connect_btn.clicked.connect(self.on_connect)
        self.disconnect_btn.clicked.connect(self.on_disconnect)
        self.pid_apply_btn.clicked.connect(self.apply_pid)
        self.setpoint_apply_btn.clicked.connect(self.apply_setpoints)
        self.start_btn.clicked.connect(self.on_start)
        self.stop_btn.clicked.connect(self.on_stop)
        self.reset_btn.clicked.connect(self.on_reset)
        
    def on_connect(self):
        """Обработка подключения"""
        command = {
            'action': 'connect',
            'host': self.host_edit.text(),
            'port': self.port_spin.value(),
            'timeout': self.timeout_spin.value()
        }
        self.control_command.emit(command)
        
    def on_disconnect(self):
        """Обработка отключения"""
        command = {'action': 'disconnect'}
        self.control_command.emit(command)
        
    def apply_pid(self):
        """Применение ПИД коэффициентов"""
        command = {
            'action': 'set_pid',
            'kp': self.kp_spin.value(),
            'ki': self.ki_spin.value(),
            'kd': self.kd_spin.value()
        }
        self.control_command.emit(command)
        
    def apply_setpoints(self):
        """Установка уставок"""
        command = {
            'action': 'set_setpoints',
            'tension': self.tension_setpoint_spin.value(),
            'velocity': self.velocity_setpoint_spin.value()
        }
        self.control_command.emit(command)
        
    def on_start(self):
        """Команда Старт"""
        command = {'action': 'start'}
        self.control_command.emit(command)
        
    def on_stop(self):
        """Команда Стоп"""
        command = {'action': 'stop'}
        self.control_command.emit(command)
        
    def on_reset(self):
        """Команда Сброс"""
        command = {'action': 'reset'}
        self.control_command.emit(command)
        
    def set_connected(self, connected: bool):
        """Обновление состояния кнопок подключения"""
        self.connect_btn.setEnabled(not connected)
        self.disconnect_btn.setEnabled(connected)


class RealTimeGraphWidget(QWidget):
    """Виджет для отображения графиков в реальном времени"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Создаем графический виджет
        self.graph_widget = pg.GraphicsLayoutWidget()
        self.graph_widget.setBackground('w')
        
        # График момента
        self.tension_plot = self.graph_widget.addPlot(title="Момент кручения", row=0, col=0)
        self.tension_plot.setLabel('left', 'Момент', units='Н·м')
        self.tension_plot.setLabel('bottom', 'Время', units='с')
        self.tension_plot.showGrid(x=True, y=True, alpha=0.3)
        self.tension_curve = self.tension_plot.plot(pen=pg.mkPen(color='b', width=2))
        
        # График угла
        self.angle_plot = self.graph_widget.addPlot(title="Угол поворота", row=1, col=0)
        self.angle_plot.setLabel('left', 'Угол', units='°')
        self.angle_plot.setLabel('bottom', 'Время', units='с')
        self.angle_plot.showGrid(x=True, y=True, alpha=0.3)
        self.angle_curve = self.angle_plot.plot(pen=pg.mkPen(color='g', width=2))
        
        # График скорости
        self.velocity_plot = self.graph_widget.addPlot(title="Скорость нарастания", row=2, col=0)
        self.velocity_plot.setLabel('left', 'Скорость', units='Н·м/с')
        self.velocity_plot.setLabel('bottom', 'Время', units='с')
        self.velocity_plot.showGrid(x=True, y=True, alpha=0.3)
        self.velocity_curve = self.velocity_plot.plot(pen=pg.mkPen(color='r', width=2))
        
        # Настройка общего вида
        self.graph_widget.ci.layout.setRowStretchFactor(0, 3)
        self.graph_widget.ci.layout.setRowStretchFactor(1, 3)
        self.graph_widget.ci.layout.setRowStretchFactor(2, 2)
        
        layout.addWidget(self.graph_widget)
        self.setLayout(layout)
        
        # Данные для графиков
        self.time_data = np.array([])
        self.tension_data = np.array([])
        self.angle_data = np.array([])
        self.velocity_data = np.array([])
        
        self.max_points = 1000  # Максимальное количество точек на графике
        
    def update_graphs(self, time: float, tension: float, angle: float, velocity: float):
        """Обновление графиков новыми данными"""
        # Добавляем новые данные
        self.time_data = np.append(self.time_data[-self.max_points+1:], time)
        self.tension_data = np.append(self.tension_data[-self.max_points+1:], tension)
        self.angle_data = np.append(self.angle_data[-self.max_points+1:], angle)
        self.velocity_data = np.append(self.velocity_data[-self.max_points+1:], velocity)
        
        # Обновляем кривые
        self.tension_curve.setData(self.time_data, self.tension_data)
        self.angle_curve.setData(self.time_data, self.angle_data)
        self.velocity_curve.setData(self.time_data, self.velocity_data)
        
    def clear_graphs(self):
        """Очистка графиков"""
        self.time_data = np.array([])
        self.tension_data = np.array([])
        self.angle_data = np.array([])
        self.velocity_data = np.array([])
        
        self.tension_curve.setData([], [])
        self.angle_curve.setData([], [])
        self.velocity_curve.setData([], [])


class ModbusRegistersWidget(QWidget):
    """Виджет для отображения и редактирования регистров Modbus"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Таблица регистров
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['Адрес', 'Значение (DEC)', 'Значение (HEX)', 'Описание'])
        self.table.horizontalHeader().setStretchLastSection(True)
        
        # Кнопки управления
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Обновить")
        self.write_btn = QPushButton("Записать выделенные")
        self.write_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.write_btn)
        btn_layout.addStretch()
        
        layout.addWidget(self.table)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        
    def update_registers(self, registers: list):
        """Обновление таблицы регистров"""
        self.table.setRowCount(len(registers))
        
        descriptions = {
            0: "Дискретные входы",
            1: "АЦП датчика момента",
            2: "Угол поворота (младшее слово)",
            3: "Угол поворота (старшее слово)",
            4: "Дискретные выходы",
            5: "Состояние оборудования",
            60: "Индекс буфера"
        }
        
        for i, value in enumerate(registers):
            # Адрес
            addr_item = QTableWidgetItem(str(i))
            addr_item.setFlags(addr_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            # Десятичное значение
            dec_item = QTableWidgetItem(str(value))
            
            # Шестнадцатеричное значение
            hex_item = QTableWidgetItem(f"0x{value:04X}")
            hex_item.setFlags(hex_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            # Описание
            desc = descriptions.get(i, "")
            desc_item = QTableWidgetItem(desc)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            self.table.setItem(i, 0, addr_item)
            self.table.setItem(i, 1, dec_item)
            self.table.setItem(i, 2, hex_item)
            self.table.setItem(i, 3, desc_item)


class MainWindow(QMainWindow):
    """Главное окно приложения"""
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.modbus_handler: Optional[RealTimeData] = None
        
        self.setup_ui()
        self.setup_modbus()
        
    def setup_ui(self):
        """Настройка интерфейса"""
        self.setWindowTitle("Система управления испытательным стендом")
        self.setGeometry(100, 100, 1400, 800)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной layout
        main_layout = QHBoxLayout(central_widget)
        
        # Разделитель для левой и правой панелей
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Левая панель - управление и отображение данных
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Виджет отображения данных
        self.sensor_display = SensorDisplayWidget()
        
        # Панель управления
        self.control_panel = ControlPanelWidget()
        
        left_layout.addWidget(self.sensor_display)
        left_layout.addWidget(self.control_panel)
        
        # Правая панель - графики и регистры
        right_panel = QTabWidget()
        
        # Вкладка с графиками
        self.graph_widget = RealTimeGraphWidget()
        right_panel.addTab(self.graph_widget, "Графики")
        
        # Вкладка с регистрами
        self.registers_widget = ModbusRegistersWidget()
        right_panel.addTab(self.registers_widget, "Регистры Modbus")
        
        # Добавляем панели в разделитель
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 1000])
        
        main_layout.addWidget(splitter)
        
        # Строка состояния
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Готов к работе")
        
        # Таймер для обновления UI
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui)
        self.ui_timer.start(100)  # Обновление 10 раз в секунду
        
        # Подключение сигналов от панели управления
        self.control_panel.control_command.connect(self.handle_control_command)
        
    def setup_modbus(self):
        """Инициализация Modbus обработчика"""
        try:
            self.modbus_handler = RealTimeData(self.config)
            self.modbus_handler.data_updated.connect(self.on_modbus_data_received)
            self.modbus_handler.poller.connection_status.connect(
                self.sensor_display.update_connection_status
            )
            self.status_bar.showMessage("Modbus обработчик инициализирован")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось инициализировать Modbus: {str(e)}")
            
    @pyqtSlot(list)
    def on_modbus_data_received(self, registers):
        """Обработка полученных данных от Modbus"""
        # Обновление виджета регистров
        self.registers_widget.update_registers(registers)
        
        # Обновление статуса
        current_time = datetime.now().strftime("%H:%M:%S")
        self.status_bar.showMessage(f"Данные получены: {current_time}")
        
    def update_ui(self):
        """Обновление UI элементов"""
        if self.modbus_handler:
            # Обновление значений датчиков
            tension = self.modbus_handler.get_torque()
            angle = self.modbus_handler.get_angle()
            velocity = self.modbus_handler.get_velocity()
            
            self.sensor_display.update_values(tension, angle, velocity)
            
            # Обновление графиков
            current_time = time.time() - self.modbus_handler.time_origin
            self.graph_widget.update_graphs(current_time, tension, angle, velocity)
            
    @pyqtSlot(dict)
    def handle_control_command(self, command: dict):
        """Обработка команд от панели управления"""
        action = command.get('action')
        
        if action == 'connect':
            self.connect_modbus(command)
        elif action == 'disconnect':
            self.disconnect_modbus()
        elif action == 'set_pid':
            self.set_pid_parameters(command)
        elif action == 'set_setpoints':
            self.set_setpoints(command)
        elif action in ['start', 'stop', 'reset']:
            self.send_control_command(action)
            
    def connect_modbus(self, params: dict):
        """Подключение к Modbus устройству"""
        try:
            # Обновление конфигурации
            self.config.set('modbus', 'host', params['host'])
            self.config.set('modbus', 'port', str(params['port']))
            self.config.set('modbus', 'timeout', str(params['timeout']))
            
            # Обновление настроек соединения
            self.modbus_handler.update_connection_settings()
            
            self.control_panel.set_connected(True)
            self.status_bar.showMessage(f"Подключение к {params['host']}:{params['port']}")
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка подключения", str(e))
            
    def disconnect_modbus(self):
        """Отключение от Modbus устройства"""
        self.control_panel.set_connected(False)
        self.status_bar.showMessage("Соединение разорвано")
        
    def set_pid_parameters(self, params: dict):
        """Установка ПИД параметров"""
        try:
            regs = {
                'Modbus_KP': params['kp'],
                'Modbus_KI': params['ki'],
                'Modbus_KD': params['kd']
            }
            self.modbus_handler.modbus_registers_to_PLC_update(regs)
            self.status_bar.showMessage("ПИД параметры установлены")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось установить ПИД параметры: {str(e)}")
            
    def set_setpoints(self, params: dict):
        """Установка уставок"""
        try:
            regs = {
                'Modbus_TensionSV': int(params['tension'] * 100),  # Пример масштабирования
                'Modbus_VelocitySV': int(params['velocity'] * 10)   # Пример масштабирования
            }
            self.modbus_handler.modbus_registers_to_PLC_update(regs)
            self.status_bar.showMessage("Уставки установлены")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось установить уставки: {str(e)}")
            
    def send_control_command(self, command: str):
        """Отправка дискретной команды"""
        try:
            ctrl_reg = 0
            
            if command == 'start':
                ctrl_reg = 0x01  # Бит старта
            elif command == 'stop':
                ctrl_reg = 0x02  # Бит остановки
            elif command == 'reset':
                ctrl_reg = 0x04  # Бит сброса
                
            regs = {'Modbus_CTRL': ctrl_reg}
            self.modbus_handler.modbus_registers_to_PLC_update(regs)
            
            self.status_bar.showMessage(f"Команда '{command}' отправлена")
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось отправить команду: {str(e)}")
            
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        if self.modbus_handler:
            # Остановка потоков
            if hasattr(self.modbus_handler.poller_thread, 'quit'):
                self.modbus_handler.poller_thread.quit()
                self.modbus_handler.poller_thread.wait()
                
        event.accept()


def main():
    """Точка входа в приложение"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Создание конфигурации (заглушка, нужно заменить на реальную)
    class ConfigStub:
        def __init__(self):
            self.data = {
                'modbus': {
                    'host': '127.0.0.1',
                    'port': '502',
                    'timeout': '1.0',
                    'poll_interval_ms': '100'
                },
                'ui': {
                    'max_graph_points': '1000'
                }
            }
            
        def get(self, section, key, default=None):
            return self.data.get(section, {}).get(key, default)
            
        def set(self, section, key, value):
            if section not in self.data:
                self.data[section] = {}
            self.data[section][key] = value
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Настройка темной темы (опционально)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(palette)
    
    config = ConfigStub()
    window = MainWindow(config)
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()