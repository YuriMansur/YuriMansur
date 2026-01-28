# Обмен данными с оборудованием стенда по ModbusTCP.
# Включает данные датчиков, состояния оборудования и управляющие команды.
# Все данные передаются в едином цикле обмена с периодом,
# установленным в переменной poll_interval.
# Обмен с ПЛК стенда происходит только в данном модуле.
import logging
import time
from ctypes import c_short, c_int, c_uint

import numpy as np
from PyQt6.QtCore import (
    Qt,
    QThread,
    QTimer,
    QObject,
    pyqtSignal as Signal,
    pyqtSlot as Slot,
)
import asyncio
from pymodbus.client import ModbusTcpClient
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
from command_handler import float_to_words, words_to_float

READ_BUFFER_SIZE = 110
BUFFER_LENGTH = 50          # размер буфера данных от ПЛК
DI_ADDRESS = 0
ADC_ADDRESS = 1
ANGLE_ADDRESS = 2
DQ_ADDRESS = 4
STATE_ADDRESS = 5
BUFFER_ADDRESS = 10
INDEX_ADDRESS = 60
WRITE_BUFFER_ADDRESS = 111

BUF_START = BUFFER_ADDRESS
BUF_END = BUFFER_ADDRESS + BUFFER_LENGTH

REALTIME_DATA_WINDOW = 1    # временное окно для хранения данных (мин)
PLC_POLLING_INTERVAL = 4    # интервал опроса датчиков контроллером (мс)
DATA_STORAGE_LEN = REALTIME_DATA_WINDOW * 60 * 1000 / PLC_POLLING_INTERVAL
DATA_STORAGE_END_INDX = DATA_STORAGE_LEN - BUFFER_LENGTH - 1 # Последний индекс, куда можно писать (с учетом размера буфера)

class ModbusPoller(QObject):
    """Background worker handling Modbus communication.
    Фоновый рабочий объект, управляющий обменом по Modbus.
    """
    data_received = Signal(list)
    connection_status = Signal(bool)

    def __init__(self, data_set):
        """Initialize poller with a reference to the data set.
        Инициализировать опрос ПЛК со ссылкой на набо+р данных.
        """
        QObject.__init__(self)
        logging.debug('worker init')
        self.data_set = data_set
        self.cfg = self.data_set.config
        self.client = None
        self.poll_interval = self.cfg.get('modbus', 'poll_interval', 100)
        self.result = None
        self.read_holding_register_address = 0      # Начальный адрес регистра для чтения
        self.registers_number = READ_BUFFER_SIZE    # Количество регистров для чтения
        self.data_received.connect(self.data_set.update)

        # Настройка и запуск таймера опроса ПЛК
        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.on_timer)
        self.timer.start(self.poll_interval)

    async def poll_modbus(self):
        self.init_modbus()
        await self.client.connect()
        response = None
        if self.client.connected:
            self.connection_status.emit(True)
        else:
            self.connection_status.emit(False)

        try:
            response = await self.client.readwrite_registers(
                read_address=self.read_holding_register_address,
                read_count=self.registers_number,
                write_address=WRITE_BUFFER_ADDRESS,
                values= self.data_set.write_regs,
            )
        except ModbusException as e:
            logging.error(f"Modbus error: {e}")
        finally:
            if response is not None:
                self.data_received.emit(response.registers)
            self.client.close()

    def init_modbus(self):
        # Настройка Modbus клиента на основе конфигурации
        host = self.cfg.get('modbus', 'host', '127.0.0.1')
        port = self.cfg.get('modbus', 'port', 502)
        timeout = self.cfg.get('modbus', 'timeout', 1.0)
        self.client = AsyncModbusTcpClient(host, port=port, timeout=timeout)

    @Slot()
    # Обработчик таймера опроса
    def on_timer(self):
        asyncio.run(self.poll_modbus())


