# ============================================================
# 03_estructura_apps.ps1
# Crea la estructura modular (apps + services + selectors)
# SIN mover lógica todavía — solo scaffold seguro.
# PowerShell 7 | Ejecutar desde C:\Proyectos\bitacora_ee
# ============================================================
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Proyectos\bitacora_ee"
Set-Location $ProjectRoot

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  03 · ESTRUCTURA MODULAR (scaffold)" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$appsRoot = Join-Path $ProjectRoot "apps"
$domains = @("core", "usuarios", "flota", "telemetria", "reportes", "bitacora", "auditoria", "tickets")

# Crear apps/
New-Item -ItemType Directory -Path $appsRoot -Force | Out-Null
$initApps = Join-Path $appsRoot "__init__.py"
if (-not (Test-Path $initApps)) {
    "# Apps package — dominios de Bitácora E.E.`n" | Set-Content $initApps -Encoding UTF8
}

foreach ($domain in $domains) {
    $appDir = Join-Path $appsRoot $domain
    New-Item -ItemType Directory -Path $appDir -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $appDir "tests") -Force | Out-Null

    $files = @{
        "__init__.py"     = "# App: $domain`n"
        "apps.py"         = @"
from django.apps import AppConfig

class $($domain.Substring(0,1).ToUpper() + $domain.Substring(1))Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.$domain'
    label = '$domain'
    verbose_name = '$domain'
"@
        "models.py"       = @"
# models.py — $domain
# Migrar aquí los modelos relacionados cuando se haga el split real.
from django.db import models
"@
        "services.py"     = @"
# services.py — lógica de negocio de $domain
# Las vistas solo validan request y llaman a estas funciones.
"@
        "selectors.py"    = @"
# selectors.py — queries optimizadas (select_related / prefetch_related)
# Evitar N+1 aquí.
"@
        "urls.py"         = @"
from django.urls import path
# from . import views

urlpatterns = [
    # path('', views.list_view, name='${domain}_list'),
]
"@
        "admin.py"        = "# admin.py — $domain`nfrom django.contrib import admin`n"
        "tests/__init__.py" = ""
        "tests/test_services.py" = @"
# Tests de services — $domain
import pytest

# def test_ejemplo():
#     assert True
"@
    }

    foreach ($name in $files.Keys) {
        $path = Join-Path $appDir $name
        $dir = Split-Path $path -Parent
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        if (-not (Test-Path $path)) {
            $files[$name] | Set-Content $path -Encoding UTF8
        }
    }

    Write-Host "  ✓ apps/$domain/" -ForegroundColor Green
}

# Dentro de buses: services + selectors (para usar YA sin migrar apps)
$busesDir = Join-Path $ProjectRoot "buses"
foreach ($f in @("services.py", "selectors.py")) {
    $p = Join-Path $busesDir $f
    if (-not (Test-Path $p)) {
        @"
# $f — capa de negocio / queries para la app buses (legacy)
# Ir moviendo lógica de views.py aquí de forma gradual.
"@ | Set-Content $p -Encoding UTF8
        Write-Host "  ✓ buses/$f" -ForegroundColor Green
    }
}

# Carpeta views/ dentro de buses (para el script 04)
$viewsDir = Join-Path $busesDir "views"
New-Item -ItemType Directory -Path $viewsDir -Force | Out-Null
$viewsInit = Join-Path $viewsDir "__init__.py"
if (-not (Test-Path $viewsInit)) {
    @"
# views package — módulos por dominio.
# Tras ejecutar 04_dividir_views.ps1, importar desde aquí.
"@ | Set-Content $viewsInit -Encoding UTF8
    Write-Host "  ✓ buses/views/" -ForegroundColor Green
}

# Documentación rápida de la arquitectura
$archNote = Join-Path $ProjectRoot "apps\README.md"
@"
# Apps — Dominios de Bitácora E.E.

Esta carpeta es el **scaffold** de la arquitectura modular.

| App | Responsabilidad |
|-----|-----------------|
| core | Patio, ConfiguracionSistema, utilidades compartidas |
| usuarios | Usuario, login, roles, cuotas |
| flota | InventarioFlota, DispositivoGPS, MovimientoFlota |
| telemetria | DatosBusae, DatosGenesis |
| reportes | ReportePendiente, HistorialAtencion, UnidadFueraServicio |
| bitacora | BitacoraRegistro, FormularioPlantilla |
| auditoria | AuditLog |
| tickets | Ticket |

## Capas dentro de cada app

- ``models.py`` — modelos Django
- ``selectors.py`` — lecturas optimizadas (sin efectos secundarios)
- ``services.py`` — lógica de negocio (crear, actualizar, orquestar)
- ``views`` / ``urls`` — presentación / HTTP
- ``tests/`` — pytest

## Estado actual

Todavía la lógica vive en ``buses/``.  
Los scripts siguientes moverán código de forma gradual.
"@ | Set-Content $archNote -Encoding UTF8

Write-Host ""
Write-Host "✓ Scaffold listo en apps/ y buses/services.py + selectors.py" -ForegroundColor Green
Write-Host "  Siguiente: 04_dividir_views.ps1" -ForegroundColor Yellow
Write-Host ""
