# opc_scanner.py
import asyncio
import json
from asyncua import Client, ua

class OPCScanner:
    def __init__(self, server_url):
        self.server_url = server_url
        self.client = Client(server_url)
        self.nodes = {}

    async def connect(self):
        await self.client.connect()
        self.root = self.client.nodes.objects

    async def disconnect(self):
        await self.client.disconnect()

    async def explore_node(self, node):
        """Рекурсивно обходит дерево и собирает информацию о node"""
        try:
            children = await node.get_children()
            node_name = await node.read_display_name()
            node_class = await node.read_node_class()
            value = None
            data_type = None

            if node_class == ua.NodeClass.Variable:
                try:
                    value = await node.read_value()
                    data_type_node = await node.read_data_type()
                    data_type = str(data_type_node)
                except Exception:
                    value = None

            node_info = {
                "name": node_name.Text,
                "node_class": node_class.name,
                "type": data_type,
                "value": value,
                "children": []
            }

            for child in children:
                child_info = await self.explore_node(child)
                node_info["children"].append(child_info)

            return node_info
        except Exception as e:
            return {"error": str(e)}

    async def scan(self):
        """Запуск рекурсивного сканирования с корня"""
        self.nodes = await self.explore_node(self.root)
        return self.nodes

    def save_json(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.nodes, f, indent=2, ensure_ascii=False)

# Пример запуска
async def main():
    scanner = OPCScanner("opc.tcp://192.168.1.10:4840/freeopcua/server/")
    await scanner.connect()
    await scanner.scan()
    await scanner.disconnect()

    # Сохраняем результаты
    scanner.save_json("opc_tags.json")
    scanner.save_yaml("opc_tags.yaml")

    print("Сканирование завершено!")

if __name__ == "__main__":
    asyncio.run(main())