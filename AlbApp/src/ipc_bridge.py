"""
ipc_bridge.py — мост между рабочим процессом и GUI.

QTimer раз в DRAIN_MS дренирует live_q и транслирует сообщения в bus-сигналы.
bus.command → cmd_q → рабочий процесс записывает тег на PLC.

Мост device-agnostic: переносит только (имя, значение/данные), не зная ни одного
конкретного тега. Что есть что — решают конфиг (worker) и виджеты GUI.
"""

import queue as _queue

from PyQt6.QtCore import QObject, QTimer
from event_bus import bus


class IpcBridge(QObject):
    """Соединяет рабочий процесс с шиной событий GUI.

    live_q → bus-сигналы (точки, массивы, состояния тегов, статус сервера)
    bus.command → cmd_q → рабочий процесс
    """

    DRAIN_MS = 50  # интервал дрейна очереди (мс)

    def __init__(self, live_q, cmd_q, parent=None):
        super().__init__(parent)
        self._live_q = live_q
        self._cmd_q  = cmd_q

        # Таблица: тип сообщения из live_q → действие с шиной (всё по имени).
        self._handlers = {
            'points':       lambda m: bus.stream_points.emit(m['name'], m['times'], m['vals']),
            'array':        lambda m: bus.stream_array.emit(m['name'], m['data']),
            'rate':         lambda m: bus.stream_rate.emit(m['name'], m['step_ms']),
            'tag':          lambda m: bus.tag_state.emit(m['name'], m['val']),
            'connected':    lambda m: bus.server_connected.emit(m['server']),
            'disconnected': lambda m: bus.server_disconnected.emit(m['server']),
            'reconnecting': lambda m: bus.reconnecting.emit(m['server'], m['interval']),
            'error':        lambda m: bus.server_error.emit(m['server'], m['error']),
        }

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._drain)
        self._timer.start(self.DRAIN_MS)

        # Команды от GUI → cmd_q → worker (по логическому имени тега)
        bus.command.connect(
            lambda name, val: self._cmd_q.put_nowait({'cmd': name, 'val': int(val)}))

    def stop(self):
        """Остановить дрейн очереди (вызывать при закрытии приложения)."""
        self._timer.stop()

    # ── Дрейн очереди ─────────────────────────────────────────────────────────

    def _drain(self):
        while True:
            try:
                msg = self._live_q.get_nowait()
            except _queue.Empty:
                break
            except Exception as e:
                print(f"[IpcBridge] drain error: {e}")
                break
            # Одно битое сообщение не должно ронять весь тик дрейна.
            try:
                self._dispatch(msg)
            except Exception as e:
                print(f"[IpcBridge] dispatch error: {e} | msg={msg}")

    def _dispatch(self, msg: dict):
        handler = self._handlers.get(msg.get('type'))
        if handler:
            handler(msg)
