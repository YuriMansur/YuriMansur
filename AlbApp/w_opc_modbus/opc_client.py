"""
OPC UA Client Manager
Асинхронный клиент для работы с OPC UA серверами
"""
from typing import Dict, Any, Optional, List, Callable
from asyncua import Client
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class OPCVariable:
    """Описание переменной OPC UA"""
    name: str                    # Уникальное имя переменной
    node_id: str                 # NodeId переменной (например: "ns=2;i=2")
    server_id: str               # ID сервера
    data_type: Optional[str] = None  # Тип данных (опционально)


class OPCUAClient:
    """Клиент для одного OPC UA сервера"""

    def __init__(self, server_id: str, url: str, timeout: int = 10):
        """
        Args:
            server_id: уникальный ID сервера
            url: URL сервера (например: "opc.tcp://localhost:4840")
            timeout: таймаут подключения в секундах
        """
        self.server_id = server_id
        self.url = url
        self.timeout = timeout
        self.client: Optional[Client] = None
        self.connected = False
        self.subscription = None
        self._monitored_items = {}

    async def connect(self):
        """Подключение к OPC UA серверу"""
        try:
            self.client = Client(url=self.url, timeout=self.timeout)
            await self.client.connect()
            self.connected = True
            logger.info(f"[{self.server_id}] Подключено к {self.url}")
        except Exception as e:
            logger.error(f"[{self.server_id}] Ошибка подключения: {e}")
            self.connected = False
            raise

    async def disconnect(self):
        """Отключение от сервера"""
        if self.client:
            try:
                # Удаляем подписки
                if self.subscription:
                    await self.subscription.delete()
                    self.subscription = None
                    self._monitored_items = {}

                await self.client.disconnect()
                self.connected = False
                logger.info(f"[{self.server_id}] Отключено от {self.url}")
            except Exception as e:
                logger.error(f"[{self.server_id}] Ошибка при отключении: {e}")

    async def read_node(self, node_id: str):
        """
        Чтение значения узла

        Args:
            node_id: NodeId узла (например: "ns=2;i=2")

        Returns:
            Значение узла
        """
        if not self.connected:
            raise ConnectionError(f"[{self.server_id}] Не подключен к серверу")

        try:
            node = self.client.get_node(node_id)
            value = await node.read_value()
            return value
        except Exception as e:
            logger.error(f"[{self.server_id}] Ошибка чтения {node_id}: {e}")
            raise

    async def write_node(self, node_id: str, value: Any):
        """
        Запись значения в узел

        Args:
            node_id: NodeId узла
            value: Значение для записи
        """
        if not self.connected:
            raise ConnectionError(f"[{self.server_id}] Не подключен к серверу")

        try:
            node = self.client.get_node(node_id)
            await node.write_value(value)
            logger.debug(f"[{self.server_id}] Записано {value} в {node_id}")
        except Exception as e:
            logger.error(f"[{self.server_id}] Ошибка записи в {node_id}: {e}")
            raise

    async def subscribe_to_node(self, node_id: str, callback: Callable):
        """
        Подписка на изменения узла

        Args:
            node_id: NodeId узла
            callback: Функция обратного вызова при изменении (node, val, data)
        """
        if not self.connected:
            raise ConnectionError(f"[{self.server_id}] Не подключен к серверу")

        # Создаем подписку если её нет
        if not self.subscription:
            self.subscription = await self.client.create_subscription(500, callback)

        # Добавляем мониторинг узла
        node = self.client.get_node(node_id)
        handle = await self.subscription.subscribe_data_change(node)
        self._monitored_items[node_id] = handle

        logger.info(f"[{self.server_id}] Подписка на {node_id}")

    async def get_node_info(self, node_id: str) -> Dict[str, Any]:
        """
        Получение информации об узле

        Returns:
            Словарь с информацией: {browse_name, data_type, value}
        """
        if not self.connected:
            raise ConnectionError(f"[{self.server_id}] Не подключен к серверу")

        node = self.client.get_node(node_id)

        return {
            "browse_name": await node.read_browse_name(),
            "data_type": await node.read_data_type(),
            "value": await node.read_value(),
        }


