"""High level commands for interacting with the PLC.

The handler converts application requests into register writes and
communicates them through ``write_to_plc``. Errors such as unsupported
commands are reported via the ``error`` signal.
"""

import logging
import struct

from PyQt6.QtCore import QObject, pyqtSignal as Signal, QTimer

CONTROL_BITS = {
    "power_on":     0,
    "reset_torque": 4,
    "reset_angle":  5,
    "write_retain": 6,
    "reset_error":  7,
    "reset_alarm":  8,
}
CONTROL_CMD = {
    "halt":         0b000,
    "jog_cw":       0b001,
    "jog_ccw":      0b010,
    "torque_hold":  0b011,
    "move_to_angle":0b100,
    "stop":         0b111,
}

def words_to_float(word1, word2, byte_order="CDAB"):
    """
    Преобразует два 16-битных слова (WORD) в 32-битное число float.

    :param word1: Первое 16-битное слово (из первого регистра).
    :param word2: Второе 16-битное слово (из второго регистра).
    :param byte_order: Порядок байт/слов. "CDAB" (swapped) или "ABCD" (big-endian).
    :return: Значение float.
    """
    if byte_order == "CDAB":  # Младшее слово первое
        packed_bytes = struct.pack('>HH', word2, word1)
    elif byte_order == "ABCD":  # Старшее слово первое
        packed_bytes = struct.pack('>HH', word1, word2)
    else:
        raise ValueError("Неподдерживаемый порядок байт. Используйте 'CDAB' или 'ABCD'.")

    # Распаковываем 4 байта как big-endian float
    float_val = struct.unpack('>f', packed_bytes)[0]
    return float_val

def float_to_words(float_val, byte_order="CDAB"):
    """
    Преобразует 32-битное число float в два 16-битных слова (WORD).

    :param float_val: Значение float для преобразования.
    :param byte_order: Порядок слов. "CDAB" (swapped) или "ABCD" (big-endian).
    :return: Кортеж из двух 16-битных слов (word1, word2).
    """
    # Упаковываем float в 4-байтовую последовательность (big-endian)
    packed_bytes = struct.pack('>f', float_val)

    # Распаковываем 4 байта в два 16-битных беззнаковых целых числа (WORD)
    # Это дает нам слова в порядке "ABCD" (старшее, затем младшее)
    word_abcd = struct.unpack('>HH', packed_bytes)
    word1_abcd, word2_abcd = word_abcd[0], word_abcd[1]

    if byte_order == "ABCD":
        return (word1_abcd, word2_abcd)
    elif byte_order == "CDAB":
        # Для порядка "CDAB" меняем слова местами
        return (word2_abcd, word1_abcd)
    else:
        raise ValueError("Неподдерживаемый порядок байт. Используйте 'CDAB' или 'ABCD'.")



