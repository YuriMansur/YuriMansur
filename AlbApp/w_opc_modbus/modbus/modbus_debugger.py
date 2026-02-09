"""
Modbus Worker Debugger - Тестовый отладчик с GUI для множественных PLC

═══════════════════════════════════════════════════════════════════════════════
АРХИТЕКТУРА: QThread + asyncio (БЕЗ qasync)
═══════════════════════════════════════════════════════════════════════════════

ДИАГРАММА ПОТОКОВ:
═════════════════

    ┌─────────────────────────────────────────────────────────────────────┐
    │                     ГЛАВНЫЙ ПОТОК (Main Thread)                     │
    │                                                                       │
    │  ┌────────────────────────────────────────────────────────────────┐ │
    │  │               ModbusDebugger (QMainWindow)                     │ │
    │  │                  Qt Event Loop (app.exec())                    │ │
    │  │                                                                │ │
    │  │  • Управление GUI                                             │ │
    │  │  • Обработка кликов кнопок                                    │ │
    │  │  • Прием signals от worker потоков                            │ │
    │  │  • Отображение результатов                                    │ │
    │  └────────────────────────────────────────────────────────────────┘ │
    │                              │                                        │
    │                              │ PyQt Signals (thread-safe)             │
    │                              │                                        │
    └──────────────────────────────┼────────────────────────────────────────┘
                                   │
                  ┌────────────────┼────────────────┐
                  │                │                │
                  ▼                ▼                ▼
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │  WORKER THREAD  │ │  WORKER THREAD  │ │  WORKER THREAD  │
    │      (PLC1)     │ │      (PLC2)     │ │      (PLC3)     │
    │                 │ │                 │ │                 │
    │ PLCWorkerThread │ │ PLCWorkerThread │ │ PLCWorkerThread │
    │                 │ │                 │ │                 │
    │ asyncio.new_    │ │ asyncio.new_    │ │ asyncio.new_    │
    │ event_loop()    │ │ event_loop()    │ │ event_loop()    │
    │                 │ │                 │ │                 │
    │ ┌─────────────┐ │ │ ┌─────────────┐ │ │ ┌─────────────┐ │
    │ │AsyncPLCWorker│ │ │AsyncPLCWorker│ │ │AsyncPLCWorker│ │
    │ │             │ │ │ │             │ │ │ │             │ │
    │ │ - connect   │ │ │ │ - connect   │ │ │ │ - connect   │ │
    │ │ - read/write│ │ │ │ - read/write│ │ │ │ - read/write│ │
    │ │ - polls     │ │ │ │ - polls     │ │ │ │ - polls     │ │
    │ └─────────────┘ │ │ └─────────────┘ │ │ └─────────────┘ │
    │        │        │ │        │        │ │        │        │
    │        ▼        │ │        ▼        │ │        ▼        │
    │  ┌──────────┐  │ │  ┌──────────┐  │ │  ┌──────────┐  │
    │  │Modbus TCP│  │ │  │Modbus TCP│  │ │  │Modbus TCP│  │
    │  │192.168.1.1│ │ │  │192.168.1.2│ │ │  │192.168.1.3│ │
    │  └──────────┘  │ │  └──────────┘  │ │  └──────────┘  │
    └─────────────────┘ └─────────────────┘ └─────────────────┘

ОСНОВНЫЕ КОМПОНЕНТЫ:
═══════════════════

1. ModbusDebugger (QMainWindow)
   ├── Работает в главном потоке Qt
   ├── Управляет множественными PLCWorkerThread
   ├── Принимает signals от worker потоков
   └── Отображает результаты в GUI

2. PLCWorkerThread (QThread)
   ├── Отдельный поток для каждого PLC
   ├── Создает asyncio.new_event_loop() в run()
   ├── Thread-safe методы для работы с PLC
   │   ├── connect_to_plc()
   │   ├── disconnect_from_plc()
   │   ├── execute_command()
   │   └── add_poll()
   └── PyQt signals для результатов
       ├── connected
       ├── disconnected
       ├── command_completed
       └── command_error

3. AsyncPLCWorker (async class)
   ├── Работает в asyncio loop потока
   ├── Управляет Modbus TCP соединением
   ├── Обрабатывает команды (read/write)
   └── Выполняет циклические опросы (polls)

КЛЮЧЕВЫЕ ОСОБЕННОСТИ:
═══════════════════

✅ ИЗОЛЯЦИЯ
   • Каждый PLC в отдельном потоке
   • Ошибка в PLC1 НЕ влияет на PLC2
   • Отказ одного соединения НЕ блокирует другие

✅ ПАРАЛЛЕЛИЗМ
   • Истинная параллельная работа (несколько CPU cores)
   • Команды на разные PLC выполняются одновременно
   • Polls работают независимо в каждом потоке

✅ THREAD-SAFETY
   • asyncio.run_coroutine_threadsafe() для вызовов из GUI
   • PyQt signals для передачи результатов
   • threading.Lock для latest_data

✅ БЕЗ qasync
   • Стандартный Qt event loop (app.exec())
   • Нет гибридного loop в главном потоке
   • Проще отладка и меньше конфликтов

WORKFLOW КОМАНДЫ:
════════════════

Пользователь нажимает "Читать"
    ↓
_read_command() (главный поток)
    ↓
thread.execute_command(cmd) × N PLC (неблокирующий)
    ↓
asyncio.run_coroutine_threadsafe() → worker потоки
    ↓
_async_execute_command() в каждом loop
    ↓
worker.request() → Modbus TCP
    ↓
signal command_completed.emit(result)
    ↓
_on_command_result() (главный поток)
    ↓
Накопление результатов (pending_results)
    ↓
Когда все собраны → _display_command_results()
    ↓
Отображение в GUI

ОТЛИЧИЯ ОТ ВЕРСИИ С qasync:
══════════════════════════

СТАРАЯ ВЕРСИЯ (qasync):               НОВАЯ ВЕРСИЯ (QThread):
──────────────────────────           ──────────────────────────
from qasync import QEventLoop        from PyQt6.QtCore import QThread

async def _connect_plc():            def _connect_plc():
    worker = AsyncPLCWorker(...)         thread = PLCWorkerThread(...)
    task = asyncio.create_task(...)     thread.start()

await asyncio.gather(*tasks)         thread.execute_command()
                                     # Результаты через signals

loop = QEventLoop(app)               app = QApplication(sys.argv)
loop.run_forever()                   sys.exit(app.exec())

ОДИН event loop для всех             ОТДЕЛЬНЫЙ event loop для каждого
asyncio.create_task() в GUI          QThread.start() + signals

ПАТТЕРН:
═══════
Основан на OpcUaWorker из AlbApp/src/communication/protocols/opc_ua.py
"""

import sys
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QTextEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QGroupBox, QTabWidget, QCheckBox, QTableWidget, QTableWidgetItem
)
from PyQt6.QtCore import QTimer, Qt

# PLCWorkerThread - наша QThread обертка с asyncio event loop
from plc_worker_thread import PLCWorkerThread


