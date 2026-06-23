"""Системный лог приложения на SQLite (отдельно от экспорта испытаний).

Экспорт испытаний (export.py) отвечает на «что было в испытании №N».
Этот лог — эксплуатационный/аудиторский: связь с ПЛК, аварии ПЛК, действия
оператора (нажатия кнопок), системные события. Отдельный файл logs.db, т.к.
у логов другой жизненный цикл (их много, их периодически чистят — purge()).

Надёжность: WAL + транзакции, дозапись не повреждается при прерывании.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta

_DB_PATH = Path(__file__).parent / "db" / "logs.db"

# уровни
LEVEL_INFO  = "INFO"
LEVEL_WARN  = "WARN"
LEVEL_ALARM = "ALARM"

# категории
CAT_CONN   = "связь"
CAT_PLC    = "плк"
CAT_ACTION = "действие"
CAT_SYS    = "система"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    level    TEXT,
    category TEXT,
    source   TEXT,
    message  TEXT,
    details  TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_ts  ON app_log(ts);
CREATE INDEX IF NOT EXISTS idx_log_cat ON app_log(category);
CREATE INDEX IF NOT EXISTS idx_log_lvl ON app_log(level);
"""


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)   # папка logger/db
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode = WAL")
    return c


def init_db() -> None:
    with _conn() as c:
        c.executescript(_SCHEMA)


# ── запись ────────────────────────────────────────────────────────────────────
def log(category: str, message: str, level: str = LEVEL_INFO,
        source: str = None, details: dict = None) -> None:
    """Записать событие в системный лог."""
    init_db()
    with _conn() as c:
        c.execute(
            "INSERT INTO app_log (ts, level, category, source, message, details)"
            " VALUES (?,?,?,?,?,?)",
            (_now(), level, category, source, message,
             json.dumps(details, ensure_ascii=False) if details else None))


def log_connection(server: str, state: str, level: str = LEVEL_INFO) -> None:
    """Событие связи: подключено / отключено / переподключение."""
    log(CAT_CONN, f"{server}: {state}", level=level, source=server)


def log_alarm(source: str, message: str) -> None:
    """Авария ПЛК (уровень ALARM)."""
    log(CAT_PLC, message, level=LEVEL_ALARM, source=source)


def log_action(message: str, source: str = "UI") -> None:
    """Действие оператора (нажатие кнопки и т.п.)."""
    log(CAT_ACTION, message, level=LEVEL_INFO, source=source)


# ── выборки / обслуживание ────────────────────────────────────────────────────
def list_logs(level: str = None, category: str = None,
              since: str = None, limit: int = 1000) -> list[dict]:
    """Записи лога (новые сверху) с опц. фильтрами."""
    init_db()
    q = "SELECT * FROM app_log"
    cond, args = [], []
    if level:
        cond.append("level = ?");    args.append(level)
    if category:
        cond.append("category = ?"); args.append(category)
    if since:
        cond.append("ts >= ?");      args.append(since)
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY id DESC"
    if limit:
        q += " LIMIT ?"; args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def purge(days: int = 30) -> int:
    """Удалить записи старше N дней (ретенция). Возвращает число удалённых."""
    init_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(sep=" ", timespec="seconds")
    with _conn() as c:
        cur = c.execute("DELETE FROM app_log WHERE ts < ?", (cutoff,))
        return cur.rowcount
