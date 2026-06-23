"""Экспорт (журнал испытаний) на SQLite.

В отличие от протокола (итоговый документ), это растущий реестр всех запусков,
в т.ч. прерванных. Каждое испытание — группа: строка-шапка в `tests`
(её id = «Испытание №*») + связанные записи событий и измерений по `test_id`.

Надёжность: запись идёт транзакциями в режиме WAL — прерывание/сбой приложения
не повреждает данные, ранее записанное сохраняется. Файл БД лежит рядом с
модулем (export.db), путь абсолютный — приложение переносимо.
"""
import sqlite3
from pathlib import Path
from datetime import datetime

_DB_PATH = Path(__file__).parent / "db" / "export.db"

# статусы испытания
STATUS_RUNNING   = "идёт"
STATUS_DONE      = "завершено"
STATUS_INTERRUPT = "прервано"
STATUS_ALARM     = "авария"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tests (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,  -- Испытание №*
    start_ts         TEXT NOT NULL,
    end_ts           TEXT,
    status           TEXT NOT NULL,
    gost             TEXT,
    method           TEXT,
    stand            TEXT,
    sample_name      TEXT,
    sample_id        TEXT,
    operator         TEXT,
    interrupt_reason TEXT
);
CREATE TABLE IF NOT EXISTS test_events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id  INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    ts       TEXT NOT NULL,
    step     TEXT,
    message  TEXT
);
CREATE TABLE IF NOT EXISTS test_measurements (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id  INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    ts       TEXT NOT NULL,
    step     TEXT,
    name     TEXT NOT NULL,
    value    TEXT,
    unit     TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_test ON test_events(test_id);
CREATE INDEX IF NOT EXISTS idx_meas_test   ON test_measurements(test_id);
"""


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)   # папка export/db
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")   # crash-safe дозапись
    return c


def init_db() -> None:
    """Создать БД/таблицы, если их ещё нет (идемпотентно)."""
    with _conn() as c:
        c.executescript(_SCHEMA)


# ── запись ────────────────────────────────────────────────────────────────────
def start_test(gost: str = None, method: str = None, stand: str = None,
               sample_name: str = None, sample_id: str = None,
               operator: str = None) -> int:
    """Открыть новое испытание (статус «идёт»). Возвращает его номер (id)."""
    init_db()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO tests (start_ts, status, gost, method, stand,"
            " sample_name, sample_id, operator) VALUES (?,?,?,?,?,?,?,?)",
            (_now(), STATUS_RUNNING, gost, method, stand,
             sample_name, sample_id, operator))
        return cur.lastrowid


def log_event(test_id: int, step: str = None, message: str = None) -> None:
    """Записать событие/шаг испытания."""
    with _conn() as c:
        c.execute(
            "INSERT INTO test_events (test_id, ts, step, message) VALUES (?,?,?,?)",
            (test_id, _now(), step, message))


def log_measurement(test_id: int, name: str, value, unit: str = None,
                    step: str = None) -> None:
    """Записать измерение/значение (value хранится как текст — годится для
    чисел и текстовых отметок вроде характера повреждения)."""
    with _conn() as c:
        c.execute(
            "INSERT INTO test_measurements (test_id, ts, step, name, value, unit)"
            " VALUES (?,?,?,?,?,?)",
            (test_id, _now(), step,
             name, None if value is None else str(value), unit))


def finish_test(test_id: int, status: str = STATUS_DONE,
                interrupt_reason: str = None) -> None:
    """Закрыть испытание с итоговым статусом (завершено/прервано/авария)."""
    with _conn() as c:
        c.execute(
            "UPDATE tests SET end_ts = ?, status = ?, interrupt_reason = ?"
            " WHERE id = ?",
            (_now(), status, interrupt_reason, test_id))


# ── выборки (для просмотрщика) ─────────────────────────────────────────────────
def list_tests(limit: int = None, status: str = None) -> list[dict]:
    """Список испытаний (новые сверху). Опц. фильтр по статусу."""
    init_db()
    q = "SELECT * FROM tests"
    args: list = []
    if status:
        q += " WHERE status = ?"
        args.append(status)
    q += " ORDER BY id DESC"
    if limit:
        q += " LIMIT ?"
        args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def get_test(test_id: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM tests WHERE id = ?", (test_id,)).fetchone()
        return dict(r) if r else None


def get_events(test_id: int) -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM test_events WHERE test_id = ? ORDER BY id", (test_id,))]


def get_measurements(test_id: int) -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM test_measurements WHERE test_id = ? ORDER BY id", (test_id,))]


def delete_test(test_id: int) -> None:
    """Удалить испытание со всеми связанными записями (каскад)."""
    with _conn() as c:
        c.execute("DELETE FROM tests WHERE id = ?", (test_id,))
