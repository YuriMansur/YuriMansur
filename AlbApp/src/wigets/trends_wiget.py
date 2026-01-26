import sys
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, 
                             QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QSpinBox, QFormLayout, QGroupBox, QColorDialog)
from PyQt6.QtCore import Qt
import pyqtgraph as pg


class PyQtGraphWidget(QWidget):
    #Виджет графика с использованием pyqtgraph
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.setup_plot()
        
    def setup_ui(self):
        """Настройка пользовательского интерфейса"""
        main_layout = QVBoxLayout(self)
        
        # Панель управления
        control_group = QGroupBox("Управление графиком")
        control_layout = QFormLayout()
        
        # Кнопки управления
        self.btn_add_line = QPushButton("Добавить линию")
        self.btn_add_scatter = QPushButton("Добавить точки")
        self.btn_clear = QPushButton("Очистить график")
        
        # Настройки графика
        self.spin_points = QSpinBox()
        self.spin_points.setRange(10, 1000)
        self.spin_points.setValue(100)
        self.spin_points.valueChanged.connect(self.update_plot)
        
        # Цвет линии
        self.color_btn = QPushButton()
        self.color_btn.setStyleSheet("background-color: #FF5733;")
        self.color_btn.clicked.connect(self.change_line_color)
        self.current_color = '#FF5733'
        
        control_layout.addRow("Количество точек:", self.spin_points)
        control_layout.addRow("Цвет линии:", self.color_btn)
        control_layout.addWidget(self.btn_add_line)
        control_layout.addWidget(self.btn_add_scatter)
        control_layout.addWidget(self.btn_clear)
        control_group.setLayout(control_layout)
        
        # Виджет графика
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.setLabel('left', 'Значение Y', units='ед.')
        self.plot_widget.setLabel('bottom', 'Значение X', units='ед.')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()
        
        # Добавление элементов в основной layout
        main_layout.addWidget(control_group)
        main_layout.addWidget(self.plot_widget, 1)
        
        # Подключение сигналов
        self.btn_add_line.clicked.connect(self.add_sine_wave)
        self.btn_add_scatter.clicked.connect(self.add_scatter_points)
        self.btn_clear.clicked.connect(self.clear_plot)
        
        # Инициализация данных
        self.lines = []
        self.scatters = []
        
    def setup_plot(self):
        """Начальная настройка графика"""
        # Добавляем начальную кривую
        self.add_sine_wave()
        
    def add_sine_wave(self):
        """Добавление синусоидальной волны"""
        n_points = self.spin_points.value()
        x = np.linspace(0, 10, n_points)
        y = np.sin(x)
        
        # Создаем линию
        line = self.plot_widget.plot(
            x, y, 
            pen=pg.mkPen(color=self.current_color, width=2),
            name=f'Синус {len(self.lines) + 1}'
        )
        self.lines.append(line)
        
    def add_scatter_points(self):
        """Добавление точечного графика"""
        n_points = min(50, self.spin_points.value())
        x = np.random.rand(n_points) * 10
        y = np.random.rand(n_points) * 2 - 1
        
        # Создаем точки
        scatter = self.plot_widget.plot(
            x, y, 
            pen=None,
            symbol='o',
            symbolSize=10,
            symbolBrush=pg.mkColor(44, 130, 201),
            name=f'Точки {len(self.scatters) + 1}'
        )
        self.scatters.append(scatter)
        
    def update_plot(self):
        self.clear_plot()
        self.add_sine_wave()
        
    def clear_plot(self):
        for line in self.lines:
            self.plot_widget.removeItem(line)
        for scatter in self.scatters:
            self.plot_widget.removeItem(scatter)
        self.lines.clear()
        self.scatters.clear()
        
    def change_line_color(self):
        """Изменение цвета линии"""
        color = QColorDialog.getColor()
        if color.isValid():
            self.current_color = color.name()
            self.color_btn.setStyleSheet(f"background-color: {self.current_color};")
            
    def set_data(self, x_data, y_data, label="Данные", color=None):
        self.clear_plot()
        
        if color is None:
            color = self.current_color
            
        line = self.plot_widget.plot(
            x_data, y_data, 
            pen=pg.mkPen(color=color, width=2),
            name=label
        )
        self.lines.append(line)
        
    def set_labels(self, x_label="X", y_label="Y"):
        self.plot_widget.setLabel('bottom', x_label)
        self.plot_widget.setLabel('left', y_label)
        
    def enable_grid(self, x=True, y=True, alpha=0.3):
        """Включение/выключение сетки"""
        self.plot_widget.showGrid(x=x, y=y, alpha = alpha)
        
    def save_plot(self, filename):
        """Сохранение графика в файл"""
        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
        exporter.export(filename)
