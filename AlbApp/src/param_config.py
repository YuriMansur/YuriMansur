"""Конфиг-движок параметров испытаний.

Два слоя конфигурации:
  • gost_config.json — СТРУКТУРА: какие параметры существуют у каждого ГОСТа
    (уровни нагружения P1…P8 / A60…A100, условие I/II, поля сил, методики).
    Отсюда движок «создаёт» параметры — наполнение комбобоксов и форм.
  • params.json — ЗНАЧЕНИЯ: конкретные числа сил, подставляемые в созданные
    параметры, плюс сведения о стенде (stand_info). Этот слой только читается
    (и перезаписывается из экрана настроек).

Оба файла лежат рядом с этим модулем (рабочая директория приложения = AlbApp/src).
"""
import json
from pathlib import Path

_DIR = Path(__file__).parent          # src/
_APP = _DIR.parent                    # AlbApp/
_CONFIG_PATH = _APP / "patch" / "gost_config.json"     # структура (подкладывается)
_PARAMS_PATH = _APP / "configs" / "params.json"        # значения сил

_cfg_cache: dict | None = None


# ── структура (gost_config.json) ─────────────────────────────────────────────
def _config() -> dict:
    """Загрузить и закэшировать структуру (статична на время сессии)."""
    global _cfg_cache
    if _cfg_cache is None:
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                _cfg_cache = json.load(f)
        except (OSError, json.JSONDecodeError):
            _cfg_cache = {"f_fields": [], "stand_fields": [], "gosts": {}}
    return _cfg_cache


def _gost(gost: str) -> dict:
    return _config().get("gosts", {}).get(gost, {})


def gosts() -> list[str]:
    """Список ГОСТов (корень иерархии)."""
    return list(_config().get("gosts", {}).keys())


def load_levels(gost: str) -> list[str]:
    """Уровни нагружения: P1…P8 / A60…A100."""
    return _gost(gost).get("load_levels", [])


def conditions(gost: str) -> list[str]:
    """Условия нагружения (I/II) или [] если у ГОСТа их нет."""
    return _gost(gost).get("conditions", [])


def has_conditions(gost: str) -> bool:
    return bool(conditions(gost))


def fields(gost: str) -> list[str]:
    """Поля сил (F), отображаемые для данного ГОСТа."""
    return _gost(gost).get("fields", [])


def methods(gost: str) -> list[str]:
    """Конкретные методики данного ГОСТа."""
    return _gost(gost).get("methods", [])


def f_fields() -> list[str]:
    """Полный список ключей полей сил (порядок отображения)."""
    return _config().get("f_fields", [])


def stand_fields() -> list[tuple[str, str]]:
    """Поля сведений о стенде в виде [(label, key), …]."""
    return [(d["label"], d["key"]) for d in _config().get("stand_fields", [])]


# ── значения (params.json) ───────────────────────────────────────────────────
def read_params() -> dict:
    """Прочитать params.json (пустой dict, если файла нет / битый)."""
    try:
        with open(_PARAMS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def write_params(data: dict) -> None:
    with open(_PARAMS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def values(gost: str, level: str, cond: str) -> dict | None:
    """Значения сил для (ГОСТ, уровень, условие). cond == "" — без оси условия."""
    data = read_params()
    try:
        return data[gost][level][cond] if cond else data[gost][level]
    except KeyError:
        return None


def stand_info() -> dict:
    return read_params().get("stand_info", {})
