# ============================================================
# 04_dividir_views.ps1 (v2 — usa AST de Python, no regex)
# Divide buses/views.py en buses/views/*.py por dominio.
# Requiere: python en PATH (3.8+). No borra nada sin backup.
# Ejecutar desde la raiz del repo (C:\Proyectos\bitacora_ee)
# ============================================================
$ErrorActionPreference = "Stop"
$Root      = Get-Location
$ViewsPath = Join-Path $Root "buses\views.py"
$ViewsBak  = Join-Path $Root "buses\views.py.bak"
$PkgDir    = Join-Path $Root "buses\views"
$HelperPy  = Join-Path $Root "scripts_refactor\_split_views.py"
$MapJson   = Join-Path $Root "scripts_refactor\_domain_map.json"

if (-not (Test-Path $ViewsPath)) { Write-Host "ERROR: no existe buses\views.py" -ForegroundColor Red; exit 1 }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "ERROR: python no esta en PATH" -ForegroundColor Red; exit 1 }

Copy-Item $ViewsPath $ViewsBak -Force
Write-Host "Backup: buses\views.py.bak" -ForegroundColor Green
New-Item -ItemType Directory -Path $PkgDir -Force | Out-Null

# ── Mapa dominio -> funciones (ajusta aqui si agregas vistas nuevas) ──
$map = [ordered]@{
  auth        = @("require_tecnico","require_admin","_client_ip","login_view","privacidad_view","logout_view")
  dashboard   = @("dashboard","get_contador_hoy","api_contador","api_resumen")
  reportes    = @("api_reportes","api_inventario")
  bitacora    = @("api_guardar_bitacora","api_bitacora_cola","api_bitacoras_historial","_bitacora_to_dict","api_formulario_activo","api_formulario_editor")
  usuarios    = @("api_usuarios","api_usuario_crear","api_usuario_editar","api_usuario_eliminar","api_usuario_reset_password")
  flota       = @("api_flota","api_flota_accion","api_flota_import","api_flota_import_matriz")
  gps         = @("api_gps","api_gps_accion","api_gps_import")
  poller_api  = @("api_genesis_import","_calcular_patio_row","_parse_hora_entrada","api_busae_import","api_poller_health","api_poller_sync")
  auditoria   = @("api_auditoria")
  config      = @("api_config","api_patios")
  tickets     = @("api_tickets","api_ticket_crear","api_ticket_accion")
}
($map | ConvertTo-Json -Depth 3) | Set-Content $MapJson -Encoding UTF8

# ── Helper Python: extrae por AST (fiable con decoradores y funciones anidadas) ──
$py = @'
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
'@
Set-Content -Path $HelperPy -Value $py -Encoding UTF8

python $HelperPy $ViewsPath $MapJson $PkgDir

# Verificar sintaxis de cada modulo antes de tocar nada mas
$syntaxOk = $true
Get-ChildItem $PkgDir -Filter "*.py" | ForEach-Object {
    python -c "import ast; ast.parse(open(r'$($_.FullName)', encoding='utf-8').read())"
    if ($LASTEXITCODE -ne 0) { $syntaxOk = $false; Write-Host "SINTAXIS INVALIDA: $($_.Name)" -ForegroundColor Red }
}

if (-not $syntaxOk) {
    Write-Host "Se detuvo por errores de sintaxis. Revisa buses\views\ (views.py original NO se toco)." -ForegroundColor Red
    exit 1
}

Remove-Item $ViewsPath -Force
Write-Host "buses\views.py eliminado (queda .bak). buses\views\ es ahora el paquete activo." -ForegroundColor Green
Write-Host ""
Write-Host "Siguiente paso: python manage.py check" -ForegroundColor Yellow
Write-Host "Si algo falla: Copy-Item buses\views.py.bak buses\views.py -Force; Remove-Item buses\views -Recurse -Force" -ForegroundColor DarkGray
