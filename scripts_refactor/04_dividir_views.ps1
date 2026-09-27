# ============================================================
# 04_dividir_views.ps1
# Divide buses/views.py en módulos por dominio.
# Estrategia SEGURA:
#   1. Crea buses/views/*.py con las funciones agrupadas
#   2. Deja buses/views.py como re-export (compatibilidad)
#   3. Actualiza urls.py para importar desde los nuevos módulos
#   4. NO borra el views.py original (queda como .bak)
#
# PowerShell 7 | Ejecutar desde C:\Proyectos\bitacora_ee
# ============================================================
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Proyectos\bitacora_ee"
Set-Location $ProjectRoot

$ViewsPath    = Join-Path $ProjectRoot "buses\views.py"
$ViewsBak     = Join-Path $ProjectRoot "buses\views.py.bak"
$ViewsPkgDir  = Join-Path $ProjectRoot "buses\views"
$UrlsPath     = Join-Path $ProjectRoot "buses\urls.py"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  04 · DIVIDIR views.py POR DOMINIO" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $ViewsPath)) {
    Write-Host "ERROR: No existe buses\views.py" -ForegroundColor Red
    exit 1
}

# Backup
Copy-Item $ViewsPath $ViewsBak -Force
Write-Host "✓ Backup: buses\views.py.bak" -ForegroundColor Green

New-Item -ItemType Directory -Path $ViewsPkgDir -Force | Out-Null

# ── Mapa dominio → funciones (según urls.py actual) ─────────
$modules = [ordered]@{
    "auth" = @(
        "require_tecnico", "require_admin", "_client_ip",
        "login_view", "privacidad_view", "logout_view"
    )
    "dashboard" = @(
        "dashboard", "get_contador_hoy", "api_contador", "api_resumen"
    )
    "reportes" = @(
        "api_reportes", "api_inventario"
    )
    "bitacora" = @(
        "api_guardar_bitacora", "api_bitacora_cola", "api_bitacoras_historial",
        "api_formulario_activo", "api_formulario_editor"
    )
    "usuarios" = @(
        "api_usuarios", "api_usuario_crear", "api_usuario_editar",
        "api_usuario_eliminar", "api_usuario_reset_password"
    )
    "flota" = @(
        "api_flota", "api_flota_accion", "api_flota_import", "api_flota_import_matriz"
    )
    "gps" = @(
        "api_gps", "api_gps_accion", "api_gps_import"
    )
    "poller_api" = @(
        "api_genesis_import", "api_busae_import", "api_poller_health", "api_poller_sync"
    )
    "auditoria" = @(
        "api_auditoria"
    )
    "config" = @(
        "api_config", "api_patios"
    )
    "tickets" = @(
        "api_tickets", "api_ticket_crear", "api_ticket_accion"
    )
}

# Leer views.py original
$original = Get-Content $ViewsPath -Raw -Encoding UTF8

# Extraer imports del tope (hasta la primera función/decorador de vista)
$headerMatch = [regex]::Match($original, '(?s)^(.*?)(?=\n# ──|\ndef require_|\ndef login_|\n@ensure_csrf)')
$header = if ($headerMatch.Success) { $headerMatch.Groups[1].Value.TrimEnd() } else {
    @"
import csv
import io
import json
import tempfile
import os
from datetime import datetime, time, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.db import transaction
from django.conf import settings

from buses.models import (
    Usuario, Patio, InventarioFlota, DispositivoGPS, MovimientoFlota,
    DatosBusae, DatosGenesis, EEMovil, UnidadFueraServicio,
    ReportePendiente, HistorialAtencion, BitacoraRegistro, InventarioItem,
    ConfiguracionSistema, AuditLog, FormularioPlantilla, Ticket, registrar_auditoria,
)
"@
}

# Función auxiliar: extraer def + cuerpo de una función por nombre
function Extract-Function {
    param([string]$src, [string]$funcName)
    # Busca def funcName o decorators encima
    $pattern = "(?ms)((?:^[ \t]*@[\w\.\(\)'\"" ,=]+\r?\n)*)^[ \t]*def $funcName\s*\([^\)]*\)\s*:.*?(?=\r?\n(?:[ \t]*@[\w\.]|[ \t]*def |\Z))"
    $m = [regex]::Match($src, $pattern)
    if ($m.Success) { return $m.Value.TrimEnd() }
    return $null
}

