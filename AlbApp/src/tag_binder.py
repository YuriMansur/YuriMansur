"""TagBinder — удобная привязка Qt-слотов к переменным из servers.json.

Обёртка над шиной (event_bus): вместо ручной фильтрации «если имя == ...»
в каждом слоте — точечная подписка на конкретный тег/поток и запись на ПЛК
по имени. Имена берутся из patch/servers.json (тоже подкладывается стендом).

  tags.on("cmdPowerOn", cb)   # cb(value) вызовется при изменении тега
  tags.write("cmdPowerOn", 1) # запись на ПЛК (через bus.command → worker)
"""
import json
from pathlib import Path

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

    # ── маршрутизация сигналов шины в адресные колбэки ──────────────────────
    def _route(self, name: str, val) -> None:
        for cb in self._cbs.get(name, []):
            cb(val)

    def _route_points(self, name: str, _t, v) -> None:
        for cb in self._cbs.get(name, []):
            cb(v)


# единый экземпляр на приложение (как bus)
tags = TagBinder()