class ModbusDebugger(QMainWindow):
    """
    Главное окно отладчика для работы с множественными Modbus PLC

    ОСОБЕННОСТИ АРХИТЕКТУРЫ:
    =======================
    1. Каждый PLC работает в отдельном QThread с собственным asyncio event loop
    2. GUI работает в главном потоке Qt (БЕЗ qasync)
    3. Коммуникация между потоками через PyQt signals (thread-safe)
    4. Результаты команд собираются асинхронно через signals

    СТРУКТУРА ДАННЫХ:
    ================
    self.plcs = {
        "PLC1": {
            "thread": PLCWorkerThread,  # Поток с event loop
            "connected": bool,           # Статус подключения
            "config": {                  # Конфигурация PLC
                "host": "192.168.1.1",
                "port": 502,
                "device_id": 1
            }
        }
    }

    WORKFLOW ПОДКЛЮЧЕНИЯ:
    ====================
    1. Пользователь нажимает "Подключить"
    2. _connect_plc() создает PLCWorkerThread
    3. thread.start() запускает QThread (создается event loop в run())
    4. QTimer.singleShot(100) откладывает подключение (ждем создания loop)
    5. thread.connect_to_plc() вызывает _async_connect() в loop потока
    6. Результат возвращается через signal connected/connection_error

    WORKFLOW КОМАНД:
    ===============
    1. Пользователь нажимает "Читать" или "Записать"
    2. _read_command() / _write_command() отправляют команду всем активным PLC
    3. thread.execute_command() вызывает _async_execute_command() в loop потока
    4. Результаты возвращаются через signals command_completed/command_error
    5. Когда собраны все результаты, отображаются в GUI через _display_command_results()
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Modbus Worker Debugger - Multi PLC (QThread)")
        self.setGeometry(100, 100, 1200, 700)

        # ===== ХРАНИЛИЩЕ PLC =====
        # Словарь всех PLC: {plc_id: {"thread": PLCWorkerThread, "config": {...}, "connected": bool}}
        # ВАЖНО: "thread" может быть None, если PLC еще не подключен
        self.plcs = {}

        # ===== АКТИВНЫЕ PLC ДЛЯ КОМАНД =====
        # Множество ID PLC, на которые будут отправляться команды (read/write/poll)
        # Пользователь может выбрать несколько PLC одновременно
        self.active_plc_ids = set()

        # ===== СБОР РЕЗУЛЬТАТОВ ОТ МНОЖЕСТВЕННЫХ PLC =====
        # Когда команда отправляется на N PLC, результаты приходят асинхронно через signals
        # Мы собираем их в pending_results и ждем, пока len(pending_results) >= expected_results
        self.pending_results = {}   # {plc_id: result} - накопитель результатов
        self.expected_results = 0    # Сколько результатов мы ожидаем от текущей команды

        # ===== СОЗДАНИЕ UI =====
        self._create_ui()

        # ===== ТАЙМЕР ДЛЯ ОБНОВЛЕНИЯ GUI =====
        # Обновляет таблицу PLC и таблицу polls каждые 500мс
        # ВАЖНО: Обновление thread-safe, т.к. используем get_latest_data() с lock
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_gui)
        self.timer.start(500)

    def _create_ui(self):
        """Создание интерфейса"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Создаем вкладки
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Вкладка управления PLC
        self.tabs.addTab(self._create_plc_management_tab(), "🏭 Управление PLC")

        # Вкладка команд
        self.tabs.addTab(self._create_commands_tab(), "⚡ Команды")

        # Вкладка polls
        self.tabs.addTab(self._create_polls_tab(), "🔄 Циклические опросы")

        # Вкладка логов
        self.tabs.addTab(self._create_logs_tab(), "📋 Логи")

    def _create_plc_management_tab(self):
        """Вкладка управления PLC"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Группа добавления нового PLC
        add_group = QGroupBox("Добавить новый PLC")
        add_layout = QVBoxLayout(add_group)

        # PLC ID
        plc_layout = QHBoxLayout()
        plc_layout.addWidget(QLabel("PLC ID:"))
        self.new_plc_id_input = QLineEdit("PLC1")
        plc_layout.addWidget(self.new_plc_id_input)
        add_layout.addLayout(plc_layout)

        # Host
        host_layout = QHBoxLayout()
        host_layout.addWidget(QLabel("Host:"))
        self.new_host_input = QLineEdit("192.168.6.199")
        host_layout.addWidget(self.new_host_input)
        add_layout.addLayout(host_layout)

        # Port
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))
        self.new_port_input = QSpinBox()
        self.new_port_input.setRange(1, 65535)
        self.new_port_input.setValue(502)
        port_layout.addWidget(self.new_port_input)
        add_layout.addLayout(port_layout)

        # Device ID
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel("Device ID:"))
        self.new_device_id_input = QSpinBox()
        self.new_device_id_input.setRange(1, 255)
        self.new_device_id_input.setValue(1)
        device_layout.addWidget(self.new_device_id_input)
        add_layout.addLayout(device_layout)

        # Кнопка добавления
        add_btn = QPushButton("➕ Добавить PLC")
        add_btn.clicked.connect(self._add_plc)
        add_layout.addWidget(add_btn)

        layout.addWidget(add_group)

        # Таблица PLC
        plc_list_group = QGroupBox("Список PLC")
        plc_list_layout = QVBoxLayout(plc_list_group)

        self.plc_table = QTableWidget()
        self.plc_table.setColumnCount(6)
        self.plc_table.setHorizontalHeaderLabels(["PLC ID", "Host:Port", "Device ID", "Статус", "Действия", "Активный"])
        self.plc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        plc_list_layout.addWidget(self.plc_table)

        layout.addWidget(plc_list_group)

        return widget

    def _create_commands_tab(self):
        """Вкладка разовых команд"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Группа чтения
        read_group = QGroupBox("Чтение регистров")
        read_layout = QVBoxLayout(read_group)

        read_params = QHBoxLayout()
        read_params.addWidget(QLabel("Тип:"))
        self.read_type_combo = QComboBox()
        self.read_type_combo.addItems(["holding", "input", "coil", "discrete"])
        read_params.addWidget(self.read_type_combo)

        read_params.addWidget(QLabel("Адрес:"))
        self.read_address_input = QSpinBox()
        self.read_address_input.setRange(0, 65535)
        self.read_address_input.setValue(0)
        read_params.addWidget(self.read_address_input)

        read_params.addWidget(QLabel("Количество:"))
        self.read_count_input = QSpinBox()
        self.read_count_input.setRange(1, 125)
        self.read_count_input.setValue(10)
        read_params.addWidget(self.read_count_input)

        self.read_btn = QPushButton("📖 Читать")
        self.read_btn.clicked.connect(self._read_command)  # Теперь не async
        read_params.addWidget(self.read_btn)

        read_layout.addLayout(read_params)

        self.read_result = QTextEdit()
        self.read_result.setReadOnly(True)
        self.read_result.setMaximumHeight(100)
        read_layout.addWidget(self.read_result)

        layout.addWidget(read_group)

        # Группа записи
        write_group = QGroupBox("Запись регистров")
        write_layout = QVBoxLayout(write_group)

        write_params = QHBoxLayout()
        write_params.addWidget(QLabel("Тип:"))
        self.write_type_combo = QComboBox()
        self.write_type_combo.addItems(["holding", "holdings", "coil", "coils"])
        write_params.addWidget(self.write_type_combo)

        write_params.addWidget(QLabel("Адрес:"))
        self.write_address_input = QSpinBox()
        self.write_address_input.setRange(0, 65535)
        self.write_address_input.setValue(0)
        write_params.addWidget(self.write_address_input)

        write_params.addWidget(QLabel("Значение:"))
        self.write_value_input = QLineEdit("100")
        write_params.addWidget(self.write_value_input)

        self.write_btn = QPushButton("✍️ Записать")
        self.write_btn.clicked.connect(self._write_command)  # Теперь не async
        write_params.addWidget(self.write_btn)

        write_layout.addLayout(write_params)

        write_help = QLabel("Формат значения: одно число (100) или список [1,2,3]")
        write_help.setStyleSheet("color: gray; font-size: 10px;")
        write_layout.addWidget(write_help)

        self.write_result = QTextEdit()
        self.write_result.setReadOnly(True)
        self.write_result.setMaximumHeight(80)
        write_layout.addWidget(self.write_result)

        layout.addWidget(write_group)

        layout.addStretch()
        return widget

    def _create_polls_tab(self):
        """Вкладка циклических опросов"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Настройка опроса
        poll_setup = QGroupBox("Добавить опрос")
        poll_layout = QVBoxLayout(poll_setup)

        poll_params = QHBoxLayout()
        poll_params.addWidget(QLabel("Имя:"))
        self.poll_name_input = QLineEdit("poll_1")
        poll_params.addWidget(self.poll_name_input)

        poll_params.addWidget(QLabel("Тип:"))
        self.poll_type_combo = QComboBox()
        self.poll_type_combo.addItems(["holding", "input", "coil", "discrete"])
        poll_params.addWidget(self.poll_type_combo)

        poll_params.addWidget(QLabel("Адрес:"))
        self.poll_address_input = QSpinBox()
        self.poll_address_input.setRange(0, 65535)
        poll_params.addWidget(self.poll_address_input)

        poll_params.addWidget(QLabel("Кол-во:"))
        self.poll_count_input = QSpinBox()
        self.poll_count_input.setRange(1, 125)
        self.poll_count_input.setValue(10)
        poll_params.addWidget(self.poll_count_input)

        poll_params.addWidget(QLabel("Интервал (сек):"))
        self.poll_interval_input = QDoubleSpinBox()
        self.poll_interval_input.setRange(0.1, 60.0)
        self.poll_interval_input.setValue(1.0)
        self.poll_interval_input.setSingleStep(0.1)
        poll_params.addWidget(self.poll_interval_input)

        self.add_poll_btn = QPushButton("➕ Добавить опрос")
        self.add_poll_btn.clicked.connect(self._add_poll)
        poll_params.addWidget(self.add_poll_btn)

        poll_layout.addLayout(poll_params)
        layout.addWidget(poll_setup)

        # Таблица с активными опросами
        polls_group = QGroupBox("Активные опросы (latest_data)")
        polls_layout = QVBoxLayout(polls_group)

        self.polls_table = QTableWidget()
        self.polls_table.setColumnCount(3)
        self.polls_table.setHorizontalHeaderLabels(["Имя", "Последние данные", "Время"])
        polls_layout.addWidget(self.polls_table)

        layout.addWidget(polls_group)

        return widget

    def _create_logs_tab(self):
        """Вкладка логов"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Кнопки управления
        buttons = QHBoxLayout()
        clear_btn = QPushButton("🗑️ Очистить логи")
        clear_btn.clicked.connect(lambda: self.log_text.clear())
        buttons.addWidget(clear_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        # Лог
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        return widget

    # ==========================================================================
    # Логика работы с PLC
    # ==========================================================================

    def _add_plc(self):
        """Добавление нового PLC"""
        plc_id = self.new_plc_id_input.text().strip()

        if not plc_id:
            self.log("❌ Введите PLC ID")
            return

        if plc_id in self.plcs:
            self.log(f"❌ PLC '{plc_id}' уже существует")
            return

        host = self.new_host_input.text()
        port = self.new_port_input.value()
        device_id = self.new_device_id_input.value()

        # Добавляем PLC в список
        self.plcs[plc_id] = {
            "thread": None,  # PLCWorkerThread будет создан при подключении
            "connected": False,
            "config": {
                "host": host,
                "port": port,
                "device_id": device_id
            }
        }

        self.log(f"✅ Добавлен PLC '{plc_id}' ({host}:{port})")

        self._update_plc_table()

        # Инкрементируем имя для следующего PLC
        num = int(plc_id.replace("PLC", "")) if "PLC" in plc_id and plc_id.replace("PLC", "").isdigit() else 1
        self.new_plc_id_input.setText(f"PLC{num + 1}")

    def _connect_plc(self, plc_id: str):
        """
        Подключение к PLC - создание и запуск PLCWorkerThread

        ВАЖНО: Метод больше НЕ async! Работает синхронно в главном потоке.

        АЛГОРИТМ:
        =========
        1. Создаем PLCWorkerThread (QThread обертку)
        2. Подключаем все signals ДО запуска потока (КРИТИЧНО!)
        3. thread.start() запускает QThread.run(), который создает asyncio.new_event_loop()
        4. Ждем 100мс для создания loop (QTimer.singleShot)
        5. Вызываем thread.connect_to_plc() - это запускает async подключение в loop потока
        6. Результат возвращается через signal connected/connection_error

        THREAD-SAFETY:
        ==============
        - Создание thread и подключение signals - в главном потоке (безопасно)
        - thread.start() - запускает поток (безопасно)
        - thread.connect_to_plc() - thread-safe метод, использует run_coroutine_threadsafe()

        ПАТТЕРН QTimer.singleShot():
        ===========================
        Почему используем отложенный вызов?
        - thread.start() запускает run(), но event loop создается не мгновенно
        - Если сразу вызвать connect_to_plc(), loop может быть None
        - Задержка 100мс гарантирует, что loop.run_forever() уже запущен

        Args:
            plc_id: Уникальный идентификатор PLC (например "PLC1")
        """
        if plc_id not in self.plcs:
            return

        plc = self.plcs[plc_id]

        # Проверка на повторное подключение
        if plc["connected"]:
            self.log(f"⚠️ PLC '{plc_id}' уже подключен")
            return

        try:
            config = plc["config"]
            self.log(f"🔌 Подключение к PLC '{plc_id}' ({config['host']}:{config['port']})...")

            # ===== ШАГ 1: СОЗДАНИЕ ПОТОКА =====
            # Создаем QThread с asyncio event loop внутри
            thread = PLCWorkerThread(
                plc_id, config["host"], config["port"], config["device_id"]
            )

            # ===== ШАГ 2: ПОДКЛЮЧЕНИЕ SIGNALS =====
            # КРИТИЧНО: Подключаем signals ПЕРЕД thread.start()!
            # Иначе первые сигналы могут быть потеряны

            # Signal: Успешное подключение к PLC
            thread.connected.connect(lambda: self._on_plc_connected(plc_id))

            # Signal: Отключение от PLC
            thread.disconnected.connect(lambda: self._on_plc_disconnected(plc_id))

            # Signal: Ошибка подключения
            thread.connection_error.connect(lambda err: self._on_plc_error(plc_id, err))

            # Signal: Результат выполнения команды (read/write)
            thread.command_completed.connect(lambda res: self._on_command_result(plc_id, res))

            # Signal: Ошибка выполнения команды
            thread.command_error.connect(lambda err: self._on_command_error(plc_id, err))

            # Signal: Обновление данных из polls (опционально)
            thread.data_updated.connect(self._on_data_updated)

            # ===== ШАГ 3: СОХРАНЕНИЕ И ЗАПУСК =====
            # Сохраняем thread в словарь PLC
            plc["thread"] = thread

            # Запускаем поток - это вызовет PLCWorkerThread.run()
            # run() создаст asyncio.new_event_loop() и запустит loop.run_forever()
            thread.start()

            # ===== ШАГ 4: ОТЛОЖЕННОЕ ПОДКЛЮЧЕНИЕ =====
            # Даем 100мс на создание event loop в потоке
            # Затем вызываем thread.connect_to_plc() - это thread-safe метод
            # connect_to_plc() использует asyncio.run_coroutine_threadsafe() для вызова _async_connect()
            QTimer.singleShot(100, lambda: thread.connect_to_plc())

        except Exception as e:
            self.log(f"❌ Ошибка создания потока для PLC '{plc_id}': {e}")
            plc["thread"] = None
            self._update_plc_table()

    def _disconnect_plc(self, plc_id: str):
        """
        Отключение от PLC - остановка PLCWorkerThread

        ВАЖНО: Метод больше НЕ async! Работает синхронно в главном потоке.

        АЛГОРИТМ:
        =========
        1. thread.stop() - вызывает _async_disconnect() в loop потока
        2. _async_disconnect() останавливает AsyncPLCWorker
        3. loop.call_soon_threadsafe(loop.stop) - останавливает event loop
        4. thread.wait() - ждет завершения потока (блокирующий вызов!)
        5. Signal disconnected эмитится и вызывает _on_plc_disconnected()

        THREAD-SAFETY:
        ==============
        - thread.stop() - thread-safe метод
        - Использует run_coroutine_threadsafe() для вызова _async_disconnect()
        - thread.wait() блокирует GUI поток до завершения (обычно < 1 сек)

        БЛОКИРУЮЩИЙ ВЫЗОВ:
        ==================
        thread.stop() включает thread.wait() - это БЛОКИРУЕТ главный поток!
        Но это приемлемо, т.к.:
        - Отключение происходит быстро (обычно < 500мс)
        - Альтернатива (async) усложнит архитектуру
        - При закрытии приложения это необходимо для корректного завершения

        Args:
            plc_id: Уникальный идентификатор PLC
        """
        if plc_id not in self.plcs:
            return

        plc = self.plcs[plc_id]

        # Проверяем, есть ли что отключать
        if not plc["connected"] and not plc.get("thread"):
            return

        try:
            self.log(f"🔌 Отключение от PLC '{plc_id}'...")

            if plc.get("thread"):
                # ===== ОСТАНОВКА ПОТОКА =====
                # Это БЛОКИРУЮЩИЙ вызов! Ждет завершения потока.
                # Внутри вызывается:
                # 1. asyncio.run_coroutine_threadsafe(_async_disconnect(), loop).result(timeout=5.0)
                # 2. loop.call_soon_threadsafe(loop.stop)
                # 3. thread.wait()
                plc["thread"].stop()
                plc["thread"] = None

            plc["connected"] = False
            # Обновление таблицы произойдет через signal disconnected
            # (вызов _on_plc_disconnected)

        except Exception as e:
            self.log(f"❌ Ошибка отключения от PLC '{plc_id}': {e}")
            self._update_plc_table()

    def _remove_plc(self, plc_id: str):
        """Удаление PLC"""
        if plc_id not in self.plcs:
            return

        plc = self.plcs[plc_id]

        if plc["connected"]:
            self.log(f"❌ Сначала отключитесь от PLC '{plc_id}'")
            return

        del self.plcs[plc_id]

        # Если это был активный PLC, удаляем из множества активных
        if plc_id in self.active_plc_ids:
            self.active_plc_ids.discard(plc_id)
            self.log(f"✅ PLC '{plc_id}' удален из активных")

        self.log(f"✅ PLC '{plc_id}' удален")
        self._update_plc_table()

    def _toggle_active_plc(self, plc_id: str):
        """Переключение активности PLC (добавить/убрать из активных)"""
        if plc_id in self.plcs:
            if plc_id in self.active_plc_ids:
                self.active_plc_ids.discard(plc_id)
                self.log(f"⚫ PLC '{plc_id}' деактивирован")
            else:
                self.active_plc_ids.add(plc_id)
                self.log(f"✅ PLC '{plc_id}' активирован")
            self._update_plc_table()

    # ==========================================================================
    # ОБРАБОТЧИКИ SIGNALS ОТ PLCWorkerThread
    # ==========================================================================
    # Эти методы вызываются автоматически Qt при получении signals от потоков.
    # ВАЖНО: Обработчики выполняются в ГЛАВНОМ ПОТОКЕ, а не в worker потоке!
    # Qt автоматически обеспечивает thread-safety для signals.
    #
    # МЕХАНИЗМ:
    # 1. Worker поток эмитит signal (например, connected.emit())
    # 2. Qt помещает событие в очередь главного потока
    # 3. Главный event loop вызывает подключенный slot (_on_plc_connected)
    # 4. Slot выполняется в главном потоке - безопасно обновлять GUI
    # ==========================================================================

    def _on_plc_connected(self, plc_id: str):
        """
        Обработчик успешного подключения к PLC

        Вызывается когда PLCWorkerThread эмитит signal connected.
        Это означает, что:
        - AsyncPLCWorker создан
        - Соединение с Modbus TCP установлено
        - _command_loop() запущен и готов принимать команды

        THREAD-SAFETY:
        ==============
        Вызывается в главном потоке (Qt гарантирует), безопасно обновлять GUI.

        Args:
            plc_id: ID подключенного PLC
        """
        plc = self.plcs.get(plc_id)
        if plc:
            plc["connected"] = True
            self.log(f"✅ PLC '{plc_id}' подключен")
            self._update_plc_table()  # Обновляем таблицу (кнопки и статус)

    def _on_plc_disconnected(self, plc_id: str):
        """
        Обработчик отключения от PLC

        Вызывается когда PLCWorkerThread эмитит signal disconnected.
        Это означает, что:
        - AsyncPLCWorker остановлен (worker.stop() вызван)
        - Все poll tasks отменены
        - Соединение с Modbus TCP закрыто

        Args:
            plc_id: ID отключенного PLC
        """
        plc = self.plcs.get(plc_id)
        if plc:
            plc["connected"] = False
            self.log(f"🔌 PLC '{plc_id}' отключен")
            self._update_plc_table()  # Обновляем таблицу

    def _on_plc_error(self, plc_id: str, error: str):
        """
        Обработчик ошибки подключения к PLC

        Вызывается когда PLCWorkerThread эмитит signal connection_error.
        Причины ошибки:
        - Неверный IP адрес / порт
        - PLC недоступен в сети
        - Таймаут подключения
        - Ошибка создания AsyncModbusTcpClient

        Args:
            plc_id: ID PLC с ошибкой
            error: Текст ошибки
        """
        self.log(f"❌ [{plc_id}] Ошибка: {error}")
        plc = self.plcs.get(plc_id)
        if plc:
            plc["connected"] = False
            self._update_plc_table()

    def _on_command_result(self, plc_id: str, result):
        """
        Обработчик успешного выполнения команды от PLC

        ПАТТЕРН СБОРА РЕЗУЛЬТАТОВ:
        =========================
        Когда команда отправляется на N активных PLC, результаты приходят асинхронно:
        1. _read_command() отправляет команду на PLC1, PLC2, PLC3
        2. Устанавливаем expected_results = 3
        3. Каждый PLC вызывает этот обработчик при завершении
        4. Результаты накапливаются в pending_results
        5. Когда len(pending_results) >= expected_results - отображаем все

        THREAD-SAFETY:
        ==============
        pending_results - это dict в главном потоке, обновляется только из slots.
        Все slots вызываются последовательно в главном потоке - нет race conditions.

        Args:
            plc_id: ID PLC, который выполнил команду
            result: Результат команды (например, список регистров [100, 200, 300])
        """
        # Сохраняем результат от этого PLC
        self.pending_results[plc_id] = result

        # Проверяем, собрали ли мы все результаты
        if len(self.pending_results) >= self.expected_results:
            # Все результаты получены - отображаем
            self._display_command_results()

    def _on_command_error(self, plc_id: str, error: str):
        """
        Обработчик ошибки выполнения команды от PLC

        Причины ошибки:
        - Неверный адрес регистра
        - Неверный тип регистра
        - Таймаут операции
        - Потеря связи с PLC
        - ModbusException

        ВАЖНО:
        ======
        Ошибка сохраняется как результат ("Error: ..."), чтобы не ломать
        механизм сбора результатов. Если один PLC вернул ошибку, остальные
        могут вернуть успешный результат.

        Args:
            plc_id: ID PLC с ошибкой
            error: Текст ошибки
        """
        self.log(f"❌ [{plc_id}] Ошибка команды: {error}")

        # Сохраняем ошибку как результат
        self.pending_results[plc_id] = f"Error: {error}"

        # Проверяем, собрали ли мы все результаты (включая ошибки)
        if len(self.pending_results) >= self.expected_results:
            self._display_command_results()

    def _on_data_updated(self, poll_name: str, data: dict):
        """
        Обработчик обновления данных из poll (опционально)

        Вызывается каждый раз, когда poll_loop обновляет latest_data.
        В текущей реализации не используется, т.к. данные обновляются
        через _update_gui() по таймеру.

        Можно использовать для:
        - Логирования изменений
        - Триггеров на определенные значения
        - Уведомлений об аномалиях

        Args:
            poll_name: Имя poll (например "PLC1_poll_1")
            data: Словарь с данными {"data": [100, 200, 300]}
        """
        # Опционально: логировать или обрабатывать обновления
        pass

    def _display_command_results(self):
        """
        Отображение собранных результатов от всех PLC

        Вызывается когда собраны результаты от всех активных PLC.
        Форматирует результаты и отображает в текстовых полях.

        ФОРМАТ ОТОБРАЖЕНИЯ:
        ===================
        [PLC1] ✅ [100, 200, 300]
        [PLC2] ❌ Error: Connection timeout
        [PLC3] ✅ [150, 250, 350]

        УПРОЩЕНИЕ:
        ==========
        Обновляем оба поля (read_result и write_result), т.к. мы не различаем
        тип команды. В реальном приложении можно добавить флаг или проверку.
        """
        result_text = ""

        # Форматируем результаты от каждого PLC
        for plc_id, result in self.pending_results.items():
            if isinstance(result, str) and result.startswith("Error"):
                # Ошибка
                result_text += f"[{plc_id}] ❌ {result}\n"
            else:
                # Успешный результат (обычно список регистров)
                result_text += f"[{plc_id}] ✅ {result}\n"

        # Обновляем оба поля результатов
        # (можно улучшить, добавив различение read/write)
        self.read_result.setText(result_text)
        self.write_result.setText(result_text)

    def _update_plc_table(self):
        """Обновление таблицы PLC"""
        self.plc_table.setRowCount(len(self.plcs))

        for row, (plc_id, plc) in enumerate(self.plcs.items()):
            config = plc["config"]

            # PLC ID
            self.plc_table.setItem(row, 0, QTableWidgetItem(plc_id))

            # Host:Port
            self.plc_table.setItem(row, 1, QTableWidgetItem(f"{config['host']}:{config['port']}"))

            # Device ID
            self.plc_table.setItem(row, 2, QTableWidgetItem(str(config['device_id'])))

            # Статус
            status_item = QTableWidgetItem("🟢 Подключено" if plc["connected"] else "⚫ Отключено")
            self.plc_table.setItem(row, 3, status_item)

            # Кнопки действий
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)

            if plc["connected"]:
                disconnect_btn = QPushButton("🔌 Отключить")
                disconnect_btn.clicked.connect(lambda checked, pid=plc_id: self._disconnect_plc(pid))
                actions_layout.addWidget(disconnect_btn)
            else:
                connect_btn = QPushButton("🔌 Подключить")
                connect_btn.clicked.connect(lambda checked, pid=plc_id: self._connect_plc(pid))
                actions_layout.addWidget(connect_btn)

                remove_btn = QPushButton("🗑️")
                remove_btn.clicked.connect(lambda checked, pid=plc_id: self._remove_plc(pid))
                actions_layout.addWidget(remove_btn)

            self.plc_table.setCellWidget(row, 4, actions_widget)

            # Чекбокс "Активный" (можно выбрать несколько PLC)
            active_widget = QWidget()
            active_layout = QHBoxLayout(active_widget)
            active_layout.setContentsMargins(2, 2, 2, 2)
            active_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            active_checkbox = QPushButton("✓" if plc_id in self.active_plc_ids else "○")
            active_checkbox.setMaximumWidth(40)
            active_checkbox.clicked.connect(lambda checked, pid=plc_id: self._toggle_active_plc(pid))
            active_layout.addWidget(active_checkbox)

            self.plc_table.setCellWidget(row, 5, active_widget)

        self.plc_table.resizeColumnsToContents()

    def _read_command(self):
        """
        Выполнение команды чтения на всех активных PLC

        ВАЖНО: Метод больше НЕ async! Работает синхронно в главном потоке.

        СТАРЫЙ ПОДХОД (с qasync):
        ========================
        async def _read_command(self):
            tasks = [plc["worker"].request(cmd) for plc_id in active_plc_ids]
            results = await asyncio.gather(*tasks)  # Блокирует event loop
            display_results(results)

        НОВЫЙ ПОДХОД (QThread + signals):
        =================================
        def _read_command(self):
            for plc_id in active_plc_ids:
                thread.execute_command(cmd)  # Неблокирующий вызов
            # Результаты придут через signals

        ПРЕИМУЩЕСТВА:
        =============
        - НЕ блокирует GUI event loop
        - Истинный параллелизм (каждый PLC в своем потоке)
        - Упрощенная обработка ошибок (через signals)
        - Легко добавлять/удалять PLC динамически

        WORKFLOW:
        =========
        1. Пользователь нажимает кнопку "Читать"
        2. Этот метод вызывается синхронно
        3. Формируем команду ("read", type, address, count)
        4. Отправляем команду всем активным PLC через thread.execute_command()
        5. execute_command() использует run_coroutine_threadsafe() для вызова _async_execute_command()
        6. _async_execute_command() вызывает worker.request() в loop потока
        7. Результат эмитится через signal command_completed
        8. _on_command_result() собирает результаты от всех PLC
        9. Когда все результаты собраны - отображаем через _display_command_results()

        ПАТТЕРН СБОРА РЕЗУЛЬТАТОВ:
        =========================
        pending_results = {}      # Очищаем
        expected_results = N      # Количество активных PLC

        Для каждого PLC:
            thread.execute_command()  # Неблокирующий вызов

        # Метод завершается, GUI не блокируется

        # Позже, асинхронно:
        _on_command_result(plc_id, result)  # Накапливаем результаты
        if len(pending_results) >= expected_results:
            _display_command_results()  # Отображаем все
        """
        if not self.active_plc_ids:
            self.log("❌ Не выбраны активные PLC (отметьте нужные в таблице)")
            return

        # Получаем параметры команды из GUI
        type_ = self.read_type_combo.currentText()    # "holding", "input", "coil", "discrete"
        address = self.read_address_input.value()     # Адрес первого регистра
        count = self.read_count_input.value()         # Количество регистров для чтения

        self.log(f"📖 Чтение {type_} регистров на {len(self.active_plc_ids)} PLC: адрес={address}, количество={count}")

        # ===== ФОРМИРОВАНИЕ КОМАНДЫ =====
        # Команда - это tuple, который будет передан в AsyncPLCWorker.request()
        # Формат: ("read", type, address, count)
        command = ("read", type_, address, count)

        # ===== ОЧИСТКА РЕЗУЛЬТАТОВ ПРЕДЫДУЩЕЙ КОМАНДЫ =====
        self.pending_results = {}   # Очищаем накопитель результатов
        self.expected_results = 0    # Сбрасываем счетчик ожидаемых результатов

        # ===== ОТПРАВКА КОМАНДЫ ВСЕМ АКТИВНЫМ PLC =====
        for plc_id in self.active_plc_ids:
            plc = self.plcs.get(plc_id)

            # Проверяем, что PLC подключен и thread существует
            if plc and plc["connected"] and plc.get("thread"):
                # ===== THREAD-SAFE ОТПРАВКА КОМАНДЫ =====
                # execute_command() - это синхронный метод, который:
                # 1. Использует asyncio.run_coroutine_threadsafe()
                # 2. Вызывает _async_execute_command() в loop потока
                # 3. НЕ блокирует текущий поток
                plc["thread"].execute_command(command)

                # Увеличиваем счетчик ожидаемых результатов
                self.expected_results += 1
            else:
                # PLC не подключен - пропускаем
                self.log(f"⚠️ [{plc_id}] PLC не подключен, пропускаем")

        # Проверяем, есть ли подключенные PLC
        if self.expected_results == 0:
            self.log("❌ Нет подключенных активных PLC")
            self.read_result.setText("Нет подключенных PLC")
            return

        # ===== МЕТОД ЗАВЕРШАЕТСЯ =====
        # GUI НЕ блокируется! Результаты придут асинхронно через signals:
        # - _on_command_result() для успешных результатов
        # - _on_command_error() для ошибок
        # Когда все результаты собраны, _display_command_results() отобразит их

    def _write_command(self):
        """
        Выполнение команды записи на всех активных PLC

        ВАЖНО: Метод больше НЕ async! Работает синхронно в главном потоке.

        ОСОБЕННОСТИ ЗАПИСИ:
        ===================
        Запись сложнее чтения, т.к. нужно:
        - Парсить значение из строки (может быть одно число или список)
        - Определить count автоматически (для списков)
        - Различать типы записи (holding/holdings, coil/coils)

        ФОРМАТЫ ЗНАЧЕНИЙ:
        =================
        Одно значение:
            "100" → value = 100, type = "holding" или "coil"

        Несколько значений:
            "[100, 200, 300]" → value = [100, 200, 300], type = "holdings" или "coils"

        ТИПЫ ЗАПИСИ:
        ============
        - "holding" → write_register (одно значение)
        - "holdings" → write_registers (несколько значений)
        - "coil" → write_coil (один бит)
        - "coils" → write_coils (несколько битов)

        WORKFLOW:
        =========
        Аналогичен _read_command(), но с дополнительным параметром value в команде.
        Команда: ("write", type, address, count, value)

        ОБРАБОТКА ОШИБОК:
        =================
        Ошибки парсинга обрабатываются локально (try-except).
        Ошибки выполнения (Modbus) приходят через signal command_error.
        """
        if not self.active_plc_ids:
            self.log("❌ Не выбраны активные PLC (отметьте нужные в таблице)")
            return

        try:
            # Получаем параметры команды из GUI
            type_ = self.write_type_combo.currentText()   # "holding", "holdings", "coil", "coils"
            address = self.write_address_input.value()    # Адрес первого регистра
            value_text = self.write_value_input.text()    # Значение(я) для записи

            # ===== ПАРСИНГ ЗНАЧЕНИЯ =====
            # Поддерживаем два формата:
            # 1. Одно значение: "100" → int
            # 2. Список значений: "[100, 200, 300]" → list
            if value_text.startswith('[') and value_text.endswith(']'):
                # Список - используем eval (небезопасно для production, но ок для debugger)
                value = eval(value_text)
            else:
                # Одно значение - преобразуем в int
                value = int(value_text)

            # Определяем count автоматически
            count = len(value) if isinstance(value, list) else 1

            self.log(f"✍️ Запись в {type_} на {len(self.active_plc_ids)} PLC: адрес={address}, значение={value}")

            # ===== ФОРМИРОВАНИЕ КОМАНДЫ =====
            # Формат: ("write", type, address, count, value)
            # ВАЖНО: count нужен для AsyncPLCWorker, хотя для write можно определить из value
            command = ("write", type_, address, count, value)

            # ===== ОЧИСТКА РЕЗУЛЬТАТОВ =====
            self.pending_results = {}
            self.expected_results = 0

            # ===== ОТПРАВКА КОМАНДЫ ВСЕМ АКТИВНЫМ PLC =====
            for plc_id in self.active_plc_ids:
                plc = self.plcs.get(plc_id)
                if plc and plc["connected"] and plc.get("thread"):
                    # Thread-safe отправка команды
                    plc["thread"].execute_command(command)
                    self.expected_results += 1
                else:
                    self.log(f"⚠️ [{plc_id}] PLC не подключен, пропускаем")

            if self.expected_results == 0:
                self.log("❌ Нет подключенных активных PLC")
                self.write_result.setText("Нет подключенных PLC")
                return

            # Результаты придут через signals (_on_command_result / _on_command_error)

        except Exception as e:
            # Ошибка парсинга значения (например, невалидный список)
            self.write_result.setText(f"Критическая ошибка: {e}")
            self.log(f"❌ Критическая ошибка парсинга: {e}")

    def _add_poll(self):
        """
        Добавление циклического опроса на все активные PLC

        ЦИКЛИЧЕСКИЙ ОПРОС (POLL):
        ========================
        Poll - это фоновая задача, которая периодически читает указанные регистры
        и сохраняет результат в latest_data.

        ОТЛИЧИЕ ОТ КОМАНДЫ:
        ===================
        Команда (read/write):
        - Разовое выполнение
        - Результат возвращается через signal command_completed
        - Пользователь явно нажимает кнопку

        Poll:
        - Непрерывное выполнение (цикл с интервалом)
        - Результаты сохраняются в latest_data автоматически
        - Отображается в таблице polls через таймер _update_gui()

        WORKFLOW:
        =========
        1. Пользователь настраивает параметры poll (имя, тип, адрес, интервал)
        2. Нажимает "Добавить опрос"
        3. Этот метод вызывается синхронно
        4. Для каждого активного PLC:
           - Формируем poll_config с уникальным именем (добавляем префикс plc_id)
           - Вызываем thread.add_poll(poll_config)
        5. add_poll() использует run_coroutine_threadsafe() для вызова _async_add_poll()
        6. _async_add_poll() создает задачу asyncio.create_task(worker._poll_loop())
        7. _poll_loop() работает в фоне, обновляя latest_data каждые interval секунд

        ИМЕНОВАНИЕ:
        ===========
        Каждый poll должен иметь уникальное имя.
        Если пользователь задал имя "poll_1", а опрос добавляется на 3 PLC:
        - PLC1: "PLC1_poll_1"
        - PLC2: "PLC2_poll_1"
        - PLC3: "PLC3_poll_1"

        Это позволяет различать данные от разных PLC в таблице polls.

        СТРУКТУРА POLL_CONFIG:
        =====================
        {
            "name": "PLC1_poll_1",     # Уникальное имя
            "type": "holding",          # Тип регистров
            "address": 0,               # Адрес первого регистра
            "count": 10,                # Количество регистров
            "interval": 1.0             # Интервал опроса в секундах
        }
        """
        if not self.active_plc_ids:
            self.log("❌ Не выбраны активные PLC (отметьте нужные в таблице)")
            return

        try:
            # Получаем параметры poll из GUI
            name = self.poll_name_input.text()           # Базовое имя (например "poll_1")
            type_ = self.poll_type_combo.currentText()   # Тип регистров
            address = self.poll_address_input.value()    # Адрес первого регистра
            count = self.poll_count_input.value()        # Количество регистров
            interval = self.poll_interval_input.value()  # Интервал в секундах

            self.log(f"🔄 Добавление опроса '{name}' на {len(self.active_plc_ids)} PLC: {type_}[{address}:{address+count-1}] каждые {interval}с")

            added_count = 0
            for plc_id in self.active_plc_ids:
                plc = self.plcs.get(plc_id)

                # Проверяем, что PLC подключен
                if not plc or not plc["connected"] or not plc.get("thread"):
                    self.log(f"⚠️ [{plc_id}] PLC не подключен, пропускаем")
                    continue

                # ===== ФОРМИРОВАНИЕ КОНФИГУРАЦИИ POLL =====
                # ВАЖНО: Добавляем префикс plc_id к имени для уникальности
                poll_config = {
                    "name": f"{plc_id}_{name}",  # Уникальное имя: "PLC1_poll_1"
                    "type": type_,
                    "address": address,
                    "count": count,
                    "interval": interval
                }

                # ===== THREAD-SAFE ДОБАВЛЕНИЕ POLL =====
                # add_poll() - синхронный метод, который:
                # 1. Использует asyncio.run_coroutine_threadsafe()
                # 2. Вызывает _async_add_poll() в loop потока
                # 3. _async_add_poll() создает задачу worker._poll_loop()
                # 4. _poll_loop() работает в фоне, обновляя latest_data
                plc["thread"].add_poll(poll_config)

                self.log(f"✅ [{plc_id}] Опрос '{name}' добавлен")
                added_count += 1

            if added_count > 0:
                self.log(f"✅ Опрос '{name}' успешно добавлен на {added_count} PLC")

                # ===== АВТОИНКРЕМЕНТ ИМЕНИ =====
                # Увеличиваем номер в имени для следующего опроса
                # "poll_1" → "poll_2"
                num = int(name.split('_')[-1]) if '_' in name else 0
                self.poll_name_input.setText(f"poll_{num + 1}")
            else:
                self.log("❌ Не удалось добавить опрос ни на один PLC")

        except Exception as e:
            self.log(f"❌ Ошибка добавления опроса: {e}")

    def _update_gui(self):
        """
        Обновление GUI - вызывается по таймеру каждые 500мс

        НАЗНАЧЕНИЕ:
        ===========
        - Обновляет таблицу PLC (статус, кнопки)
        - Обновляет таблицу polls (последние данные от всех PLC)

        THREAD-SAFETY:
        ==============
        Этот метод вызывается в главном потоке по таймеру Qt.
        Для получения данных от потоков используется thread-safe метод get_latest_data().

        МЕХАНИЗМ get_latest_data():
        ==========================
        1. В PLCWorkerThread работает _sync_latest_data_loop()
        2. Каждые 500мс копирует worker.latest_data в _latest_data с lock
        3. get_latest_data() возвращает копию _latest_data с lock
        4. Два потока НЕ обращаются к одним данным напрямую - используется копирование

        АЛЬТЕРНАТИВА:
        =============
        Вместо таймера можно было использовать signal data_updated от каждого poll.
        Но это создает много событий (каждый poll эмитит каждые N секунд).
        Таймер проще и эффективнее для отображения.

        ОПТИМИЗАЦИЯ:
        ============
        Если PLC много (10+), таймер может замедлить GUI.
        Решения:
        - Увеличить интервал таймера (1000мс вместо 500мс)
        - Обновлять только видимые строки таблицы
        - Использовать QTableView с моделью вместо QTableWidget
        """
        # ===== ОБНОВЛЕНИЕ ТАБЛИЦЫ PLC =====
        # Обновляет статус, кнопки подключения/отключения
        self._update_plc_table()

        # ===== СБОР ДАННЫХ ОТ ВСЕХ PLC =====
        all_latest_data = {}
        for plc_id, plc in self.plcs.items():
            if plc["connected"] and plc.get("thread"):
                # ===== THREAD-SAFE ПОЛУЧЕНИЕ ДАННЫХ =====
                # get_latest_data() использует threading.Lock внутри
                # Возвращает копию _latest_data, не прямую ссылку
                plc_data = plc["thread"].get_latest_data()

                # Объединяем данные от всех PLC
                # Имена polls уникальны (содержат префикс plc_id)
                all_latest_data.update(plc_data)

        # ===== ОБНОВЛЕНИЕ ТАБЛИЦЫ POLLS =====
        self.polls_table.setRowCount(len(all_latest_data))
        for i, (name, data) in enumerate(all_latest_data.items()):
            # Имя poll (например "PLC1_poll_1")
            self.polls_table.setItem(i, 0, QTableWidgetItem(name))

            # Данные (обрезаем до 100 символов для длинных списков)
            self.polls_table.setItem(i, 1, QTableWidgetItem(str(data)[:100]))

            # Время последнего обновления
            self.polls_table.setItem(i, 2, QTableWidgetItem(datetime.now().strftime("%H:%M:%S")))

        # Автоматическая подгонка ширины столбцов
        self.polls_table.resizeColumnsToContents()

    def log(self, message: str):
        """
        Добавление сообщения в лог с временной меткой

        ФОРМАТ:
        =======
        [HH:MM:SS.mmm] Текст сообщения

        АВТОПРОКРУТКА:
        ==============
        Лог автоматически прокручивается к последнему сообщению.
        Это удобно для отслеживания событий в реальном времени.

        THREAD-SAFETY:
        ==============
        Метод вызывается только из главного потока (обработчики signals, GUI callbacks).
        QTextEdit не thread-safe, поэтому вызов из worker потока был бы ошибкой.

        Args:
            message: Текст сообщения для логирования
        """
        # Создаем временную метку с миллисекундами
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Убираем последние 3 цифры (микросекунды)

        # Добавляем сообщение в лог
        self.log_text.append(f"[{timestamp}] {message}")

        # ===== АВТОПРОКРУТКА К ПОСЛЕДНЕМУ СООБЩЕНИЮ =====
        # Устанавливаем позицию scrollbar в максимум (самый низ)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def closeEvent(self, event):
        """
        Обработка закрытия окна - корректная остановка всех потоков

        КРИТИЧЕСКАЯ ВАЖНОСТЬ:
        ====================
        При закрытии приложения НЕОБХОДИМО корректно остановить все потоки!
        Иначе:
        - Event loops останутся запущенными
        - Соединения с PLC останутся открытыми
        - Процесс Python не завершится (зависнет)

        АЛГОРИТМ:
        =========
        1. Останавливаем таймер GUI (прекращаем обновления)
        2. Для каждого PLC:
           - Проверяем, запущен ли thread
           - Вызываем thread.stop() - это БЛОКИРУЮЩИЙ вызов!
        3. thread.stop() выполняет:
           - _async_disconnect() в loop потока (останавливает worker)
           - loop.call_soon_threadsafe(loop.stop) (останавливает event loop)
           - thread.wait() (ждет завершения QThread.run())
        4. Принимаем событие закрытия

        БЛОКИРОВКА GUI:
        ===============
        closeEvent БЛОКИРУЕТ GUI пока все потоки не остановятся!
        Это нормально, т.к.:
        - Остановка каждого потока занимает < 1 сек
        - Важнее корректное завершение, чем мгновенное закрытие
        - Альтернатива (async завершение) сложна и не даст преимуществ

        ПОЧЕМУ list(self.plcs.items())?
        ===============================
        Используем list() для создания копии, т.к. в теории можно модифицировать
        self.plcs во время итерации (хотя в данном коде это не происходит).
        Хорошая практика для безопасности.

        Args:
            event: QCloseEvent - событие закрытия окна
        """
        # ===== ОСТАНОВКА ТАЙМЕРА =====
        # Прекращаем периодическое обновление GUI
        self.timer.stop()

        # ===== ОСТАНОВКА ВСЕХ ПОТОКОВ =====
        for plc_id, plc in list(self.plcs.items()):
            if plc.get("thread") and plc["thread"].isRunning():
                self.log(f"Остановка потока {plc_id}...")

                # ===== БЛОКИРУЮЩАЯ ОСТАНОВКА ПОТОКА =====
                # thread.stop() - это синхронный метод, который:
                # 1. Вызывает _async_disconnect() через run_coroutine_threadsafe()
                # 2. Ждет завершения с timeout=5.0 сек
                # 3. Останавливает event loop через loop.call_soon_threadsafe()
                # 4. Вызывает thread.wait() - ждет завершения QThread
                #
                # ВАЖНО: Этот вызов БЛОКИРУЕТ текущий поток до завершения!
                plc["thread"].stop()

        # Принимаем событие закрытия (окно закроется)
        event.accept()


