import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QTextEdit,
    QFormLayout, QFrame
)
from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtGui import QFont

# Backend управляет OPC UA серверами — каждый сервер в отдельном QThread с asyncio
from unified_backend_package.backend.opcua_backend import OpcUaBackend

# OpcUaButton  — кнопка с двумя режимами (клик / удержание) и feedback-подсветкой
# WriteChannel — связывает сигналы кнопки с конкретным тегом в backend
from upgradable_qt_widgets.button import OpcUaButton, WriteChannel

# Идентификатор сервера внутри OpcUaBackend.
# Произвольная строка — используется как ключ словаря backend.servers
SERVER_ID = "TEST_OPC"


# ══════════════════════════════════════════════════════════════════════════════
# LogWidget — виджет лога с временными метками и цветными сообщениями
# ══════════════════════════════════════════════════════════════════════════════

class LogWidget(QTextEdit):
    """
    Поле вывода событий в стиле терминала.

    Каждая строка содержит временную метку и цветное сообщение.
    Цвет задаётся при вызове log() — стандартные CSS-цвета или hex.

    Примеры:
        log.log("Подключение...")              # белый (дефолт)
        log.log("Подключен", "green")          # зелёный — успех
        log.log("Ошибка: ...", "red")          # красный — ошибка
        log.log("read ns=2;s=T = 23.5", "blue")  # синий — чтение
        log.log("Watchdog: обрыв", "orange")   # оранжевый — предупреждение
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setReadOnly(True)               # только чтение — пользователь не вводит текст
        self.setMaximumHeight(200)           # ограничиваем высоту, чтобы не растягивалось
        self.setFont(QFont("Consolas", 9))   # моноширинный шрифт — столбики выравниваются

        # Тёмный фон
        self.setStyleSheet("background-color: #3c3c3c; color: #f0f0f0;")

    def log(self, msg: str, color: str = "#f0f0f0"):
        """
        Добавить строку в лог.

        Args:
            msg:   Текст сообщения
            color: CSS-цвет — имя ("red", "green") или hex ("#2ecc71").
                   По умолчанию #f0f0f0 — почти белый, хорошо читается на тёмном фоне.
        """
        # Временная метка с миллисекундами — точность до 1 мс
        ts = QDateTime.currentDateTime().toString("hh:mm:ss.zzz")

        # Временная метка чуть темнее (#e0e0e0) — отличается от основного текста,
        # но не отвлекает от содержимого сообщения
        self.append(
            f'<span style="color:#e0e0e0">[{ts}]</span> '
            f'<span style="color:{color}">{msg}</span>'
        )

        # Автоскролл — прокручиваем вниз, чтобы всегда была видна последняя строка
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


# ══════════════════════════════════════════════════════════════════════════════
# StatusLabel — цветной индикатор состояния соединения
# ══════════════════════════════════════════════════════════════════════════════

class StatusLabel(QLabel):
    """
    Лейбл с тремя визуальными состояниями подключения.

    Состояния и их внешний вид:
        "disconnected" → красный  ● Отключен       (начальное состояние)
        "connecting"   → жёлтый   ◌ Подключение...
        "connected"    → зелёный  ● Подключен

    Использование:
        label.set_state("connecting")   # при нажатии "Подключить"
        label.set_state("connected")    # когда backend сообщил об успехе
        label.set_state("disconnected") # при отключении или ошибке
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(120)  # фиксируем ширину — текст не прыгает при смене состояния
        self._set_disconnected()   # инициализируем в начальное состояние

    # --- Приватные методы смены стиля ---

    def _set_disconnected(self):
        """Красный — нет подключения"""
        self.setText("● Отключен")
        self.setStyleSheet("color: #e74c3c; font-weight: bold;")

    def _set_connected(self):
        """Зелёный — подключение активно"""
        self.setText("● Подключен")
        self.setStyleSheet("color: #2ecc71; font-weight: bold;")

    def _set_connecting(self):
        """Жёлтый — идёт процесс подключения"""
        self.setText("◌ Подключение...")
        self.setStyleSheet("color: #f39c12; font-weight: bold;")

    def set_state(self, state: str):
        """
        Публичный метод смены состояния.

        Args:
            state: "connected" | "connecting" | "disconnected"
        """
        if state == "connected":
            self._set_connected()
        elif state == "connecting":
            self._set_connecting()
        else:
            self._set_disconnected()


