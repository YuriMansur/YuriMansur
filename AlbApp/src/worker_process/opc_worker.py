"""
opc_worker.py — OPC UA оркестрация рабочего процесса (Qt-free).

Подключение к серверу, подписка на «редкие» теги (кнопки, уставка), активный
опрос массивов, запись команд из GUI и авто-переподключение. Данные скармливает
кольцевым процессорам (RingProc) и пересылает в GUI через live_q.

Конфигурация (сервер, теги, polls, logging) читается из servers.json рядом с
этим модулем. NodeId собирается из ns сервера и пути тега: ns=<ns>;s=<base><имя>.
"""

import asyncio
import json
import re
import queue as _queue
from pathlib import Path

from asyncua import Client, ua

from worker_process.ring_buffer import RingProc

# servers.json подкладывается в AlbApp/patch (src/worker_process → AlbApp)
_CONFIG_PATH = Path(__file__).parents[2] / "patch" / "servers.json"


def _node_id(ns: int, path: str) -> str:
    return f"ns={ns};s={path}"


def load_config() -> list[dict]:
    """Прочитать servers.json и разрешить имена тегов в NodeId."""
    raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    servers: list[dict] = []
    for srv in raw.get("servers", []):
        name = srv["name"]
        ns = srv.get("ns", 0)
        # Общий префикс пути узла (чтобы не повторять его в каждом теге).
        base = srv.get("base", "")
        # tags — либо список коротких имён (путь = base + имя), либо словарь
        # {имя: путь-суффикс} (путь = base + суффикс) для нестандартных тегов.
        raw_tags = srv.get("tags", {})
        items = ({n: n for n in raw_tags} if isinstance(raw_tags, list) else raw_tags)
        tags = {n: _node_id(ns, base + suffix) for n, suffix in items.items()}

        def resolve(tag: str, _name=name, _tags=tags) -> str:
            
            if tag not in _tags:
                raise ValueError(f"Сервер {_name}: тег '{tag}' не найден в секции 'tags'")
            return _tags[tag]

        # Блок logging описывает кольцевые потоки (ring) с индексом index_tag.
        log = srv.get("logging")
        logging_cfg = None
        if log:
            logging_cfg = {
                "index":      resolve(log["index_tag"]),
                "array_size": log.get("array_size", 50),
                "ring": [
                    {
                        "node":               resolve(r["tag"]),
                        "measurement":        r["measurement"],
                        "points_msg":         r.get("points_msg", r["measurement"]),
                        "raw_array_msg":      r.get("raw_array_msg"),
                        "scalar_node":        resolve(r["scalar"]) if r.get("scalar") else None,
                        "scalar_measurement": r.get("scalar_measurement"),
                        "scalar_msg":         r.get("scalar_msg"),
                    }
                    for r in log.get("ring", [])
                ],
            }

        servers.append({
            "name":               name,
            "endpoint":           srv["endpoint"],
            "auto_reconnect":     srv.get("auto_reconnect", True),
            "reconnect_interval": srv.get("reconnect_interval", 5),
            "tags":               tags,
            "subscribe":          [resolve(t) for t in srv.get("subscribe", [])],
            "polls": [
                {
                    "name":       p["name"],
                    "interval":   p.get("interval", 1.0),
                    "sequential": p.get("sequential", False),
                    "nodes":      [resolve(t) for t in p.get("tags", [])],
                }
                for p in srv.get("polls", [])
            ],
            "logging": logging_cfg,
        })
    return servers


# Рабочий процесс ведёт один сервер. Весь worker-side конфиг читается здесь.
_SRV = load_config()[0]
OPC_ENDPOINT       = _SRV["endpoint"]
OPC_SERVER_ID      = _SRV["name"]
RECONNECT_INTERVAL = _SRV["reconnect_interval"]   # секунд до следующей попытки
_POLL              = _SRV["polls"][0]
POLL_INTERVAL      = _POLL["interval"]            # секунд между опросами массивов
POLL_NIDS          = _POLL["nodes"]               # порядок: cc, затем массивы
SUBSCRIBE_NIDS     = _SRV["subscribe"]            # кнопки + уставка
_LOGGING           = _SRV["logging"]              # описание кольцевых потоков