class OPCUAManager:
    """Менеджер OPC UA клиентов"""

    def __init__(self):
        self._clients: Dict[str, OPCUAClient] = {}
        self._variables: Dict[str, OPCVariable] = {}

        # 🔧 ВСЯ КОНФИГУРАЦИЯ ЗДЕСЬ
        self._config = [
            {
                "server_id": "Server1",
                "url": "opc.tcp://localhost:4840",
                "timeout": 10,
                # 📌 ПЕРЕМЕННЫЕ ДЛЯ Server1
                "variables": [
                    {"name": "temperature", "node_id": "ns=2;i=2"},
                    {"name": "pressure", "node_id": "ns=2;i=3"},
                    {"name": "status", "node_id": "ns=2;i=4"},
                ],
            },
            # Можно добавить другие серверы
            # {
            #     "server_id": "Server2",
            #     "url": "opc.tcp://192.168.1.100:4840",
            #     "variables": [...]
            # },
        ]

    async def connect_all(self):
        """Подключение ко всем серверам из конфигурации"""
        for cfg in self._config:
            server_id = cfg["server_id"]

            # Создаем клиент
            client = OPCUAClient(
                server_id=server_id,
                url=cfg["url"],
                timeout=cfg.get("timeout", 10)
            )

            # Подключаемся
            try:
                await client.connect()
                self._clients[server_id] = client

                # Регистрируем переменные
                for var_cfg in cfg.get("variables", []):
                    var = OPCVariable(
                        name=var_cfg["name"],
                        node_id=var_cfg["node_id"],
                        server_id=server_id,
                        data_type=var_cfg.get("data_type")
                    )
                    self._variables[var_cfg["name"]] = var

                logger.info(f"[{server_id}] Зарегистрировано переменных: {len(cfg.get('variables', []))}")

            except Exception as e:
                logger.error(f"[{server_id}] Не удалось подключиться: {e}")

    async def disconnect_all(self):
        """Отключение от всех серверов"""
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()

    async def read_var(self, name: str):
        """
        Чтение переменной по имени

        Args:
            name: имя зарегистрированной переменной

        Returns:
            Значение переменной
        """
        if name not in self._variables:
            raise ValueError(f"Переменная '{name}' не зарегистрирована")

        var = self._variables[name]

        if var.server_id not in self._clients:
            raise ValueError(f"Сервер '{var.server_id}' не подключен")

        client = self._clients[var.server_id]
        return await client.read_node(var.node_id)

    async def write_var(self, name: str, value: Any):
        """
        Запись значения в переменную

        Args:
            name: имя зарегистрированной переменной
            value: значение для записи
        """
        if name not in self._variables:
            raise ValueError(f"Переменная '{name}' не зарегистрирована")

        var = self._variables[name]

        if var.server_id not in self._clients:
            raise ValueError(f"Сервер '{var.server_id}' не подключен")

        client = self._clients[var.server_id]
        await client.write_node(var.node_id, value)

    async def subscribe_var(self, name: str, callback: Callable):
        """
        Подписка на изменения переменной

        Args:
            name: имя переменной
            callback: функция обратного вызова
        """
        if name not in self._variables:
            raise ValueError(f"Переменная '{name}' не зарегистрирована")

        var = self._variables[name]

        if var.server_id not in self._clients:
            raise ValueError(f"Сервер '{var.server_id}' не подключен")

        client = self._clients[var.server_id]
        await client.subscribe_to_node(var.node_id, callback)

    def list_variables(self) -> Dict[str, OPCVariable]:
        """Получить список всех зарегистрированных переменных"""
        return self._variables.copy()

    def list_servers(self) -> Dict[str, Dict[str, Any]]:
        """Получить список всех серверов"""
        servers = {}
        for server_id, client in self._clients.items():
            servers[server_id] = {
                "server_id": server_id,
                "url": client.url,
                "connected": client.connected,
                "variables_count": len([v for v in self._variables.values() if v.server_id == server_id])
            }
        return servers

    async def read_multiple(self, var_names: List[str]) -> Dict[str, Any]:
        """
        Чтение нескольких переменных одновременно

        Args:
            var_names: список имён переменных

        Returns:
            Словарь {имя: значение}
        """
        tasks = {}
        for name in var_names:
            tasks[name] = self.read_var(name)

        results = {}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                logger.error(f"Ошибка чтения '{name}': {e}")
                results[name] = None

        return results
