from enum import Enum, auto          # Enum — базовый класс перечислений; auto() — автоматическое значение
from typing import Optional           # Optional[T] = T | None — для аннотации необязательных параметров
from PyQt6.QtWidgets import QPushButton  # стандартная кнопка Qt — базовый класс
from PyQt6.QtCore import QTimer, pyqtSignal  # QTimer — таймер повтора в HOLD-режиме; pyqtSignal — объявление сигналов


class ButtonMode(Enum):
    """Режим работы кнопки — передаётся в конструктор OpcUaButton."""
    CLICK  = auto()  # одиночный клик: emit True один раз при нажатии
    TOGGLE = auto()  # переключатель: каждый клик инвертирует внутренний флаг
    HOLD   = auto()  # удержание: emit True пока кнопка зажата, с повтором по таймеру


class OpcUaButton(QPushButton):

    # Сигналы
    state_changed = pyqtSignal(bool)  # испускается при любом изменении состояния (True/False)

    # Конструктор
    def __init__(
        self,
        off_text      : str,                             # текст кнопки в состоянии «выкл» (0 / False)
        on_text       : Optional[str]  = None,           # текст кнопки в состоянии «вкл»  (1 / True); None — не меняется
        off_color     : Optional[str]  = None,           # цвет фона в состоянии «выкл»; None — системный цвет
        on_color      : Optional[str]  = "#2ecc71",      # цвет фона в состоянии «вкл»;  None — системный цвет
        mode          : ButtonMode     = ButtonMode.CLICK,  # режим работы — по умолчанию одиночный клик
        hold_interval : int            = 100,            # интервал повтора в мс для HOLD-режима (100 мс = 10 раз/сек)
    ):
        super().__init__(off_text)  # инициализируем QPushButton с текстом

        self._mode         = mode         # сохраняем режим работы
        self._toggle_state = False        # внутренний флаг TOGGLE: False = выкл, True = вкл
        self._off_text     = off_text     # текст «выкл»
        self._on_text      = on_text      # текст «вкл» (None — текст не переключается)

        # строим stylesheet-строки из переданных цветов
        self._style_off = f"background-color: {off_color}; color: white;" if off_color else ""
        self._style_on  = f"background-color: {on_color};  color: white;" if on_color  else ""

        self._timer = QTimer(self)                        # таймер для HOLD-режима; self — родитель, чтобы авто-удалялся
        self._timer.setInterval(hold_interval)            # устанавливаем интервал повтора
        self._timer.timeout.connect(self._on_hold_tick)   # каждый тик таймера → _on_hold_tick

        self.clicked.connect(self._on_clicked)    # сигнал clicked  → обработчик клика
        self.pressed.connect(self._on_pressed)    # сигнал pressed  → обработчик нажатия
        self.released.connect(self._on_released)  # сигнал released → обработчик отпускания

        self.setStyleSheet(self._style_off)  # применяем начальный стиль сразу

    # ── Обработка событий ─────────────────────────────────────────────────────

    def _on_clicked(self):
        """Вызывается при каждом завершённом клике (pressed + released на кнопке)."""
        if self._mode == ButtonMode.TOGGLE:              # режим переключателя
            self._toggle_state = not self._toggle_state  # инвертируем флаг состояния
            self.state_changed.emit(self._toggle_state)  # сообщаем новое bool-состояние
        elif self._mode == ButtonMode.CLICK:      # режим одиночного клика
            self.state_changed.emit(True)         # однократный импульс True

    def _on_pressed(self):
        """Вызывается в момент нажатия кнопки (до отпускания)."""
        if self._mode == ButtonMode.HOLD:   # только в HOLD-режиме
            self.state_changed.emit(True)   # немедленный первый импульс True при нажатии
            self._timer.start()             # запускаем таймер повторов

    def _on_hold_tick(self):
        """Вызывается таймером каждые hold_interval мс пока кнопка удерживается."""
        self.state_changed.emit(True)  # повторный импульс True

    def _on_released(self):
        """Вызывается при отпускании кнопки."""
        if self._mode == ButtonMode.HOLD:   # только в HOLD-режиме
            self._timer.stop()              # останавливаем таймер повторов
            self.state_changed.emit(False)  # сообщаем «отпущено» — False

    # ── Внешний API ───────────────────────────────────────────────────────────

    def set_online(self, online: bool):
        """Переключить доступность кнопки (сервер подключён / отключён).
        При отключении сбрасывает активное состояние."""
        self.setEnabled(online)
        if not online:
            self.set_active(False)

    def set_active(self, state: bool):
        """
        Обновляет визуальное состояние кнопки (цвет + текст).
        В TOGGLE-режиме синхронизирует внутренний флаг.
        """
        if self._mode == ButtonMode.TOGGLE:  # в режиме переключателя синхронизируем внутренний флаг
            self._toggle_state = state       # чтобы следующий клик отсчитывал от актуального состояния

        self.setStyleSheet(self._style_on if state else self._style_off)  # применяем нужный стиль

        if self._on_text is not None:                                  # если задан текст «вкл»
            self.setText(self._on_text if state else self._off_text)   # переключаем подпись кнопки