# arr_node → тип сообщения для отправки «сырого» массива в GUI (если задан)
RAW_ARRAY_MAP = {r["node"]: r["raw_array_msg"]
                 for r in _LOGGING["ring"] if r.get("raw_array_msg")}

# Резолв имя ↔ NodeId. Worker — единственный владелец OPC-адресов: команды от
# GUI приходят по имени, наружу теги тоже уходят по имени.
_TAGS        = _SRV["tags"]                            # имя → NodeId
_NAME_BY_NID = {nid: name for name, nid in _TAGS.items()}  # NodeId → имя


def _normalize_nid(nid_str: str) -> str:
    """Привести NodeId к формату ns=X;s=... если asyncua вернул repr-формат."""
    if not nid_str.startswith("NodeId("):
        return nid_str
    m_ns = re.search(r"NamespaceIndex=(\d+)", nid_str)
    m_id = re.search(r"Identifier='([^']+)'", nid_str)
    if m_ns and m_id:
        return f"ns={m_ns.group(1)};s={m_id.group(1)}"
    return nid_str


class _SubHandler:
    """Обработчик подписок asyncua — вызывается из asyncio event loop."""

    def __init__(self, live_q, procs: list):
        self._live_q = live_q
        self._procs  = procs

    def datachange_notification(self, node, val, data):
        try:
            nid = _normalize_nid(str(node.nodeid))
            # Подписанные скаляры (напр. уставка) нужны своему RingProc для
            # записи рядом с точками — каждый проц сам игнорирует чужие теги.
            for p in self._procs:
                p.on_data(OPC_SERVER_ID, nid, val)
            self._live_q.put_nowait({'type': 'tag', 'name': _NAME_BY_NID.get(nid), 'val': val})
        except Exception as e:
            print(f"[SubHandler] error: {e}")


async def _keep_existing(nodes: dict, kind: str) -> dict:
    """Отсеять узлы, которых нет в адресном пространстве сервера.

    Один отсутствующий узел (например, ещё не заведённый на ПЛК general_fault)
    не должен ронять всё соединение в цикл реконнекта — пропускаем его с
    предупреждением, остальные работают. Это же гасит шторм переподключений,
    который копит сессии на сервере (BadTooManySessions). Прочие ошибки чтения
    (реальный разрыв связи) пробрасываем — пусть срабатывает reconnect.
    """
    out: dict = {}
    for nid, node in nodes.items():
        try:
            await node.read_value()
            out[nid] = node
        except Exception as e:
            if "BadNodeIdUnknown" in str(e):
                print(f"[worker] {kind}: узел отсутствует на сервере, пропуск: {nid}")
            else:
                raise
    return out


