from PyQt6.QtWidgets import (QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout, QPushButton)
from PyQt6.QtCore import QTimer
from gui.windows.experiment_window.ui_experiment_wiget import ExperimentWidget
from gui.windows.trengs_window.trends_wiget import TrendsWiget
from gui.windows.settings_window.ui_settings_wiget import SettingsWidget
from gui.windows.messages_window.messages_viewer import MessagesWidget
from gui.style_classes.nav_button import NavigationButton


def _load_log_tags() -> list:
    """Прочитать patch/log_tags.json — какие теги логировать в БД сообщений."""
    import json
    from pathlib import Path
    try:
        p = Path(__file__).resolve().parents[3] / "patch" / "log_tags.json"
        return json.loads(p.read_text(encoding="utf-8")).get("tags", [])
    except (OSError, ValueError) as e:
        print(f"[log_tags] не удалось прочитать конфиг: {e}")
        return []


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
        # значки рисуются кодом (gui/icons.py) и перекрашиваются вместе с надписью
        page_data = [
            (" Испытания",          "#1abc9c", "flask"),
            (" Видеоналожение",     "#e74c3c", "video"),
            (" Тренды",             "#3498db", "chart"),
            (" Сообщения",          "#e67e22", "chat"),
            (" Экспорт",            "#27ae60", "export"),
            (" Протоколы/Журналы",  "#e84393", "doc"),
            (" Настройки",          "#9b59b6", "gear"),
        ]

        # Создание кнопок навигации
        for i, (title, color, icon_kind) in enumerate(page_data):

            # Создание кнопки навигации
            btn = NavigationButton(title, color, icon_kind)

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

        # Кнопка сброса аварий (справа, где раньше были «Протоколы»).
        # Иконка — треугольник аварии в круговой стрелке, рисуется кодом
        # (gui/icons.py), белым по красному фону кнопки.
        from PyQt6.QtGui import QIcon
        from PyQt6.QtCore import QSize
        from gui.icons import make_icon
        self._btn_reset_nav = QPushButton(" Сброс аварий")
        self._btn_reset_nav.setIcon(QIcon(make_icon("reset_fault", "#ffffff", 20)))
        self._btn_reset_nav.setIconSize(QSize(20, 20))
        self._btn_reset_nav.setFixedHeight(36)
        self._btn_reset_nav.setToolTip("Сброс аварий")
        self._btn_reset_nav.setStyleSheet(
            "QPushButton { background: #c0392b; color: white; font-weight: bold;"
            " border-radius: 4px; padding: 0 14px; }"
            "QPushButton:hover { background: #e74c3c; }"
        )
        nav_layout.addWidget(self._btn_reset_nav)

        self._dark_mode = True

