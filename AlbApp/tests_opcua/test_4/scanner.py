import json
from opcua import Client, ua

def scan(
    endpoint: str,
    output_file: str,
    progress_cb=None,
    node_classes=None,
    namespaces=None,
    progress_count_cb=None  # callback для прогресса
):
    """
    Сканирование OPC UA с фильтром и прогрессом.
    progress_count_cb(i) будет вызываться на каждый найденный узел.
    """

    node_classes = node_classes or [ua.NodeClass.Variable, ua.NodeClass.Object, ua.NodeClass.View]

    def count_nodes(node):
        count = 0
        try:
            children = node.get_children()
        except Exception:
            return 0

        for child in children:
            try:
                node_class = child.get_node_class()
                node_ns = child.nodeid.NamespaceIndex
                if node_class not in node_classes:
                    continue
                if namespaces is not None and node_ns not in namespaces:
                    continue
                count += 1
                if node_class in (ua.NodeClass.Object, ua.NodeClass.View):
                    count += count_nodes(child)
            except Exception:
                continue
        return count

    def browse(node, counter):
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

                if node_class not in node_classes:
                    continue
                if namespaces is not None and node_ns not in namespaces:
                    continue

                counter['current'] += 1
                if progress_count_cb:
                    progress_count_cb(counter['current'])

                if node_class == ua.NodeClass.Variable:
                    result[name] = {"node_id": str(child.nodeid)}
                    if progress_cb:
                        progress_cb(f"Variable: {name}")
                elif node_class in (ua.NodeClass.Object, ua.NodeClass.View):
                    result[name] = browse(child, counter)

            except Exception:
                continue
        return result

    client = Client(endpoint)
    try:
        client.connect()
        root = client.get_root_node()
        objects = root.get_child(["0:Objects"])
        # Считаем общее количество узлов для прогресса
        total_nodes = count_nodes(objects)
        counter = {'current': 0}
        tree = {"Objects": browse(objects, counter)}
    except Exception as e:
        raise RuntimeError(e)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)

    return total_nodes
