from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QStackedWidget, QGridLayout,
    QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QFrame, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

# Импорт из существующей папки wigets
from wigets.trends_wiget import PyQtGraphWidget  
from wigets.settings_wiget import SettingsWidget 
from wigets.experiment_wiget import ExperimentWidget 


class MainWindow(QMainWindow):
    def __init__(self):              
        super().__init__()
# Настройка главного экрана
############################################################
        # Настройка окна                      
        self.setWindowTitle("AlbApp")                       
        self.current_page = 0                

        # Центральный виджет
        central_widget = QWidget()                          
        self.setCentralWidget(central_widget) 

        # Основной layout
        main_layout = QVBoxLayout(central_widget)    
        main_layout.setContentsMargins(0, 0, 0, 0)        
        main_layout.setSpacing(0)       

        # Создание верхней панели навигации добавление ее в основной лэйаут    
        self.create_top_navigation()              
        main_layout.addWidget(self.top_nav_panel)    
        
        # Виджет контента
        content_widget = QWidget()    

        # Добавление layout и отступов для контента                   
        content_layout = QVBoxLayout(content_widget)    
        content_layout.setContentsMargins(20, 20, 20, 20)   

        # StackedWidget для страниц   
        self.stacked_widget = QStackedWidget()          

        # Создание страниц с подсветкой
        self.create_pages()                  

        # Добавление "stacked widget" в лэйаут контента
        content_layout.addWidget(self.stacked_widget)     

        # Добавление контента в основной layout
        main_layout.addWidget(content_widget)

        # Устанавливаем первую страницу активной
        
        self.switch_page(0)
        # Инициализация конфигурации в "settings" виджете
        self.settings_widget.init_from_config()

    #Создание верхней панели навигации
    def create_top_navigation(self):
        self.top_nav_panel = QWidget()
        self.top_nav_panel.setStyleSheet("""
            QWidget {
                background-color: #34495e;
                border-bottom: 3px solid #3498db;
            }
        """)
        # Основной layout панели навигации и настрока отступов
        nav_layout = QHBoxLayout(self.top_nav_panel)
        nav_layout.setContentsMargins(10, 5, 10, 5)
        nav_layout.setSpacing(0)

        # Кнопки навигации
        self.nav_buttons = []
        page_data = [
            ("🧪 Испытания", "#1abc9c"),
            ("📈 Тренды", "#3498db"),
            ("⚙️ Настройки", "#9b59b6"),
        ]
        # Создание кнопок навигации
        for i, (title, color) in enumerate(page_data):

            # Создание кнопки навигации и делаем ее переключаемой
            btn = NavigationButton(title, color)
            btn.setCheckable(True) 

            # Подключение сигнала клика к переключению страницы
            btn.clicked.connect(lambda checked, idx = i: self.switch_page(idx))

            # Добавление кнопки в список и лайаут
            self.nav_buttons.append(btn)
            nav_layout.addWidget(btn)

        # Добавление растяжки для выравнивания кнопок влево
        nav_layout.addStretch()

    #Создание страниц
    def create_pages(self):
        # Страница 1: Испытание
        page1 = ExperimentWidget()
        page1.setObjectName("experiment_page")

        # Страница 2: Тренды
        page2 = PyQtGraphWidget()
        page2.setObjectName("trends_page")
        
        # Страница 3: Настройки
        page3 = SettingsWidget()
        page3.setObjectName("settings_page")
    
        # Добавляем страницы
        self.stacked_widget.addWidget(page1)
        self.stacked_widget.addWidget(page2)  
        self.stacked_widget.addWidget(page3)

        # Сохраняем ссылки на виджеты страниц
        self.experiment_widget = page1
        self.trends_widget = page2
        self.settings_widget = page3

    # Переключение страниц
    def switch_page(self, index):
        self.current_page = index
        self.stacked_widget.setCurrentIndex(index)
        # Обновление состояния кнопок навигации
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

# Настройка кнопок навигации и переключение страниц 
class NavigationButton(QPushButton):
    def __init__(self, text, color):
        super().__init__(text)
        # Сохранение цвета кнопки
        self.color = color
        # Фиксированная высота кнопки
        self.setFixedHeight(40)
        # Курсор при наведении
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Базовые стили
        self.update_style(False)
    
    # Обновление стиля в зависимости от состояния активности
    def update_style(self, active):
        if active:
            style = f"""
                QPushButton {{
                    background-color: {self.color};
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    font-weight: bold;
                    border-bottom: 3px solid white;
                    margin: 0 2px;
                }}
                QPushButton:hover {{
                    background-color: {self.darken_color(self.color)};
                }}
            """
        else:
            style = f"""
                QPushButton {{
                    background-color: transparent;
                    color: #ecf0f1;
                    border: none;
                    padding: 10px 20px;
                    margin: 0 2px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.1);
                    color: white;
                    border-bottom: 3px solid {self.color};
                }}
            """
        # Применение стиля   
        self.setStyleSheet(style)

    # Затемнение цвета для hover эффекта
    def darken_color(self, hex_color):
        color = QColor(hex_color)
        return color.darker(120).name()
    
    # Переопределение метода setChecked для обновления стиля при смене состояния
    def setChecked(self, checked):
        super().setChecked(checked)
        self.update_style(checked)