class RealTimeData(QObject):
    """Хранение и обработка данных, получаемых по Modbus."""

    data_updated = Signal(list)
    prev_time = 0

    def __init__(self, config, parent=None):
        """Инициализация параметров и запуск рабочего потока."""
        QObject.__init__(self)
        self.config = config

        # период опроса датчиков в миллисекундах
        self.poll_interval = self.config.get('modbus', 'poll_interval_ms', 100)
        # период опроса в секундах
        self.poll_interval_s = float(self.poll_interval) / 1000.0
        # Длина массива данных с учётом интервала опроса датчиков
        self.data_window_length = int(DATA_STORAGE_LEN)

        # Слово состояния дискретных сигналов от ПЛК
        self.in_status = 0x00

        # данные от датчика угла поворота, в градусах
        self.angle_data = np.zeros(self.data_window_length, dtype=np.int32)

        # Данные от датчика угла поворота (преобразованные, в градусах)
        self.angle_data_c = np.zeros(self.data_window_length, dtype=np.float16)

        # данные от датчика крутящего момента, RAW АЦП
        self.torque_data = np.zeros(self.data_window_length, dtype=np.int16)

        # данные от датчика крутящего момента, масштабированные 500:1 (25000 = 50 Нм)
        self.torque_data_scaled = np.zeros(self.data_window_length, dtype=np.int16)

        # Данные от датчика крутящего момента (преобразованные к Нм)
        self.torque_data_c = np.zeros(self.data_window_length, dtype=np.float32)

        # Скорость нарастания момента (моментальные значения в Нм/с)
        self.velocity_data = np.zeros(self.data_window_length, dtype=np.float16)

        # временные метки для потока данных, в мс
        self.times = np.zeros(self.data_window_length, dtype=np.int64)
        self.ptr = 0  # Указатель текущей позиции данных
        self.curr_index = 0
        self.prev_index = 0
        self.index_offset = 0
        self.head = 0

        # Текущие значения датчиков (данные ПЛК)
        self.tension_adc = 0        # Данные АЦП датчика момента
        self.tension_nc = 0         # Момент нескорректированный, Нм
        self.tension = 0.0          # Момент скорректированный, Нм
        self.angle = 0              # Угол поворота в градусах нескорректированный
        self.velocity = 0           # Скорость нарастания момента

        self.write_regs = [0x00] * 30 # 30 регистров для записи в ПЛК

        # Для обмена по Modbus создаем отдельный поток
        # переносим в отдельный поток
        # запускаем поток
        self.poller = ModbusPoller(self)
        self.poller_thread = QThread()
        self.poller.moveToThread(self.poller_thread)
        self.poller_thread.start()

        self.time_origin = time.time()  # Начальная временная метка для датасета
        self.prev_time = time.time()

    # Слот вызывается из ModbusPoller когда завершено получение новых данных от PLC
    @Slot(list)
    def update(self, registers):
        """ Обновление данных по полученным регистрам."""
        self._write_torque_buffer(registers)

        self.times[self.ptr] = round((time.time() - self.time_origin) * 1000)
        self.torque_data_c[self.ptr] = self.tension
        self.angle_data_c[self.ptr] = self.get_real_angle(registers)
        self.velocity_data[self.ptr] = 0 #self.get_real_velocity()
        self.ptr += 1

        # Если массив заполнен, сдвигаем данные
        if self.ptr >= self.data_window_length:
            self.times[:-1] = self.times[1:]
            self.torque_data_c[:-1] = self.torque_data_c[1:]
            self.angle_data_c[:-1] = self.angle_data_c[1:]
            self.velocity_data[:-1] = self.velocity_data[1:]
            self.ptr = self.data_window_length - 1

        # Фиксируем текущие данные от датчика момента
        self.tension_adc = c_short(registers[1]).value
        self.tension_nc = self.get_real_tension_nc(self.tension_adc)
        self.tension = self.get_real_tension(self.tension_nc)

        # Фиксируем текущие данные от датчика угла
        self.angle = self.get_real_angle(registers)

        # Фиксируем текущую скорость нарастания момента
        self.velocity =  self.get_real_velocity() #self.velocity_data[self.ptr-1]

        # Считываем состояние регистров
        self.in_status = c_short(registers[0]).value
        self.data_updated.emit(registers)

    def _write_torque_buffer(self, registers):
        """ Контроллер читает данные с датчика момента с периодом своего цикла 4 мс в кольцевой буфер размером BUFFER_LENGTH = 50
            АРМ читает ВЕСЬ буфер с периодом примерно 100 мс. Этот период в Windows плавает в пределах 50%
            поэтому буфер взят с запасом (50 значений, хотя всего за период 4 мс в среднем мы получаем 25 значений)
            текущее смещение которое мы вычисляем каждый раз когда читаем буфер позволяет записывать значения
            последовательно без пропусков и дублирования в локальный массив большого размера
        """

        self.prev_index = self.curr_index  # Сохраняем предыдущий полученный указатель от ПЛК
        self.curr_index = registers[INDEX_ADDRESS]  # Получаем новый указатель от ПЛК
        if self.prev_index < self.curr_index:
            # Находим смещение указателя (то есть фактически количество
            # новых значений которые были записаны в буфер за время прошедшее между двумя опросами
            self.index_offset = self.curr_index - self.prev_index
        else:
            self.index_offset = BUFFER_LENGTH + self.curr_index - self.prev_index
        buffer = [c_short(i).value for i in registers[BUF_START:BUF_END]]  # читаем буфер и приводим его к типу INT

        if self.head > DATA_STORAGE_END_INDX:
            # Если указатель достиг конца хранилища данных сдвигаем данные в хранилище на размер буфера:
            self.torque_data_scaled[:-BUFFER_LENGTH] = self.torque_data_scaled[BUFFER_LENGTH:]
            self.head -= BUFFER_LENGTH
        self.torque_data_scaled[self.head:self.head+BUFFER_LENGTH] = buffer

        # новый индекс смещаем на фактическое количество новых записей в буфере
        self.head += self.index_offset

    # def _write_torque_buffer(self, buf: list, index):
    #     if index > (self.data_window_length - BUFFER_LENGTH - 1):
    #         self.torque_data_scaled[:-BUFFER_LENGTH] = self.torque_data_scaled[BUFFER_LENGTH:]
    #         index = self.data_window_length - BUFFER_LENGTH
    #     self.torque_data_scaled[index:index+BUFFER_LENGTH] = buf[:]


    def get_real_tension_nc(self, torque_adc):
        """Преобразование регистров в значение крутящего момента (нескорректированного)"""
        tension = 50.0 * float(torque_adc) / 16384.0
        # client = self.poller.client
        # tension = client.convert_from_registers(registers[6:8], client.DATATYPE.FLOAT32)
        return tension

    def get_real_tension(self, torque_nc):
        """Преобразование регистров в значение крутящего момента (корректированного в соответствии с калибровочной моделью)"""
        tension = torque_nc * 1.0 + 0
        # client = self.poller.client
        # tension = client.convert_from_registers(registers[8:10], client.DATATYPE.FLOAT32)
        # tension = client.convert_from_registers(registers[10:11], client.DATATYPE.INT16)
        return tension

    def get_real_angle(self, registers):
        """Преобразование регистров в значение угла."""
        _angle = c_uint((registers[3] << 16) | registers[2]).value
        angle = float(_angle)/768.0
        return angle

    def get_real_velocity(self):
        """Расчёт скорости нарастания момента."""
        velocity = 0.0
        if self.ptr > 0:
            velocity = (
                self.torque_data_c[self.ptr] - self.torque_data_c[self.ptr - 1]
            ) / self.poll_interval
        return velocity

    def _get_dataset_by_name(self, dataset_name):
        """Возврат массива данных по имени."""
        match dataset_name:
            case 'tension_data_c':
                return self.torque_data_c
            case 'angle_data_c':
                return self.angle_data_c
            case 'velocity_data':
                return self.velocity_data
        return None

    def get_visible_chunk(self):
        ds = self.torque_data_scaled
        points = self.config.get('ui', 'max_graph_points', 1000)
        max_buffer_index = self.data_window_length - points
        if self.curr_index <= max_buffer_index:
            return ds[self.curr_index-points:self.curr_index]

    def get_torque(self):
        return self.tension

    def get_velocity(self):
        return self.velocity

    def get_angle(self):
        return self.angle

    @Slot(dict)
    def modbus_registers_to_PLC_update(self, regs):
        """Обновление регистров Modbus для записи в ПЛК."""
        for key, reg in regs.items():
            match key:
                case 'Modbus_CTRL':
                    self.write_regs[0] = reg
                case 'Modbus_TensionSV':
                    self.write_regs[1] = reg
                case 'Modbus_VelocitySV':
                    self.write_regs[2] = reg
                case 'Modbus_DQ_CTRL':
                    self.write_regs[3] = reg
                case 'Modbus_UZ_CTRL':
                    self.write_regs[4] = reg
                case 'Modbus_KP':
                    _kp = float_to_words(reg)
                    self.write_regs[5] = _kp[0]
                    self.write_regs[6] = _kp[1]
                case 'Modbus_KI':
                    _ki = float_to_words(reg)
                    self.write_regs[7] = _ki[0]
                    self.write_regs[8] = _ki[1]
                case 'Modbus_KD':
                    _kd = float_to_words(reg)
                    self.write_regs[9] = _kd[0]
                    self.write_regs[10] = _kd[1]
                case 'Modbus_CC_LO':
                    cc_lo = list(map(float_to_words, reg))
                    for i in range(len(cc_lo)):
                        self.write_regs[17 + i * 2] = cc_lo[i][0]
                        self.write_regs[18 + i * 2] = cc_lo[i][1]
                case 'Modbus_CC_HI':
                    cc_hi = list(map(float_to_words, reg))
                    for i in range(len(cc_hi)):
                        self.write_regs[23 + i * 2] = cc_hi[i][0]
                        self.write_regs[24 + i * 2] = cc_hi[i][1]
                case 'Modbus_AUX':
                    self.write_regs[11] = reg

    @Slot()
    def update_connection_settings(self):
        """Применение настроек Modbus и периода опроса из конфигурации."""
        self.poll_interval = self.config.get('modbus', 'poll_interval_ms', 100)
        self.poll_interval_s = float(self.poll_interval) / 1000.0
        if self.poller.timer:
            self.poller.timer.setInterval(self.poll_interval)
        # self.poller.init_modbus()

class Dyno(QObject):
    def __init__(self, config):
        QObject.__init__(self)
        self.config = config
        self.dyno_value = 0.0
        self.port_name = self.config.get('dyno', 'port_name')
        # Для работы с динамометром АЦД/1У обмен с COM портом переносим в отдельный поток
        self.serial_dyno = SerialHandler(self.port_name)
        self.dyno_thread = QThread()
        self.serial_dyno.moveToThread(self.dyno_thread)
        self.dyno_thread.start()
        self.serial_dyno.response_ready.connect(self.update)

    @Slot(str, float)
    def update(self, value_text, value):
        self.dyno_value = value

    def get_value(self):
        return self.dyno_value
