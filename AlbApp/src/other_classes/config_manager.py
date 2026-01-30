import json
import os
from PyQt6.QtCore import QObject, pyqtSignal


class ConfigManager(QObject):
    """
    - хранит конфигурацию в памяти
    - загружает / сохраняет в JSON
    - сообщает о факте изменения (signal)

    НЕ отвечает:
    - когда именно сохранять
    - кто инициировал изменение
    """
# Проброс сигнала Qt
    changed = pyqtSignal()

    def __init__(self, config_file: str = "config.json"):
        super().__init__()
        # Gуть к JSON-файлу конфигурации
        self._config_file = config_file
        # Cловарь, в котором хранится вся конфигурация в памяти
        self._config: dict = {}

    
    def load(self) -> None:
        """Загрузить конфигурацию из файла."""
        if not os.path.exists(self._config_file):
            self._config = {}
            return

        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._config = {}

    def save(self) -> None:
        """Сохранить текущую конфигурацию в файл."""
        with open(self._config_file, "w", encoding="utf-8") as f:
            json.dump(self._config, f, ensure_ascii=False, indent=4)

    def get(self, key, default = None):
        """Получить значение из конфигурации."""
        return self._config.get(key, default)

    def set(self, key, value) -> None:
        """
        Установить значение.

        Сигнал `changed` испускается ТОЛЬКО если значение реально изменилось.
        """
        if self._config.get(key) == value:
            return

        self._config[key] = value
        self.changed.emit()

    def as_dict(self) -> dict:
        """Вернуть копию конфигурации (read-only)."""
        return dict(self._config)
