# ============================================================
# RUN_ALL.ps1 — Ejecuta scripts 00 → 06 en orden
# Puedes saltar alguno con -Skip 04  o detenerte en uno con -Until 03
# PowerShell 7 | Ejecutar desde C:\Proyectos\bitacora_ee
# ============================================================
param(
    [int[]]$Skip = @(),
    [int]$Until = 6
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\Proyectos\bitacora_ee"
$ScriptsDir  = Join-Path $ProjectRoot "scripts_refactor"

if (-not (Test-Path $ScriptsDir)) {
    Write-Host "ERROR: Copia primero la carpeta scripts_refactor a $ProjectRoot" -ForegroundColor Red
    exit 1
}

Set-Location $ProjectRoot

$scripts = @(
    @{ N = 0; File = "00_backup.ps1";              Title = "Backup" },
    @{ N = 1; File = "01_seguridad_gitignore.ps1"; Title = "Seguridad + gitignore" },
    @{ N = 2; File = "02_settings_seguridad.ps1";  Title = "Settings seguridad" },
    @{ N = 3; File = "03_estructura_apps.ps1";     Title = "Estructura apps" },
    @{ N = 4; File = "04_dividir_views.ps1";       Title = "Dividir views" },
    @{ N = 5; File = "05_docker_scaffold.ps1";     Title = "Docker scaffold" },
    @{ N = 6; File = "06_ci_tests.ps1";            Title = "CI + tests" }
)

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  BITÁCORA E.E. — REFACTOR AUTOMATIZADO 00→06" -ForegroundColor Magenta
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host ""

foreach ($s in $scripts) {
    if ($s.N -in $Skip) {
        Write-Host "  ⊗ Saltando $($s.N) — $($s.Title)" -ForegroundColor DarkGray
        continue
    }
    if ($s.N -gt $Until) {
        Write-Host "  ⊗ Detenido en -Until $Until" -ForegroundColor DarkGray
        break
    }

    $path = Join-Path $ScriptsDir $s.File
    if (-not (Test-Path $path)) {
        Write-Host "  ✗ No existe $($s.File)" -ForegroundColor Red
        exit 1
    }

    Write-Host "───────────────────────────────────────────────────────" -ForegroundColor DarkCyan
    Write-Host "  Ejecutando $($s.File) ..." -ForegroundColor White
    & $path
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        Write-Host "  ✗ Falló script $($s.N). Abortando." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  TODOS LOS SCRIPTS COMPLETADOS" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Verificación recomendada:" -ForegroundColor Cyan
Write-Host "    cd C:\Proyectos\bitacora_ee"
Write-Host "    .\venv\Scripts\Activate.ps1"
Write-Host "    python manage.py check"
Write-Host "    python manage.py migrate"
Write-Host "    pytest -q"
Write-Host ""
Write-Host "  Si el script 04 rompió algo:" -ForegroundColor Yellow
Write-Host "    Copy-Item buses\views.py.bak buses\views.py -Force"
Write-Host "    Remove-Item -Recurse -Force buses\views"
Write-Host ""