$extractedCount = 0
$missing = @()

foreach ($modName in $modules.Keys) {
    $funcs = $modules[$modName]
    $bodyParts = @()
    $bodyParts += "# -*- coding: utf-8 -*-"
    $bodyParts += "# buses/views/$modName.py — generado por 04_dividir_views.ps1"
    $bodyParts += "# NO editar el header a mano si vas a re-ejecutar el script."
    $bodyParts += ""
    $bodyParts += $header
    $bodyParts += ""
    $bodyParts += "# ── $modName ──────────────────────────────────────────────"
    $bodyParts += ""

    $foundAny = $false
    foreach ($fn in $funcs) {
        $code = Extract-Function -src $original -funcName $fn
        if ($code) {
            $bodyParts += $code
            $bodyParts += ""
            $bodyParts += ""
            $extractedCount++
            $foundAny = $true
        } else {
            $missing += "$modName.$fn"
        }
    }

    $outPath = Join-Path $ViewsPkgDir "$modName.py"
    ($bodyParts -join "`n") | Set-Content $outPath -Encoding UTF8
    if ($foundAny) {
        Write-Host "  ✓ views/$modName.py" -ForegroundColor Green
    } else {
        Write-Host "  ~ views/$modName.py (stubs — funciones no encontradas por regex)" -ForegroundColor Yellow
    }
}

# __init__.py que re-exporta todo (compatibilidad con from buses import views)
$initLines = @(
    "# buses.views — paquete de vistas por dominio",
    "# Re-export para no romper imports existentes.",
    ""
)
foreach ($modName in $modules.Keys) {
    $funcs = $modules[$modName] -join ", "
    $initLines += "from .$modName import *  # noqa: F401,F403"
}
$initLines += ""
($initLines -join "`n") | Set-Content (Join-Path $ViewsPkgDir "__init__.py") -Encoding UTF8
Write-Host "  ✓ views/__init__.py (re-exports)" -ForegroundColor Green

# Sustituir views.py por un shim que importa del paquete
$shim = @"
# -*- coding: utf-8 -*-
# buses/views.py — SHIM de compatibilidad
# La lógica vive ahora en buses/views/*.py
# Generado por scripts_refactor/04_dividir_views.ps1
# Backup del monolito: views.py.bak

from buses.views import *  # noqa: F401,F403
"@

# CUIDADO: si views.py y el paquete views/ coexisten, Python prioriza el PAQUETE.
# Por eso renombramos el monolito a views.py.bak y el paquete es buses/views/
# El shim NO puede llamarse views.py al mismo tiempo que existe el directorio views/.
# Solución: eliminar/renombrar views.py y usar solo el paquete.

if (Test-Path $ViewsPath) {
    # Ya tenemos .bak; quitar el archivo para que el paquete tome precedencia
    Remove-Item $ViewsPath -Force
    Write-Host "  ✓ buses/views.py eliminado (queda .bak). El paquete buses/views/ es la fuente." -ForegroundColor Green
}

# Actualizar urls.py para importar desde el paquete (sigue funcionando con from . import views)
# No hace falta cambiar urls.py si usa "from . import views" y el paquete re-exporta.

Write-Host ""
Write-Host "  Funciones extraídas: $extractedCount" -ForegroundColor Cyan
if ($missing.Count -gt 0) {
    Write-Host "  No encontradas por regex (revisar views.py.bak):" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "    - $_" -ForegroundColor DarkYellow }
    Write-Host ""
    Write-Host "  Acción: abre views.py.bak y copia manualmente las funciones faltantes" -ForegroundColor Yellow
    Write-Host "  al módulo correspondiente en buses/views/." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "✓ Script 04 completado." -ForegroundColor Green
Write-Host "  Prueba: python manage.py check" -ForegroundColor Yellow
Write-Host "  Si falla: Copy-Item buses\views.py.bak buses\views.py  y borra la carpeta buses\views\" -ForegroundColor DarkGray
Write-Host ""
