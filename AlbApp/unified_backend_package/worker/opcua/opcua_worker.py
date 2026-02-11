import asyncio
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Callable, Tuple
from asyncua import Client, Node, ua
from asyncua.common.subscription import Subscription, DataChangeNotif
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

logger = logging.getLogger(__name__)

# Обработчик изменений данных от OPC UA подписок.
# Это класс-адаптер между интерфейсом библиотеки asyncua и нашим кодом.
# asyncua при создании подписки (create_subscription) принимает объект handler,
# у которого ОБЯЗАТЕЛЬНО должен быть метод datachange_notification().
# Когда значение переменной на OPC UA сервере изменяется, asyncua автоматически
# вызывает handler.datachange_notification(node, val, data).
#
# Цепочка вызовов:
#   OPC UA Сервер → asyncua библиотека → SubscriptionHandler.datachange_notification()
#   → self.callback(node_id, val) → AsyncOpcUaWorker._on_data_change()
#   → OpcUaWorkerThread (QThread) → Qt signal → GUI
class SubscriptionHandler:
    """
    SubscriptionHandler — паттерн Observer (наблюдатель) для OPC UA протокола.

    Библиотека asyncua требует объект-обработчик с методом datachange_notification(),
    который она будет вызывать при изменении данных на сервере.
    Этот класс оборачивает вызов asyncua в простой callback(node_id, value).
    """

    def __init__(self, callback: Optional[Callable[[str, Any], None]] = None):
        """
        Args:
            callback: Функция-обработчик изменений данных.
                Тип: Optional[Callable[[str, Any], None]]
                Разбор типа по частям:
                  - Optional[...]  — может быть None (callback необязателен)
                  - Callable       — вызываемый объект (функция, метод, lambda)
                  - [str, Any]     — принимает 2 аргумента:
                      str — node_id, строковый ID узла (например "ns=2;s=Temperature")
                      Any — value, новое значение (float, int, bool, str — зависит от узла)
                  - None           — ничего не возвращает (return type)
                  - = None         — значение по умолчанию: обработчик не задан

                Примеры того, что можно передать:
                  callback=lambda nid, val: print(nid, val)
                  callback=self._on_data_change
                  callback=None  (изменения будут молча игнорироваться)
        """

        # Сохраняем переданную callback-функцию как поле экземпляра.
        # При вызове datachange_notification() мы проверим self.callback на None
        # и если он задан — вызовем его с преобразованными аргументами.
        self.callback = callback

    def datachange_notification(self, node: Node, val, data: DataChangeNotif):
        """
        Вызывается АВТОМАТИЧЕСКИ библиотекой asyncua при изменении значения переменной.
        Мы НЕ вызываем этот метод сами — его вызывает asyncua изнутри.

        Args:
            node (Node): Объект узла OPC UA, значение которого изменилось.
                Содержит:
                  node.nodeid                    — объект NodeId (адрес на сервере)
                  node.nodeid.NamespaceIndex     — namespace (например 2)
                  node.nodeid.Identifier         — имя переменной ("Temperature")
                  str(node.nodeid)               — строка "ns=2;s=Temperature"

            val: Новое значение переменной. Тип зависит от переменной на сервере:
                float  — температура, давление (24.1, 101.3)
                int    — счётчики, коды (1500, 42)
                bool   — состояния (True/False)
                str    — текстовые статусы ("Running")

            data (DataChangeNotif): Полная структура уведомления от сервера.
                Содержит (не используется в текущем коде, но доступно):
                  data.monitored_item.Value.SourceTimestamp  — когда PLC зафиксировал значение
                  data.monitored_item.Value.ServerTimestamp  — когда OPC сервер отправил
                  data.monitored_item.Value.StatusCode       — качество данных (Good/Bad)
        """

        # Преобразуем объект NodeId в строку для удобства.
        # NodeId(ns=2, s="Temperature") → "ns=2;s=Temperature"
        node_id = str(node.nodeid)

        # Проверяем что callback задан (не None) и вызываем его.
        # Передаём только node_id и val — упрощённый интерфейс.
        # Если нужен timestamp или quality — можно расширить callback, добавив параметр data.
        if self.callback:
            self.callback(node_id, val)

# Асинхронный OPC UA клиент
class AsyncOpcUaWorker:
    def __init__(
        self,
        endpoint: str,
        namespace: int = 2,
        timeout: float = 10.0,
        on_data_changed: Optional[Callable[[str, Any], None]] = None,
        # --- Security (аутентификация) ---
        username: Optional[str] = None,
        password: Optional[str] = None,
        # --- Certificate (сертификат X.509) ---
        certificate_path: Optional[str] = None,
        private_key_path: Optional[str] = None,
        security_policy: Optional[str] = None,
        security_mode: Optional[str] = None,
        # --- Auto-reconnect ---
        auto_reconnect: bool = False,
        reconnect_interval: float = 5.0,
        max_reconnect_attempts: int = 0):
        """
        Args:
            endpoint: URL сервера (например "opc.tcp://192.168.1.10:4840")
            namespace: Namespace index (по умолчанию 2)
            timeout: Таймаут операций в секундах
            on_data_changed: Callback для изменений (node_id, value)
            username: Имя пользователя для аутентификации (None = анонимный доступ)
            password: Пароль для аутентификации
            certificate_path: Путь к файлу клиентского сертификата X.509 (.der или .pem).
                None = без сертификата (анонимный или username/password доступ).
                Пример: "certs/client_cert.der"
            private_key_path: Путь к файлу закрытого ключа клиента (.pem).
                Используется вместе с certificate_path для подписи сообщений.
                Пример: "certs/client_key.pem"
            security_policy: Политика безопасности для шифрования канала.
                None = "None" (без шифрования, подходит для тестов).
                Варианты:
                  "Basic256Sha256" — рекомендуемая (AES-256 + SHA-256)
                  "Basic256"       — устаревшая (AES-256 + SHA-1)
                  "Basic128Rsa15"  — устаревшая (RSA 1.5, не рекомендуется)
                  "Aes128Sha256RsaOaep" — новая (AES-128 + SHA-256 + RSA OAEP)
            security_mode: Режим безопасности сообщений.
                None = "None" (без подписи и шифрования).
                Варианты:
                  "Sign"           — сообщения подписываются (целостность)
                  "SignAndEncrypt" — подпись + шифрование (конфиденциальность + целостность)
            auto_reconnect: Включить автоматическое переподключение при обрыве
            reconnect_interval: Интервал между попытками переподключения (секунды)
            max_reconnect_attempts: Макс. число попыток (0 = бесконечно)
        """
        # Сохраняем параметры подключения к OPC UA серверу
        self.endpoint = endpoint
        self.namespace = namespace
        self.timeout = timeout
        self.on_data_changed = on_data_changed

        # --- Security ---
        # Логин/пароль для аутентификации на сервере. None = анонимный доступ.
        self._username = username
        self._password = password

        # --- Certificate (X.509) ---
        # Сертификат и ключ для TLS-аутентификации и шифрования канала.
        # В OPC UA сертификат выполняет ДВЕ роли:
        #   1. Аутентификация клиента — сервер проверяет кто подключается
        #   2. Шифрование канала — все данные передаются зашифрованными
        #
        # Форматы файлов:
        #   certificate_path — .der (бинарный) или .pem (Base64, текстовый)
        #   private_key_path — .pem (закрытый ключ, НИКОГДА не передаётся серверу)
        #
        # Как получить сертификат:
        #   1. Самоподписанный (тест): openssl req -x509 -newkey rsa:2048 ...
        #   2. От CA (продакшн): запрос в IT/security отдел
        #   3. Сгенерить через asyncua: await client.load_client_certificate()
        self._certificate_path = certificate_path
        self._private_key_path = private_key_path

        # Политика безопасности — определяет алгоритмы шифрования канала.
        # None = без шифрования. "Basic256Sha256" = рекомендуемая.
        self._security_policy = security_policy

        # Режим безопасности — определяет что защищается.
        # None = ничего. "Sign" = целостность. "SignAndEncrypt" = целостность + конфиденциальность.
        self._security_mode = security_mode

        # Создаем контейнеры до подключения:
        # - Объекты asyncua
        self.client: Optional[Client] = None
        # - Подписки
        self.subscription: Optional[Subscription] = None
        # - Для вызова datachange_notification()
        self.handler: Optional[SubscriptionHandler] = None
        # - Подписанные теги: {"ns=2;s=Temperature": handle_id}
        self.subscribed_tags: Dict[str, int] = {}
        # - Кэш последних значений: {"ns=2;s=Temperature": 24.1} Обновляется при уведомлении от сервера
        self.latest_data: Dict[str, Any] = {}
        # - Флаг подключения. Приватный (с _) — доступ через property is_connected
        self._connected = False

        # --- Polling (множественные именованные циклы) ---
        # Реестр активных poll loop'ов. Каждый цикл — отдельная запись в словаре.
        # Ключ — имя цикла (str), значение — dict с параметрами:
        # {
        #     "fast": {"task": asyncio.Task, "nodes": [...], "interval": 0.2, "active": True},
        #     "slow": {"task": asyncio.Task, "nodes": [...], "interval": 5.0, "active": True},
        # }
        self._poll_loops: Dict[str, Dict[str, Any]] = {}

        # --- Auto-reconnect ---
        # Флаг включения автоматического переподключения
        self._auto_reconnect = auto_reconnect
        # Интервал между попытками (секунды)
        self._reconnect_interval = reconnect_interval
        # Макс. число попыток (0 = бесконечно)
        self._max_reconnect_attempts = max_reconnect_attempts
        # Task для цикла переподключения
        self._reconnect_task: Optional[asyncio.Task] = None
        # Сохранённые параметры подписок/polling для восстановления после reconnect
        self._saved_subscriptions: Dict[str, Optional[str]] = {}  # {node_id: tag_name}
        self._saved_polls: Dict[str, Dict[str, Any]] = {}  # {name: {nodes, interval}}

        # --- Node Cache ---
        # Кэш объектов Node — избегаем повторных вызовов client.get_node().
        # get_node() каждый раз создаёт новый объект Node (парсинг строки node_id).
        # Для hot path (poll loops, частые read/write) это лишние аллокации.
        # Ключ — строковый node_id, значение — объект Node.
        self._node_cache: Dict[str, Node] = {}

        # --- Connection Watchdog ---
        # Периодическая проверка что соединение живое (heartbeat).
        # Обнаруживает обрыв ДО ошибки в read/write — позволяет раньше запустить reconnect.
        self._watchdog_task: Optional[asyncio.Task] = None
        self._watchdog_interval: float = 5.0  # интервал проверки (секунды)

        # --- Diagnostics / Stats ---
        # Счётчики операций для мониторинга и отладки.
        self._stats: Dict[str, Any] = {
            "reads": 0,             # кол-во успешных read_node()
            "writes": 0,            # кол-во успешных write_node()
            "read_errors": 0,       # кол-во ошибок чтения
            "write_errors": 0,      # кол-во ошибок записи
            "reconnects": 0,        # кол-во переподключений
            "last_read_ms": 0.0,    # latency последнего чтения (мс)
            "last_write_ms": 0.0,   # latency последней записи (мс)
            "connected_at": None,   # datetime подключения
            "total_uptime_s": 0.0,  # общее время подключения (секунды)
        }

        # --- Event Subscription ---
        # Подписка на события (аварии, условия) — отдельно от data change подписок.
        # OPC UA Events — это уведомления типа "Alarm triggered", "Condition changed".
        self._event_subscriptions: Dict[str, int] = {}  # {event_type_node_id: handle}
        self._on_event: Optional[Callable[[Dict[str, Any]], None]] = None


