# ============================================================
# 01_seguridad_gitignore.ps1
# - Refuerza .gitignore
# - Quita del tracking: .env, db.sqlite3, cookies.txt, __pycache__, etc.
# NO borra los archivos locales, solo deja de trackearlos.
# PowerShell 7 | Ejecutar desde C:\Proyectos\bitacora_ee
# ============================================================
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Proyectos\bitacora_ee"
Set-Location $ProjectRoot

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  01 · SEGURIDAD + .gitignore" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── 1. .gitignore profesional ────────────────────────────────
$gitignoreContent = @"
# ── Python ──────────────────────────────────────────────────
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
.venv/
env/
ENV/
*.egg-info/
dist/
build/
.mypy_cache/
.pytest_cache/
.coverage
htmlcov/
.tox/
.ruff_cache/

# ── Django ──────────────────────────────────────────────────
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal
staticfiles/
media/
/static/collected/

# ── Secretos y entorno ──────────────────────────────────────
.env
.env.*
!.env.example
*.pem
*.key
cookies.txt
secrets/
credentials/

# ── IDE / OS ────────────────────────────────────────────────
.idea/
.vscode/
*.swp
*.swo
*~
.DS_Store
Thumbs.db
Desktop.ini

# ── Node (si frontend futuro) ───────────────────────────────
node_modules/
npm-debug.log*
yarn-error.log*
dist/
.next/

# ── Celery / Redis dumps ────────────────────────────────────
celerybeat-schedule
celerybeat.pid
dump.rdb

# ── Backups locales ─────────────────────────────────────────
*.bak
*.backup
scripts_refactor/.last_backup

# ── Datos locales sensibles ─────────────────────────────────
data_matriz.xlsx
!data_matriz.example.xlsx
"@

$gitignorePath = Join-Path $ProjectRoot ".gitignore"
$gitignoreContent | Set-Content $gitignorePath -Encoding UTF8
Write-Host "✓ .gitignore actualizado" -ForegroundColor Green

# ── 2. Quitar del índice de Git (sin borrar archivos) ────────
if (Test-Path (Join-Path $ProjectRoot ".git")) {
    Write-Host "→ Quitando archivos sensibles del tracking de Git..." -ForegroundColor Yellow

    $toUntrack = @(
        '.env',
        'db.sqlite3',
        'cookies.txt',
        'data_matriz.xlsx'
    )

    foreach ($f in $toUntrack) {
        $full = Join-Path $ProjectRoot $f
        if (Test-Path $full) {
            git rm --cached --ignore-unmatch $f 2>$null
            Write-Host "  ✓ Untracked: $f" -ForegroundColor Green
        }
    }

    # Carpetas cache
    git rm -r --cached --ignore-unmatch "**/__pycache__" 2>$null
    git rm -r --cached --ignore-unmatch "buses/__pycache__" 2>$null
    git rm -r --cached --ignore-unmatch "poller/__pycache__" 2>$null

    Write-Host ""
    Write-Host "  NOTA: Los archivos siguen en disco. Solo dejaron de trackearse." -ForegroundColor Yellow
    Write-Host "  Haz commit cuando quieras: git add .gitignore && git commit -m 'chore: seguridad - secretos fuera del tracking'" -ForegroundColor Yellow
} else {
    Write-Host "  (No hay repo Git inicializado — se omite untrack)" -ForegroundColor DarkYellow
}

# ── 3. Verificar que .env.example no tenga secretos reales ───
$envExample = Join-Path $ProjectRoot ".env.example"
if (Test-Path $envExample) {
    $content = Get-Content $envExample -Raw
    $suspicious = @('password', 'secret', 'key=') | Where-Object { $content -match $_ -and $content -notmatch 'cambia|change|example|xxx|your-' }
    if ($suspicious) {
        Write-Host ""
        Write-Host "  AVISO: Revisa .env.example — podría contener valores reales." -ForegroundColor Magenta
    } else {
        Write-Host "✓ .env.example parece limpio" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "✓ Script 01 completado." -ForegroundColor Green
Write-Host ""
