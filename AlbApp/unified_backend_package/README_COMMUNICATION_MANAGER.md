# CommunicationManager - Документация

## 📋 Описание

**CommunicationManager** - единый менеджер для управления устройствами Modbus TCP и OPC UA через общий API.

### Ключевые возможности:
- ✅ Единый API для Modbus TCP и OPC UA
- ✅ Создание и параметрирование устройств
- ✅ Управление тегами и регистрами
- ✅ Qt signals для обновлений данных
- ✅ Автоматическая маршрутизация команд к нужному backend
- ✅ Абстракция тегов (одинаковый интерфейс для разных протоколов)

---

## 🚀 Быстрый старт

```python
from AlbApp.unified_backend_package import CommunicationManager

# Создаем менеджер
manager = CommunicationManager()

# Добавляем Modbus устройство
manager.add_device("PLC1", "modbus", {
    "host": "192.168.1.1",
    "port": 502,
    "device_id": 1
}, tags={
    "Temperature": {"reg_type": "holding", "address": 0, "format": "float32"}
})

# Добавляем OPC UA устройство
manager.add_device("OPC1", "opcua", {
    "endpoint": "opc.tcp://192.168.1.10:4840",
    "namespace": 2
}, tags={
    "Temperature": {"node_id": "ns=2;s=Temperature"}
})

# Подключаем signals
manager.tag_updated.connect(lambda dev, tag, val: print(f"{dev}.{tag} = {val}"))

# Подключаем устройства
manager.connect_device("PLC1")
manager.connect_device("OPC1")

# Подписываемся на теги
manager.subscribe_tag("PLC1", "Temperature")
manager.subscribe_tag("OPC1", "Temperature")

# Читаем/пишем данные (единый API!)
manager.write_tag("PLC1", "Temperature", 25.5)
manager.write_tag("OPC1", "Temperature", 25.5)
```

---

## 📚 API Reference

### Управление устройствами

#### `add_device(device_id, device_type, config, tags=None)`

Добавить устройство.

**Параметры:**
- `device_id` (str) - Уникальный ID
- `device_type` (str) - "modbus" или "opcua"
- `config` (dict) - Конфигурация устройства
- `tags` (dict) - Конфигурация тегов (опционально)

**Пример для Modbus:**
```python
manager.add_device("PLC1", "modbus", {
    "host": "192.168.1.1",
    "port": 502,
    "device_id": 1
}, tags={
    "Temperature": {
        "reg_type": "holding",
        "address": 0,
        "count": 2,
        "format": "float32",
        "interval": 1000
    }
})
```

**Пример для OPC UA:**
```python
manager.add_device("OPC1", "opcua", {
    "endpoint": "opc.tcp://192.168.1.10:4840",
    "namespace": 2
}, tags={
    "Temperature": {"node_id": "ns=2;s=Temperature"}
})
```

#### `connect_device(device_id)` / `disconnect_device(device_id, blocking=False)`

Подключить/отключить устройство.

#### `is_connected(device_id)` → bool

Проверить подключение.

#### `get_devices()` → Dict

Получить все устройства.

---

### Работа с тегами (Unified API)

#### `subscribe_tag(device_id, tag_name, tag_config=None)`

Подписаться на тег (работает для Modbus и OPC UA).

**Для OPC UA:**
```python
manager.subscribe_tag("OPC1", "Temperature", {
    "node_id": "ns=2;s=Temperature"
})
```

**Для Modbus (создает poll):**
```python
manager.subscribe_tag("PLC1", "Temperature", {
    "reg_type": "holding",
    "address": 0,
    "count": 2,
    "format": "float32",
    "interval": 1000
})
```

#### `read_tag(device_id, tag_name)` → value

Прочитать значение тега.

- Modbus: возвращает значение синхронно
- OPC UA: результат через signal `tag_updated`

#### `write_tag(device_id, tag_name, value)` → bool

Записать значение тега (единый API для обоих протоколов).

```python
# Работает одинаково для Modbus и OPC UA!
manager.write_tag("PLC1", "Temperature", 25.5)
manager.write_tag("OPC1", "Temperature", 25.5)
```

#### `unsubscribe_tag(device_id, tag_name)`

Отписаться от тега.

---

### Прямая работа с регистрами (Modbus)

#### `read_register(device_id, reg_type, address, count=1, format="raw")`

Прямое чтение регистра Modbus.

```python
value = manager.read_register("PLC1", "holding", 100, 2, format="float32")
```

#### `write_register(device_id, reg_type, address, value, format="raw")`

Прямая запись регистра Modbus.

```python
manager.write_register("PLC1", "holding", 100, 42)
```

---

### Доступ к данным

#### `get_latest_data(device_id)` → Dict

Получить последние данные от устройства.

```python
data = manager.get_latest_data("PLC1")
print(data)  # {"Temperature": 23.5, "Pressure": 101.3}
```

#### `get_all_data()` → Dict[str, Dict]

Получить данные от всех устройств.

```python
all_data = manager.get_all_data()
# {
#   "PLC1": {"Temperature": 23.5},
#   "OPC1": {"Temperature": 23.5}
# }
```

---

## 🔔 Qt Signals

### Обновления данных

**`tag_updated(device_id: str, tag_name: str, value: Any)`**

Эмитится при обновлении тега (OPC UA subscriptions или Modbus polls).

```python
manager.tag_updated.connect(
    lambda dev, tag, val: print(f"{dev}.{tag} = {val}")
)
```

