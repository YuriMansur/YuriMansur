from PyQt6.QtWidgets import (QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout)
from PyQt6.QtCore import QTimer
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
        central_widget.setObjectName("main_central")

        # Установка как главный центральный виджет
        self.setCentralWidget(central_widget)

        # Основной лэйаут
        self.main_layout = QVBoxLayout(central_widget)

        # Внутренние отступы лэйаута.
        self.main_layout.setContentsMargins(4, 4, 4, 4)

        # Расстояние между виджетами внутри лэйаута
        self.main_layout.setSpacing(0)
        main_layout = self.main_layout

        # Создание верхней панели навигации   
        self.create_top_navigation()

        # Добавление страницы в лэйаут
        main_layout.addWidget(self.top_nav_panel)    
        
        # Виджет контента
        content_widget = QWidget()

        # Добавление лэйаута                  
        content_layout = QVBoxLayout(content_widget) 

        # Внутренние отступы лэйаута.
        content_layout.setContentsMargins(0, 0, 0, 0)   

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
        QTimer.singleShot(0, self.apply_theme)
        
#Создание верхней панели навигации
    def create_top_navigation(self):

        # Создание виджета верхней панели
        self.top_nav_panel = QWidget()

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

        # Тогл светлой/тёмной темы справа
        from PyQt6.QtWidgets import QPushButton
        self._dark_mode = True
        self._btn_theme = QPushButton("🌙")
        self._btn_theme.setFixedSize(36, 36)
        self._btn_theme.setToolTip("Переключить тему")
        self._btn_theme.clicked.connect(self._toggle_theme)
        nav_layout.addWidget(self._btn_theme)

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

        page1.alarm_test.connect(self._start_alarm_blink)
        page1.alarm_reset.connect(self._stop_alarm_blink)

    def _start_alarm_blink(self):
        if hasattr(self, "_blink_timer") and self._blink_timer.isActive():
            return
        self._blink_state = False
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._do_blink)
        self._blink_timer.start(250)

    def _do_blink(self):
        self._blink_state = not self._blink_state
        if self._blink_state:
            self.centralWidget().setStyleSheet("QWidget#main_central { border: 4px solid #e74c3c; }")
        else:
            self.centralWidget().setStyleSheet("QWidget#main_central { border: 4px solid transparent; }")

    @staticmethod
    def _dark_palette():
        from PyQt6.QtGui import QPalette, QColor
        D = QColor
        p = QPalette()
        # Основные
        p.setColor(QPalette.ColorRole.Window,          D(30,  30,  30))
        p.setColor(QPalette.ColorRole.WindowText,      D(224, 224, 224))
        p.setColor(QPalette.ColorRole.Base,            D(22,  22,  22))
        p.setColor(QPalette.ColorRole.AlternateBase,   D(40,  40,  40))
        p.setColor(QPalette.ColorRole.Text,            D(224, 224, 224))
        p.setColor(QPalette.ColorRole.PlaceholderText, D(120, 120, 120))
        p.setColor(QPalette.ColorRole.Button,          D(45,  45,  45))
        p.setColor(QPalette.ColorRole.ButtonText,      D(224, 224, 224))
        p.setColor(QPalette.ColorRole.BrightText,      D(255, 100, 100))
        p.setColor(QPalette.ColorRole.Link,            D(82,  152, 255))
        p.setColor(QPalette.ColorRole.Highlight,       D(42,  130, 218))
        p.setColor(QPalette.ColorRole.HighlightedText, D(255, 255, 255))
        p.setColor(QPalette.ColorRole.ToolTipBase,     D(50,  50,  50))
        p.setColor(QPalette.ColorRole.ToolTipText,     D(224, 224, 224))
        p.setColor(QPalette.ColorRole.Mid,             D(60,  60,  60))
        p.setColor(QPalette.ColorRole.Dark,            D(20,  20,  20))
        p.setColor(QPalette.ColorRole.Shadow,          D(0,   0,   0))
        # Disabled
        g = QPalette.ColorGroup.Disabled
        p.setColor(g, QPalette.ColorRole.WindowText,  D(100, 100, 100))
        p.setColor(g, QPalette.ColorRole.Text,        D(100, 100, 100))
        p.setColor(g, QPalette.ColorRole.ButtonText,  D(100, 100, 100))
        p.setColor(g, QPalette.ColorRole.Highlight,   D(60,  60,  60))
        return p

    @staticmethod
    def _light_palette():
        from PyQt6.QtGui import QPalette, QColor
        D = QColor
        p = QPalette()
        p.setColor(QPalette.ColorRole.Window,          D(240, 240, 240))
        p.setColor(QPalette.ColorRole.WindowText,      D(20,  20,  20))
        p.setColor(QPalette.ColorRole.Base,            D(255, 255, 255))
        p.setColor(QPalette.ColorRole.AlternateBase,   D(233, 233, 233))
        p.setColor(QPalette.ColorRole.Text,            D(20,  20,  20))
        p.setColor(QPalette.ColorRole.PlaceholderText, D(160, 160, 160))
        p.setColor(QPalette.ColorRole.Button,          D(225, 225, 225))
        p.setColor(QPalette.ColorRole.ButtonText,      D(20,  20,  20))
        p.setColor(QPalette.ColorRole.BrightText,      D(200, 0,   0))
        p.setColor(QPalette.ColorRole.Link,            D(0,   100, 200))
        p.setColor(QPalette.ColorRole.Highlight,       D(42,  130, 218))
        p.setColor(QPalette.ColorRole.HighlightedText, D(255, 255, 255))
        p.setColor(QPalette.ColorRole.ToolTipBase,     D(255, 255, 220))
        p.setColor(QPalette.ColorRole.ToolTipText,     D(20,  20,  20))
        p.setColor(QPalette.ColorRole.Mid,             D(180, 180, 180))
        p.setColor(QPalette.ColorRole.Dark,            D(160, 160, 160))
        p.setColor(QPalette.ColorRole.Shadow,          D(100, 100, 100))
        g = QPalette.ColorGroup.Disabled
        p.setColor(g, QPalette.ColorRole.WindowText,  D(150, 150, 150))
        p.setColor(g, QPalette.ColorRole.Text,        D(150, 150, 150))
        p.setColor(g, QPalette.ColorRole.ButtonText,  D(150, 150, 150))
        p.setColor(g, QPalette.ColorRole.Highlight,   D(200, 200, 200))
        return p

    def apply_theme(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        app.setPalette(self._dark_palette() if self._dark_mode else self._light_palette())
        text_color = "#ecf0f1" if self._dark_mode else "#1a1a1a"
        for btn in self.nav_buttons:
            btn.set_text_color(text_color)
        if hasattr(self, "stacked_widget"):
            for i in range(self.stacked_widget.count()):
                w = self.stacked_widget.widget(i)
                if hasattr(w, "set_theme"):
                    w.set_theme(self._dark_mode)

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self._btn_theme.setText("🌙" if self._dark_mode else "☀️")
        self.apply_theme()

    def _stop_alarm_blink(self):
        if hasattr(self, "_blink_timer"):
            self._blink_timer.stop()
        self.centralWidget().setStyleSheet("QWidget#main_central { border: 4px solid transparent; }")

# Переключение страниц
    def switch_page(self, index):

        # Запись страницы
        self.current_page = index

        # Переход к странице
        self.stacked_widget.setCurrentIndex(index)

        # Обновление состояния кнопок навигации
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
