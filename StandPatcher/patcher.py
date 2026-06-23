"""Движок подкладки конфигов стенда в текущую программу (AlbApp).

Каждому стенду соответствует бандл конфигов в stands/<dir>/. По выбору стенда
движок копирует файлы бандла в целевые пути AlbApp (см. stands_config.json:
targets — мапа «имя конфига → относительный путь внутри AlbApp/src»).

Все пути резолвятся относительно каталога этого модуля, поэтому приложение
переносимо: достаточно держать StandPatcher рядом с AlbApp.
"""
import json
import shutil
from pathlib import Path

BASE = Path(__file__).parent
_CONFIG_PATH = BASE / "stands_config.json"


def load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def albapp_root(cfg: dict) -> Path:
    """Абсолютный путь к каталогу AlbApp/src (цель подкладки)."""
    return (BASE / cfg.get("albapp_root", "../AlbApp/src")).resolve()


def stand_dir(stand: dict) -> Path:
    """Каталог бандла конкретного стенда."""
    return BASE / "stands" / stand["dir"]


def patch_stand(stand: dict, cfg: dict) -> list[tuple[bool, str]]:
    """Подложить все конфиги стенда в AlbApp.

    Возвращает список (ok, сообщение) по каждому файлу — для построчного лога.
    """
    log: list[tuple[bool, str]] = []
    root = albapp_root(cfg)
    src_base = stand_dir(stand)

    if not root.exists():
        return [(False, f"Каталог AlbApp не найден: {root}")]
    if not src_base.exists():
        return [(False, f"Бандл стенда не найден: {src_base}")]

    for name, rel_target in cfg["targets"].items():
        src = src_base / name
        dst = root / rel_target

        # каталог (например, methodics) — копируем все *.json внутри
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            files = sorted(src.glob("*.json"))
            if not files:
                log.append((False, f"{name}: бандл пуст ({src})"))
                continue
            for f in files:
                target = dst / f.name
                try:
                    shutil.copy2(f, target)
                    log.append((True, f"{name}/{f.name}  →  {_rel(target, root)}"))
                except OSError as e:
                    log.append((False, f"{name}/{f.name}: ошибка — {e}"))
            continue

        # обычный файл
        if not src.exists():
            log.append((False, f"{name}: нет в бандле ({src})"))
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            log.append((True, f"{name}  →  {_rel(dst, root)}"))
        except OSError as e:
            log.append((False, f"{name}: ошибка — {e}"))

    return log


def _rel(path: Path, root: Path) -> str:
    """Путь относительно AlbApp/src для компактного лога."""
    try:
        return f"AlbApp/src/{path.relative_to(root).as_posix()}"
    except ValueError:
        return str(path)
