"""
Модуль для логирования подключений и событий протокола
"""

import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime


class ConnectionLogger:
    """Логгер для отслеживания подключений"""
    
    def __init__(self, log_dir: str = "logs", log_file: str = "connection.log"):
        """
        Инициализация логгера подключений
        
        Args:
            log_dir: Директория для логов
            log_file: Имя файла лога
        """
        self.log_dir = Path(log_dir)
        self.log_file = self.log_dir / log_file
        
        # Создаём директорию логов если её нет
        self.log_dir.mkdir(exist_ok=True)
        
        # Создаём логгер
        self.logger = logging.getLogger("ConnectionLog")
        self.logger.setLevel(logging.DEBUG)
        
        # Удаляем старые обработчики
        self.logger.handlers.clear()
        
        # Форматер с детальной информацией
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Обработчик для файла (ротирующийся)
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_file,
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # Обработчик для консоли
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
    
    def log_connection(self, protocol: str, host: str, port: int, status: str, details: str = ""):
        """
        Залогировать подключение
        
        Args:
            protocol: Протокол (Modbus TCP, OPC UA)
            host: Хост подключения
            port: Порт подключения
            status: Статус (SUCCESS, FAILED, DISCONNECTED)
            details: Дополнительные детали
        """
        message = f"[{protocol}] {host}:{port} | {status}"
        if details:
            message += f" | {details}"
        
        if status == "SUCCESS":
            self.logger.info(message)
        elif status == "FAILED":
            self.logger.error(message)
        elif status == "DISCONNECTED":
            self.logger.warning(message)
        else:
            self.logger.debug(message)
    
    def log_protocol_switch(self, old_protocol: str, new_protocol: str, status: str):
        """Залогировать переключение протокола"""
        message = f"Protocol Switch: {old_protocol} -> {new_protocol} | {status}"
        if status == "SUCCESS":
            self.logger.info(message)
        else:
            self.logger.error(message)
    
    def log_error(self, protocol: str, error_msg: str):
        """Залогировать ошибку"""
        message = f"[{protocol}] ERROR: {error_msg}"
        self.logger.error(message)
    
    def log_config_loaded(self, config_file: str):
        """Залогировать загрузку конфигурации"""
        message = f"Configuration loaded from: {config_file}"
        self.logger.info(message)
    
    def get_log_file(self) -> str:
        """Получить путь к файлу логов"""
        return str(self.log_file)
    
    def read_recent_logs(self, lines: int = 50) -> str:
        """
        Прочитать последние строки логов
        
        Args:
            lines: Количество строк для чтения
            
        Returns:
            Текст последних строк логов
        """
        if not self.log_file.exists():
            return "Log file not found"
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
                return ''.join(recent)
        except Exception as e:
            return f"Error reading log: {e}"
    
    def clear_logs(self):
        """Очистить лог файл"""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Logs cleared at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            self.logger.info("Logs cleared")
        except Exception as e:
            self.logger.error(f"Error clearing logs: {e}")


# Глобальный логгер
_connection_logger = None


def get_connection_logger() -> ConnectionLogger:
    """Получить глобальный логгер подключений"""
    global _connection_logger
    if _connection_logger is None:
        _connection_logger = ConnectionLogger()
    return _connection_logger