async def _run_connected(client: Client, live_q, cmd_q, procs: list):
    """Работает пока соединение живо. Исключение = разрыв → reconnect."""
    live_q.put_nowait({'type': 'connected', 'server': OPC_SERVER_ID})

    # Кэш объектов узлов
    poll_nodes  = {nid: client.get_node(nid) for nid in POLL_NIDS}
    sub_nodes   = {nid: client.get_node(nid) for nid in SUBSCRIBE_NIDS}
    write_nodes: dict = {}

    # Префлайт: убрать отсутствующие узлы, чтобы один ненайденный тег не валил
    # всё соединение (и не плодил сессии на сервере).
    poll_nodes = await _keep_existing(poll_nodes, "poll")
    sub_nodes  = await _keep_existing(sub_nodes,  "subscribe")
    poll_order = [nid for nid in POLL_NIDS if nid in poll_nodes]

    # keepalive-узел: стандартный Server/ServerStatus/State (i=2259) есть на любом
    # OPC UA сервере. Пингуем его каждый цикл, чтобы обрыв ловился даже когда все
    # data-теги отсутствуют и poll_order пуст (иначе воркер молча висит «подключённым»).
    status_node = client.get_node("i=2259")

    # Подписка на кнопки и уставку (только на существующие узлы). Период
    # публикации 100 мс — чтобы авария и уставка доезжали до GUI быстро.
    handler = _SubHandler(live_q, procs)
    sub = await client.create_subscription(100, handler)
    if sub_nodes:
        await sub.subscribe_data_change(list(sub_nodes.values()))

    # Начальное чтение подписанных тегов (состояния кнопок)
    for nid, node in sub_nodes.items():
        try:
            val = await node.read_value()
            for p in procs:
                p.on_data(OPC_SERVER_ID, nid, val)
            live_q.put_nowait({'type': 'tag', 'name': _NAME_BY_NID.get(nid), 'val': val})
        except Exception as e:
            print(f"[worker] initial read {nid}: {e}")

    loop = asyncio.get_event_loop()

    while True:
        t_start = loop.time()

        # Выполнить команды записи из GUI (неблокирующий дрейн)
        while True:
            try:
                cmd = cmd_q.get_nowait()
                name = cmd['cmd']                 # логическое имя тега
                val  = cmd['val']
                nid  = _TAGS.get(name)
                if nid is None:
                    print(f"[worker] неизвестная команда '{name}'")
                    continue
                if nid not in write_nodes:
                    write_nodes[nid] = client.get_node(nid)
                try:
                    await write_nodes[nid].write_value(ua.DataValue(ua.Variant(int(val))))
                    readback = await write_nodes[nid].read_value()
                    live_q.put_nowait({'type': 'tag', 'name': name, 'val': readback})
                except Exception as e:
                    print(f"[worker] write {name}: {e}")
            except _queue.Empty:
                break

        # Последовательный опрос массивов (порядок из конфига: cc → массивы;
        # отсутствующие на сервере узлы исключены префлайтом)
        for nid in poll_order:
            val = await poll_nodes[nid].read_value()   # исключение → выход → reconnect
            for p in procs:
                p.on_data(OPC_SERVER_ID, nid, val)
            raw_name = RAW_ARRAY_MAP.get(nid)
            if raw_name:
                live_q.put_nowait({'type': 'array', 'name': raw_name,
                                   'data': list(val) if val else []})

        # keepalive: проверка живости соединения — детект обрыва даже без data-тегов
        await status_node.read_value()   # исключение → выход → reconnect

        elapsed = loop.time() - t_start
        await asyncio.sleep(max(0.0, POLL_INTERVAL - elapsed))


async def run_worker_loop(live_q, cmd_q, procs: list):
    """Основной цикл с авто-переподключением."""
    while True:
        try:
            async with Client(url=OPC_ENDPOINT) as client:
                await _run_connected(client, live_q, cmd_q, procs)
        except Exception as e:
            print(f"[worker] disconnected: {e}")

        for p in procs:
            p.on_disconnect(OPC_SERVER_ID)
        live_q.put_nowait({'type': 'disconnected',  'server': OPC_SERVER_ID})
        live_q.put_nowait({'type': 'reconnecting',  'server': OPC_SERVER_ID,
                           'interval': RECONNECT_INTERVAL})
        await asyncio.sleep(RECONNECT_INTERVAL)


def build_procs(write_api, bucket: str, org: str, live_q) -> list:
    """Создать по одному RingProc на каждый кольцевой поток из конфига.

    Колбэк потока кладёт его точки в live_q под своим типом сообщения.
    """
    def emit(stream):
        return lambda times, vals: live_q.put_nowait(
            {'type': 'points', 'name': stream, 'times': times, 'vals': vals})

    return [
        RingProc(
            write_api, bucket, org,
            measurement=r["measurement"], cc_nid=_LOGGING["index"], arr_nid=r["node"],
            on_points=emit(r["points_msg"]),
            scalar_nid=r["scalar_node"],
            scalar_measurement=r["scalar_measurement"],
            on_scalar=emit(r["scalar_msg"]) if r["scalar_msg"] else None,
            array_size=_LOGGING["array_size"],
        )
        for r in _LOGGING["ring"]
    ]
