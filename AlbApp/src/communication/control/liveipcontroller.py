from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtCore import Qt


class IPv4Model(BaseModel):
    """Pydantic модель для проверки IP"""
    ip_address: str

    @validator('ip_address')
    def check_ip(cls, v):
        parts = v.split('.')
        if len(parts) != 4:
            raise ValueError("Должно быть 4 октета")
        for part in parts:
            if not part.isdigit():
                raise ValueError("Только цифры")
            value = int(part)
            if not (0 <= value <= 255):
                raise ValueError("Октет вне диапазона 0–255")
        return v


class LiveIpController:
    """
    Контроллер QLineEdit для IPv4:
    - Live-проверка при каждом вводе
    - Подсветка: красная/зелёная
    - Статичные точки
    - Максимум 3 цифры на октет
    """

    def __init__(self, ip_input: QLineEdit, default_ip: str = "127.0.0.1"):
        self.ip_input = ip_input

        # Маска ввода со статичными точками
        self.ip_input.setInputMask("000.000.000.000;_")
        self.ip_input.setPlaceholderText("___ . ___ . ___ . ___")

        # Устанавливаем дефолтный IP
        self.ip_input.setText(default_ip)
        self._apply_validation(default_ip)

        # Live-проверка при каждом вводе
        self.ip_input.textChanged.connect(self._on_text_changed)
        self.ip_input.editingFinished.connect(self._on_editing_finished)

    # ----------------- Проверка через Pydantic -----------------
    @staticmethod
    def _is_valid_ipv4(ip: str) -> bool:
        try:
            IPv4Model(ip_address=ip)
            return True
        except ValidationError:
            return False

    # ----------------- Подсветка поля -----------------
    def _set_style(self, valid: bool):
        if valid:
            self.ip_input.setStyleSheet("QLineEdit { border: 2px solid #2ecc71; }")  # зелёная
        else:
            self.ip_input.setStyleSheet("QLineEdit { border: 2px solid #e74c3c; }")  # красная

    # ----------------- Применение проверки -----------------
    def _apply_validation(self, ip: str):
        valid = self._is_valid_ipv4(ip)
        self._set_style(valid)
        return valid

    # ----------------- Live проверка -----------------
    def _on_text_changed(self, text: str):
        octets = text.split(".")
        new_octets = []

        for octet in octets:
            digits = ''.join(c for c in octet if c.isdigit())
            if len(digits) > 3:
                digits = digits[:3]  # максимум 3 цифры на октет
            new_octets.append(digits)

        new_text = ".".join(new_octets)
        if new_text != text:
            cursor = self.ip_input.cursorPosition()
            self.ip_input.blockSignals(True)
            self.ip_input.setText(new_text)
            self.ip_input.setCursorPosition(cursor)
            self.ip_input.blockSignals(False)

        # Подсветка
        self._set_style(self._is_valid_ipv4(new_text))

    # ----------------- Завершение редактирования -----------------
    def _on_editing_finished(self):
        ip = self.ip_input.text()
        self._apply_validation(ip)
