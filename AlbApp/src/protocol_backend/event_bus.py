"""
event_bus.py — глобальная шина событий.

Менеджер пишет в шину, окно читает из шины.
Ни менеджер, ни окно не знают друг о друге.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    # Менеджер → окно
    server_connected    = pyqtSignal(str)
    server_disconnected = pyqtSignal(str)
    server_error        = pyqtSignal(str, str)
    reconnecting        = pyqtSignal(str, int)
    data_updated        = pyqtSignal(str, str, object)
    write_completed     = pyqtSignal(str, str, bool)

    # GUI → менеджер (нажатия кнопок, без тегов)
    cmd_control_mode    = pyqtSignal(bool)
    cmd_forward         = pyqtSignal(bool)
    cmd_backward        = pyqtSignal(bool)
    cmd_power_on        = pyqtSignal(bool)
    cmd_power_off       = pyqtSignal(bool)

    # Менеджер → GUI (состояния кнопок от PLC)
    state_control_mode  = pyqtSignal(bool)
    state_forward       = pyqtSignal(bool)
    state_backward      = pyqtSignal(bool)
    state_power_on      = pyqtSignal(bool)
    state_power_off     = pyqtSignal(bool)

    # Менеджер → GUI (данные массива тензодатчиков)
    tenza_array_updated = pyqtSignal(list)

    # TenzaProcessor → TrendsWidget (готовые точки для live-графика)
    tenza_points = pyqtSignal(list, list)  # (timestamps: list[float], values: list[float])


bus = EventBus()
