import json

def generate_py(json_file: str, output_py: str):
    """Генерация Python переменных из JSON"""

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = ["# Auto-generated OPC UA tags\n"]

    def walk(obj, prefix=""):
        for k, v in obj.items():
            if isinstance(v, dict) and "node_id" in v:
                var = f"{prefix}{k}".replace(" ", "_")
                lines.append(f'{var} = "{v["node_id"]}"')
            elif isinstance(v, dict):
                walk(v, prefix=f"{prefix}{k}_")

    walk(data.get("Objects", {}))

    with open(output_py, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
