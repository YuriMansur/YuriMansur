from PyQt6.QtWidgets import (QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QPushButton)
from PyQt6.QtCore import QTimer, QPoint, QEvent, QPropertyAnimation, QEasingCurve
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
    # Боковая панель навигации: открывается кнопкой «меню» (три полоски) в
    # шапке, прячется при выборе вкладки или когда курсор с неё уходит.
    # Контент занимает всё окно, панель ложится поверх него.
    NAV_WIDTH   = 230   # ширина панели, px
    NAV_ANIM_MS = 180
    STAND_TITLE_COLOR = "#f1c40f"   # надпись с номером стенда в шапке — жёлтый

    def __init__(self):
        super().__init__()
# Настройка главного экрана

        # Настройка окна: заголовок и шапка — с именем стенда этого процесса
        import stand
        self._stand = stand.current()
        self.setWindowTitle(f"AlbApp — {self._stand['title']}")

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

        self._dark_mode = True

        # Расстояние между виджетами внутри лэйаута
        self.main_layout.setSpacing(0)
        main_layout = self.main_layout

        # Шапка: слева кнопка меню вкладок, по центру крупно номер стенда —
        # окон может быть несколько (по одному на стенд), оператор должен
        # видеть, к какому относится это
        from PyQt6.QtWidgets import QLabel, QHBoxLayout
        from PyQt6.QtCore import Qt, QSize
        self._header = QWidget()
        self._header.setObjectName("stand_header")
        self._header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._header.setFixedHeight(44)
        hdr = QHBoxLayout(self._header)
        hdr.setContentsMargins(6, 4, 6, 4)
        hdr.setSpacing(0)
        self._btn_menu = QPushButton()
        self._btn_menu.setObjectName("menu_btn")
        self._btn_menu.setFixedSize(36, 36)
        self._btn_menu.setIconSize(QSize(22, 22))
        self._btn_menu.setToolTip("Меню вкладок")
        self._btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_menu.clicked.connect(lambda: self._set_nav_shown(not self._nav_shown))
        # Кнопка сброса аварий — в правом углу шапки, всегда на виду.
        # Иконка — треугольник аварии в круговой стрелке, рисуется кодом
        # (gui/icons.py), белым по красному фону кнопки.
        from PyQt6.QtGui import QIcon
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
        # слева — кнопка меню в контейнере той же ширины, что «Сброс аварий»
        # справа: тогда название стенда стоит точно по центру
        left = QWidget()
        left_lay = QHBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(self._btn_menu)
        left_lay.addStretch()
        left.setFixedWidth(self._btn_reset_nav.sizeHint().width())
        hdr.addWidget(left)
        self._stand_header = QLabel(self._stand["title"])
        self._stand_header.setObjectName("stand_title")
        self._stand_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.addWidget(self._stand_header, 1)
        hdr.addWidget(self._btn_reset_nav)
        main_layout.addWidget(self._header)

        # Виджет контента
        content_widget = QWidget()

        # Добавление лэйаута
        content_layout = QVBoxLayout(content_widget)

        # Внутренние отступы лэйаута.
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Контейнер для страниц
        self.stacked_widget = QStackedWidget()

        # Боковая панель — поверх контента, вне лэйаута. Создаётся до страниц:
        # create_pages вешает на её кнопку «Сброс аварий» запись тега
        self.create_side_navigation()

        # Создание страниц
        self.create_pages()

        # Добавление контейнера в лэйаут контента
        content_layout.addWidget(self.stacked_widget)

        # Добавление контента в основной лэйаут
        main_layout.addWidget(content_widget)

        # Устанавливаем первую страницу активной
        self.switch_page(0)
        QTimer.singleShot(0, self.apply_theme)

