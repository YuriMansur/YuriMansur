"""stand.py — текущий стенд процесса.

Приложение работает по одному стенду на процесс: лаунчер (app.py без
аргументов) показывает список стендов из patch/stands.json и запускает на
каждый выбранный отдельный процесс `app.py --stand <id>`. Идентификатор
стенда живёт в переменной окружения ALB_STAND — её наследует и рабочий
процесс (OPC UA + Influx), поэтому воркер и GUI видят один и тот же стенд.

Стенды различаются только адресом ПЛК (сигналы одинаковые — тот же
servers.json) и своими данными: журнал сообщений, экспорт, протоколы и
настройки камер лежат в stands/<id>/. InfluxDB общая — точки разделяются
тегом `server` (= id стенда).
"""

import json
import os
import sys
from pathlib import Path

ENV_VAR   = "ALB_STAND"
_ROOT     = Path(__file__).resolve().parent.parent          # AlbApp/
_CFG      = _ROOT / "patch" / "stands.json"
_DATA_DIR = _ROOT / "stands"


def load_stands() -> list[dict]:
    """Список стендов из конфига (id, title, endpoint)."""
    try:
        return json.loads(_CFG.read_text(encoding="utf-8")).get("stands", [])
    except (OSError, ValueError) as e:
        print(f"[stand] не удалось прочитать {_CFG.name}: {e}")
        return []


def current_id() -> str | None:
    """id стенда этого процесса (из окружения); None — не задан."""
    return os.environ.get(ENV_VAR) or None


def set_current(stand_id: str) -> None:
    """Зафиксировать стенд процесса — до старта рабочего процесса, чтобы
    тот унаследовал переменную."""
    os.environ[ENV_VAR] = stand_id


def current() -> dict:
    """Описание текущего стенда. Без ALB_STAND — первый из конфига
    (запуск модулей напрямую, отладка)."""
    stands = load_stands()
    sid = current_id()
    for s in stands:
        if s.get("id") == sid:
            return s
    if sid is not None:
        print(f"[stand] стенд '{sid}' не найден в {_CFG.name} — беру первый")
    return stands[0] if stands else {"id": "default", "title": "Стенд", "endpoint": None}


def data_dir(stand_id: str | None = None) -> Path:
    """Папка данных стенда: stands/<id>/ (создаётся при обращении).
    По умолчанию — текущего стенда процесса."""
    d = _DATA_DIR / (stand_id or current()["id"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def redirect_output_to_log() -> None:
    """Под pythonw (запуск из лаунчера) stdout/stderr нет — print и трейсбеки
    ушли бы в никуда. Направляем их в stands/<id>/app.log (дозапись, построчно).
    При запуске из консоли ничего не меняем."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    f = open(data_dir() / "app.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f


# ── «стенд уже открыт» ────────────────────────────────────────────────────────
# Окно стенда — независимый процесс: лаунчер его не держит и может быть закрыт
# или запущен заново. Поэтому признак «открыт» живёт не в памяти лаунчера, а в
# lock-файле с pid окна; живость pid проверяется у системы.

def _lock_path(stand_id: str) -> Path:
    return data_dir(stand_id) / "window.pid"


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)          # POSIX: сигнал 0 — только проверка существования
        return True
    except OSError:
        return False


def window_pid(stand_id: str) -> int | None:
    """pid живого окна стенда или None (нет lock-файла / процесс уже умер)."""
    try:
        pid = int(_lock_path(stand_id).read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if _pid_alive(pid) else None


def is_running(stand_id: str) -> bool:
    return window_pid(stand_id) is not None


def claim_window(stand_id: str | None = None, pid: int | None = None) -> None:
    """Пометить процесс окном стенда. По умолчанию — текущий процесс и текущий
    стенд; лаунчер вызывает с pid только что созданного окна, чтобы стенд
    считался открытым сразу, не дожидаясь его старта."""
    _lock_path(stand_id or current()["id"]).write_text(str(pid or os.getpid()))


def release_window() -> None:
    """Снять пометку при штатном выходе (при аварийном — pid просто окажется
    мёртвым). Удаляем только свой lock: если по ошибке поднялось второе окно
    того же стенда, оно не должно «освободить» стенд, занятый первым."""
    try:
        path = _lock_path(current()["id"])
        if path.read_text().strip() == str(os.getpid()):
            path.unlink()
    except (OSError, ValueError):
        pass
