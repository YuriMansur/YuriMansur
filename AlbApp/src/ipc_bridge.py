"""
ipc_bridge.py — мост между рабочим процессом и GUI.

QTimer раз в DRAIN_MS дренирует live_q и транслирует сообщения в bus-сигналы.
bus.cmd_* → cmd_q → рабочий процесс записывает тег на PLC.
"""

import queue as _queue
from datetime import datetime, timezone

from PyQt6.QtCore import QObject, QTimer
from protocol_backend.event_bus import bus

# NodeId тегов — должны совпадать с worker_process/main.py
_BASE = "ns=4;s=|var|Xinje-Cortex-Linux-SM-CNC.Application.MAIN.StandLogicEx."

NOWSETPOINT_NID   = _BASE + "nowSetpoint"
CMD_POWER_ON_NID  = _BASE + "cmdPowerOn"
CMD_POWER_OFF_NID = _BASE + "cmdPowerOff"
CMD_FORWARD_NID   = _BASE + "cmdForwardJogging"
CMD_BACKWARD_NID  = _BASE + "cmdBackwardJogging"
CMD_CTRL_NID      = _BASE + "cmdChangeControlMode"


class IpcBridge(QObject):
    """Соединяет рабочий процесс с шиной событий GUI.

    live_q → bus-сигналы (тензо, перемещение, состояния кнопок, статус сервера)
    bus.cmd_* → cmd_q → рабочий процесс
    """

    DRAIN_MS = 50  # интервал дрейна очереди (мс)

    def __init__(self, live_q, cmd_q, parent=None):
        super().__init__(parent)
        self._live_q = live_q
        self._cmd_q  = cmd_q

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._drain)
        self._timer.start(self.DRAIN_MS)

        # Команды от GUI → cmd_q → рабочий процесс
        bus.cmd_control_mode.connect(lambda v: self._cmd_q.put_nowait({'nid': CMD_CTRL_NID,      'val': int(v)}))
        bus.cmd_forward     .connect(lambda v: self._cmd_q.put_nowait({'nid': CMD_FORWARD_NID,   'val': int(v)}))
        bus.cmd_backward    .connect(lambda v: self._cmd_q.put_nowait({'nid': CMD_BACKWARD_NID,  'val': int(v)}))
        bus.cmd_power_on    .connect(lambda v: self._cmd_q.put_nowait({'nid': CMD_POWER_ON_NID,  'val': int(v)}))
        bus.cmd_power_off   .connect(lambda v: self._cmd_q.put_nowait({'nid': CMD_POWER_OFF_NID, 'val': int(v)}))

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
            self._dispatch(msg)

    def _dispatch(self, msg: dict):
        t = msg.get('type')
        if t == 'tenza':
            bus.tenza_points.emit(msg['times'], msg['vals'])
        elif t == 'displacement':
            bus.displacement_points.emit(msg['times'], msg['vals'])
        elif t == 'setpoint':
            bus.nowSetpoint_points.emit(msg['times'], msg['vals'])
        elif t == 'tenza_array':
            bus.tenza_array_updated.emit(msg['data'])
        elif t == 'connected':
            bus.server_connected.emit(msg['server'])
        elif t == 'disconnected':
            bus.server_disconnected.emit(msg['server'])
        elif t == 'reconnecting':
            bus.reconnecting.emit(msg['server'], msg['interval'])
        elif t == 'tag':
            self._dispatch_tag(msg['nid'], msg['val'])

    # Таблица: nid → действие с bus
    _TAG_DISPATCH = {
        CMD_CTRL_NID:      lambda v: bus.state_control_mode.emit(bool(v)),
        CMD_FORWARD_NID:   lambda v: bus.state_forward     .emit(bool(v)),
        CMD_BACKWARD_NID:  lambda v: bus.state_backward    .emit(bool(v)),
        CMD_POWER_ON_NID:  lambda v: bus.state_power_on    .emit(bool(v)),
        CMD_POWER_OFF_NID: lambda v: bus.state_power_off   .emit(bool(v)),
        NOWSETPOINT_NID:   lambda v: bus.nowSetpoint_points.emit(
            [datetime.now(timezone.utc).timestamp()], [float(v)]
        ),
    }

    def _dispatch_tag(self, nid: str, val):
        fn = self._TAG_DISPATCH.get(nid)
        if fn:
            fn(val)