#Создание боковой панели навигации
    def create_side_navigation(self):

        # Панель — дочерний виджет центрального, но не в его лэйауте:
        # позиционируется вручную и накладывается поверх контента
        central = self.centralWidget()
        self.nav_panel = QWidget(central)
        self.nav_panel.setObjectName("nav_panel")
        # иначе фон из стиля по objectName у голого QWidget не рисуется
        from PyQt6.QtCore import Qt
        self.nav_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.nav_panel.setFixedWidth(self.NAV_WIDTH)

        # Создание основного лэйаута панели навигации
        nav_layout = QVBoxLayout(self.nav_panel)

        # Внутренние отступы лэйаута
        nav_layout.setContentsMargins(6, 10, 6, 10)

        # Расстояние между виджетами внутри лэйаута
        nav_layout.setSpacing(2)

        # Кнопки навигации
        self.nav_buttons = []

        # Кортеж стилизации кнопок
        # значки рисуются кодом (gui/icons.py) и перекрашиваются вместе с надписью
        page_data = [
            (" Испытания",          "#1abc9c", "flask"),
            (" Видеоналожение",     "#6c5ce7", "video"),
            (" Тренды",             "#3498db", "chart"),
            (" Сообщения",          "#e67e22", "chat"),
            (" Экспорт",            "#27ae60", "export"),
            (" Протоколы/Журналы",  "#e84393", "doc"),
            (" Настройки",          "#9b59b6", "gear"),
        ]

        # Создание кнопок навигации
        for i, (title, color, icon_kind) in enumerate(page_data):

            # Создание кнопки навигации
            btn = NavigationButton(title, color, icon_kind, vertical=True)

            # Добавление возможности переключения
            btn.setCheckable(True)

            # Подключение сигнала клика к переключению страницы
            btn.clicked.connect(lambda checked, idx = i: self.switch_page(idx))

            # Добавление кнопки в список
            self.nav_buttons.append(btn)

            # Добавление кнопки в лайаут панели навигации
            nav_layout.addWidget(btn)

        # Растяжка: кнопки вкладок прижаты к верху панели
        nav_layout.addStretch()

        # Выезд/уход панели — анимация позиции; скрытое состояние — за левым краем
        self._nav_shown = False
        self._nav_anim = QPropertyAnimation(self.nav_panel, b"pos", self)
        self._nav_anim.setDuration(self.NAV_ANIM_MS)
        self._nav_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._layout_nav_panel()
        central.installEventFilter(self)     # подгонять высоту под окно

        # Слежение за курсором (как у накладной панели камер): открытая панель
        # прячется, когда курсор с неё уходит
        self._nav_timer = QTimer(self)
        self._nav_timer.setInterval(80)
        self._nav_timer.timeout.connect(self._track_nav_hover)
        self._nav_timer.start()

    def _nav_top(self) -> int:
        """Верх панели — под шапкой: кнопка ☰ и название стенда остаются видны,
        повторное нажатие ☰ закрывает панель."""
        hdr = getattr(self, "_header", None)
        return hdr.geometry().bottom() + 1 if hdr is not None else 0

    def _layout_nav_panel(self):
        """Панель от низа шапки до низа окна; скрытая — за левым краем."""
        central = self.centralWidget()
        top = self._nav_top()
        self.nav_panel.setFixedHeight(max(0, central.height() - top))
        if self._nav_anim.state() != QPropertyAnimation.State.Running:
            self.nav_panel.move(0 if self._nav_shown else -self.NAV_WIDTH, top)
        self.nav_panel.raise_()

    def _set_nav_shown(self, shown: bool):
        if shown == self._nav_shown:
            return
        self._nav_shown = shown
        self.nav_panel.raise_()
        self._nav_anim.stop()
        self._nav_anim.setStartValue(self.nav_panel.pos())
        self._nav_anim.setEndValue(QPoint(0 if shown else -self.NAV_WIDTH, self._nav_top()))
        self._nav_anim.start()

    def _track_nav_hover(self):
        if not self._nav_shown:
            return
        from PyQt6.QtGui import QCursor
        central = self.centralWidget()
        pos = central.mapFromGlobal(QCursor.pos())
        # небольшой запас справа, чтобы панель не дёргалась на границе
        if not central.rect().contains(pos) or pos.x() > self.NAV_WIDTH + 12:
            self._set_nav_shown(False)

    def eventFilter(self, obj, event):
        if obj is self.centralWidget() and event.type() == QEvent.Type.Resize:
            self._layout_nav_panel()
        return super().eventFilter(obj, event)

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
        self._btn_reset_nav.clicked.connect(_reset_faults)   # «Сброс аварий» в правом углу шапки

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
        # шапка с номером стенда и кнопкой меню
        if getattr(self, "_header", None) is not None:
            from PyQt6.QtGui import QIcon
            from gui.icons import make_icon
            # Фон шапки — нейтральный по теме; сама надпись — одним ярким
            # цветом, который в интерфейсе больше нигде не занят (вкладки —
            # бирюза/синий/оранжевый/зелёный/розовый/фиолетовый, красный — за
            # аварией и сбросом). Жёлтый — свободен и виден в обеих темах.
            fg, bg = (("#ecf0f1", "#2b2b2b") if self._dark_mode else ("#1a1a1a", "#dcdcdc"))
            accent = self.STAND_TITLE_COLOR
            self._header.setStyleSheet(
                f"QWidget#stand_header {{ background: {bg}; border-radius: 4px; }}"
                f"QLabel#stand_title {{ color: {accent}; font-size: 22px; font-weight: bold;"
                " letter-spacing: 1px; }"
                "QPushButton#menu_btn { background: transparent; border: none; border-radius: 4px; }"
                "QPushButton#menu_btn:hover { background: rgba(128, 128, 128, 0.25); }")
            self._btn_menu.setIcon(QIcon(make_icon("menu", fg, 22)))
        # фон панели непрозрачный — она ложится поверх контента
        if getattr(self, "nav_panel", None) is not None:
            bg, border = (("#232323", "#4a4a4a") if self._dark_mode
                          else ("#e9e9e9", "#b8b8b8"))
            self.nav_panel.setStyleSheet(
                f"QWidget#nav_panel {{ background: {bg}; border-right: 1px solid {border}; }}")
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

        # вкладка выбрана — панель уезжает, контент открыт целиком
        if getattr(self, "nav_panel", None) is not None:
            self._set_nav_shown(False)

    def closeEvent(self, event):
        # остановить фоновые потоки захвата камер, иначе приложение висит на выходе
        from gui.windows.experiment_window.section1 import _CameraWidget
        for cam in self.findChildren(_CameraWidget):
            try:
                cam._close_camera()
            except Exception:
                pass
        super().closeEvent(event)