# ══════════════════════════════════════════════════════════════════════════════
# TestWindow — главное окно теста
# ══════════════════════════════════════════════════════════════════════════════

class TestWindow(QMainWindow):
    """
    Тестовое окно: демонстрирует полную интеграцию OpcUaButton + OpcUaBackend.

    Поток данных при нажатии кнопки:
        1. OpcUaButton.clicked / pressed
        2.   → value_changed(1) эмитируется кнопкой
        3.   → WriteChannel.write(1) принимает сигнал
        4.   → OpcUaBackend.write_node(SERVER_ID, node_id, 1)
        5.   → OpcUaWorkerThread (отдельный QThread, asyncio event loop)
        6.   → asyncua: запись в OPC UA сервер
        7.   → write_completed(server_id, node_id, success) эмитируется backend
        8.   → WriteChannel.feedback_to(btn) фильтрует по server_id + node_id
        9.   → OpcUaButton.set_active(success) — зелёная подсветка при успехе

    Структура окна:
        ┌─ Подключение ────────────────────────────────────────┐
        │  Endpoint: [opc.tcp://192.168.6.6:4840]              │
        │  ● Отключен          [Подключить] [Отключить]        │
        └──────────────────────────────────────────────────────┘
        ┌─ OpcUaButton ────────────────────────────────────────┐
        │  NodeId: [ns=2;s=Start]                [Применить]  │
        │  ─────────────────────────────────────────────────── │
        │  Режим: обычный клик   │  Режим: удержание (hold)   │
        │  [   Отправить 1    ]  │  [      Удерживай       ]  │
        │  state_changed(True)   │  state_changed(True)        │
        └──────────────────────────────────────────────────────┘
        ┌─ Чтение тега ────────────────────────────────────────┐
        │  NodeId: [ns=2;s=Temperature]  [Читать]  Значение: — │
        └──────────────────────────────────────────────────────┘
        ┌─ Лог событий ────────────────────────────────────────┐
        │  [12:34:56.789] Подключение к opc.tcp://...          │
        │  [12:34:57.123] [TEST_OPC] Подключен                 │
        │  [12:34:57.456] Канал → ns=2;s=Start                 │
        │                                          [Очистить]  │
        └──────────────────────────────────────────────────────┘
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpcUaButton + OpcUaBackend — тест")
        self.setMinimumWidth(600)

        # OpcUaBackend — центральный объект управления OPC UA серверами.
        # Внутри каждый сервер живёт в отдельном QThread с asyncio event loop,
        # поэтому сбой одного сервера не влияет на другие и не блокирует GUI.
        self.backend = OpcUaBackend()

        # Список активных WriteChannel — ОБЯЗАТЕЛЬНО держим явные ссылки.
        # WriteChannel — это QObject, и если на него нет ссылок, Python GC
        # удалит его, сигналы отвалятся, и кнопки перестанут писать в OPC UA.
        self._channels: list[WriteChannel] = []

        # Атрибуты для feedback-слотов — создаются в _apply_node_id().
        # Объявляем здесь чтобы избежать AttributeError при первом disconnect().
        self._click_feedback = None
        self._hold_feedback  = None

        self._build_ui()               # строим layout
        self._connect_backend_signals() # подписываемся на события backend

    # ══════════════════════════════════════════════════════════════════════════
    # Построение UI
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        """
        Собирает главный вертикальный layout из четырёх секций (QGroupBox).
        Каждая секция — отдельный метод для читаемости.
        """
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setSpacing(10)                 # отступ между секциями
        root.setContentsMargins(12, 12, 12, 12)  # поля от краёв окна

        root.addWidget(self._build_connection_group())  # 1. Подключение
        root.addWidget(self._build_buttons_group())     # 2. Кнопки OpcUaButton
        root.addWidget(self._build_read_group())        # 3. Чтение тега
        root.addWidget(self._build_log_group())         # 4. Лог событий

    def _build_connection_group(self) -> QGroupBox:
        """
        Секция подключения к OPC UA серверу.

        Содержит:
          - Поле ввода endpoint (адрес сервера)
          - StatusLabel — цветной индикатор состояния
          - Кнопки "Подключить" / "Отключить"
        """
        box = QGroupBox("Подключение")
        form = QFormLayout(box)

        # Поле ввода адреса сервера в формате opc.tcp://<ip>:<port>
        self.le_endpoint = QLineEdit("opc.tcp://192.168.6.6:4840")
        form.addRow("Endpoint:", self.le_endpoint)

        # Горизонтальная строка: [статус] ---- [Подключить] [Отключить]
        btn_row = QHBoxLayout()

        self.status_label   = StatusLabel()           # цветной индикатор состояния
        self.btn_connect    = QPushButton("Подключить")
        self.btn_disconnect = QPushButton("Отключить")
        # "Отключить" недоступна пока не подключены — активируется в _on_server_connected
        self.btn_disconnect.setEnabled(False)

        self.btn_connect.clicked.connect(self._on_connect)
        self.btn_disconnect.clicked.connect(self._on_disconnect)

        btn_row.addWidget(self.status_label)
        btn_row.addStretch()             # прижимаем кнопки вправо
        btn_row.addWidget(self.btn_connect)
        btn_row.addWidget(self.btn_disconnect)
        form.addRow(btn_row)

        return box

    def _build_buttons_group(self) -> QGroupBox:
        """
        Секция тестирования OpcUaButton.

        Содержит:
          - Поле ввода NodeId тега + кнопка "Применить" (пересоздаёт WriteChannel)
          - Левая кнопка: hold=False — обычный клик, отправляет 1 один раз
          - Правая кнопка: hold=True — удержание, повторяет 1 каждые 100 мс
          - Метки под кнопками — показывают последнее значение state_changed(bool)
        """
        box = QGroupBox("OpcUaButton")
        layout = QVBoxLayout(box)

        # ── Строка ввода NodeId ──────────────────────────────────────────────
        # NodeId — полный адрес тега в OPC UA, например: ns=2;s=Start
        # Namespace уже содержится внутри строки (ns=X), отдельно вводить не нужно
        node_row = QHBoxLayout()
        node_row.addWidget(QLabel("NodeId тега:"))

        self.le_node_id = QLineEdit("ns=2;s=Start")
        self.le_node_id.setPlaceholderText("ns=2;s=TagName")

        self.btn_apply_node = QPushButton("Применить")
        # При нажатии "Применить" — пересоздаём WriteChannel с новым node_id.
        # Это позволяет менять тег "на лету" без перезапуска приложения.
        self.btn_apply_node.clicked.connect(self._apply_node_id)

        node_row.addWidget(self.le_node_id)
        node_row.addWidget(self.btn_apply_node)
        layout.addLayout(node_row)

        # ── Горизонтальный разделитель ───────────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # ── Две кнопки бок о бок ────────────────────────────────────────────
        btns_row = QHBoxLayout()

        # Левая: hold=False — обычная кнопка
        # Поведение: click → state_changed(True), value_changed(1)
        # Полезно: однократная команда пуска, сброса и т.п.
        click_col = QVBoxLayout()
        click_col.addWidget(QLabel(
            "Режим: обычный клик",
            alignment=Qt.AlignmentFlag.AlignCenter
        ))
        self.btn_click = OpcUaButton(
            "Отправить 1",
            hold=False,
            active_text="OK"       # текст меняется на "OK" при set_active(True)
        )
        self.btn_click.setMinimumHeight(50)
        self.btn_click.setEnabled(False)   # заблокирована до подключения
        click_col.addWidget(self.btn_click)
        btns_row.addLayout(click_col)

        # Правая: hold=True — кнопка удержания
        # Поведение: нажатие → state_changed(True) + value_changed(1) каждые 100 мс
        #            отпускание → timer.stop() + state_changed(False) + value_changed(0)
        # Полезно: джог-движение, удержание клапана открытым и т.п.
        hold_col = QVBoxLayout()
        hold_col.addWidget(QLabel(
            "Режим: удержание (hold)",
            alignment=Qt.AlignmentFlag.AlignCenter
        ))
        self.btn_hold = OpcUaButton(
            "Удерживай",
            hold=True,
            active_text="Отправляет..."  # текст при активном удержании
        )
        self.btn_hold.setMinimumHeight(50)
        self.btn_hold.setEnabled(False)   # заблокирована до подключения
        hold_col.addWidget(self.btn_hold)
        btns_row.addLayout(hold_col)

        layout.addLayout(btns_row)

        # ── Метки последнего сигнала ─────────────────────────────────────────
        # Отображают значение state_changed(bool) после последнего взаимодействия.
        # Помогают убедиться, что сигналы кнопки работают корректно.
        sig_row = QHBoxLayout()
        self.lbl_click_signal = QLabel("—", alignment=Qt.AlignmentFlag.AlignCenter)
        self.lbl_hold_signal  = QLabel("—", alignment=Qt.AlignmentFlag.AlignCenter)
        sig_row.addWidget(self.lbl_click_signal)
        sig_row.addWidget(self.lbl_hold_signal)
        layout.addLayout(sig_row)

        return box

    def _build_read_group(self) -> QGroupBox:
        """
        Секция разового чтения тега.

        Отправляет read_node() и отображает результат.
        Результат приходит асинхронно через signal read_completed → _on_read_completed.
        """
        box = QGroupBox("Чтение тега")
        h = QHBoxLayout(box)

        # Поле ввода NodeId тега для чтения (может отличаться от тега записи)
        self.le_read_node = QLineEdit("ns=2;s=Temperature")
        self.le_read_node.setPlaceholderText("NodeId для чтения")

        self.btn_read = QPushButton("Читать")
        self.btn_read.setEnabled(False)   # активируется после подключения

        self.lbl_read_result = QLabel("—")
        self.lbl_read_result.setMinimumWidth(150)  # место для длинных значений

        self.btn_read.clicked.connect(self._on_read)

        h.addWidget(QLabel("NodeId:"))
        h.addWidget(self.le_read_node)
        h.addWidget(self.btn_read)
        h.addWidget(QLabel("Значение:"))
        h.addWidget(self.lbl_read_result)

        return box

    def _build_log_group(self) -> QGroupBox:
        """
        Секция лога событий.

        Выводит все сигналы OpcUaBackend:
          - server_connected / server_disconnected
          - server_error
          - write_completed (OK / FAIL)
          - read_completed (значение)
          - watchdog_disconnect
        """
        box = QGroupBox("Лог событий")
        v = QVBoxLayout(box)

        self.log = LogWidget()  # тёмный терминал с цветными строками

        # Кнопка очистки — встроенный QTextEdit.clear() стирает всё содержимое
        btn_clear = QPushButton("Очистить")
        btn_clear.setMaximumWidth(100)
        btn_clear.clicked.connect(self.log.clear)

        v.addWidget(self.log)
        v.addWidget(btn_clear, alignment=Qt.AlignmentFlag.AlignRight)
        return box

    # ══════════════════════════════════════════════════════════════════════════
    # Подключение сигналов backend → слоты GUI
    # ══════════════════════════════════════════════════════════════════════════

    def _connect_backend_signals(self):
        """
        Подписываемся на все события OpcUaBackend.

        Сигналы эмитируются из OpcUaWorkerThread (отдельный QThread),
        но Qt автоматически маршрутизирует их в главный поток GUI
        через queued connection — это thread-safe без дополнительных mutex.

        Подключаем здесь один раз при создании окна.
        """
        # Состояние соединения
        self.backend.server_connected.connect(self._on_server_connected)
        self.backend.server_disconnected.connect(self._on_server_disconnected)

        # Ошибка — сеть недоступна, сервер отклонил, timeout и т.д.
        self.backend.server_error.connect(
            lambda srv, err: self.log.log(f"[{srv}] Ошибка: {err}", "red"))

        # Результаты операций чтения / записи
        self.backend.write_completed.connect(self._on_write_completed)
        self.backend.read_completed.connect(self._on_read_completed)

        # Watchdog — периодически пингует сервер; этот сигнал = соединение потеряно
        self.backend.watchdog_disconnect.connect(
            lambda srv: self.log.log(f"[{srv}] Watchdog: соединение потеряно", "orange"))

    def _on_server_connected(self, srv: str):
        """
        Слот: сервер успешно подключён.

        Активируем все кнопки работы с тегами и сразу привязываем WriteChannel,
        чтобы пользователь мог нажимать кнопки без дополнительного шага.
        """
        self.log.log(f"[{srv}] Подключен", "green")
        self.status_label.set_state("connected")
        self.btn_connect.setEnabled(False)     # "Подключить" — недоступна
        self.btn_disconnect.setEnabled(True)   # "Отключить" — доступна
        self._enable_buttons(True)             # разблокировать кнопки тегов
        self._apply_node_id()                  # автопривязка WriteChannel

    def _on_server_disconnected(self, srv: str):
        """
        Слот: сервер отключился (штатно или по watchdog).

        Блокируем кнопки тегов — нельзя писать/читать без подключения.
        """
        self.log.log(f"[{srv}] Отключен")
        self.status_label.set_state("disconnected")
        self.btn_connect.setEnabled(True)       # "Подключить" — снова доступна
        self.btn_disconnect.setEnabled(False)   # "Отключить" — недоступна
        self._enable_buttons(False)             # заблокировать кнопки тегов

    def _on_write_completed(self, srv: str, node: str, success: bool):
        """
        Слот: запись тега завершена.

        Args:
            srv:     server_id
            node:    NodeId тега который писали
            success: True — сервер принял значение, False — ошибка записи
        """
        status = "OK" if success else "FAIL"
        color  = "green" if success else "red"
        self.log.log(f"[{srv}] write {node} → {status}", color)

    def _on_read_completed(self, srv: str, node: str, value):
        """
        Слот: чтение тега завершено.

        Выводим значение и в лог, и в лейбл секции "Чтение тега".
        """
        self.log.log(f"[{srv}] read {node} = {value}", "blue")
        self.lbl_read_result.setText(str(value))

    # ══════════════════════════════════════════════════════════════════════════
    # Действия пользователя
    # ══════════════════════════════════════════════════════════════════════════

    def _on_connect(self):
        """
        Нажата кнопка "Подключить".

        Алгоритм:
          1. Читаем endpoint из поля ввода
          2. Добавляем сервер в backend (если ещё не добавлен)
          3. Вызываем connect_server() — запускает QThread и asyncio подключение
          4. Результат придёт через signal server_connected или server_error
        """
        endpoint = self.le_endpoint.text().strip()
        if not endpoint:
            self.log.log("Введите endpoint", "red")
            return

        self.log.log(f"Подключение к {endpoint}...")
        self.status_label.set_state("connecting")
        self.btn_connect.setEnabled(False)  # блокируем, чтобы не кликали повторно

        # add_server() создаёт OpcUaWorkerThread, но ещё не запускает его.
        # Если SERVER_ID уже есть — пропускаем (повторный add_server вернёт False).
        if SERVER_ID not in self.backend.servers:
            self.backend.add_server(SERVER_ID, endpoint)

        # connect_server() запускает поток и через loop_ready инициирует async connect.
        # Этот вызов неблокирующий — GUI продолжает работать, результат придёт через сигнал.
        self.backend.connect_server(SERVER_ID)

    def _on_disconnect(self):
        """
        Нажата кнопка "Отключить".

        blocking=False — неблокирующий режим: GUI не замерзает,
        disconnect происходит в фоне, результат — сигнал server_disconnected.
        """
        self.backend.disconnect_server(SERVER_ID, blocking=False)
        self.log.log("Отключение...")

    def _apply_node_id(self):
        """
        Привязать WriteChannel к обеим кнопкам по текущему значению поля NodeId.

        Вызывается:
          - Автоматически после подключения (_on_server_connected)
          - Вручную при нажатии кнопки "Применить"

        Что делает:
          1. Создаёт два WriteChannel (по одному на каждую кнопку)
          2. Отключает старые signal-slot соединения (если были)
          3. Подключает новые: btn.value_changed → channel.write
          4. Подключает feedback: write_completed → channel.feedback_to(btn)
          5. Подписывается на state_changed для отладочных меток

        Почему два канала (а не один)?
          Каждый WriteChannel хранит ссылку на кнопку для feedback.
          Один канал на двух кнопках дал бы feedback только одной из них.
        """
        node_id = self.le_node_id.text().strip()

        # Пропускаем если: поле пустое ИЛИ сервер не подключён
        if not node_id or not self.backend.is_connected(SERVER_ID):
            return

        self.log.log(f"Канал → {node_id}")

        # Создаём новые каналы с текущим node_id
        ch_click = WriteChannel(self.backend, SERVER_ID, node_id)
        ch_hold  = WriteChannel(self.backend, SERVER_ID, node_id)

        # ВАЖНО: сохраняем ссылки в self._channels.
        # WriteChannel — QObject без родителя, Python GC удалит его
        # как только исчезнут все ссылки. Сохраняя в списке — защищаем от GC.
        self._channels = [ch_click, ch_hold]

        # Отключаем старые соединения перед переподключением.
        # try/except нужен для первого вызова — self._click_feedback ещё None.
        try:
            self.btn_click.value_changed.disconnect()
            self.btn_hold.value_changed.disconnect()
            self.backend.write_completed.disconnect(self._click_feedback)
            self.backend.write_completed.disconnect(self._hold_feedback)
        except Exception:
            pass  # первый вызов — старых соединений ещё нет, это нормально

        # Подключаем запись: нажатие кнопки → write_node в OPC UA сервер
        # value_changed(int) → WriteChannel.write(int) → backend.write_node(...)
        self.btn_click.value_changed.connect(ch_click.write)
        self.btn_hold.value_changed.connect(ch_hold.write)

        # Подключаем feedback (подсветку кнопки по результату записи).
        # feedback_to(btn) возвращает слот, который:
        #   - принимает write_completed(server_id, node_id, success)
        #   - фильтрует по своему server_id + node_id (игнорирует чужие теги)
        #   - вызывает btn.set_active(success) — зелёная подсветка при успехе
        self._click_feedback = ch_click.feedback_to(self.btn_click)
        self._hold_feedback  = ch_hold.feedback_to(self.btn_hold)
        self.backend.write_completed.connect(self._click_feedback)
        self.backend.write_completed.connect(self._hold_feedback)

        # Метки отладки: показывают последнее значение state_changed(bool)
        # True = кнопка нажата/удерживается, False = отпущена
        self.btn_click.state_changed.connect(
            lambda v: self.lbl_click_signal.setText(f"state_changed({v})"))
        self.btn_hold.state_changed.connect(
            lambda v: self.lbl_hold_signal.setText(f"state_changed({v})"))

    def _on_read(self):
        """
        Нажата кнопка "Читать".

        Отправляет асинхронный запрос read_node().
        Результат придёт через signal read_completed → _on_read_completed.
        """
        node_id = self.le_read_node.text().strip()
        if not node_id:
            return
        self.backend.read_node(SERVER_ID, node_id)
        self.log.log(f"read → {node_id}")

    def _enable_buttons(self, enabled: bool):
        """
        Включить / выключить все интерактивные элементы работы с тегами.

        Вызывается при изменении состояния подключения:
          True  — подключились, можно работать
          False — отключились, блокируем чтобы не было ошибок
        """
        self.btn_click.setEnabled(enabled)
        self.btn_hold.setEnabled(enabled)
        self.btn_apply_node.setEnabled(enabled)
        self.btn_read.setEnabled(enabled)

    # ══════════════════════════════════════════════════════════════════════════
    # Lifecycle
    # ══════════════════════════════════════════════════════════════════════════

    def closeEvent(self, event):
        """
        Обработчик закрытия окна.

        stop_all() с blocking=True — ждёт корректного завершения всех QThread.
        Это важно: без явной остановки потоки могут зависнуть или вызвать
        ошибки при завершении процесса Python.
        """
        self.backend.stop_all()  # блокирует до полной остановки всех потоков
        event.accept()           # разрешаем закрытие окна


# ══════════════════════════════════════════════════════════════════════════════
# Точка входа
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)

    # Fusion — кроссплатформенный стиль: одинаково выглядит на Windows/Linux/macOS
    app.setStyle("Fusion")

    win = TestWindow()
    win.show()

    # app.exec() — главный event loop Qt. Блокирует до закрытия окна.
    # sys.exit() передаёт код возврата операционной системе.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
