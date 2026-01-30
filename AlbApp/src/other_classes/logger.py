import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(
    name: str = "app",
    log_dir: str = "logs",
    level: int = logging.INFO,
    max_bytes: int = 2 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """
    Собствено пишет логи.
    
    Файл + консоль, ротация логов, UTF-8,без дублирования сообщений.

    :param name: Имя логгера (позволяет использовать один логгер в разных модулях).
    :param log_dir: Папка для файлов логов.
    :param level: Уровень логирования (DEBUG, INFO, WARNING...).
    :param max_bytes: Максимальный размер одного файла логов.
    :param backup_count: Сколько старых логов хранить при ротации
    """
# Создание директории логов
    log_path = Path(log_dir)
        # - parents  = True — cоздаёт все родительские директории при необходимости
        # - exist_ok = True —  Не выбрасывает ошибку, если папка уже есть 
    log_path.mkdir(parents = True, exist_ok = True)
    
# Cоздаёт или возвращает существующий логгер с этим именем.
    logger = logging.getLogger(name)
    # Глобальный уровень логирования для этого логгера.
    logger.setLevel(level)
    # Предотвращает дублирование сообщений в корневой логгер.
    logger.propagate = False
    # Защита от повторной инициализации
    if logger.handlers:
        return logger  

# Формат вывода логов:
        # - asctime — время события
        # - levelname — уровень (INFO...) -8s выравнивание уровней в консоли/файле.
        # - name — имя логгера
        # - message — сообщение
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

# Файл логов
        # - log_path — "директория для логов"/"имя файла".log
        # - maxBytes — максимальный размер одного файла
        # - backupCount — количество старых логов, которые будут храниться.
        # - encoding="utf-8" — корректно хранит кириллицу.
    file_handler = RotatingFileHandler(
        log_path / f"{name}.log",
        maxBytes = max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    # Форматирует вывод
    file_handler.setFormatter(formatter)
    # Фильтрует сообщения ниже уровня.
    file_handler.setLevel(level)

# Консоль
    # Выводит лог в консоль
    console_handler = logging.StreamHandler()
    # Форматирует вывод
    console_handler.setFormatter(formatter)
    # Фильтрует сообщения ниже уровня.
    console_handler.setLevel(level)

# Добавляет обработчики к логгеру
    # Сообщение в файл
    logger.addHandler(file_handler)
    # Сообщение в консоль
    logger.addHandler(console_handler)

# Возвращаем готовый логгер
    return logger
