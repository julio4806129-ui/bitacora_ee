#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (Test-Path .\venv\Scripts\Activate.ps1) { . .\venv\Scripts\Activate.ps1 }

$matriz = if (Test-Path .\data_matriz.xlsx) { '.\data_matriz.xlsx' } else { $args[0] }
if (-not $matriz -or -not (Test-Path $matriz)) {
    Write-Host "Uso: .\scripts\import_matriz.ps1 [ruta\MATRIZ.xlsx]" -ForegroundColor Yellow
    Write-Host "No se encontró data_matriz.xlsx en el proyecto."
    exit 1
}
Write-Host "==> Importando $matriz" -ForegroundColor Cyan
python manage.py import_matriz $matriz
Write-Host "Listo." -ForegroundColor Green
