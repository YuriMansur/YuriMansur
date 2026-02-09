# План интеграции QThread + asyncio для Modbus Debugger

## Контекст

Пользователь хочет комбинировать QThread и qasync так, чтобы каждый PLC контроллер работал в **отдельном QThread** с собственным asyncio event loop. Это обеспечит:
- Изоляцию контроллеров (ошибка одного не влияет на другие)
- Улучшенную производительность (параллельная работа)
- Упрощенную отладку (каждый PLC в своем потоке)

### Текущая архитектура (modbus_debugger.py)
- Использует **qasync.QEventLoop** для интеграции Qt + asyncio
- Все AsyncPLCWorker работают в **ОДНОМ главном event loop**
- Множественные активные PLC (self.active_plc_ids = set())
- Команды выполняются параллельно через `asyncio.gather()`
- GUI может блокироваться при интенсивных операциях

### Целевая архитектура
- Каждый PLC в **отдельном QThread**
- Собственный `asyncio.new_event_loop()` для каждого потока
- Thread-safe коммуникация через `asyncio.run_coroutine_threadsafe()`
- **PyQt signals** для передачи результатов в GUI
- **Паттерн OpcUaWorker** из `src/communication/protocols/opc_ua.py`

### Преимущества
1. **Изоляция**: Ошибка в одном PLC не влияет на другие
2. **Производительность**: Истинная параллельная работа (не только concurrent)
3. **Масштабируемость**: Легко добавлять/удалять PLC динамически
4. **Отладка**: Каждый PLC имеет свой thread ID
5. **Упрощение**: Убираем qasync из main() - стандартный Qt event loop

---

## План реализации

### Этап 1: Создание PLCWorkerThread (новый файл)

**Файл**: `w_opc_modbus/modbus/plc_worker_thread.py`

Создать QThread обертку для AsyncPLCWorker по паттерну **OpcUaWorker**:

```python
class PLCWorkerThread(QThread):
    """QThread обертка для AsyncPLCWorker"""

    # === SIGNALS для коммуникации с GUI ===
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    connection_error = pyqtSignal(str)
    data_updated = pyqtSignal(str, dict)  # (poll_name, data)
    command_completed = pyqtSignal(object)
    command_error = pyqtSignal(str)

    def __init__(self, plc_id, host, port=502, device_id=1):
        super().__init__()
        self.plc_id = plc_id
        self.host = host
        self.port = port
        self.device_id = device_id
        self.loop = None
        self.worker: Optional[AsyncPLCWorker] = None
        self._connected = False

        # Thread-safe доступ к latest_data
        self._latest_data_lock = threading.Lock()
        self._latest_data = {}

    def run(self):
        """Создание event loop в потоке (паттерн OpcUaWorker)"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def stop(self):
        """Корректная остановка потока"""
        if self._connected and self.worker:
            asyncio.run_coroutine_threadsafe(
                self._async_disconnect(), self.loop
            ).result(timeout=5.0)

        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait()

    # === PUBLIC METHODS (thread-safe, вызываются из GUI) ===

    def connect_to_plc(self):
        """Thread-safe подключение"""
        asyncio.run_coroutine_threadsafe(
            self._async_connect(), self.loop
        )

    def disconnect_from_plc(self):
        """Thread-safe отключение"""
        asyncio.run_coroutine_threadsafe(
            self._async_disconnect(), self.loop
        )

    def execute_command(self, command: tuple):
        """Thread-safe выполнение команды"""
        asyncio.run_coroutine_threadsafe(
            self._async_execute_command(command), self.loop
        )

    def add_poll(self, poll_config: dict):
        """Thread-safe добавление опроса"""
        asyncio.run_coroutine_threadsafe(
            self._async_add_poll(poll_config), self.loop
        )

    def get_latest_data(self) -> dict:
        """Thread-safe получение данных"""
        with self._latest_data_lock:
            return self._latest_data.copy()

    # === PRIVATE ASYNC METHODS (выполняются в loop потока) ===

    async def _async_connect(self):
        """Создание и запуск AsyncPLCWorker"""
        try:
            self.worker = AsyncPLCWorker(
                self.plc_id, self.host, self.port, self.device_id
            )
            asyncio.create_task(self.worker.start())
            await asyncio.sleep(0.5)  # Даем время на подключение

            self._connected = True
            self.connected.emit()

            # Запуск loop для копирования latest_data
            asyncio.create_task(self._sync_latest_data_loop())
        except Exception as e:
            self.connection_error.emit(str(e))

    async def _async_disconnect(self):
        """Остановка worker"""
        if self.worker:
            await self.worker.stop()
            self.worker = None
        self._connected = False
        self.disconnected.emit()

    async def _async_execute_command(self, command: tuple):
        """Выполнение команды read/write"""
        try:
            result = await self.worker.request(command)
            self.command_completed.emit(result)
        except Exception as e:
            self.command_error.emit(str(e))

    async def _async_add_poll(self, poll_config: dict):
        """Добавление poll loop"""
        task = asyncio.create_task(self.worker._poll_loop(poll_config))
        self.worker._poll_tasks.append(task)

    async def _sync_latest_data_loop(self):
        """Периодическое копирование latest_data"""
        while self._connected:
            if self.worker:
                worker_data = self.worker.latest_data.copy()
                with self._latest_data_lock:
                    self._latest_data = worker_data
                for poll_name, data in worker_data.items():
                    self.data_updated.emit(poll_name, {"data": data})
            await asyncio.sleep(0.5)
```

