import ast, json, sys
views_path, map_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
domains = json.loads(open(map_path, encoding="utf-8").read())
src = open(views_path, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.splitlines(keepends=True)

def segment(node):
    start = node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno
    return "".join(lines[start-1:node.end_lineno])

funcs, first_def = {}, None
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        funcs[node.name] = segment(node)
        start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
        if first_def is None or start < first_def:
            first_def = start
header = "".join(lines[:first_def-1]).rstrip() if first_def else ""

assigned, missing = set(), []
for domain, names in domains.items():
    body = [f"# buses/views/{domain}.py — generado por 04_dividir_views.ps1", "", header, ""]
    found = False
    for name in names:
        if name in funcs:
            body.append(funcs[name]); assigned.add(name); found = True
        else:
            missing.append(f"{domain}.{name}")
    text = ("\n".join(body)).rstrip() + "\n"
    open(f"{out_dir}/{domain}.py", "w", encoding="utf-8").write(text)
    print(("OK   " if found else "VACIO"), domain)

leftover = [n for n in funcs if n not in assigned]
init_lines = ["# buses/views — paquete generado, re-exporta todo"]
for domain in domains:
    init_lines.append(f"from .{domain} import *  # noqa: F401,F403")
open(f"{out_dir}/__init__.py", "w", encoding="utf-8").write("\n".join(init_lines) + "\n")

if missing:  print("FALTANTES (en el mapa pero no en views.py):", missing)
if leftover: print("SIN ASIGNAR (en views.py pero no en el mapa):", leftover)