# Подключение к серверу
    async def connect(self) -> bool:
        """
        Подключение к OPC UA серверу.
        Returns:
         - True при успехе.
         - При ошибке ConnectionError.
        """
        try:
            # Создаём объект Client
                # - url — адрес сервера ("opc.tcp://192.168.1.10:4840")
                # - timeout — сколько ждать ответа от сервера (секунды)
            self.client = Client(url=self.endpoint, timeout=self.timeout)

            # --- Security: аутентификация по логину/паролю ---
            # Если username задан — устанавливаем credentials перед подключением.
            # Без этого — анонимный доступ (подходит для тестовых серверов).
            if self._username and self._password:
                self.client.set_user(self._username)
                self.client.set_password(self._password)

            # --- Security: сертификат X.509 ---
            # Если указаны сертификат и ключ — настраиваем TLS-безопасность канала.
            # set_security() устанавливает:
            #   1. Политику шифрования (какие алгоритмы: AES-256, SHA-256 и т.д.)
            #   2. Режим безопасности (Sign / SignAndEncrypt)
            #   3. Клиентский сертификат (для аутентификации на сервере)
            #   4. Закрытый ключ (для подписи и расшифровки)
            #
            # ВАЖНО: вызывать ПЕРЕД connect(), иначе соединение установится без шифрования.
            # Сертификат должен быть в trust-list сервера, иначе сервер отклонит подключение.
            if self._certificate_path and self._private_key_path:
                await self._apply_certificate_security()

            # Устанавливаем TCP соединение с сервером.
            await self.client.connect()
            # Создаём обработчик уведомлений (наш SubscriptionHandler).
            self.handler = SubscriptionHandler(callback = self._on_data_change)

            # Создаём подписку без тегов (Subscription) на сервере.
                #  - period — интервал публикации (мс).Сервер собирает изменения и шлёт пачкой
                #  - handler — объект с методом datachange_notification(),
            self.subscription = await self.client.create_subscription(
                period = 500,
                handler = self.handler)
            # Флаг подключения = True.
            self._connected = True
            # Записываем время подключения для статистики uptime
            self._stats["connected_at"] = datetime.now(timezone.utc)
            return True
        # Обработка исключений
        except Exception as e:
            # Флаг подключения = False.
            self._connected = False
            # Пробрасываем наверх — OpcUaWorkerThread поймает и эмитит connection_error.
            raise ConnectionError(f"Failed to connect to {self.endpoint}: {e}")
        
# Отключение от сервера
    async def disconnect(self) -> bool:
        """
        Отключение от OPC UA сервера.
        Returns:
         - True при успехе. 
         - При ошибке RuntimeError.
        """
        try:
            # Останавливаем watchdog — соединение закрывается намеренно
            await self.stop_watchdog()
            # Останавливаем reconnect если запущен — мы отключаемся намеренно
            await self.stop_reconnect()
            # Останавливаем ВСЕ poll loop'ы — нет смысла опрашивать отключённый сервер
            if self._poll_loops:
                await self.stop_polling()
            # Удаляем подписку на сервере c проверкой на созданую подписку
            if self.subscription:
                await self.subscription.delete()
                # Освобождаем ссылку
                self.subscription = None
            # Закрываем соединение с сервером.
            if self.client:
                await self.client.disconnect()
                # Освобождаем ссылку
                self.client = None
            # Обновляем статистику uptime перед сбросом флага
            if self._stats["connected_at"]:
                elapsed = (datetime.now(timezone.utc) - self._stats["connected_at"]).total_seconds()
                self._stats["total_uptime_s"] += elapsed
                self._stats["connected_at"] = None
            # Флаг подключения = False.
            self._connected = False
            # Очищаем реестр тегов (handle'ы больше не валидны)
            self.subscribed_tags.clear()
            # Очищаем кэш Node-объектов — они привязаны к старому Client
            self._node_cache.clear()
            # Очищаем event подписки
            self._event_subscriptions.clear()
            return True
        # Обработка исключений
        except Exception as e:
            # Ошибка при отключении (сервер уже упал, сеть оборвалась и т.д.)
            raise RuntimeError(f"Failed to disconnect: {e}")

    @property
    def is_connected(self) -> bool:
        """
        Проверка подключения к серверу.

        @property — позволяет вызывать как атрибут: worker.is_connected (без скобок).
        Двойная проверка:
          - self._connected  — наш флаг (устанавливается в connect/disconnect)
          - self.client is not None — объект Client существует
        Обе проверки нужны на случай если client был удалён, но флаг не сброшен.
        """
        return self._connected and self.client is not None

# ==================== Security — управление аутентификацией ====================

    def set_credentials(self, username: str, password: str) -> None:
        """
        Установить или изменить логин/пароль для аутентификации.

        Вызывать ПЕРЕД connect(). Если уже подключены — нужно
        disconnect() → set_credentials() → connect() для применения.

        Args:
            username: Имя пользователя на OPC UA сервере.
            password: Пароль.

        Пример:
            worker.set_credentials("operator", "secret123")
            await worker.connect()
        """
        self._username = username
        self._password = password
        logger.info(f"Credentials set for user '{username}'")

    def clear_credentials(self) -> None:
        """
        Убрать аутентификацию — переключиться на анонимный доступ.

        После вызова следующий connect() будет без логина/пароля.
        """
        self._username = None
        self._password = None
        logger.info("Credentials cleared, anonymous access")

    @property
    def is_authenticated(self) -> bool:
        """
        Проверить, заданы ли credentials для аутентификации.

        Returns:
            True если username и password заданы.
            Не означает что аутентификация прошла успешно —
            только что credentials будут отправлены при connect().
        """
        return self._username is not None and self._password is not None

    async def get_server_endpoints(self) -> List[Dict[str, Any]]:
        """
        Получить список доступных endpoint'ов сервера с их политиками безопасности.

        Полезно для диагностики: какие методы аутентификации поддерживает сервер.
        Не требует подключения — создаёт временный Client.

        Returns:
            Список endpoint'ов:
            [
                {
                    "url": "opc.tcp://192.168.1.10:4840",
                    "security_mode": "None",            # None, Sign, SignAndEncrypt
                    "security_policy": "None",           # None, Basic256Sha256, ...
                    "user_tokens": ["Anonymous", "Username"]  # доступные методы входа
                },
                ...
            ]

        Raises:
            RuntimeError: Сервер недоступен.
        """
        try:
            # Создаём временный клиент только для запроса endpoint'ов
            temp_client = Client(url=self.endpoint, timeout=self.timeout)
            endpoints = await temp_client.connect_and_get_server_endpoints()

            result = []
            for ep in endpoints:
                tokens = []
                # Извлекаем доступные методы аутентификации
                if ep.UserIdentityTokens:
                    for token in ep.UserIdentityTokens:
                        token_type = str(token.TokenType)
                        # Преобразуем enum в читаемое имя
                        if "Anonymous" in token_type:
                            tokens.append("Anonymous")
                        elif "UserName" in token_type:
                            tokens.append("Username")
                        elif "Certificate" in token_type:
                            tokens.append("Certificate")
                        else:
                            tokens.append(token_type)

                result.append({
                    "url": ep.EndpointUrl,
                    "security_mode": str(ep.SecurityMode).split(".")[-1],
                    "security_policy": ep.SecurityPolicyUri.split("#")[-1] if ep.SecurityPolicyUri else "None",
                    "user_tokens": tokens,
                })
            return result

        except Exception as e:
            raise RuntimeError(f"Failed to get server endpoints: {e}")