**`register_updated(device_id: str, poll_name: str, data: dict)`**

Эмитится при обновлении Modbus poll.

```python
manager.register_updated.connect(
    lambda dev, poll, data: print(f"{dev}.{poll}: {data}")
)
```

### События устройств

**`device_connected(device_id: str)`**

Устройство подключено.

**`device_disconnected(device_id: str)`**

Устройство отключено.

**`device_error(device_id: str, error: str)`**

Ошибка устройства.

### События подписок

**`tag_subscribed(device_id: str, tag_name: str)`**

Тег подписан.

**`tag_unsubscribed(device_id: str, tag_name: str)`**

Тег отписан.

---

## 💡 Примеры использования

### Пример 1: Мониторинг температуры с двух источников

```python
from AlbApp.unified_backend_package import CommunicationManager

manager = CommunicationManager()

# Добавляем Modbus PLC
manager.add_device("PLC1", "modbus", {
    "host": "192.168.1.1",
    "port": 502,
    "device_id": 1
}, tags={
    "Temperature": {"reg_type": "holding", "address": 0, "format": "float32"}
})

# Добавляем OPC UA сервер
manager.add_device("OPC1", "opcua", {
    "endpoint": "opc.tcp://192.168.1.10:4840",
    "namespace": 2
}, tags={
    "Temperature": {"node_id": "ns=2;s=Temperature"}
})

# Единый обработчик для обоих источников
def on_temperature_update(device_id, tag_name, value):
    if tag_name == "Temperature":
        print(f"[{device_id}] Температура: {value}°C")
        if value > 50:
            print(f"⚠️ [{device_id}] ПРЕДУПРЕЖДЕНИЕ: Высокая температура!")

manager.tag_updated.connect(on_temperature_update)

# Подключаемся и подписываемся (одинаковый API!)
for device_id in ["PLC1", "OPC1"]:
    manager.connect_device(device_id)
    manager.subscribe_tag(device_id, "Temperature")
```

### Пример 2: Синхронизация SetPoint между PLC и SCADA

```python
# Modbus PLC
manager.add_device("PLC1", "modbus", {...}, tags={
    "SetPoint": {"reg_type": "holding", "address": 100, "format": "float32"}
})

# OPC UA SCADA
manager.add_device("SCADA", "opcua", {...}, tags={
    "SetPoint": {"node_id": "ns=2;s=SetPoint"}
})

# Синхронизация: изменение в SCADA → PLC
def sync_setpoint(device_id, tag_name, value):
    if device_id == "SCADA" and tag_name == "SetPoint":
        manager.write_tag("PLC1", "SetPoint", value)
        print(f"SetPoint синхронизирован: SCADA → PLC = {value}")

manager.tag_updated.connect(sync_setpoint)
```

### Пример 3: Запись данных в несколько устройств

```python
# Одинаковый API для записи в Modbus и OPC UA!
devices = ["PLC1", "PLC2", "OPC1", "OPC2"]

for device_id in devices:
    success = manager.write_tag(device_id, "SetPoint", 25.5)
    print(f"{device_id}: {'✓' if success else '✗'}")
```

---

## 🔧 Архитектура

```
CommunicationManager
    │
    ├── ModbusBackend (для всех Modbus устройств)
    │   ├── PLC1
    │   ├── PLC2
    │   └── ...
    │
    └── OpcUaBackend (для всех OPC UA устройств)
        ├── OPC1
        ├── OPC2
        └── ...
```

**Преимущества:**
- Единый API независимо от протокола
- Автоматическая маршрутизация к нужному backend
- Централизованное управление всеми устройствами
- Единые signals для всех типов устройств

---

## 📝 Сравнение с отдельными backend'ами

| Функция | CommunicationManager | ModbusBackend + OpcUaBackend |
|---------|---------------------|------------------------------|
| **Единый API** | ✅ Да | ❌ Разные API |
| **Signals** | ✅ Единые | ⚠️ Разные |
| **Теги** | ✅ Абстракция | ⚠️ Только OPC UA |
| **Управление** | ✅ Централизованное | ❌ Раздельное |
| **Прямой доступ к регистрам** | ✅ Да | ✅ Да |
| **Простота кода** | ✅ Высокая | ⚠️ Средняя |

**Рекомендация:** Используйте `CommunicationManager` когда работаете с устройствами обоих типов. Используйте отдельные backend'ы только если нужен специфичный функционал протокола.

---

## 🧪 Тестирование

```bash
cd YuriMansur
python -m AlbApp.unified_backend_package.example_communication_manager
```

---

## ⚠️ Важные замечания

1. **Теги для Modbus** - это абстракция поверх polls. При подписке создается poll с указанным интервалом.

2. **Чтение OPC UA** - асинхронное, результат приходит через signal `tag_updated`.

3. **Чтение Modbus** - синхронное, возвращает значение сразу (если есть poll, берется из кэша).

4. **Конфигурация тегов** - можно указать при `add_device()` или позже при `subscribe_tag()`.

5. **Lifecycle** - не забывайте вызывать `stop_all()` или `disconnect_all()` при завершении.

---

## 📖 См. также

- [ModbusBackend](README_BACKEND.md) - Modbus-специфичный функционал
- [OpcUaBackend](README_OPCUA.md) - OPC UA-специфичный функционал
- [Примеры](example_communication_manager.py) - Полный пример использования
