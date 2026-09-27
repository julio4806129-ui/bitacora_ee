# ============================================================
# 02_settings_seguridad.ps1
# Refuerza settings.py con cabeceras de seguridad (prod-ready).
# Crea backup de settings.py antes de modificar.
# PowerShell 7 | Ejecutar desde C:\Proyectos\bitacora_ee
# ============================================================
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Proyectos\bitacora_ee"
Set-Location $ProjectRoot

$SettingsPath = Join-Path $ProjectRoot "bitacora_ee\settings.py"
$BackupSettings = Join-Path $ProjectRoot "bitacora_ee\settings.py.bak"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  02 · SETTINGS DE SEGURIDAD" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $SettingsPath)) {
    Write-Host "ERROR: No existe $SettingsPath" -ForegroundColor Red
    exit 1
}

# Backup
Copy-Item $SettingsPath $BackupSettings -Force
Write-Host "✓ Backup: bitacora_ee\settings.py.bak" -ForegroundColor Green

$content = Get-Content $SettingsPath -Raw -Encoding UTF8

# Bloque de seguridad a insertar (solo se aplica cuando DEBUG=False)
$securityBlock = @'

# ═══════════════════════════════════════════════════════════
# SEGURIDAD (generado por scripts_refactor/02)
# Se activan solo en producción (DEBUG=False)
# ═══════════════════════════════════════════════════════════
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    # Confiar en proxy reverso (Nginx / Cloudflare)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Siempre activos (dev y prod)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

'@

# Evitar duplicar si ya se ejecutó
if ($content -match "generado por scripts_refactor/02") {
    Write-Host "  Ya existe el bloque de seguridad. No se modifica." -ForegroundColor Yellow
} else {
    # Insertar antes del final del archivo (después de LOGIN_*)
    if ($content -match "LOGOUT_REDIRECT_URL") {
        $content = $content -replace "(LOGOUT_REDIRECT_URL\s*=\s*[^\r\n]+)", "`$1`n$securityBlock"
    } else {
        $content = $content.TrimEnd() + "`n`n" + $securityBlock
    }
    $content | Set-Content $SettingsPath -Encoding UTF8 -NoNewline
    Write-Host "✓ Bloque de seguridad añadido a settings.py" -ForegroundColor Green
}

# Recordatorio SECRET_KEY
Write-Host ""
Write-Host "  IMPORTANTE:" -ForegroundColor Yellow
Write-Host "  - En producción: DEBUG=False y SECRET_KEY fuerte en .env"
Write-Host "  - Nunca uses el default 'django-insecure-...' en prod"
Write-Host ""

Write-Host "✓ Script 02 completado." -ForegroundColor Green
Write-Host "  Si algo falla: Copy-Item bitacora_ee\settings.py.bak bitacora_ee\settings.py" -ForegroundColor DarkGray
Write-Host ""