**Особенности**:
- Паттерн 1:1 с OpcUaWorker (проверенное решение)
- `run()`: создает `asyncio.new_event_loop()` и запускает `run_forever()`
- `stop()`: thread-safe остановка через `call_soon_threadsafe()`
- Thread-safe методы используют `run_coroutine_threadsafe()`
- Signals для передачи результатов в GUI thread

---

### Этап 2: Модификация modbus_debugger.py

#### 2.1 Изменение структуры хранения PLC

**Было**:
```python
self.plcs = {
    "PLC1": {
        "worker": AsyncPLCWorker(...),
        "task": asyncio.Task,
        "connected": bool,
        "config": {...}
    }
}
```

**Станет**:
```python
self.plcs = {
    "PLC1": {
        "thread": PLCWorkerThread(...),  # Заменяем worker+task на thread
        "connected": bool,
        "config": {...}
    }
}
```

#### 2.2 Рефакторинг _connect_plc() - убрать async

**Было** (async с create_task):
```python
async def _connect_plc(self, plc_id: str):
    worker = AsyncPLCWorker(plc_id, host, port, device_id)
    task = asyncio.create_task(worker.start())
    plc["worker"] = worker
    plc["task"] = task
```

**Станет** (sync с QThread):
```python
def _connect_plc(self, plc_id: str):
    """Больше не async!"""
    plc = self.plcs[plc_id]
    config = plc["config"]

    # Создаем thread
    thread = PLCWorkerThread(
        plc_id, config["host"], config["port"], config["device_id"]
    )

    # Подключаем signals
    thread.connected.connect(lambda: self._on_plc_connected(plc_id))
    thread.disconnected.connect(lambda: self._on_plc_disconnected(plc_id))
    thread.connection_error.connect(lambda err: self._on_plc_error(plc_id, err))
    thread.command_completed.connect(lambda res: self._on_command_result(plc_id, res))
    thread.command_error.connect(lambda err: self._on_command_error(plc_id, err))

    plc["thread"] = thread
    thread.start()  # Запускаем QThread

    # Отложенное подключение (даем время на создание loop)
    QTimer.singleShot(100, lambda: thread.connect_to_plc())
```

#### 2.3 Рефакторинг _disconnect_plc() - убрать async

**Было**:
```python
async def _disconnect_plc(self, plc_id: str):
    await plc["worker"].stop()
    plc["task"].cancel()
```

**Станет**:
```python
def _disconnect_plc(self, plc_id: str):
    """Больше не async!"""
    plc = self.plcs[plc_id]
    if plc.get("thread"):
        plc["thread"].stop()  # Блокирующий вызов
        plc["thread"] = None
        plc["connected"] = False
```

#### 2.4 Рефакторинг команд - убрать async/await

**Было** (_read_command):
```python
async def _read_command(self):
    tasks = [plc["worker"].request(cmd) for plc_id in self.active_plc_ids]
    results = await asyncio.gather(*tasks)
```

**Станет**:
```python
def _read_command(self):
    """Больше не async! Используем signals"""
    if not self.active_plc_ids:
        return

    type_ = self.read_type_combo.currentText()
    address = self.read_address_input.value()
    count = self.read_count_input.value()
    command = ("read", type_, address, count)

    # Очищаем результаты
    self.pending_results = {}
    self.expected_results = len(self.active_plc_ids)

    # Отправляем команду всем активным PLC
    for plc_id in self.active_plc_ids:
        plc = self.plcs.get(plc_id)
        if plc and plc["connected"] and plc["thread"]:
            plc["thread"].execute_command(command)  # Thread-safe
        else:
            self.expected_results -= 1

    # Результаты придут через signals
```