# ==================== Certificate — управление сертификатами X.509 ====================
# OPC UA поддерживает аутентификацию и шифрование через сертификаты X.509.
# Это промышленный стандарт безопасности для защиты канала связи.
#
# Схема работы:
#   1. Клиент имеет пару: сертификат (.der/.pem) + закрытый ключ (.pem)
#   2. Сервер имеет свой сертификат (получаем автоматически при подключении)
#   3. При connect() клиент отправляет свой сертификат серверу
#   4. Сервер проверяет сертификат (должен быть в trust-list сервера)
#   5. После handshake — канал зашифрован, данные защищены
#
# Три уровня безопасности (можно комбинировать):
#   1. Только сертификат — аутентификация + шифрование канала
#   2. Сертификат + username/password — двойная аутентификация
#   3. Без сертификата, только username/password — только аутентификация, без шифрования

    def set_certificate(self, certificate_path: str, private_key_path: str,
                        security_policy: Optional[str] = "Basic256Sha256",
                        security_mode: Optional[str] = "SignAndEncrypt") -> None:
        """
        Установить клиентский сертификат для аутентификации и шифрования.

        Вызывать ПЕРЕД connect(). Если уже подключены — нужно
        disconnect() → set_certificate() → connect().

        Args:
            certificate_path: Путь к файлу сертификата.
                Поддерживаемые форматы:
                  .der — бинарный формат (DER-encoded X.509)
                  .pem — текстовый формат (Base64-encoded, начинается с -----BEGIN CERTIFICATE-----)
                Пример: "C:/certs/client_cert.der" или "/opt/certs/client.pem"

            private_key_path: Путь к файлу закрытого ключа.
                Формат: .pem (текстовый, начинается с -----BEGIN PRIVATE KEY-----)
                ВАЖНО: этот файл НИКОГДА не передаётся серверу.
                Используется локально для подписи и расшифровки.
                Пример: "C:/certs/client_key.pem"

            security_policy: Алгоритм шифрования канала (по умолчанию "Basic256Sha256").
                "Basic256Sha256"       — рекомендуемая (AES-256 + SHA-256)
                "Aes128Sha256RsaOaep"  — новая альтернатива
                "Basic256"             — устаревшая
                None                   — без шифрования (только аутентификация по сертификату)

            security_mode: Режим защиты сообщений (по умолчанию "SignAndEncrypt").
                "SignAndEncrypt" — подпись + шифрование (рекомендуется для продакшн)
                "Sign"           — только подпись (целостность, но данные видны)
                None             — без защиты

        Raises:
            FileNotFoundError: Файл сертификата или ключа не найден.

        Пример:
            worker.set_certificate(
                certificate_path="certs/client_cert.der",
                private_key_path="certs/client_key.pem",
                security_policy="Basic256Sha256",
                security_mode="SignAndEncrypt"
            )
            await worker.connect()
        """
        # Проверяем что файлы существуют ДО подключения —
        # лучше упасть сразу с понятной ошибкой, чем получить cryptic error при connect().
        cert_path = Path(certificate_path)
        key_path = Path(private_key_path)

        if not cert_path.exists():
            raise FileNotFoundError(f"Certificate file not found: {certificate_path}")
        if not key_path.exists():
            raise FileNotFoundError(f"Private key file not found: {private_key_path}")

        self._certificate_path = str(cert_path.resolve())
        self._private_key_path = str(key_path.resolve())
        self._security_policy = security_policy
        self._security_mode = security_mode
        logger.info(f"Certificate set: {cert_path.name}, policy={security_policy}, mode={security_mode}")

    def clear_certificate(self) -> None:
        """
        Убрать привязку сертификата — переключиться на незащищённый канал.

        После вызова следующий connect() будет без сертификата.
        Если также заданы username/password — они продолжат работать
        (но канал не будет зашифрован).
        """
        self._certificate_path = None
        self._private_key_path = None
        self._security_policy = None
        self._security_mode = None
        logger.info("Certificate cleared, unsecured channel")

    @property
    def has_certificate(self) -> bool:
        """
        Проверить, привязан ли сертификат.

        Returns:
            True если certificate_path и private_key_path заданы.
            Не означает что сертификат валиден или принят сервером —
            только что он будет использован при connect().
        """
        return self._certificate_path is not None and self._private_key_path is not None

    @staticmethod
    def generate_self_signed_certificate(
        output_dir: str = "certs",
        common_name: str = "OPC UA Client",
        organization: str = "Development",
        country: str = "US",
        key_size: int = 2048,
        valid_days: int = 365,
        uri: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Сгенерировать самоподписанный X.509 сертификат и закрытый ключ.

        Для тестирования и разработки. В продакшне используйте сертификаты от CA.

        Как работает:
          1. Генерирует RSA-ключ (пара: открытый + закрытый)
          2. Создаёт X.509 сертификат с метаданными (CN, O, C)
          3. Добавляет OPC UA расширения (Application URI, Key Usage)
          4. Подписывает сертификат собственным ключом (self-signed)
          5. Сохраняет в файлы: cert.der + key.pem

        Args:
            output_dir: Папка для сохранения файлов.
                Создаётся автоматически если не существует.
                По умолчанию: "certs" (относительно рабочей директории).

            common_name: Имя клиента (поле CN в сертификате).
                Отображается в логах OPC UA сервера.
                Пример: "SCADA Client", "PLC Monitor"

            organization: Название организации (поле O в сертификате).
                Пример: "My Company", "Development Team"

            country: Код страны (поле C, 2 буквы ISO 3166).
                Пример: "US", "RU", "DE"

            key_size: Размер RSA-ключа в битах.
                2048 — минимально рекомендуемый (быстрый, подходит для тестов).
                4096 — более безопасный (медленнее генерация и handshake).

            valid_days: Срок действия сертификата в днях.
                365 — 1 год (по умолчанию).
                3650 — 10 лет (для тестового стенда).

            uri: Application URI — уникальный идентификатор приложения.
                Встраивается в сертификат как SAN (Subject Alternative Name).
                OPC UA сервер может проверять этот URI.
                None — генерируется автоматически: "urn:opcua:client:{common_name}"
                Пример: "urn:mycompany:scada:client"

        Returns:
            Tuple[str, str]: (certificate_path, private_key_path) — пути к файлам.
            Пример: ("certs/client_cert.der", "certs/client_key.pem")

        Raises:
            RuntimeError: Ошибка генерации (проблема с библиотекой cryptography).

        Пример использования:
            # Генерируем сертификат
            cert, key = AsyncOpcUaWorker.generate_self_signed_certificate(
                output_dir="my_certs",
                common_name="SCADA Client",
                valid_days=3650
            )

            # Используем для подключения
            worker = AsyncOpcUaWorker("opc.tcp://...")
            worker.set_certificate(cert, key)
            await worker.connect()
        """
        try:
            # --- Импорты из cryptography ---
            # cryptography — зависимость asyncua, не нужно устанавливать отдельно.
            # Используем lazy import: загружаем только когда метод вызван,
            # чтобы не замедлять импорт модуля если генерация не нужна.
            from cryptography import x509
            from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.backends import default_backend

            # --- 1. Создаём папку для сертификатов ---
            cert_dir = Path(output_dir)
            cert_dir.mkdir(parents=True, exist_ok=True)

            # --- 2. Генерируем RSA-ключ ---
            # RSA — алгоритм асимметричного шифрования.
            # Генерирует ДВА ключа:
            #   - Открытый (public key) — встраивается в сертификат, отправляется серверу
            #   - Закрытый (private key) — хранится в key.pem, НИКОГДА не передаётся
            #
            # public_exponent=65537 — стандартное значение (0x10001), используется всеми.
            # key_size — длина ключа в битах. Больше = безопаснее, но медленнее.
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=key_size,
                backend=default_backend(),
            )

            # --- 3. Формируем Subject (кто владелец сертификата) ---
            # Subject — метаданные в сертификате, описывающие владельца.
            # OPC UA сервер видит эти поля в логах и при проверке доступа.
            subject = x509.Name([
                # C (Country) — страна, 2 буквы ISO
                x509.NameAttribute(NameOID.COUNTRY_NAME, country),
                # O (Organization) — организация
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
                # CN (Common Name) — имя клиента (главное поле)
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ])

            # --- 4. Application URI для OPC UA ---
            # URI — уникальный идентификатор приложения в стандарте OPC UA.
            # Сервер может проверять: URI в сертификате == URI в запросе подключения.
            # Если не совпадает — сервер может отклонить подключение.
            app_uri = uri or f"urn:opcua:client:{common_name.replace(' ', '_')}"

            # --- 5. Собираем сертификат ---
            # x509.CertificateBuilder() — пошаговый конструктор сертификата.
            from datetime import timedelta, timezone
            now = datetime.now(timezone.utc)

            builder = (
                x509.CertificateBuilder()
                # subject — кто владелец (наш клиент)
                .subject_name(subject)
                # issuer — кто выдал. Для self-signed: issuer == subject (сам себе выдал)
                .issuer_name(subject)
                # Встраиваем открытый ключ в сертификат
                .public_key(private_key.public_key())
                # Серийный номер — уникальный ID сертификата (случайный)
                .serial_number(x509.random_serial_number())
                # Срок действия: от сейчас до now + valid_days
                .not_valid_before(now)
                .not_valid_after(now + timedelta(days=valid_days))
            )

            # --- 6. Добавляем расширения (Extensions) ---
            # Расширения — дополнительные поля сертификата, описывающие его назначение.

            # Subject Alternative Name (SAN) — альтернативные имена/идентификаторы.
            # OPC UA требует URI в SAN для идентификации приложения.
            builder = builder.add_extension(
                x509.SubjectAlternativeName([
                    x509.UniformResourceIdentifier(app_uri),
                ]),
                critical=False,  # critical=False — сервер может игнорировать если не понимает
            )

            # Basic Constraints — это НЕ CA (Certificate Authority).
            # ca=False — этот сертификат не может выдавать другие сертификаты.
            # Только для аутентификации клиента.
            builder = builder.add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,  # critical=True — ОБЯЗАТЕЛЬНО проверять
            )

            # Key Usage — для чего можно использовать ключ.
            # digital_signature=True — подпись сообщений (обязательно для OPC UA)
            # key_encipherment=True — шифрование ключей сессии
            # content_commitment (non_repudiation) — неотказуемость
            builder = builder.add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=True,
                    data_encipherment=True,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )

            # Extended Key Usage — расширенное назначение.
            # CLIENT_AUTH — этот сертификат для аутентификации клиента.
            # SERVER_AUTH — добавляем на случай если используется для тестового сервера.
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                    ExtendedKeyUsageOID.SERVER_AUTH,
                ]),
                critical=False,
            )

            # --- 7. Подписываем сертификат ---
            # sign() — финальный шаг: подписываем закрытым ключом.
            # SHA256 — алгоритм хеширования для подписи.
            # Self-signed: подписываем СВОИМ ключом (не CA).
            certificate = builder.sign(
                private_key=private_key,
                algorithm=hashes.SHA256(),
                backend=default_backend(),
            )

            # --- 8. Сохраняем в файлы ---
            # Сертификат в формате DER (бинарный) — стандарт для OPC UA.
            cert_file = cert_dir / "client_cert.der"
            cert_file.write_bytes(
                certificate.public_bytes(serialization.Encoding.DER)
            )

            # Закрытый ключ в формате PEM (текстовый) — стандарт для хранения.
            # NoEncryption() — ключ не зашифрован паролем.
            # В продакшне можно использовать BestAvailableEncryption(password) для защиты.
            key_file = cert_dir / "client_key.pem"
            key_file.write_bytes(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

            cert_path_str = str(cert_file.resolve())
            key_path_str = str(key_file.resolve())
            logger.info(
                f"Self-signed certificate generated:\n"
                f"  Certificate: {cert_path_str}\n"
                f"  Private key: {key_path_str}\n"
                f"  CN={common_name}, O={organization}, C={country}\n"
                f"  URI={app_uri}, Key={key_size}bit, Valid={valid_days}days"
            )
            return cert_path_str, key_path_str

        except ImportError:
            raise RuntimeError(
                "Library 'cryptography' is not installed. "
                "Install it: pip install cryptography"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to generate certificate: {e}")

    async def _apply_certificate_security(self) -> None:
        """
        Внутренний метод: применить настройки сертификата к Client перед connect().

        Вызывается из connect() если сертификат задан.
        Загружает сертификат и ключ, устанавливает security policy и mode.

        Логика работы set_security():
          1. Загружает клиентский сертификат (.der/.pem) в память
          2. Загружает закрытый ключ (.pem) в память
          3. Запрашивает у сервера его сертификат (server certificate)
          4. Устанавливает security policy (алгоритмы шифрования)
          5. Устанавливает security mode (Sign / SignAndEncrypt)
          6. Готово — при connect() канал будет зашифрован

        Raises:
            RuntimeError: Ошибка загрузки сертификата или ключа.
        """
        try:
            # Определяем security policy — алгоритмы шифрования.
            # Маппинг строковых имён в URI, которые понимает asyncua.
            # URI — стандартные идентификаторы OPC UA Foundation.
            policy_map = {
                "Basic256Sha256": "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256",
                "Basic256": "http://opcfoundation.org/UA/SecurityPolicy#Basic256",
                "Basic128Rsa15": "http://opcfoundation.org/UA/SecurityPolicy#Basic128Rsa15",
                "Aes128Sha256RsaOaep": "http://opcfoundation.org/UA/SecurityPolicy#Aes128_Sha256_RsaOaep",
                "Aes256Sha256RsaPss": "http://opcfoundation.org/UA/SecurityPolicy#Aes256_Sha256_RsaPss",
                None: None,
            }

            # Определяем security mode — что защищаем.
            # ua.MessageSecurityMode — enum из asyncua:
            #   None_ (1)          — без подписи и шифрования
            #   Sign (2)           — подпись (целостность данных)
            #   SignAndEncrypt (3)  — подпись + шифрование (полная защита)
            mode_map = {
                "Sign": ua.MessageSecurityMode.Sign,
                "SignAndEncrypt": ua.MessageSecurityMode.SignAndEncrypt,
                None: ua.MessageSecurityMode.SignAndEncrypt,  # по умолчанию — максимальная защита
            }

            policy_uri = policy_map.get(self._security_policy, policy_map[None])
            mode = mode_map.get(self._security_mode, mode_map[None])

            # set_security() — главный метод asyncua для настройки безопасности.
            # Параметры:
            #   policy    — URI политики шифрования (какие алгоритмы использовать)
            #   certificate_path — путь к клиентскому сертификату
            #   private_key_path — путь к закрытому ключу клиента
            #   mode      — режим безопасности (Sign / SignAndEncrypt)
            #
            # Что происходит внутри:
            #   1. asyncua загружает сертификат и ключ из файлов
            #   2. Получает сертификат сервера (через GetEndpoints)
            #   3. Формирует SecurityPolicy объект с выбранными алгоритмами
            #   4. При connect() использует всё это для TLS handshake
            if policy_uri:
                await self.client.set_security(
                    policy=policy_uri,
                    certificate_path=self._certificate_path,
                    private_key_path=self._private_key_path,
                    mode=mode,
                )
                logger.info(f"Security applied: policy={self._security_policy}, mode={self._security_mode}")
            else:
                # Политика None — загружаем сертификат без шифрования канала.
                # Используется когда сервер требует сертификат для аутентификации,
                # но канал шифрования не нужен (локальная сеть, тесты).
                await self.client.load_client_certificate(self._certificate_path)
                await self.client.load_private_key(self._private_key_path)
                logger.info("Certificate loaded without channel encryption")

        except Exception as e:
            raise RuntimeError(
                f"Failed to apply certificate security: {e}. "
                f"Check certificate format (.der/.pem) and key file (.pem)"
            )

    async def get_server_certificate_info(self) -> Dict[str, Any]:
        """
        Получить информацию о сертификате OPC UA сервера.

        Полезно для диагностики: какой сертификат у сервера, когда истекает,
        какой издатель (CA). Требует активного подключения.

        Returns:
            Словарь с информацией о сертификате сервера:
            {
                "server_certificate_exists": True/False,
                "endpoints_with_security": [
                    {
                        "url": "opc.tcp://...",
                        "security_policy": "Basic256Sha256",
                        "security_mode": "SignAndEncrypt",
                        "accepts_certificates": True/False
                    }
                ]
            }

        Raises:
            RuntimeError: Не удалось получить информацию.
        """
        try:
            # Получаем endpoints сервера с информацией о безопасности
            endpoints = await self.get_server_endpoints()

            # Фильтруем — оставляем только endpoints с шифрованием
            secure_eps = []
            for ep in endpoints:
                has_cert_token = "Certificate" in ep.get("user_tokens", [])
                secure_eps.append({
                    "url": ep["url"],
                    "security_policy": ep["security_policy"],
                    "security_mode": ep["security_mode"],
                    "accepts_certificates": has_cert_token,
                })

            # Проверяем наличие сертификата у текущего подключения
            has_server_cert = False
            if self.client and hasattr(self.client, 'server_certificate'):
                has_server_cert = self.client.server_certificate is not None

            return {
                "server_certificate_exists": has_server_cert,
                "endpoints_with_security": secure_eps,
            }

        except Exception as e:
            raise RuntimeError(f"Failed to get server certificate info: {e}")

# Однократное чтение ОДНОГО тэга
    async def read_node(self, node_id: str) -> Optional[Any]:
        """
        Однократное чтение значения переменной с OPC UA сервера.
        Args:
            node_id: Строковый адрес узла на сервере.
                Формат: "ns=<namespace>;s=<имя>" или "ns=<namespace>;i=<число>"
        Returns:
            Значение переменной (float, int, bool, str и т.д.)
        Raises:
            ConnectionError: Если не подключены к серверу.
            RuntimeError: Если узел не найден или ошибка чтения.
        """
        # Прверка флага подключения и наличие объекта client.
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")
        # Запрос
        try:
            # Получаем Node из кэша (или создаём и кэшируем)
            node = self._get_cached_node(node_id)
            # Засекаем время для статистики latency
            t0 = time.perf_counter()
            # Ожидаем и считываем значение
            value = await node.read_value()
            # Обновляем статистику
            self._stats["reads"] += 1
            self._stats["last_read_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            # Сохраняем в кэш для получения последних данных без повторного обращения к серверу.
            self.latest_data[node_id] = value
            return value
        # Обработка исключений
        except Exception as e:
            self._stats["read_errors"] += 1
            # Возможные причины: узел не существует, нет прав доступа, таймаут.
            raise RuntimeError(f"Failed to read node {node_id}: {e}")

# Однократная запись ОДНОГО тэга
    async def write_node(self, node_id: str, value: Any) -> bool:
        """
        Однократная запись значения в переменную на OPC UA сервере.

        Args:
            node_id: Адрес узла ("ns=2;s=SetPoint", "ns=2;i=1001")
            value: Значение для записи. Тип должен совпадать с типом на сервере:
                float, int, bool,str.   
        Returns:
            True при успешной записи.
        Raises:
            ConnectionError: Не подключены к серверу.
            RuntimeError: Узел не найден, нет прав записи, неверный тип значения.
        """
        # # Прверка флага подключения
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")

        try:
            # Получаем Node из кэша (или создаём и кэшируем)
            node = self._get_cached_node(node_id)
            # Засекаем время для статистики latency
            t0 = time.perf_counter()
            # Ожидаем успешное подтверждение записи
            await node.write_value(value)
            # Обновляем статистику
            self._stats["writes"] += 1
            self._stats["last_write_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return True
        # Обработка исключений
        except Exception as e:
            self._stats["write_errors"] += 1
            # Возможные причины: узел read-only, неверный тип, нет прав, таймаут.
            raise RuntimeError(f"Failed to write node {node_id}: {e}")

# Однократная запись НЕСКОЛЬКИХ тэгов (ПАРАЛЛЕЛЬНО)
    async def write_multiple_nodes(self, values: Dict[str, Any]) -> Dict[str, bool]:
        """
        Пакетная запись нескольких переменных ПАРАЛЛЕЛЬНО через asyncio.gather().

        При ошибке одного тега — остальные всё равно записываются.

        Args:
            values: Словарь {node_id: value} для записи.
                Пример: {
                    "ns=2;s=SetPoint": 25.5,
                    "ns=2;s=Mode": 1,
                    "ns=2;s=Enable": True
                }

        Returns:
            Словарь {node_id: success} — результат по каждому тегу.
            Пример: {"ns=2;s=SetPoint": True, "ns=2;s=Mode": True, "ns=2;s=Enable": False}

        Raises:
            ConnectionError: Не подключены к серверу.
        """
        # Проверка подключения
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")

        # Запускаем ВСЕ write_node() одновременно через asyncio.gather().
        node_ids = list(values.keys())
        raw_results = await asyncio.gather(
            *[self.write_node(node_id, value) for node_id, value in values.items()],
            return_exceptions=True
        )

        # Собираем результаты в словарь {node_id: success}
        results = {}
        for node_id, result in zip(node_ids, raw_results):
            if isinstance(result, Exception):
                results[node_id] = False
                logger.error(f"Error writing {node_id}: {result}")
            else:
                results[node_id] = True
        return results

# Однократное чтение НЕСКОЛЬКИХ тэгов (ПАРАЛЛЕЛЬНО)
    async def read_multiple_nodes(self, node_ids: List[str]) -> Dict[str, Any]:
        """
        Пакетное чтение нескольких переменных ПАРАЛЛЕЛЬНО через asyncio.gather().

        Все запросы отправляются одновременно — время = макс(время одного запроса),
        а не сумма всех. Для 10 тегов по 20мс: 20мс вместо 200мс.

        При ошибке одного тега — остальные всё равно читаются (return_exceptions=True).

        Args:
            node_ids: Список адресов узлов.
                Пример: ["ns=2;s=Temperature", "ns=2;s=Pressure", "ns=2;s=Level"]

        Returns:
            Словарь {node_id: value} для ВСЕХ запрошенных тегов.
            Если тег не прочитан — его значение будет None.
            Пример: {"ns=2;s=Temperature": 24.1, "ns=2;s=Pressure": None, "ns=2;s=Level": 85}

        Raises:
            ConnectionError: Не подключены к серверу (проверка ДО цикла).
        """
        # Проверка флага подключения
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")

        # Запускаем ВСЕ read_node() одновременно через asyncio.gather().
        # return_exceptions=True — при ошибке одного тега gather() НЕ падает,
        # а возвращает объект Exception вместо значения в массиве результатов.
        # Без этого флага одна ошибка убила бы чтение ВСЕХ тегов.
        raw_results = await asyncio.gather(
            *[self.read_node(node_id) for node_id in node_ids],
            return_exceptions=True
        )

        # Собираем результаты в словарь {node_id: value}
        results = {}
        for node_id, result in zip(node_ids, raw_results):
            if isinstance(result, Exception):
                # Этот тег не прочитался — записываем None
                results[node_id] = None
                logger.error(f"Error reading {node_id}: {result}")
            else:
                # Успешное чтение — значение уже в latest_data (записал read_node)
                results[node_id] = result
        return results

# Подписка на тег
    async def subscribe_tag(self, node_id: str, tag_name: Optional[str] = None) -> bool:
        """
        Подписаться на автоматическое отслеживание изменений тега (push-модель).
        Args:
            node_id: Адрес узла ("ns=2;s=Temperature", "ns=2;i=1001")
            tag_name: Человекочитаемое имя тега (опционально).
                Сохраняется в latest_data для удобства маппинга node_id → имя.
        Returns:
            True если подписка создана или тег уже был подписан.
        Raises:
            ConnectionError: Не подключены или Subscription не создана.
            RuntimeError: Узел не найден на сервере.
        """
        # Двойная проверка: и соединение, и наличие объекта Subscription.
        if not self.is_connected or not self.subscription:
            raise ConnectionError("Not connected or subscription not created")
        # Защита от повторной подписки OPC UA сервер создаст дубликат, а старый handle потеряется.
        if node_id in self.subscribed_tags:
            return True  

        try:
            # Создаём локальный объект-указатель на узел 
            node = self.client.get_node(node_id)
            # Сервер добавляет узел в Subscription 
            # Возвращает handle — числовой ID подписки, нужен для отписки.
            handle = await self.subscription.subscribe_data_change(node)
            # Сохраняем handle в реестр для возможности отписки: {"ns=2;s=Temperature": 42}
            self.subscribed_tags[node_id] = handle
            # Это маппинг: "ns=2;s=Temperature_name" → "Temperature" # Позволяет найти имя тега по node_id.
            if tag_name: 
                self.latest_data[f"{node_id}_name"] = tag_name
            return True
        # Обработка исключений
        except Exception as e:
            # Узел не существует на сервере или нет прав на мониторинг.
            raise RuntimeError(f"Failed to subscribe to {node_id}: {e}")

# Отписка от тега
    async def unsubscribe_tag(self, node_id: str) -> bool:
        """
        Отписаться от автоматического отслеживания тега.
        Args:
            node_id: Адрес узла ("ns=2;s=Temperature")
        Returns:
            True если отписка выполнена или тег уже не был подписан.
        Raises:
            RuntimeError: Ошибка при отписке на стороне сервера.
        """
        # Если тега нет в реестре — он уже не подписан, ничего делать не нужно.
        # Возвращаем True (идемпотентность: повторный вызов не вызывает ошибку).
        if node_id not in self.subscribed_tags:
            return True

        try:
            # Получаем handle — числовой ID тэга подписки
            handle = self.subscribed_tags[node_id]
            # Отправляем серверу запрос удаелния узла из Subscription и перестаёт его отслеживать
            await self.subscription.unsubscribe(handle)
            # Удаляем из реестра — handle больше не валиден.
            del self.subscribed_tags[node_id]
            # Очищаем кэш: последнее значение этого тега больше не актуально,
            if node_id in self.latest_data:
                del self.latest_data[node_id]
            return True
        # Обработка исключений
        except Exception as e:
            # Возможные причины: Subscription уже удалена, сервер отключился.
            raise RuntimeError(f"Failed to unsubscribe from {node_id}: {e}")

# Подписка на несколько тегов
    async def subscribe_multiple_tags(self, tags: Dict[str, str]) -> Dict[str, bool]:
        """
        Пакетная подписка на несколько тегов за один вызов.
        Args:
            tags: Словарь {tag_name: node_id}
                Пример: {
                    "Temperature": "ns=2;s=Temperature",
                    "Pressure":    "ns=2;s=Pressure",
                    "Level":       "ns=2;s=Level"
                }
        Returns:
            Словарь {tag_name: success} — результат по каждому тегу.
            Пример: {"Temperature": True, "Pressure": True, "Level": False}
        """
        # Создаем контейнер для для данных
        results = {}
        # Подписываемся последовательно — каждый вызов
        for tag_name, node_id in tags.items():
            try:
                # Сохраняем handle и tag_name в реестры
                success = await self.subscribe_tag(node_id, tag_name)
                # Читаем данные
                results[tag_name] = success
            except Exception as e:
                # Сбой одного тега — записываем False и продолжаем остальные.
                results[tag_name] = False
                # Пишем в лог исключение
                logger.error(f"Error subscribing to {tag_name}: {e}")
        return results

# Получение всех подписок на теги
    def get_subscribed_tags(self) -> List[str]:
        """Получить список подписанных тегов"""
        return list(self.subscribed_tags.keys())

# Сохранение дааных в кэш
    def _on_data_change(self, node_id: str, value: Any):
        """
        Промежуточное звено: сохраняет данные в кэш
        и пробрасывает дальше через пользовательский callback.
        Args:
            node_id: Строковый адрес узла, значение которого изменилось.
                Пример: "ns=2;s=Temperature"
                Уже преобразован в строку в SubscriptionHandler (str(node.nodeid)).
            value: Новое значение переменной (float, int, bool, str).
                Тип зависит от типа переменной на OPC UA сервере.
        """
        # Обновляем кэш последних значений.
        self.latest_data[node_id] = value
        # Пробрасываем изменение наверх через пользовательский callback.
        # Проверка на None — callback необязателен (если не задан, данные просто кэшируются).
        if self.on_data_changed:
            self.on_data_changed(node_id, value)

# Получение последних данных из кэша (без обращения к серверу)
    def get_latest_data(self) -> Dict[str, Any]:
        """
        Получить снимок (snapshot) всех кэшированных значений.
        Returns:
            Копия словаря 

            latest_data: {node_id: последнее_значение}
            Пример: {
                "ns=2;s=Temperature": 24.1,
                "ns=2;s=Pressure": 101.3,
                "ns=2;s=Temperature_name": "Temperature"  # маппинг имени (если задан)
            }

            Если не copy() а с ссылкой, то вызывающий код мог бы случайно изменить внутренний кэш:
        """
        return self.latest_data.copy()


# Запуск цикла опроса
    async def start_polling(self, name: str, node_ids: List[str], interval: float = 1.0) -> None:
        """
        Запустить именованный цикл опроса тегов.
        Args:
            name: Уникальное имя цикла.
                Пример: "fast", "slow", "diagnostics"
            node_ids: Список адресов узлов для опроса.
                Пример: ["ns=2;s=Temperature", "ns=2;s=Pressure"]
            interval: Интервал опроса в секундах (по умолчанию 1.0).
        Raises:
            ConnectionError: Не подключены к серверу.
        Пример использования:
            await worker.start_polling("fast", ["ns=2;s=Temp", "ns=2;s=Press"], interval=0.2)
            await worker.start_polling("slow", ["ns=2;s=Status"], interval=5.0)
        """
        # Проверка подключения
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")
        # Если цикл с таким именем уже существует — останавливаем старый
        # перед запуском нового (защита от дублей, см. объяснение выше)
        if name in self._poll_loops:
            await self.stop_polling(name)
        # Создаём запись в реестре с параметрами цикла
        loop_info: Dict[str, Any] = {
            "nodes": node_ids,        
            "interval": interval,     
            "active": True,           
            "task": None,
            }
        # Запускаем asyncio.Task — цикл работает в фоне event loop
        loop_info["task"] = asyncio.ensure_future(self._poll_loop(name))
        # Сохраняем в реестр
        self._poll_loops[name] = loop_info
        # Пишем в лог
        logger.info(f"Poll '{name}' started: {len(node_ids)} nodes, interval={interval}s")

# Остановка цикла опроса
    async def stop_polling(self, name: Optional[str] = None) -> None:
        """
        Остановить цикл(ы) опроса.
        Args:
            name: Имя цикла для остановки.
                - "fast" — остановить только цикл "fast"
                - None   — остановить ВСЕ циклы (используется в disconnect())
        """
        if name is not None:
            # Останавливаем ОДИН конкретный цикл
            await self._stop_single_poll(name)
        else:
            # Останавливаем ВСЕ циклы — копируем список имён,
            # т.к. _stop_single_poll() удаляет из dict во время итерации
            names = list(self._poll_loops.keys())
            for loop_name in names:
                await self._stop_single_poll(loop_name)

# Остановка цикла опроса(внутренний метод)
    async def _stop_single_poll(self, name: str) -> None:
        """
        Остановить один именованный цикл.
        Args:
            name: Имя цикла для остановки.
        """
        # Если цикла с таким именем нет — ничего делать не нужно
        if name not in self._poll_loops:
            return

        loop_info = self._poll_loops[name]
        # Сбрасываем флаг — _poll_loop() проверяет его на каждой итерации
        loop_info["active"] = False
        # Отменяем Task — прерывает await asyncio.sleep() или await read_multiple_nodes()
        task = loop_info["task"]
        if task and not task.done():
            task.cancel()
            try:
                # Ждём завершения Task
                await task
            except asyncio.CancelledError:
                # Ожидаемое исключение — Task был отменён, всё штатно
                pass
        # Удаляем из реестра — цикл завершён, запись больше не нужна
        del self._poll_loops[name]
        logger.info(f"Poll '{name}' stopped")

# Цикл опроса
    async def _poll_loop(self, name: str) -> None:
        """
        Внутренний цикл опроса для одного именованного poll loop.
        Каждую итерацию:
          1. Берёт параметры (nodes, interval) из self._poll_loops[name]
          2. Читает все теги через read_multiple_nodes() (параллельно)
          3. Вызывает on_data_changed callback для каждого изменённого тега
          4. Ждёт interval секунд
          5. Повторяет
        Args:
            name: Имя цикла — ключ в self._poll_loops.
        """
        try:
            # Получаем параметры цикла из реестра
            loop_info = self._poll_loops.get(name)
            if not loop_info:
                return

            while loop_info["active"]:
                try:
                    # Читаем все теги за один вызов (параллельно через gather)
                    data = await self.read_multiple_nodes(loop_info["nodes"])
                    # Вызываем callback для каждого успешно прочитанного тега.
                    # None означает ошибку чтения — такие теги пропускаем.
                    for node_id, value in data.items():
                        if value is not None and self.on_data_changed:
                            self.on_data_changed(node_id, value)

                except ConnectionError:
                    # Соединение потеряно
                    logger.error(f"Poll '{name}': connection lost")
                    loop_info["active"] = False
                    # Если auto-reconnect включён — запускаем переподключение
                    if self._auto_reconnect:
                        await self._start_reconnect_loop()
                    break
                except Exception as e:
                    # Непредвиденная ошибка — логируем, но НЕ останавливаем цикл.
                    logger.error(f"Poll '{name}' error: {e}")

                # Пауза между итерациями
                await asyncio.sleep(loop_info["interval"])

        except asyncio.CancelledError:
            # Task был отменён через stop_polling() — штатное завершение
            logger.info(f"Poll '{name}' cancelled")

# Запрос информации об активных циклах
    def get_active_polls(self) -> Dict[str, Dict[str, Any]]:
        """
        Получить информацию о всех активных poll loop'ах.

        Returns:
            Словарь {name: {"nodes": [...], "interval": float}}
            Пример: {
                "fast": {"nodes": ["ns=2;s=Temp"], "interval": 0.2},
                "slow": {"nodes": ["ns=2;s=Status"], "interval": 5.0}
            }
        """
        return {
            name: {"nodes": info["nodes"], "interval": info["interval"]}
            for name, info in self._poll_loops.items()
            if info["active"]
        }

# ==================== Browse — обзор дерева сервера ====================
# Позволяет обнаружить доступные узлы без знания их node_id заранее.

    async def browse_nodes(self, start_node_id: Optional[str] = None, depth: int = 1) -> List[Dict[str, Any]]:
        """
        Обзор дочерних узлов на OPC UA сервере.

        Позволяет обнаружить доступные переменные без знания node_id заранее.
        По умолчанию начинает с корня — Objects (i=85).

        Args:
            start_node_id: Узел, с которого начать обзор.
                None — начать с Objects (корень всех пользовательских данных).
                "ns=2;s=MyFolder" — начать с конкретной папки.
            depth: Глубина рекурсии (1 = только дочерние, 2 = дочерние + их дочерние).

        Returns:
            Список узлов, каждый — словарь с информацией:
            [
                {
                    "node_id": "ns=2;s=Temperature",
                    "name": "Temperature",
                    "node_class": "Variable",     # Variable, Object, Method
                    "children": [...]              # дочерние узлы (если depth > 1)
                },
                ...
            ]

        Raises:
            ConnectionError: Не подключены к серверу.
            RuntimeError: Ошибка при обзоре.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")

        try:
            # Определяем стартовый узел
            if start_node_id:
                # Пользователь указал конкретный узел
                start = self.client.get_node(start_node_id)
            else:
                # По умолчанию — Objects (i=85), корень пользовательских данных.
                # Не путать с Root (i=84) — он содержит системные папки.
                start = self.client.get_objects_node()

            return await self._browse_recursive(start, depth)

        except Exception as e:
            raise RuntimeError(f"Failed to browse nodes: {e}")

    async def _browse_recursive(self, node: Node, depth: int) -> List[Dict[str, Any]]:
        """
        Рекурсивный обход дочерних узлов.

        Args:
            node: Узел, дочерние элементы которого нужно получить.
            depth: Оставшаяся глубина рекурсии.
        """
        result = []
        # Получаем список дочерних узлов от сервера
        children = await node.get_children()

        for child in children:
            # Читаем метаданные узла
            node_class = await child.read_node_class()
            name = await child.read_display_name()

            info: Dict[str, Any] = {
                "node_id": str(child.nodeid),
                "name": name.Text,
                # NodeClass: Variable=2, Object=1, Method=4
                "node_class": node_class.name if hasattr(node_class, 'name') else str(node_class),
            }

            # Если глубина > 1 и это Object (папка) — рекурсивно обходим дочерние
            if depth > 1 and node_class == ua.NodeClass.Object:
                info["children"] = await self._browse_recursive(child, depth - 1)
            else:
                info["children"] = []

            result.append(info)

        return result

# ==================== Read Node Info — чтение с метаданными ====================
# В отличие от read_node(), возвращает не только значение, но и timestamp, quality, тип.

    async def read_node_info(self, node_id: str) -> Dict[str, Any]:
        """
        Расширенное чтение узла — значение + метаданные.

        В отличие от read_node() (только значение), возвращает полную информацию:
        timestamp, quality (Good/Bad), тип данных.

        Args:
            node_id: Адрес узла ("ns=2;s=Temperature")

        Returns:
            Словарь с полной информацией:
            {
                "node_id": "ns=2;s=Temperature",
                "value": 24.1,
                "source_timestamp": datetime(2024, 1, 15, 10, 30, 45),
                "server_timestamp": datetime(2024, 1, 15, 10, 30, 45),
                "status_code": "Good",
                "data_type": "Float"
            }

        Raises:
            ConnectionError: Не подключены к серверу.
            RuntimeError: Узел не найден.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")

        try:
            node = self.client.get_node(node_id)
            # read_data_value() возвращает DataValue — полную структуру с метаданными.
            # В отличие от read_value() который возвращает только значение.
            data_value = await node.read_data_value()

            # Извлекаем метаданные из DataValue
            result: Dict[str, Any] = {
                "node_id": node_id,
                # Само значение переменной
                "value": data_value.Value.Value if data_value.Value else None,
                # Когда PLC/датчик зафиксировал значение
                "source_timestamp": data_value.SourceTimestamp,
                # Когда OPC UA сервер отправил значение
                "server_timestamp": data_value.ServerTimestamp,
                # Качество данных: "Good" = норма, "Bad..." = проблема с датчиком/PLC
                "status_code": str(data_value.StatusCode_.name)
                    if hasattr(data_value.StatusCode_, 'name')
                    else str(data_value.StatusCode_),
            }

            # Пробуем получить тип данных узла
            try:
                data_type = await node.read_data_type_as_variant_type()
                result["data_type"] = data_type.name if hasattr(data_type, 'name') else str(data_type)
            except Exception:
                result["data_type"] = "Unknown"

            # Обновляем кэш
            if result["value"] is not None:
                self.latest_data[node_id] = result["value"]

            return result

        except Exception as e:
            raise RuntimeError(f"Failed to read node info {node_id}: {e}")

# ==================== Auto-Reconnect ====================
# Автоматическое переподключение при обрыве связи.
# При успехе восстанавливает подписки и poll loop'ы.

    async def _start_reconnect_loop(self) -> None:
        """
        Запустить цикл автоматического переподключения.

        Вызывается внутренне при обнаружении обрыва связи.
        Сохраняет текущие подписки и poll loop'ы,
        затем пытается переподключиться с восстановлением.
        """
        # Если reconnect уже запущен — не дублируем
        if self._reconnect_task and not self._reconnect_task.done():
            return

        # Сохраняем текущие подписки для восстановления после reconnect.
        # subscribed_tags: {"ns=2;s=Temperature": handle} → сохраняем node_id + tag_name
        self._saved_subscriptions = {}
        for node_id in list(self.subscribed_tags.keys()):
            # Пробуем найти сохранённое имя тега
            tag_name = self.latest_data.get(f"{node_id}_name")
            self._saved_subscriptions[node_id] = tag_name

        # Сохраняем параметры poll loop'ов
        self._saved_polls = {}
        for name, info in self._poll_loops.items():
            self._saved_polls[name] = {
                "nodes": info["nodes"],
                "interval": info["interval"]
            }

        # Запускаем цикл reconnect в фоне
        self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """
        Внутренний цикл переподключения.

        Пытается переподключиться с заданным интервалом.
        При успехе восстанавливает все подписки и poll loop'ы.
        """
        attempt = 0
        try:
            while True:
                attempt += 1
                # Проверяем лимит попыток (0 = бесконечно)
                if self._max_reconnect_attempts > 0 and attempt > self._max_reconnect_attempts:
                    logger.error(f"Reconnect: max attempts ({self._max_reconnect_attempts}) reached, giving up")
                    break

                logger.info(f"Reconnect attempt {attempt}...")

                try:
                    # Очищаем старое соединение
                    self.client = None
                    self.subscription = None
                    self.handler = None
                    self._connected = False
                    self.subscribed_tags.clear()

                    # Пробуем подключиться заново
                    await self.connect()
                    logger.info(f"Reconnect: connected after {attempt} attempt(s)")

                    # Восстанавливаем подписки
                    for node_id, tag_name in self._saved_subscriptions.items():
                        try:
                            await self.subscribe_tag(node_id, tag_name)
                            logger.info(f"Reconnect: restored subscription {node_id}")
                        except Exception as e:
                            logger.error(f"Reconnect: failed to restore subscription {node_id}: {e}")

                    # Восстанавливаем poll loop'ы
                    for name, params in self._saved_polls.items():
                        try:
                            await self.start_polling(name, params["nodes"], params["interval"])
                            logger.info(f"Reconnect: restored poll '{name}'")
                        except Exception as e:
                            logger.error(f"Reconnect: failed to restore poll '{name}': {e}")

                    # Очищаем сохранённые данные — восстановление завершено
                    self._saved_subscriptions.clear()
                    self._saved_polls.clear()
                    return  # Успех — выходим из цикла

                except Exception as e:
                    logger.warning(f"Reconnect attempt {attempt} failed: {e}")

                # Пауза перед следующей попыткой
                await asyncio.sleep(self._reconnect_interval)

        except asyncio.CancelledError:
            logger.info("Reconnect loop cancelled")

    async def trigger_reconnect(self) -> None:
        """
        Вручную запустить переподключение.

        Полезно когда вышестоящий код обнаружил обрыв связи
        (например, poll loop получил ConnectionError).
        """
        if not self._auto_reconnect:
            logger.warning("Auto-reconnect is disabled")
            return
        await self._start_reconnect_loop()

    async def stop_reconnect(self) -> None:
        """
        Остановить цикл переподключения.
        """
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        self._reconnect_task = None

# ==================== Node Cache — кэширование объектов Node ====================
# client.get_node() каждый раз создаёт новый объект Node (парсинг строки).
# Для hot path (poll loop каждые 200мс, частые read/write) это лишняя работа.
# Кэш хранит Node-объекты по строковому node_id.
# Очищается при disconnect() — Node привязан к конкретному Client.

    def _get_cached_node(self, node_id: str) -> Node:
        """
        Получить объект Node из кэша или создать и закэшировать.

        Используется внутренне вместо client.get_node() во всех методах
        read/write для избежания повторного парсинга строки node_id.

        Args:
            node_id: Строковый адрес узла ("ns=2;s=Temperature")

        Returns:
            Node — объект-указатель на узел OPC UA сервера.
        """
        if node_id not in self._node_cache:
            self._node_cache[node_id] = self.client.get_node(node_id)
        return self._node_cache[node_id]

    def clear_node_cache(self) -> None:
        """
        Очистить кэш Node-объектов.

        Полезно если структура сервера изменилась (узлы добавлены/удалены).
        При disconnect() кэш очищается автоматически.
        """
        count = len(self._node_cache)
        self._node_cache.clear()
        logger.info(f"Node cache cleared ({count} entries)")

    def get_node_cache_size(self) -> int:
        """Получить количество закэшированных Node-объектов."""
        return len(self._node_cache)

# ==================== History Read — чтение исторических данных ====================
# OPC UA серверы с Historian хранят архив значений переменных.
# Позволяет получить данные за любой период (графики, отчёты, тренды).
#
# Не все серверы поддерживают History Read — зависит от конфигурации.
# Типичные серверы с Historian: Kepware, Prosys, Unified Automation.

    async def read_history(
        self,
        node_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        num_values: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Чтение исторических данных переменной за период.

        Args:
            node_id: Адрес узла ("ns=2;s=Temperature").
                Узел должен быть Historizing=True на сервере.

            start_time: Начало периода (UTC).
                None — за последний час.
                Пример: datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

            end_time: Конец периода (UTC).
                None — текущее время.
                Пример: datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc)

            num_values: Максимальное число значений.
                0 — все значения за период (сервер определяет лимит).
                100 — не более 100 точек (для графиков с фиксированным разрешением).

        Returns:
            Список значений с метками времени:
            [
                {"timestamp": datetime(...), "value": 24.1, "status": "Good"},
                {"timestamp": datetime(...), "value": 24.3, "status": "Good"},
                ...
            ]

        Raises:
            ConnectionError: Не подключены к серверу.
            RuntimeError: Узел не поддерживает историю или ошибка сервера.

        Пример:
            # Последний час
            data = await worker.read_history("ns=2;s=Temperature")

            # Конкретный период
            from datetime import datetime, timezone
            data = await worker.read_history(
                "ns=2;s=Temperature",
                start_time=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
            )
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")

        try:
            node = self._get_cached_node(node_id)

            # Значения по умолчанию: последний час
            if end_time is None:
                end_time = datetime.now(timezone.utc)
            if start_time is None:
                start_time = end_time - timedelta(hours=1)

            # read_raw_history() — метод asyncua для чтения исторических данных.
            # Возвращает список DataValue (значение + timestamp + quality).
            # numvalues=0 означает "все значения за период" (лимит определяет сервер).
            history = await node.read_raw_history(
                starttime=start_time,
                endtime=end_time,
                numvalues=num_values,
            )

            # Преобразуем DataValue в словари
            result = []
            for data_value in history:
                result.append({
                    "timestamp": data_value.SourceTimestamp,
                    "value": data_value.Value.Value if data_value.Value else None,
                    "status": str(data_value.StatusCode_.name)
                        if hasattr(data_value.StatusCode_, 'name')
                        else str(data_value.StatusCode_),
                })

            logger.info(f"History read: {node_id}, {len(result)} values "
                        f"({start_time} to {end_time})")
            return result

        except Exception as e:
            raise RuntimeError(f"Failed to read history for {node_id}: {e}")

    async def read_history_multiple(
        self,
        node_ids: List[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        num_values: int = 0,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Пакетное чтение истории нескольких переменных ПАРАЛЛЕЛЬНО.

        Args:
            node_ids: Список адресов узлов.
            start_time: Начало периода (None = час назад).
            end_time: Конец периода (None = сейчас).
            num_values: Макс. число значений на узел (0 = все).

        Returns:
            Словарь {node_id: [history_values]}.
            Пример: {
                "ns=2;s=Temp": [{"timestamp": ..., "value": 24.1}, ...],
                "ns=2;s=Press": [{"timestamp": ..., "value": 101.3}, ...]
            }
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")

        raw_results = await asyncio.gather(
            *[self.read_history(nid, start_time, end_time, num_values)
              for nid in node_ids],
            return_exceptions=True,
        )

        results = {}
        for node_id, result in zip(node_ids, raw_results):
            if isinstance(result, Exception):
                results[node_id] = []
                logger.error(f"History read error for {node_id}: {result}")
            else:
                results[node_id] = result
        return results

# ==================== Method Call — вызов методов на сервере (RPC) ====================
# OPC UA методы — это функции на сервере, которые можно вызвать удалённо.
# Примеры: "StartPump", "StopMotor", "ResetAlarm", "Calibrate".
#
# Метод принадлежит родительскому узлу (Object):
#   Objects → MyDevice → StartPump()
#   parent_node_id = "ns=2;s=MyDevice", method_node_id = "ns=2;s=StartPump"

    async def call_method(
        self,
        parent_node_id: str,
        method_node_id: str,
        args: Optional[List[Any]] = None,
    ) -> Any:
        """
        Вызвать метод на OPC UA сервере (Remote Procedure Call).

        Args:
            parent_node_id: Адрес родительского узла (Object), которому принадлежит метод.
                Пример: "ns=2;s=MyDevice"
                В дереве сервера метод — дочерний элемент Object'а.

            method_node_id: Адрес самого метода.
                Пример: "ns=2;s=StartPump"

            args: Список аргументов для метода.
                None — метод без аргументов (например "ResetAlarm").
                [25.5] — один аргумент (например "SetTemperature(25.5)").
                [1, True, "auto"] — несколько аргументов.
                Типы должны совпадать с сигнатурой метода на сервере.

        Returns:
            Результат выполнения метода (тип зависит от метода).
            None если метод не возвращает значение.
            Пример: True (успех), 42 (код результата), "OK" (строка).

        Raises:
            ConnectionError: Не подключены к серверу.
            RuntimeError: Метод не найден, неверные аргументы, ошибка выполнения.

        Пример:
            # Без аргументов
            await worker.call_method("ns=2;s=Pump1", "ns=2;s=Start")

            # С аргументами
            result = await worker.call_method(
                "ns=2;s=Oven1",
                "ns=2;s=SetTemperature",
                args=[ua.Variant(250.0, ua.VariantType.Float)]
            )
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")

        try:
            parent = self._get_cached_node(parent_node_id)
            method = self._get_cached_node(method_node_id)

            # call_method() — метод asyncua для вызова OPC UA Method.
            # Параметры:
            #   methodid — Node метода (или строковый node_id)
            #   *args — аргументы метода
            if args:
                result = await parent.call_method(method, *args)
            else:
                result = await parent.call_method(method)

            logger.info(f"Method called: {method_node_id} on {parent_node_id}, result={result}")
            return result

        except Exception as e:
            raise RuntimeError(
                f"Failed to call method {method_node_id} on {parent_node_id}: {e}"
            )

    async def discover_methods(self, object_node_id: str) -> List[Dict[str, Any]]:
        """
        Обнаружить доступные методы на объекте.

        Полезно для исследования: какие методы есть у устройства.

        Args:
            object_node_id: Адрес Object-узла.
                Пример: "ns=2;s=MyDevice"

        Returns:
            Список методов:
            [
                {"node_id": "ns=2;s=Start", "name": "Start"},
                {"node_id": "ns=2;s=Stop", "name": "Stop"},
            ]
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")

        try:
            parent = self._get_cached_node(object_node_id)
            children = await parent.get_children()

            methods = []
            for child in children:
                node_class = await child.read_node_class()
                # ua.NodeClass.Method (4) — это метод
                if node_class == ua.NodeClass.Method:
                    name = await child.read_display_name()
                    methods.append({
                        "node_id": str(child.nodeid),
                        "name": name.Text,
                    })

            return methods

        except Exception as e:
            raise RuntimeError(f"Failed to discover methods on {object_node_id}: {e}")

# ==================== Event Subscription — подписка на события ====================
# OPC UA Events — уведомления о событиях на сервере.
# В отличие от Data Change (значение изменилось), Events — это разовые уведомления:
#   - Alarm triggered (авария сработала)
#   - Condition changed (состояние изменилось)
#   - System event (перезагрузка, ошибка)
#
# Цепочка: Сервер генерирует Event → asyncua доставляет → EventHandler → callback

    class _EventHandler:
        """Внутренний обработчик OPC UA событий."""
        def __init__(self, callback: Optional[Callable[[Dict[str, Any]], None]] = None):
            self.callback = callback

        def event_notification(self, event):
            """
            Вызывается автоматически asyncua при получении события.

            Args:
                event: Объект события от asyncua.
                    Содержит поля: SourceName, Message, Severity, Time и др.
            """
            if not self.callback:
                return
            # Преобразуем event в словарь для удобства
            event_dict = {
                "source": str(getattr(event, 'SourceName', 'Unknown')),
                "message": str(getattr(event, 'Message', '')),
                "severity": int(getattr(event, 'Severity', 0)),
                "time": getattr(event, 'Time', None),
                "event_type": str(getattr(event, 'EventType', 'Unknown')),
            }
            self.callback(event_dict)

    async def subscribe_events(
        self,
        source_node_id: Optional[str] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> bool:
        """
        Подписаться на события (аварии, условия, системные уведомления).

        Args:
            source_node_id: Узел-источник событий.
                None — подписка на Server object (i=2085, все события).
                "ns=2;s=MyDevice" — события конкретного устройства.

            event_callback: Функция-обработчик событий.
                Принимает один аргумент — словарь с полями события:
                {
                    "source": "PLC1",
                    "message": "Temperature alarm triggered",
                    "severity": 500,        # 0-1000 (0=info, 1000=critical)
                    "time": datetime(...),
                    "event_type": "AlarmConditionType"
                }

        Returns:
            True если подписка создана.

        Raises:
            ConnectionError: Не подключены.
            RuntimeError: Ошибка подписки.

        Пример:
            def on_event(event):
                print(f"ALARM: {event['message']} (severity={event['severity']})")

            await worker.subscribe_events(
                source_node_id="ns=2;s=PLC1",
                event_callback=on_event
            )
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to OPC UA server")

        try:
            # Сохраняем callback для событий
            if event_callback:
                self._on_event = event_callback

            # Определяем источник событий
            if source_node_id:
                source = self._get_cached_node(source_node_id)
            else:
                # Server object — получаем все события сервера
                source = self.client.get_node(ua.ObjectIds.Server)

            # Создаём обработчик событий
            handler = self._EventHandler(callback=self._on_event)

            # Создаём подписку на события
            sub = await self.client.create_subscription(500, handler)
            handle = await sub.subscribe_events(source)

            # Сохраняем handle для возможности отписки
            key = source_node_id or "server"
            self._event_subscriptions[key] = handle
            logger.info(f"Event subscription created for: {key}")
            return True

        except Exception as e:
            raise RuntimeError(f"Failed to subscribe to events: {e}")

    async def unsubscribe_events(self, source_node_id: Optional[str] = None) -> bool:
        """
        Отписаться от событий.

        Args:
            source_node_id: Источник событий для отписки.
                None — отписка от Server object.
        """
        key = source_node_id or "server"
        if key in self._event_subscriptions:
            del self._event_subscriptions[key]
            logger.info(f"Event subscription removed: {key}")
        return True

# ==================== Connection Watchdog — проверка живости соединения ====================
# Периодически отправляет запрос серверу (heartbeat) для обнаружения обрыва.
# Без watchdog обрыв обнаруживается только при следующем read/write (может быть поздно).
# С watchdog — обрыв обнаруживается через watchdog_interval секунд.

    async def start_watchdog(self, interval: float = 5.0) -> None:
        """
        Запустить проверку живости соединения (heartbeat).

        Периодически читает статус сервера (ServerStatus).
        При обнаружении обрыва — останавливается и запускает auto-reconnect.

        Args:
            interval: Интервал проверки в секундах (по умолчанию 5.0).
                Меньше = быстрее обнаружение обрыва, но больше нагрузка.
                Рекомендуется: 3-10 секунд.

        Пример:
            await worker.connect()
            await worker.start_watchdog(interval=3.0)
        """
        # Останавливаем предыдущий watchdog если есть
        await self.stop_watchdog()

        self._watchdog_interval = interval
        self._watchdog_task = asyncio.ensure_future(self._watchdog_loop())
        logger.info(f"Watchdog started (interval={interval}s)")

    async def stop_watchdog(self) -> None:
        """Остановить watchdog."""
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        self._watchdog_task = None

    async def _watchdog_loop(self) -> None:
        """
        Внутренний цикл watchdog.

        Каждые N секунд читает ServerStatus (i=2256) — стандартный узел,
        который есть на ВСЕХ OPC UA серверах. Если чтение падает —
        соединение потеряно.
        """
        try:
            while self.is_connected:
                try:
                    # ServerStatus (i=2256) — стандартный узел, всегда доступен.
                    # Читаем CurrentTime (i=2258) — самый легковесный запрос.
                    server_time_node = self.client.get_node(ua.ObjectIds.Server_ServerStatus_CurrentTime)
                    await server_time_node.read_value()
                    # Сервер ответил — соединение живое

                except Exception as e:
                    # Сервер не ответил — соединение потеряно
                    logger.error(f"Watchdog: connection lost ({e})")
                    self._connected = False

                    # Запускаем auto-reconnect если включён
                    if self._auto_reconnect:
                        await self._start_reconnect_loop()
                    break

                await asyncio.sleep(self._watchdog_interval)

        except asyncio.CancelledError:
            logger.info("Watchdog cancelled")

    @property
    def is_watchdog_active(self) -> bool:
        """Проверить, запущен ли watchdog."""
        return self._watchdog_task is not None and not self._watchdog_task.done()

# ==================== Diagnostics / Stats — статистика и диагностика ====================
# Счётчики операций для мониторинга, отладки и dashboards.

    def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику работы клиента.

        Returns:
            Словарь со счётчиками:
            {
                "reads": 1500,            # успешных чтений
                "writes": 42,             # успешных записей
                "read_errors": 3,         # ошибок чтения
                "write_errors": 0,        # ошибок записи
                "reconnects": 1,          # переподключений
                "last_read_ms": 12.5,     # latency последнего чтения
                "last_write_ms": 8.3,     # latency последней записи
                "connected_at": datetime, # когда подключились
                "total_uptime_s": 3600.0, # общее время подключения
                "current_uptime_s": 120.0,# текущая сессия
                "node_cache_size": 25,    # узлов в кэше
                "active_polls": 2,        # активных poll loop'ов
                "subscribed_tags": 10,    # подписанных тегов
                "is_connected": True,     # текущий статус
                "is_watchdog_active": True # watchdog запущен
            }

        Пример:
            stats = worker.get_stats()
            print(f"Reads: {stats['reads']}, Latency: {stats['last_read_ms']}ms")
        """
        stats = self._stats.copy()

        # Добавляем вычисляемые поля
        if self._stats["connected_at"]:
            stats["current_uptime_s"] = round(
                (datetime.now(timezone.utc) - self._stats["connected_at"]).total_seconds(), 1
            )
        else:
            stats["current_uptime_s"] = 0.0

        stats["node_cache_size"] = len(self._node_cache)
        stats["active_polls"] = len([p for p in self._poll_loops.values() if p["active"]])
        stats["subscribed_tags"] = len(self.subscribed_tags)
        stats["is_connected"] = self.is_connected
        stats["is_watchdog_active"] = self.is_watchdog_active

        return stats

    def reset_stats(self) -> None:
        """
        Сбросить все счётчики статистики.

        Не сбрасывает connected_at и total_uptime_s — они привязаны к сессии.
        """
        self._stats["reads"] = 0
        self._stats["writes"] = 0
        self._stats["read_errors"] = 0
        self._stats["write_errors"] = 0
        self._stats["reconnects"] = 0
        self._stats["last_read_ms"] = 0.0
        self._stats["last_write_ms"] = 0.0
        logger.info("Stats counters reset")

# ==================== Config Export/Import — сохранение конфигурации ====================
# Сохраняет/загружает параметры подключения, подписки, poll loop'ы в JSON-файл.
# Полезно для: сохранение настроек между запусками, миграция конфигурации,
# шаблоны подключений для разных серверов.

    def export_config(self, file_path: str) -> None:
        """
        Экспортировать текущую конфигурацию в JSON-файл.

        Сохраняет:
          - Параметры подключения (endpoint, namespace, timeout)
          - Security (username — без пароля!, certificate paths)
          - Подписанные теги
          - Параметры poll loop'ов
          - Настройки auto-reconnect

        ВАЖНО: Пароль и закрытый ключ НЕ сохраняются в файл (безопасность).

        Args:
            file_path: Путь к файлу для сохранения.
                Пример: "config/plc1_config.json"

        Пример:
            worker.export_config("config/opc_config.json")
        """
        config = {
            # Параметры подключения
            "endpoint": self.endpoint,
            "namespace": self.namespace,
            "timeout": self.timeout,

            # Security (без пароля и закрытого ключа!)
            "username": self._username,
            # password — НЕ сохраняем (безопасность)
            "certificate_path": self._certificate_path,
            # private_key_path — НЕ сохраняем (безопасность)
            "security_policy": self._security_policy,
            "security_mode": self._security_mode,

            # Подписанные теги
            "subscribed_tags": list(self.subscribed_tags.keys()),
            # Маппинг имён тегов
            "tag_names": {
                node_id: self.latest_data.get(f"{node_id}_name")
                for node_id in self.subscribed_tags.keys()
                if self.latest_data.get(f"{node_id}_name")
            },

            # Poll loop'ы
            "poll_loops": {
                name: {"nodes": info["nodes"], "interval": info["interval"]}
                for name, info in self._poll_loops.items()
            },

            # Auto-reconnect
            "auto_reconnect": self._auto_reconnect,
            "reconnect_interval": self._reconnect_interval,
            "max_reconnect_attempts": self._max_reconnect_attempts,
        }

        # Создаём папку если не существует
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Записываем JSON с отступами для читаемости
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"Config exported to {file_path}")

    @classmethod
    def from_config(cls, file_path: str, password: Optional[str] = None,
                    private_key_path: Optional[str] = None,
                    on_data_changed: Optional[Callable] = None) -> "AsyncOpcUaWorker":
        """
        Создать AsyncOpcUaWorker из JSON-файла конфигурации.

        Args:
            file_path: Путь к JSON-файлу (созданному через export_config()).
            password: Пароль для аутентификации (не хранится в файле).
            private_key_path: Путь к закрытому ключу (не хранится в файле).
            on_data_changed: Callback для изменений данных.

        Returns:
            Настроенный экземпляр AsyncOpcUaWorker (не подключённый).
            Нужно вызвать await worker.connect() после создания.

        Пример:
            worker = AsyncOpcUaWorker.from_config(
                "config/opc_config.json",
                password="secret123",
                private_key_path="certs/key.pem"
            )
            await worker.connect()

            # Восстановить подписки из конфига
            await worker.restore_from_config("config/opc_config.json")
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        worker = cls(
            endpoint=config["endpoint"],
            namespace=config.get("namespace", 2),
            timeout=config.get("timeout", 10.0),
            on_data_changed=on_data_changed,
            username=config.get("username"),
            password=password,
            certificate_path=config.get("certificate_path"),
            private_key_path=private_key_path,
            security_policy=config.get("security_policy"),
            security_mode=config.get("security_mode"),
            auto_reconnect=config.get("auto_reconnect", False),
            reconnect_interval=config.get("reconnect_interval", 5.0),
            max_reconnect_attempts=config.get("max_reconnect_attempts", 0),
        )

        logger.info(f"Worker created from config: {file_path}")
        return worker

    async def restore_from_config(self, file_path: str) -> Dict[str, Any]:
        """
        Восстановить подписки и poll loop'ы из конфиг-файла.

        Вызывать ПОСЛЕ connect(). Читает конфиг и пересоздаёт:
          - Подписки на теги (subscribe_tag)
          - Poll loop'ы (start_polling)

        Args:
            file_path: Путь к JSON-файлу конфигурации.

        Returns:
            Результат восстановления:
            {
                "subscriptions_restored": 10,
                "subscriptions_failed": 0,
                "polls_restored": 2,
                "polls_failed": 0,
            }
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        result = {
            "subscriptions_restored": 0,
            "subscriptions_failed": 0,
            "polls_restored": 0,
            "polls_failed": 0,
        }

        # Восстанавливаем подписки
        tag_names = config.get("tag_names", {})
        for node_id in config.get("subscribed_tags", []):
            try:
                tag_name = tag_names.get(node_id)
                await self.subscribe_tag(node_id, tag_name)
                result["subscriptions_restored"] += 1
            except Exception as e:
                result["subscriptions_failed"] += 1
                logger.error(f"Failed to restore subscription {node_id}: {e}")

        # Восстанавливаем poll loop'ы
        for name, params in config.get("poll_loops", {}).items():
            try:
                await self.start_polling(name, params["nodes"], params["interval"])
                result["polls_restored"] += 1
            except Exception as e:
                result["polls_failed"] += 1
                logger.error(f"Failed to restore poll '{name}': {e}")

        logger.info(f"Config restored from {file_path}: {result}")
        return result