class CommandHandler(QObject):
    """Dispatches control commands to the PLC.

    Signals
    -------
    write_to_plc: dict
        Emitted with the Modbus register dictionary when a command should
        be sent to the PLC.
    error: str
        Emitted when an invalid command argument is provided.
    """

    write_to_plc = Signal(dict)
    error = Signal(str)

    def __init__(self, parent=None):
        """Initialize the command handler and connect its signals."""
        super(CommandHandler, self).__init__(parent)
        self.parent = parent
        self.write_to_plc.connect(
            self.parent.realtime_data.modbus_registers_to_PLC_update
        )
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)  # интервал 250 мс
        self.timer.timeout.connect(self.on_singleshot_timer)

    def on_singleshot_timer(self):
        self._clear_control_bit(CONTROL_BITS["write_retain"])
        self._clear_control_bit(CONTROL_BITS["reset_error"])
        self._clear_control_bit(CONTROL_BITS["reset_alarm"])
        self._clear_control_bit(CONTROL_BITS["reset_torque"])
        self._clear_control_bit(CONTROL_BITS["reset_angle"])

    def set_plc_mode(self, mode):
        """Set the PLC operating mode.

        Parameters
        ----------
        mode: str
            One of ``'auto'``, ``'hand'`` or ``'service'``.

        Raises
        ------
        ValueError
            If ``mode`` is not supported. In this case the ``error`` signal
            is also emitted.
        """
        regs_ = self.parent.modbus_write_regs
        mask = 0b0001111111111111
        regs_['Modbus_CTRL'] &= mask
        match mode:
            case 'auto':
                mask = 0b0100000000000000
            case 'hand':
                mask = 0b0000000000000000
            case 'service':
                mask = 0b1000000000000000
            case 'hand_calibration':
                mask = 0b1010000000000000
            case _:
                message = f"Unsupported PLC mode: {mode}"
                logging.warning(message)
                self.error.emit(message)
                raise ValueError(message)
        regs_['Modbus_CTRL'] |= mask
        self.write_to_plc.emit(regs_)

    def servo_power_on(self):
        """Turn on the servo drive."""
        self._set_control_bit(CONTROL_BITS["power_on"])

    def servo_power_off(self):
        """Turn off the servo drive."""
        self._clear_control_bit(CONTROL_BITS["power_on"])

    def write_retain(self):
        self._set_control_bit(CONTROL_BITS["write_retain"])

    def reset_error(self):
        """Reset the servo drive error."""
        self._set_control_bit(CONTROL_BITS["reset_error"])

    def alarm_reset(self):
        """Turn off the alarm."""
        self._set_control_bit(CONTROL_BITS["reset_alarm"])

    def torque_reset(self):
        self._set_control_bit(CONTROL_BITS["reset_torque"])

    def angle_reset(self):
        self._set_control_bit(CONTROL_BITS["reset_angle"])

    def set_tension(self, tension=0, velocity=0):
        """Set the tension and velocity setpoints."""
        regs_ = self.parent.modbus_write_regs
        regs_['Modbus_TensionSV'] = tension
        regs_['Modbus_VelocitySV'] = velocity
        self.write_to_plc.emit(regs_)

    def torque_hold(self):
        self._do_command("torque_hold")

    def jog_cw(self):
        self._do_command("jog_cw")

    def jog_ccw(self):
        self._do_command("jog_ccw")

    def halt(self):
        """Halt motion"""
        self._do_command("halt")

    def stop(self):
        """Stop motion and reset setpoints to zero."""
        self._do_command("stop")

    def set_PID_parameters(self, kp, ki, kd):
        """Set PID parameters."""
        regs_ = self.parent.modbus_write_regs
        regs_["Modbus_KP"] = kp
        regs_["Modbus_KI"] = ki
        regs_["Modbus_KD"] = kd
        self.write_to_plc.emit(regs_)

    def set_calibration_coefficients(self, coeffs: dict):
        """Set caliration coefficients on PLC."""
        cc_lo = [coeffs['A1'], coeffs['B1'], coeffs['C1']]
        cc_hi = [coeffs['A2'], coeffs['B2']]
        regs_ = self.parent.modbus_write_regs
        regs_["Modbus_CC_LO"] = cc_lo
        regs_["Modbus_CC_HI"] = cc_hi
        self.write_to_plc.emit(regs_)

    def set_plc_register(self, name='Modbus_CTRL', value=0):
        """Write a raw value to a Modbus register."""
        regs_ = self.parent.modbus_write_regs
        regs_[name] = value
        self.write_to_plc.emit(regs_)

    def _do_command(self, command):
        regs_ = self.parent.modbus_write_regs
        # Создаём битовую маску по месту размещения управляющей команды в слове управления (биты с 1 по 3)
        mask = 0b111 << 1
        # Очищаем эти разряды в слове управления
        regs_['Modbus_CTRL'] &= ~mask
        # Устанавливаем новые значения
        regs_['Modbus_CTRL'] |= (CONTROL_CMD[command] << 1)
        # Отправляем в ПЛК
        self.write_to_plc.emit(regs_)

    def _set_control_bit(self, bit):
        regs_: dict = self.parent.modbus_write_regs
        regs_['Modbus_CTRL'] |= (1 << bit)
        self.write_to_plc.emit(regs_)

    def _clear_control_bit(self, bit):
        regs_: dict = self.parent.modbus_write_regs
        regs_['Modbus_CTRL'] &= ~(1 << bit)
        self.write_to_plc.emit(regs_)

    def clear_all_control_bits(self):
        """Clear all control bits."""
        regs_: dict = self.parent.modbus_write_regs
        for bit in CONTROL_BITS.values():
            regs_['Modbus_CTRL'] &= ~(1 << bit)
        self.write_to_plc.emit(regs_)