#Создание страниц
    def create_pages(self):

        # Страница 1: Испытание
        page1 = ExperimentWidget()
        page1.setObjectName("experiment_page")

        # Страница 2: Тренды
        page2 = TrendsWiget()
        page2.setObjectName("trends_page")

        # Страница 3: Сообщения (системный лог)
        page_msg = MessagesWidget()
        page_msg.setObjectName("messages_page")

        # Страница 4: Настройки
        self.settings_widget = SettingsWidget()
        page3 = self.settings_widget
        page3.setObjectName("settings_page")

        # Выбор темы живёт в настройках; стартовое значение — текущий режим
        self.settings_widget.theme_combo.setCurrentIndex(0 if self._dark_mode else 1)
        self.settings_widget.theme_combo.currentIndexChanged.connect(self._on_theme_changed)

        # Страница 5: График на видео (постобработка записей)
        from gui.windows.video_overlay_window.video_overlay_widget import VideoOverlayWidget
        page_video = VideoOverlayWidget()
        page_video.setObjectName("video_overlay_page")

        # Страница 6: Экспорт (журнал испытаний, только чтение)
        from gui.popups.export_viewer import ExportViewer
        self._export_page = ExportViewer()
        self._export_page.setObjectName("export_page")

        # Страница 7: Протоколы (просмотр папки documents)
        from gui.windows.protocols_window.protocols_widget import ProtocolsWidget
        page_protocols = ProtocolsWidget()
        page_protocols.setObjectName("protocols_page")

        # Добавляем страницы в контейнер (порядок = порядок вкладок навигации)
        self.stacked_widget.addWidget(page1)
        self.stacked_widget.addWidget(page_video)
        self.stacked_widget.addWidget(page2)
        self.stacked_widget.addWidget(page_msg)
        self.stacked_widget.addWidget(self._export_page)
        self.stacked_widget.addWidget(page_protocols)
        self.stacked_widget.addWidget(page3)

        page1.alarm_raised.connect(self._start_alarm_blink)
        page1.alarm_reset.connect(self._stop_alarm_blink)
        def _reset_faults(_=False):
            from tag_binder import tags
            tags.write("cmdResetFault", 1)   # одиночная запись TRUE на сервер (RESET_FAULT)
            # мигание НЕ гасим локально: авария снимется по фронту general_fault 1→0 от ПЛК
        self._btn_reset_nav.clicked.connect(_reset_faults)   # «Сброс аварий» на верхней панели

        # Авария по тегу general_fault: читаем тег с ПЛК и по фронту 0→1
        # поднимаем аварию: мигание рамки + прерывание в секции 3. По фронту
        # 1→0 — сброс. Сам тег прокидывается в servers.json отдельно; до этого
        # биндер просто предупредит, что имени ещё нет.
        import threading
        from tag_binder import tags
        from logger import applog
        from event_bus import bus

        def _log_rt(rec):
            # параллельно: показ на «Сообщениях» — мгновенно по сигналу,
            # запись в БД — в фоновом потоке, чтобы показ не ждал диск.
            bus.log_event.emit(rec)
            threading.Thread(target=applog.persist, args=(rec,), daemon=True).start()

        # Логирование тегов по конфигу patch/log_tags.json. По фронту 0→1/1→0
        # пишем сообщение (текст+уровень из конфига) в БД сообщений.
        self._log_tag_state: dict = {}   # tag -> последнее булево значение

        def _make_log_handler(entry):
            tag = entry["tag"]
            cat = entry.get("category", applog.CAT_PLC)
            spec_on  = entry.get("on")  or {}
            spec_off = entry.get("off") or {}
            self._log_tag_state[tag] = False

            def _handler(val):
                active = bool(val)
                if active == self._log_tag_state.get(tag, False):
                    return                         # только по фронту
                self._log_tag_state[tag] = active
                spec = spec_on if active else spec_off
                msg = spec.get("message")
                if msg:
                    level = str(spec.get("level", applog.LEVEL_INFO)).upper()
                    _log_rt(applog.make(cat, msg, level=level, source=tag))
            return _handler

        for _entry in _load_log_tags():
            if _entry.get("tag"):
                tags.on(_entry["tag"], _make_log_handler(_entry))

        # Авария по general_fault — ВСЕГДА, независимо от конфига логов:
        # мигание рамки + прерывание в секции 3. Это защитная функция, поэтому
        # хардкод (логирование этого тега — отдельно и необязательно).
        self._accident_active = False

        def _on_accident(val, _p=page1):
            active = bool(val)
            if active and not self._accident_active:
                _p.alarm_raised.emit()
            elif not active and self._accident_active:
                _p.alarm_reset.emit()
            self._accident_active = active

        tags.on("general_fault", _on_accident)

        # События связи → журнал «Сообщения» (категория Связь), по переходам:
        # подключено (разово) / потеряна / переподключение (по триггеру reconnecting).
        self._conn_seen = False    # было ли хоть одно успешное подключение
        self._conn_up   = False    # текущее состояние связи

        def _on_srv_connected(server):
            if self._conn_up:
                return                                     # уже подключены — не дублируем
            self._conn_up = True
            if not self._conn_seen:                        # «подключено» — только один раз
                self._conn_seen = True
                _log_rt(applog.make(applog.CAT_CONN, f"Связь с {server} установлена",
                                    level=applog.LEVEL_INFO, source=server))
            else:                                          # успешный реконнект после обрыва
                _log_rt(applog.make(applog.CAT_CONN, f"Связь с {server} восстановлена",
                                    level=applog.LEVEL_INFO, source=server))

        def _on_srv_disconnected(server):
            if not self._conn_up:
                return                                     # уже потеряна — не спамим
            self._conn_up = False
            _log_rt(applog.make(applog.CAT_CONN, f"Связь с {server} потеряна",
                                level=applog.LEVEL_WARN, source=server))

        def _on_srv_reconnecting(server, *_):
            # выводим на каждый триггер попытки (каждые ~5 с), пока нет связи
            if self._conn_up:
                return
            _log_rt(applog.make(applog.CAT_CONN, "Переподключение к ПЛК…",
                                level=applog.LEVEL_WARN, source=server))

        bus.server_connected.connect(_on_srv_connected)
        bus.server_disconnected.connect(_on_srv_disconnected)
        bus.reconnecting.connect(_on_srv_reconnecting)

        # «Записать» в настройках (F-параметры/стенд) → секция 2 перечитывает данные
        self.settings_widget.f_parameters_wiget.saved.connect(page1._sec2.reload_params)

        from gui.windows.experiment_window.section1 import _CameraWidget
        cam_settings = self.settings_widget.cameras_widget

        def _refresh_cam_names():
            for cam in page1.findChildren(_CameraWidget):
                cam._lbl_cam_name.setText(cam._get_cam_name())
                cam._lbl_cam_name.adjustSize()

        cam_settings.settings_saved.connect(_refresh_cam_names)
        self._known_devices: list = []

        def _on_cam_found(found: list):
            if found != self._known_devices:
                self._known_devices = found
                cam_settings.update_devices(found)

        for i, cam in enumerate(page1.findChildren(_CameraWidget)):
            cam.recording_changed.connect(cam_settings.set_recording)
            cam.cameras_found.connect(_on_cam_found)
            cam.capabilities_found.connect(lambda res, fps, idx=i: cam_settings.set_capabilities(idx, res, fps))

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

    def _on_theme_changed(self, index: int):
        self._dark_mode = bool(self.settings_widget.theme_combo.itemData(index))
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

        # Журнал испытаний перечитываем при каждом заходе на вкладку
        if (getattr(self, "_export_page", None) is not None
                and self.stacked_widget.currentWidget() is self._export_page):
            self._export_page.reload()

        # Обновление состояния кнопок навигации
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

    def closeEvent(self, event):
        # остановить фоновые потоки захвата камер, иначе приложение висит на выходе
        from gui.windows.experiment_window.section1 import _CameraWidget
        for cam in self.findChildren(_CameraWidget):
            try:
                cam._close_camera()
            except Exception:
                pass
        super().closeEvent(event)
