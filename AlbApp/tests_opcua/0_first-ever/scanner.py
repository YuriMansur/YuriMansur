import json
from opcua import Client, ua

def scan(
    endpoint: str,
    output_file: str,
    progress_cb=None,
    node_classes=None,  # список ua.NodeClass
    namespaces=None     # список namespace индексов
):
    """
    Сканирование OPC UA с фильтром по NodeClass и namespace.
    node_classes: list, например [ua.NodeClass.Variable]
    namespaces: list, например [2, 3]
    """

    node_classes = node_classes or [ua.NodeClass.Variable, ua.NodeClass.Object, ua.NodeClass.View]

    def browse(node):
        result = {}
        try:
            children = node.get_children()
        except Exception:
            return result

        for child in children:
            try:
                name = child.get_browse_name().Name
                node_class = child.get_node_class()
                node_ns = child.nodeid.NamespaceIndex

                # фильтр
                if node_class not in node_classes:
                    continue
                if namespaces is not None and node_ns not in namespaces:
                    continue

                if node_class == ua.NodeClass.Variable:
                    result[name] = {"node_id": str(child.nodeid)}
                    if progress_cb:
                        progress_cb(f"Variable: {name}")

                elif node_class in (ua.NodeClass.Object, ua.NodeClass.View):
                    result[name] = browse(child)

            except Exception:
                continue

        return result

    client = Client(endpoint)
    try:
        client.connect()
        root = client.get_root_node()
        objects = root.get_child(["0:Objects"])
        tree = {"Objects": browse(objects)}
    except Exception as e:
        raise RuntimeError(e)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)
