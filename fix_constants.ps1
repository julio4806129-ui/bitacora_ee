# ============================================================
# fix_constants.ps1
# Repara constantes de modulo que el split de views.py se salto
# (solo extrajo funciones, no dicts a nivel de modulo).
# Ejecutar desde la raiz del repo, con views.py.bak presente.
# ============================================================
$ErrorActionPreference = "Stop"
$Bak = "buses\views.py.bak"
if (-not (Test-Path $Bak)) { Write-Host "ERROR: no existe $Bak" -ForegroundColor Red; exit 1 }

$py = @'
import re, sys
bak_path, bitacora_path, config_path = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(bak_path, encoding="utf-8").read()

def block(start_marker, end_marker):
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j].rstrip() + "\n"

maps_block = block("MAP_GPS = {'FUNCIONA'", "def _bitacora_to_dict")
config_block = block("CONFIG_SCHEMA = {", "@require_admin")

def insert_after_imports(path, snippet, guard):
    text = open(path, encoding="utf-8").read()
    if guard in text:
        print("ya presente, se omite:", path)
        return
    marker = "from django.conf import settings"
    idx = text.index(marker) + len(marker)
    text = text[:idx] + "\n\n" + snippet + text[idx:]
    open(path, "w", encoding="utf-8").write(text)
    print("insertado en", path)

insert_after_imports(bitacora_path, maps_block, "MAP_GPS = {")
insert_after_imports(config_path, config_block, "CONFIG_SCHEMA = {")
'@
Set-Content -Path "scripts_refactor\_fix_constants.py" -Value $py -Encoding UTF8
python scripts_refactor\_fix_constants.py $Bak "buses\views\bitacora.py" "buses\views\config.py"

python manage.py check
