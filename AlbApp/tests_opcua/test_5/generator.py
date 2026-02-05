import json

def generate_py(json_file: str, py_file: str):
    """Генерация Python-кода с переменными из JSON"""

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = []

    def build_vars(d, prefix=""):
        for k, v in d.items():
            if not isinstance(v, dict):
                continue

            # Создаём уникальное имя переменной
            name = (prefix + "_" + k).replace(" ", "_") if prefix else k.replace(" ", "_")

            # Если есть node_id, создаём строковую переменную
            if "node_id" in v:
                lines.append(f'{name} = "{v["node_id"]}"')

            # Рекурсивно обрабатываем все вложенные словари
            for kk, vv in v.items():
                if isinstance(vv, dict):
                    build_vars({kk: vv}, prefix=name)

    build_vars(data.get("Objects", {}))

    with open(py_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
