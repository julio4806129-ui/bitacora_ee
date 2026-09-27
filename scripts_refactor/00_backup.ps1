# ============================================================
# 00_backup.ps1 — Backup completo del proyecto Bitácora E.E.
# PowerShell 7 | Ejecutar desde C:\Proyectos\bitacora_ee
# ============================================================
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Proyectos\bitacora_ee"
$Timestamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot  = "C:\Proyectos\backups_bitacora_ee"
$BackupDir   = Join-Path $BackupRoot "backup_$Timestamp"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  00 · BACKUP Bitácora E.E." -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $ProjectRoot)) {
    Write-Host "ERROR: No existe $ProjectRoot" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

Write-Host "→ Copiando proyecto a $BackupDir ..." -ForegroundColor Yellow

# Excluir venv, node_modules, __pycache__, .git grandes si hace falta
$exclude = @('venv', '.venv', 'node_modules', '__pycache__', '.git', 'staticfiles', 'media')
$robocopyArgs = @(
    $ProjectRoot,
    $BackupDir,
    '/E',           # subdirectorios
    '/XD'
) + $exclude + @(
    '/NFL', '/NDL', '/NJH', '/NJS', '/nc', '/ns', '/np'
)

& robocopy @robocopyArgs | Out-Null
# robocopy exit codes 0-7 = success variants
if ($LASTEXITCODE -ge 8) {
    Write-Host "ERROR en robocopy (código $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

# Backup explícito de archivos sensibles
$sensibles = @('.env', 'db.sqlite3', 'cookies.txt')
foreach ($f in $sensibles) {
    $src = Join-Path $ProjectRoot $f
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $BackupDir $f) -Force
        Write-Host "  ✓ Guardado: $f" -ForegroundColor Green
    }
}

# Resumen
$size = (Get-ChildItem $BackupDir -Recurse -File -ErrorAction SilentlyContinue |
         Measure-Object -Property Length -Sum).Sum / 1MB

Write-Host ""
Write-Host "  Backup listo:" -ForegroundColor Green
Write-Host "    Ruta : $BackupDir"
Write-Host "    Tamaño aprox: $([math]::Round($size, 1)) MB"
Write-Host ""
Write-Host "  Guarda esta ruta por si necesitas revertir." -ForegroundColor Yellow
Write-Host ""

# Guardar ruta del último backup para otros scripts
$BackupDir | Set-Content (Join-Path $ProjectRoot "scripts_refactor\.last_backup") -Encoding UTF8
Write-Host "✓ Ruta guardada en scripts_refactor\.last_backup" -ForegroundColor Green
Write-Host ""