#### 2.5 Добавление обработчиков signals

```python
def _on_plc_connected(self, plc_id: str):
    plc = self.plcs.get(plc_id)
    if plc:
        plc["connected"] = True
        self.log(f"✅ PLC '{plc_id}' подключен")
        self._update_plc_table()

def _on_plc_disconnected(self, plc_id: str):
    plc = self.plcs.get(plc_id)
    if plc:
        plc["connected"] = False
        self.log(f"🔌 PLC '{plc_id}' отключен")
        self._update_plc_table()

def _on_plc_error(self, plc_id: str, error: str):
    self.log(f"❌ [{plc_id}] Ошибка: {error}")

def _on_command_result(self, plc_id: str, result):
    """Сбор результатов от всех PLC"""
    self.pending_results[plc_id] = result

    # Если собрали все результаты
    if len(self.pending_results) == self.expected_results:
        # Отображаем результаты
        result_text = ""
        for pid, res in self.pending_results.items():
            result_text += f"[{pid}] ✅ {res}\n"
        self.read_result.setText(result_text)

def _on_command_error(self, plc_id: str, error: str):
    self.log(f"❌ [{plc_id}] Ошибка: {error}")
    self.pending_results[plc_id] = f"Error: {error}"

    if len(self.pending_results) == self.expected_results:
        # Отображаем результаты
        pass
```

#### 2.6 Рефакторинг _update_gui()

**Было**:
```python
def _update_gui(self):
    for plc_id, plc in self.plcs.items():
        if plc["connected"] and plc["worker"]:
            all_latest_data.update(plc["worker"].latest_data)
```

**Станет**:
```python
def _update_gui(self):
    all_latest_data = {}
    for plc_id, plc in self.plcs.items():
        if plc["connected"] and plc.get("thread"):
            # Thread-safe копия
            plc_data = plc["thread"].get_latest_data()
            all_latest_data.update(plc_data)
    # ... обновление таблицы
```

#### 2.7 Рефакторинг _update_plc_table()

**Убрать** `asyncio.create_task` из lambda:

**Было**:
```python
connect_btn.clicked.connect(
    lambda checked, pid=plc_id: asyncio.create_task(self._connect_plc(pid))
)
```

**Станет**:
```python
connect_btn.clicked.connect(
    lambda checked, pid=plc_id: self._connect_plc(pid)
)
```

#### 2.8 Рефакторинг closeEvent()

**Было**:
```python
def closeEvent(self, event):
    for plc_id, plc in self.plcs.items():
        if plc["connected"]:
            asyncio.create_task(self._disconnect_plc(plc_id))
```

**Станет**:
```python
def closeEvent(self, event):
    """Корректное завершение всех потоков"""
    self.timer.stop()

    for plc_id, plc in list(self.plcs.items()):
        if plc.get("thread") and plc["thread"].isRunning():
            self.log(f"Остановка {plc_id}...")
            plc["thread"].stop()  # Блокирующий вызов

    event.accept()
```

#### 2.9 Рефакторинг main() - убрать qasync

**Было**:
```python
def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)  # qasync
    asyncio.set_event_loop(loop)
    window = ModbusDebugger()
    window.show()
    with loop:
        loop.run_forever()
```

**Станет**:
```python
def main():
    """Стандартный Qt event loop (без qasync)"""
    app = QApplication(sys.argv)
    window = ModbusDebugger()
    window.show()
    sys.exit(app.exec())
```

---

### Этап 3: Минимальные изменения в AsyncPLCWorker

**AsyncPLCWorker практически НЕ НУЖНО менять!**

Опционально (для явной thread-safety):
```python
import threading

class AsyncPLCWorker:
    def __init__(self, ...):
        # ...existing...
        self._data_lock = threading.Lock()

    async def _poll_loop(self, poll: dict):
        # ...existing...
        # with self._data_lock:  # Опционально
        self.latest_data[name] = data  # dict assignment atomic в CPython
```

**Обоснование**: Worker работает только в своем event loop, доступ извне только через `get_latest_data()` с lock.

---

## Критические файлы

### Файлы для создания:
1. **`w_opc_modbus/modbus/plc_worker_thread.py`** (~300 строк)
   - Новый класс PLCWorkerThread(QThread)
   - Паттерн из OpcUaWorker

