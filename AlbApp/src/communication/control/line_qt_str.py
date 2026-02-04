class IPBuilder:
    """
    Логика ввода IP с предустановленными точками.
    Контролирует:
        - каждый октет 0-255
        - ввод только цифр
        - backspace
    """
    def __init__(self):
        # четыре октета, изначально все "0"
        self.octets = ["___.___.___.___"]
        self.current_octet = 0
        self.cursor_pos_in_octet = 0  
        
    def add_char(self, ch: str) -> bool:
        """Добавляет цифру в текущий октет"""
        if not ch.isdigit():
            return False

        if self.cursor_pos_in_octet >= 3:
            return False  # внутри октета максимум 3 цифры

        # формируем новое значение октета
        octet_value = self.octets[self.current_octet]
        octet_value = (
            octet_value[:self.cursor_pos_in_octet] + ch + octet_value[self.cursor_pos_in_octet+1:]
        )

        # проверка диапазона
        if int(octet_value) > 255:
            return False

        self.octets[self.current_octet] = octet_value
        self.cursor_pos_in_octet += 1

        # переход к следующему октету, если заполнен
        if self.cursor_pos_in_octet == 3 and self.current_octet < 3:
            self.current_octet += 1
            self.cursor_pos_in_octet = 0

        return True

    def backspace(self):
        """Удаляет цифру в текущем октете или переходит к предыдущему"""
        if self.cursor_pos_in_octet > 0:
            self.cursor_pos_in_octet -= 1
            self.octets[self.current_octet] = (
                self.octets[self.current_octet][:self.cursor_pos_in_octet] + 
                "0" + 
                self.octets[self.current_octet][self.cursor_pos_in_octet+1:]
            )
        elif self.current_octet > 0:
            self.current_octet -= 1
            self.cursor_pos_in_octet = len(self.octets[self.current_octet])
            self.backspace()  # рекурсивно удалить предыдущую цифру

    def get_ip(self) -> str:
        """Возвращает IP с точками"""
        return ".".join(self.octets)

    def is_valid(self) -> bool:
        """Проверка валидности IP"""
        for o in self.octets:
            if len(o) == 0:
                return False
            if not (0 <= int(o) <= 255):
                return False
            if len(o) > 1 and o.startswith("0"):
                return False
        return True
