"""
event_bus.py — глобальная шина событий (GUI-сторона).

worker (через ipc_bridge) пишет в шину, виджеты читают. Ни worker, ни виджеты
не знают друг о друге. Сигналы — ОБОБЩЁННЫЕ, параметризованы именем тега/потока,
а не конкретным устройством: одна и та же шина работает под любой servers.json.
Какой тег/поток к чему относится — решают конфиг (worker) и сами виджеты.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    # ── статус сервера ──────────────────────────────────────────────────────
    server_connected    = pyqtSignal(str)
    server_disconnected = pyqtSignal(str)
    server_error        = pyqtSignal(str, str)
    reconnecting        = pyqtSignal(str, int)

    # ── GUI → worker ────────────────────────────────────────────────────────
    command       = pyqtSignal(str, object)        # (имя_тега, значение) — запись на ПЛК

    # ── worker → GUI ────────────────────────────────────────────────────────
    tag_state     = pyqtSignal(str, object)        # (имя_тега, значение)        — состояние (кнопки)
    stream_points = pyqtSignal(str, list, list)    # (имя_потока, times, values) — точки для графика
    stream_array  = pyqtSignal(str, list)          # (имя_потока, data)          — сырой массив

    # ── системный лог: мгновенный вывод строки в «Сообщения» ─────────────────
    log_event     = pyqtSignal(object)             # запись лога (dict) — real-time, без опроса БД

    # ── диагностика (worker → лог); пока зарезервировано ─────────────────────
    data_updated    = pyqtSignal(str, str, object)
    write_completed = pyqtSignal(str, str, bool)


bus = EventBus()
