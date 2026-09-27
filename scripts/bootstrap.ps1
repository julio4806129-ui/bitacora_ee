#Requires -Version 7.0
<#
.SYNOPSIS
  Bootstrap Bitácora E.E en Windows (PowerShell 7+)
.DESCRIPTION
  Crea venv, instala deps, migra, seed e inicia servidor de desarrollo.
  Uso:  .\scripts\bootstrap.ps1
  Desde: C:\Proyectos\bitacora_ee
#>
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$Root\manage.py")) {
    $Root = Get-Location
}
Set-Location $Root
Write-Host "==> Directorio: $Root" -ForegroundColor Cyan

# 1) Venv
if (-not (Test-Path "$Root\venv\Scripts\python.exe")) {
    Write-Host "==> Creando venv..." -ForegroundColor Cyan
    python -m venv venv
}
& "$Root\venv\Scripts\Activate.ps1"

# 2) Deps
Write-Host "==> Instalando requirements..." -ForegroundColor Cyan
python -m pip install --upgrade pip
pip install -r requirements.txt

# 3) .env
if (-not (Test-Path "$Root\.env")) {
    if (Test-Path "$Root\.env.example") {
        Copy-Item "$Root\.env.example" "$Root\.env"
        Write-Host "==> .env creado desde .env.example (revisa secretos)" -ForegroundColor Yellow
    }
}

# Forzar SQLite en dev si no hay Postgres
$env:USE_SQLITE = if ($env:USE_SQLITE) { $env:USE_SQLITE } else { 'True' }

# 4) Migraciones
Write-Host "==> makemigrations + migrate..." -ForegroundColor Cyan
python manage.py makemigrations buses
python manage.py migrate

# 5) Seed
Write-Host "==> seed_initial..." -ForegroundColor Cyan
python manage.py seed_initial

Write-Host ""
Write-Host "Listo. Para arrancar:" -ForegroundColor Green
Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "  python manage.py runserver 0.0.0.0:8000" -ForegroundColor White
Write-Host "Login ejemplo: codigo 13283 (tras configurar password en FASE 0)" -ForegroundColor Yellow
