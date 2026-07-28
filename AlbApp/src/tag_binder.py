"""TagBinder — удобная привязка Qt-слотов к переменным из servers.json.

Обёртка над шиной (event_bus): вместо ручной фильтрации «если имя == ...»
в каждом слоте — точечная подписка на конкретный тег/поток и запись на ПЛК
по имени. Имена берутся из patch/servers.json (тоже подкладывается стендом).

  tags.on("cmdPowerOn", cb)   # cb(value) вызовется при изменении тега
  tags.write("cmdPowerOn", 1) # запись на ПЛК (через bus.command → worker)
  link.state                  # текущее состояние связи с ПЛК (см. LinkState)
"""
import json
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from event_bus import bus

_SERVERS = Path(__file__).parent.parent / "patch" / "servers.json"


def _known_names() -> set[str]:
    """Имена тегов + имена потоков (из logging.ring) — для мягкой валидации."""
    try:
        data = json.loads(_SERVERS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    names: set[str] = set()
    for srv in data.get("servers", []):
        names.update(srv.get("tags", []))
        for r in srv.get("logging", {}).get("ring", []):
            for k in ("points_msg", "raw_array_msg", "scalar_msg"):
                if r.get(k):
                    names.add(r[k])
    return names


class TagBinder:
    def __init__(self):
        self._known = _known_names()
        self._cbs: dict[str, list] = {}
        self._last: dict = {}
        bus.tag_state.connect(self._remember)
        bus.tag_state.connect(self._route)
        bus.stream_array.connect(self._route)
        bus.stream_points.connect(self._route_points)

    def on(self, name: str, callback) -> None:
        """Подписаться на конкретный тег/поток. callback получает значение."""
        if self._known and name not in self._known:
            print(f"[TagBinder] предупреждение: '{name}' нет в servers.json")
        self._cbs.setdefault(name, []).append(callback)

    def write(self, tag: str, value) -> None:
        """Запись значения тега на ПЛК."""
        bus.command.emit(tag, int(value))

    def last(self, name: str, default=None):
        """Последнее известное значение тега.

        Сигналы шины событийные: значение приходит по изменению, и виджет,
        созданный позже, его уже не увидит. Кэш позволяет прочитать состояние
        сразу при построении — как link.state для состояния связи.
        """
        return self._last.get(name, default)

    def _remember(self, name: str, val) -> None:
        self._last[name] = val

    # ── маршрутизация сигналов шины в адресные колбэки ──────────────────────
    def _route(self, name: str, val) -> None:
        for cb in self._cbs.get(name, []):
            cb(val)

    def _route_points(self, name: str, _t, v) -> None:
        for cb in self._cbs.get(name, []):
            cb(v)


class LinkState(QObject):
    """Текущее состояние связи с ПЛК — с запоминанием последнего значения.

    Сигналы шины событийные: виджет, построенный уже ПОСЛЕ подключения, события
    не увидит и навсегда останется с «нет связи». Здесь состояние кэшируется
    один раз на приложение, поэтому виджет читает его сразу при построении
    (link.state), а на изменения подписывается через link.changed.

    Разрыв воркер шлёт парой disconnected → reconnecting, поэтому после обрыва
    видимое состояние — RECONNECTING (авто-переподключение уже идёт).
    """
    UNKNOWN      = "unknown"    # событий ещё не было — связь неизвестна
    UP           = "up"
    DOWN         = "down"
    RECONNECTING = "reconnecting"

    changed = pyqtSignal(str, str)   # (состояние, имя сервера)

    def __init__(self):
        super().__init__()
        self.state  = self.UNKNOWN
        self.server = ""
        bus.server_connected   .connect(lambda srv:     self._set(self.UP, srv))
        bus.server_disconnected.connect(lambda srv:     self._set(self.DOWN, srv))
        bus.reconnecting       .connect(lambda srv, _i: self._set(self.RECONNECTING, srv))

    def _set(self, state: str, server: str) -> None:
        if (state, server) == (self.state, self.server):
            return                      # состояние не изменилось — не дёргаем виджеты
        self.state, self.server = state, server
        self.changed.emit(state, server)


# единые экземпляры на приложение (как bus)
tags = TagBinder()
link = LinkState()
