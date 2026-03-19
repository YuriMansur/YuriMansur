from PyQt6.QtWidgets import (QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout)
from gui.windows.experiment_window.ui_experiment_wiget import ExperimentWidget
from gui.windows.trengs_window.trends_wiget import TrendsWiget
from gui.windows.settings_window.ui_settings_wiget import SettingsWidget
from gui.style_classes.nav_button import NavigationButton


class MainWindow(QMainWindow):
    def __init__(self):              
        super().__init__()
# Настройка главного экрана

        # Настройка окна                      
        self.setWindowTitle("AlbApp")

        #Установка стартового окна в контейнере                       
        self.current_page = 0                

        # Создание виджета 
        central_widget = QWidget() 

        # Установка как главный центральный виджет                         
        self.setCentralWidget(central_widget) 

        # Основной лэйаут
        main_layout = QVBoxLayout(central_widget)  

        # Внутренние отступы лэйаута.
        main_layout.setContentsMargins(0, 0, 0, 0)     

        # Расстояние между виджетами внутри лэйаута
        main_layout.setSpacing(0)       

        # Создание верхней панели навигации   
        self.create_top_navigation()

        # Добавление страницы в лэйаут
        main_layout.addWidget(self.top_nav_panel)    
        
        # Виджет контента
        content_widget = QWidget()

        # Добавление лэйаута                  
        content_layout = QVBoxLayout(content_widget) 

        # Внутренние отступы лэйаута.
        content_layout.setContentsMargins(20, 20, 20, 20)   

        # Контейнер для страниц   
        self.stacked_widget = QStackedWidget()          

        # Создание страниц
        self.create_pages()                  

        # Добавление контейнера в лэйаут контента
        content_layout.addWidget(self.stacked_widget)     

        # Добавление контента в основной лэйаут
        main_layout.addWidget(content_widget)

        # Устанавливаем первую страницу активной
        self.switch_page(0)
        
#Создание верхней панели навигации
    def create_top_navigation(self):

        # Создание виджета верхней панели
        self.top_nav_panel = QWidget()

        # Стилизация верхне панели
        self.top_nav_panel.setStyleSheet("""
            QWidget {
                background-color: #34495e;
                border-bottom: 3px solid #3498db;
            }
        """)

        # Создание основного лэйаута панели навигации
        nav_layout = QHBoxLayout(self.top_nav_panel)

        # Внутренние отступы лэйаута
        nav_layout.setContentsMargins(10, 5, 10, 5)

        # Расстояние между виджетами внутри лэйаута
        nav_layout.setSpacing(0)

        # Кнопки навигации
        self.nav_buttons = []

        # Кортеж стилизации кнопок
        page_data = [
            ("🧪 Испытания", "#1abc9c"),
            ("📈 Тренды", "#3498db"),
            ("⚙️ Настройки", "#9b59b6"),
        ]

        # Создание кнопок навигации
        for i, (title, color) in enumerate(page_data):

            # Создание кнопки навигации
            btn = NavigationButton(title, color)

            # Добавление возможности переключения
            btn.setCheckable(True) 

            # Подключение сигнала клика к переключению страницы
            btn.clicked.connect(lambda checked, idx = i: self.switch_page(idx))

            # Добавление кнопки в список
            self.nav_buttons.append(btn)

            # Добавление кнопки в лайаут панели навигации
            nav_layout.addWidget(btn)

        # Добавление растяжки для выравнивания кнопок влево
        nav_layout.addStretch()

#Создание страниц
    def create_pages(self):

        # Страница 1: Испытание
        page1 = ExperimentWidget()
        page1.setObjectName("experiment_page")

        # Страница 2: Тренды
        page2 = TrendsWiget()
        page2.setObjectName("trends_page")
        
        # Страница 3: Настройки
        self.settings_widget = SettingsWidget()
        page3 = self.settings_widget
        page3.setObjectName("settings_page")
    
        # Добавляем страницы в контейнер
        self.stacked_widget.addWidget(page1)
        self.stacked_widget.addWidget(page2)  
        self.stacked_widget.addWidget(page3)

# Переключение страниц
    def switch_page(self, index):

        # Запись страницы
        self.current_page = index

        # Переход к странице
        self.stacked_widget.setCurrentIndex(index)

        # Обновление состояния кнопок навигации
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