def main():
    """
    Запуск отладчика - стандартный Qt event loop (БЕЗ qasync)

    КЛЮЧЕВОЕ ОТЛИЧИЕ ОТ СТАРОЙ ВЕРСИИ:
    ==================================
    СТАРЫЙ КОД (с qasync):
    ---------------------
    from qasync import QEventLoop
    import asyncio

    app = QApplication(sys.argv)
    loop = QEventLoop(app)              # qasync интеграция
    asyncio.set_event_loop(loop)        # Главный loop = Qt + asyncio
    window = ModbusDebugger()
    window.show()
    with loop:
        loop.run_forever()              # Гибридный event loop

    НОВЫЙ КОД (QThread + asyncio):
    ------------------------------
    app = QApplication(sys.argv)
    window = ModbusDebugger()
    window.show()
    sys.exit(app.exec())                # Стандартный Qt event loop

    ПОЧЕМУ БЕЗ qasync?
    ==================
    1. Упрощение: Не нужна интеграция Qt + asyncio в главном потоке
    2. Изоляция: Каждый PLC имеет свой asyncio loop в отдельном потоке
    3. Стабильность: qasync может конфликтовать с некоторыми async библиотеками
    4. Производительность: Истинный параллелизм (несколько CPU cores)
    5. Стандартность: Используем проверенный Qt паттерн (QThread)

    ГДЕ ASYNCIO?
    ============
    asyncio работает в КАЖДОМ PLCWorkerThread:
    - PLCWorkerThread.run() создает asyncio.new_event_loop()
    - В этом loop работает AsyncPLCWorker
    - Коммуникация с GUI через PyQt signals (thread-safe)

    ПАТТЕРН:
    ========
    Главный поток:    Qt event loop (GUI)
    Worker поток 1:   asyncio event loop (PLC1)
    Worker поток 2:   asyncio event loop (PLC2)
    Worker поток 3:   asyncio event loop (PLC3)
    ...

    Каждый поток изолирован, сбой одного не влияет на другие!
    """
    # ===== СОЗДАНИЕ ПРИЛОЖЕНИЯ =====
    app = QApplication(sys.argv)

    # ===== СОЗДАНИЕ ГЛАВНОГО ОКНА =====
    window = ModbusDebugger()
    window.show()

    # ===== ЗАПУСК СТАНДАРТНОГО QT EVENT LOOP =====
    # app.exec() - блокирующий вызов, возвращает код завершения
    # sys.exit() - завершает процесс Python с этим кодом
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