### Файлы для модификации:
2. **`w_opc_modbus/modbus/modbus_debugger.py`** (~50-70% кода)
   - Убрать все `async def` → `def`
   - Заменить `asyncio.create_task()` → `thread.start()`
   - Убрать `await` → signals
   - Добавить обработчики signals
   - Изменить main()

3. **`w_opc_modbus/modbus/modbus_worker.py`** (0-5% кода)
   - Опционально: добавить threading.Lock
   - Все остальное БЕЗ ИЗМЕНЕНИЙ

### Референсные файлы:
4. **`src/communication/protocols/opc_ua.py`**
   - Паттерн OpcUaWorker для копирования

---

## Порядок выполнения

### День 1: Инфраструктура
1. Создать `plc_worker_thread.py` (копировать структуру OpcUaWorker)
2. Реализовать `__init__`, `run()`, `stop()`
3. Добавить signals
4. Unit тесты для thread lifecycle

### День 2: Async методы
1. Реализовать `_async_connect()` и `connect_to_plc()`
2. Реализовать `_async_disconnect()`
3. Реализовать `_async_execute_command()`
4. Тесты подключения/отключения

### День 3: Интеграция
1. Добавить import в modbus_debugger.py
2. Рефакторить `_connect_plc()` (убрать async)
3. Рефакторить `_disconnect_plc()` (убрать async)
4. Добавить обработчики signals
5. Тестировать один PLC

### День 4: Команды
1. Рефакторить `_read_command()` (убрать async)
2. Рефакторить `_write_command()` (убрать async)
3. Добавить сбор результатов через signals
4. Тестировать команды на нескольких PLC

### День 5: Polls и GUI
1. Рефакторить `_add_poll()` (убрать async)
2. Реализовать `_sync_latest_data_loop()` в PLCWorkerThread
3. Рефакторить `_update_gui()`
4. Тестировать polls

### День 6: Cleanup
1. Рефакторить `closeEvent()`
2. Рефакторить `main()` (убрать qasync)
3. Убрать все упоминания qasync
4. Рефакторить `_update_plc_table()`

### День 7: Тестирование
1. Integration тесты (множественные PLC)
2. Stress тесты (быстрое подключение/отключение)
3. Performance тесты (5+ PLC)
4. Тесты на deadlocks

---

## Верификация

### 1. Unit тесты PLCWorkerThread
```python
def test_thread_lifecycle():
    thread = PLCWorkerThread("TEST", "127.0.0.1")
    thread.start()
    assert thread.isRunning()
    thread.stop()
    assert not thread.isRunning()
```

### 2. Integration тесты
```python
def test_multiple_plcs():
    app = QApplication([])
    window = ModbusDebugger()

    # Добавляем 3 PLC
    for i in range(1, 4):
        window._add_plc()
        window._connect_plc(f"PLC{i}")

    # Проверяем изоляцию потоков
    thread_ids = set()
    for plc in window.plcs.values():
        if plc.get("thread"):
            thread_ids.add(plc["thread"].currentThreadId())

    assert len(thread_ids) == 3  # 3 разных потока!
```

### 3. Проверка thread-safety
- Быстрое подключение/отключение (10 циклов)
- Одновременные команды на 5 PLC
- Корректное завершение при закрытии

### 4. Performance
- 5+ PLC одновременно
- Циклические опросы на всех
- Проверка CPU usage (должно использоваться несколько ядер)

---

## Потенциальные проблемы и решения

### Проблема 1: GUI замирает при stop()
**Решение**: Использовать QTimer для отложенной остановки

### Проблема 2: Signals не доходят
**Решение**: Подключать signals ДО thread.start()

### Проблема 3: Latest_data не обновляется
**Решение**: Запускать `_sync_latest_data_loop()` в `_async_connect()`

### Проблема 4: Ошибка при повторном подключении
**Решение**: Создавать новый thread для каждого подключения

### Проблема 5: Memory leak
**Решение**: Вызывать `thread.deleteLater()` при отключении

---

## Преимущества новой архитектуры

1. **Изоляция**: Ошибка одного PLC не влияет на другие
2. **Производительность**: Истинный параллелизм (несколько CPU cores)
3. **Масштабируемость**: Легко добавлять PLC
4. **Отладка**: Thread ID для каждого PLC
5. **Упрощение**: Убираем qasync, стандартный Qt паттерн
6. **Переиспользование**: Паттерн OpcUaWorker уже проверен в проекте
