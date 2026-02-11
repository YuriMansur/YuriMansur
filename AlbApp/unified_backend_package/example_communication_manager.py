"""
Example: CommunicationManager - Единый менеджер для Modbus + OPC UA

Демонстрация работы с множественными устройствами разных протоколов
через единый API.

ЗАПУСК:
    cd YuriMansur
    python -m AlbApp.unified_backend_package.example_communication_manager
"""

import sys
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication

# Добавляем корневую папку в sys.path
_root_dir = Path(__file__).parent.parent.parent  # YuriMansur/
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

from AlbApp.unified_backend_package.communication_manager import CommunicationManager


def main():
    """Пример использования CommunicationManager"""
    print("="*70)
    print("COMMUNICATION MANAGER - Единый API для Modbus + OPC UA")
    print("="*70)

    # Создаем Qt приложение
    app = QApplication(sys.argv)

    # ===== СОЗДАНИЕ МЕНЕДЖЕРА =====
    print("\n1. Создание Communication Manager...")
    manager = CommunicationManager()

    # ===== ПОДКЛЮЧАЕМ SIGNALS =====
    print("\n2. Подключение signals...")

    manager.device_connected.connect(
        lambda dev: print(f"   [✓] {dev} подключено")
    )
    manager.device_disconnected.connect(
        lambda dev: print(f"   [✗] {dev} отключено")
    )
    manager.device_error.connect(
        lambda dev, err: print(f"   [ERROR] {dev}: {err}")
    )
    manager.tag_updated.connect(
        lambda dev, tag, val: print(f"   [TAG] {dev}.{tag} = {val}")
    )
    manager.register_updated.connect(
        lambda dev, poll, data: print(f"   [REG] {dev}.{poll}: {data}")
    )

    # ===== ДОБАВЛЕНИЕ MODBUS УСТРОЙСТВА =====
    print("\n3. Добавление Modbus устройства...")

    manager.add_device(
        device_id="PLC1",
        device_type="modbus",
        config={
            "host": "192.168.6.199",
            "port": 502,
            "device_id": 1
        },
        tags={
            "Temperature": {
                "reg_type": "holding",
                "address": 0,
                "count": 2,
                "format": "float32",
                "interval": 1000
            },
            "Pressure": {
                "reg_type": "holding",
                "address": 2,
                "count": 2,
                "format": "float32",
                "interval": 1000
            },
            "Status": {
                "reg_type": "holding",
                "address": 100,
                "count": 1,
                "format": "raw",
                "interval": 500
            }
        }
    )
    print("   [+] PLC1 добавлен (Modbus TCP)")

    # ===== ДОБАВЛЕНИЕ OPC UA УСТРОЙСТВА =====
    print("\n4. Добавление OPC UA устройства...")

    manager.add_device(
        device_id="OPC1",
        device_type="opcua",
        config={
            "endpoint": "opc.tcp://localhost:4840",
            "namespace": 2
        },
        tags={
            "Temperature": {"node_id": "ns=2;s=Temperature"},
            "Pressure": {"node_id": "ns=2;s=Pressure"},
            "SetPoint": {"node_id": "ns=2;s=SetPoint"}
        }
    )
    print("   [+] OPC1 добавлен (OPC UA)")

    # ===== ПОДКЛЮЧЕНИЕ УСТРОЙСТВ =====
    print("\n5. Подключение устройств...")

    print("\n   Подключаем PLC1 (Modbus)...")
    manager.connect_device("PLC1")
    time.sleep(2)

    print("\n   Подключаем OPC1 (OPC UA)...")
    manager.connect_device("OPC1")
    time.sleep(2)

    # ===== ПРОВЕРКА ПОДКЛЮЧЕНИЙ =====
    print("\n6. Проверка подключений...")
    devices = manager.get_devices()
    for dev_id, dev_info in devices.items():
        status = "✓ Подключено" if manager.is_connected(dev_id) else "✗ Отключено"
        print(f"   {dev_id} ({dev_info['type']}): {status}")

    # ===== ПОДПИСКА НА ТЕГИ =====
    print("\n7. Подписка на теги...")

    # PLC1 (Modbus) - создаем polls
    print("\n   PLC1 (Modbus):")
    if manager.is_connected("PLC1"):
        manager.subscribe_tag("PLC1", "Temperature")
        print("      [+] Temperature (poll)")
        manager.subscribe_tag("PLC1", "Pressure")
        print("      [+] Pressure (poll)")
    else:
        print("      [!] PLC1 не подключен, пропускаем")

    # OPC1 (OPC UA) - создаем subscriptions
    print("\n   OPC1 (OPC UA):")
    if manager.is_connected("OPC1"):
        manager.subscribe_tag("OPC1", "Temperature")
        print("      [+] Temperature (subscription)")
        manager.subscribe_tag("OPC1", "Pressure")
        print("      [+] Pressure (subscription)")
    else:
        print("      [!] OPC1 не подключен, пропускаем")

    time.sleep(2)

    # ===== ЧТЕНИЕ ТЕГОВ =====
    print("\n8. Чтение тегов...")

    if manager.is_connected("PLC1"):
        print("\n   PLC1 (Modbus):")
        temp = manager.read_tag("PLC1", "Temperature")
        print(f"      Temperature = {temp}")

        pressure = manager.read_tag("PLC1", "Pressure")
        print(f"      Pressure = {pressure}")

    if manager.is_connected("OPC1"):
        print("\n   OPC1 (OPC UA):")
        print("      Читаем Temperature (результат через signal)...")
        manager.read_tag("OPC1", "Temperature")

    time.sleep(1)

    # ===== ЗАПИСЬ ТЕГОВ =====
    print("\n9. Запись тегов...")

    if manager.is_connected("PLC1"):
        print("\n   PLC1 (Modbus):")
        success = manager.write_tag("PLC1", "Temperature", 25.5)
        print(f"      Запись Temperature = 25.5: {'✓' if success else '✗'}")

    if manager.is_connected("OPC1"):
        print("\n   OPC1 (OPC UA):")
        success = manager.write_tag("OPC1", "SetPoint", 30.0)
        print(f"      Запись SetPoint = 30.0: {'✓' if success else '✗'}")

    time.sleep(1)

    # ===== ПРЯМАЯ РАБОТА С РЕГИСТРАМИ (MODBUS) =====
    print("\n10. Прямая работа с Modbus регистрами...")

    if manager.is_connected("PLC1"):
        # Чтение регистра
        value = manager.read_register("PLC1", "holding", 100, 1, format="raw")
        print(f"    Holding[100] = {value}")

        # Запись регистра
        success = manager.write_register("PLC1", "holding", 100, 42)
        print(f"    Запись Holding[100] = 42: {'✓' if success else '✗'}")

    # ===== ПОЛУЧЕНИЕ ВСЕХ ДАННЫХ =====
    print("\n11. Получение всех данных...")
    all_data = manager.get_all_data()
    for dev_id, data in all_data.items():
        print(f"\n   {dev_id}:")
        for key, value in data.items():
            print(f"      {key}: {value}")

    # ===== МОНИТОРИНГ В РЕАЛЬНОМ ВРЕМЕНИ =====
    print("\n12. Мониторинг в реальном времени (5 секунд)...")
    print("    Данные будут приходить через signals")
    print("    Нажмите Ctrl+C для остановки\n")

    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n[!] Прервано пользователем")

    # ===== ОТКЛЮЧЕНИЕ =====
    print("\n13. Отключение всех устройств...")
    manager.disconnect_all(blocking=True)
    print("   [✓] Все устройства отключены")

    # ===== ЗАВЕРШЕНИЕ =====
    print("\n" + "="*70)
    print("ПРИМЕР ЗАВЕРШЕН")
    print("="*70)
    print("\nСводка:")
    print("  ✓ Единый API для Modbus и OPC UA")
    print("  ✓ Автоматическая маршрутизация команд")
    print("  ✓ Qt signals для всех обновлений")
    print("  ✓ Абстракция тегов (одинаковый интерфейс)")
    print("  ✓ Прямой доступ к регистрам Modbus")

    manager.stop_all()


if __name__ == "__main__":
    main()
