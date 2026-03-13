from typing import Optional
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import QTimer, QObject, pyqtSignal, pyqtSlot


class WriteChannel(QObject):
    """
    Канал записи — связывает Qt сигнал с конкретным тегом backend.

    Хранит server_id и node_id внутри себя.
    Кнопка не знает про адреса — просто подключается к каналу.

    ПРИМЕР:
    =======
        channel = WriteChannel(backend, "OPC1", "ns=2;s=Start")

        # Чистое подключение сигнал → слот, без lambda и адресов
        btn.value_changed.connect(channel.write)

        # Несколько кнопок к одному каналу
        btn_start.value_changed.connect(channel.write)
        btn_stop.value_changed.connect(channel.write)
    """

    def __init__(self, backend, server_id: str, node_id: str, parent=None):
        super().__init__(parent)
        self._backend   = backend    # OpcUaBackend
        self._server_id = server_id  # ID сервера
        self._node_id   = node_id    # NodeId тега

    @pyqtSlot(int)
    def write(self, value: int):
        """Слот для подключения к value_changed(int) кнопки"""
        self._backend.write_node(self._server_id, self._node_id, value)

    @pyqtSlot(bool)
    def write_bool(self, value: bool):
        """Слот для подключения к state_changed(bool) кнопки"""
        self._backend.write_node(self._server_id, self._node_id, int(value))

    def feedback_to(self, button: "OpcUaButton"):
        """
        Возвращает слот для подключения write_completed → подсветка кнопки.
        Фильтрует по своему node_id — реагирует только на свой тег.

        Использование:
            backend.write_completed.connect(channel.feedback_to(btn))
        """
        server_id = self._server_id  # захватываем в замыкание один раз
        node_id   = self._node_id

        @pyqtSlot(str, str, bool)
        def _slot(srv: str, nid: str, success: bool):
            # Реагируем только на свой сервер + тег — остальные игнорируем
            if srv == server_id and nid == node_id:
                button.set_active(success)

        return _slot

# Стиль по умолчанию — без изменений
_STYLE_DEFAULT = ""

# Стиль активного состояния — зелёный фон, белый текст
_STYLE_ACTIVE  = "background-color: #2ecc71; color: white;"


class OpcUaButton(QPushButton):
    """
    Универсальная кнопка с двумя режимами и подсветкой состояния.

    СИГНАЛ:
    =======
    state_changed(bool) — эмитится при взаимодействии с кнопкой.
    Подключай к любому слоту снаружи.

    РЕЖИМЫ:
    =======
    hold=False (по умолчанию) — обычный клик:
        Клик → state_changed(True)

    hold=True — удержание:
        Нажатие    → state_changed(True),  повторяет каждые hold_interval мс
        Отпускание → state_changed(False)

    FEEDBACK:
    =========
    set_active(bool) — слот для подсветки и опциональной смены текста.

    ПРИМЕР:
    =======
        btn = OpcUaButton("Пуск", hold=True, active_text="Работает")

        # Создаём канал — он хранит адрес тега
        channel = WriteChannel(backend, "OPC1", "ns=2;s=Start")

        # Чистое Qt подключение — никаких lambda, никаких адресов в GUI
        btn.value_changed.connect(channel.write)       # int: 1/0
        btn.state_changed.connect(channel.write_bool)  # bool: True/False

        # Feedback — подсветка кнопки по состоянию
        backend.write_completed.connect(channel.feedback_to(btn))
    """

    # bool сигнал — True при нажатии/клике, False при отпускании (hold режим)
    # Подключай к write_bool() канала или к любому слоту принимающему bool
    state_changed = pyqtSignal(bool)

    # int сигнал — 1 при нажатии, 0 при отпускании
    # Подключай к write() канала: btn.value_changed.connect(channel.write)
    value_changed = pyqtSignal(int)

    def __init__(
        self,
        text: str,                             # текст на кнопке (дефолтное состояние)
        hold: bool = False,                    # True — режим удержания
        hold_interval: int = 100,              # интервал повторной отправки при удержании (мс)
        active_text: Optional[str] = None,     # текст при set_active(True), None — не менять
        parent=None
    ):
        super().__init__(text, parent)

        self._hold         = hold          # флаг режима удержания
        self._default_text = text          # исходный текст для сброса
        self._active_text  = active_text   # текст в активном состоянии

        # Таймер для периодической отправки сигнала при удержании
        self._timer = QTimer(self)
        self._timer.setInterval(hold_interval)        # интервал срабатывания
        self._timer.timeout.connect(self._on_hold_tick)  # слот по таймеру

        # Подключаем Qt сигналы кнопки к внутренним слотам
        self.clicked.connect(self._on_clicked)    # обычный клик
        self.pressed.connect(self._on_pressed)    # момент нажатия
        self.released.connect(self._on_released)  # момент отпускания

    # ------------------------------------------------------------------
    # Обычный режим (hold=False)
    # ------------------------------------------------------------------

    def _on_clicked(self):
        # Срабатывает только в обычном режиме
        if not self._hold:
            self.state_changed.emit(True)
            self.value_changed.emit(1)

    # ------------------------------------------------------------------
    # Режим удержания (hold=True)
    # ------------------------------------------------------------------

    def _on_pressed(self):
        # Нажатие — эмитим True/1 и запускаем таймер повторения
        if self._hold:
            self.state_changed.emit(True)
            self.value_changed.emit(1)
            self._timer.start()

    def _on_hold_tick(self):
        # Таймер — повторяем True/1 каждые hold_interval мс пока кнопка зажата
        self.state_changed.emit(True)
        self.value_changed.emit(1)

    def _on_released(self):
        # Отпускание — останавливаем таймер и эмитим False/0
        if self._hold:
            self._timer.stop()
            self.state_changed.emit(False)
            self.value_changed.emit(0)

    # ------------------------------------------------------------------
    # Feedback — подсветка и текст по состоянию
    # ------------------------------------------------------------------

    def set_active(self, state: bool):
        """
        Устанавливает визуальное состояние кнопки.
        Подключай к любому Qt сигналу через lambda.

        state=True  → зелёный фон + active_text (если задан)
        state=False → обычный стиль + default_text (если active_text задан)
        """
        # Меняем стиль
        self.setStyleSheet(_STYLE_ACTIVE if state else _STYLE_DEFAULT)

        # Меняем текст только если active_text был задан
        if self._active_text is not None:
            self.setText(self._active_text if state else self._default_text)

    def set_state_texts(self, default_text: str, active_text: str):
        """Задать или изменить тексты для каждого состояния"""
        self._default_text = default_text  # текст неактивного состояния
        self._active_text  = active_text   # текст активного состояния

    # ------------------------------------------------------------------
    # Сеттеры
    # ------------------------------------------------------------------

    def set_hold_mode(self, enabled: bool):
        """Переключить режим удержания во время работы"""
        if self._hold and not enabled:
            self._timer.stop()  # останавливаем таймер если выключаем hold
        self._hold = enabled
