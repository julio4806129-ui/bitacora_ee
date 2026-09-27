# ============================================================
# 05_docker_scaffold.ps1
# Genera Dockerfile, docker-compose (dev) y nginx.conf básico.
# PowerShell 7 | Ejecutar desde C:\Proyectos\bitacora_ee
# ============================================================
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Proyectos\bitacora_ee"
Set-Location $ProjectRoot

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  05 · DOCKER SCAFFOLD" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── Dockerfile ───────────────────────────────────────────────
$dockerfile = @'
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/media /app/logs /app/staticfiles \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -f http://localhost:8000/api/poller/health/ || curl -f http://localhost:8000/ || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "bitacora_ee.wsgi:application"]
'@

$dockerfile | Set-Content (Join-Path $ProjectRoot "Dockerfile") -Encoding UTF8
Write-Host "  ✓ Dockerfile" -ForegroundColor Green

# ── .dockerignore ────────────────────────────────────────────
$dockerignore = @'
venv/
.venv/
__pycache__/
*.pyc
.git/
.env
db.sqlite3
*.bak
scripts_refactor/.last_backup
node_modules/
staticfiles/
media/
.pytest_cache/
.mypy_cache/
htmlcov/
cookies.txt
'@
$dockerignore | Set-Content (Join-Path $ProjectRoot ".dockerignore") -Encoding UTF8
Write-Host "  ✓ .dockerignore" -ForegroundColor Green

# ── docker-compose.yml (dev) ─────────────────────────────────
$compose = @'
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: bitacora_db
      POSTGRES_USER: bitacora_user
      POSTGRES_PASSWORD: enterprise_password_2026
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bitacora_user -d bitacora_db"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  web:
    build: .
    command: >
      sh -c "python manage.py migrate --noinput &&
             python manage.py runserver 0.0.0.0:8000"
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      USE_SQLITE: "False"
      DB_HOST: db
      DB_NAME: bitacora_db
      DB_USER: bitacora_user
      DB_PASSWORD: enterprise_password_2026
      DB_PORT: "5432"
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/1
      DJANGO_DEBUG: "True"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  worker:
    build: .
    command: celery -A bitacora_ee worker -l info
    volumes:
      - .:/app
    env_file:
      - .env
    environment:
      USE_SQLITE: "False"
      DB_HOST: db
      DB_NAME: bitacora_db
      DB_USER: bitacora_user
      DB_PASSWORD: enterprise_password_2026
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/1
    depends_on:
      - web
      - redis

  beat:
    build: .
    command: celery -A bitacora_ee beat -l info
    volumes:
      - .:/app
    env_file:
      - .env
    environment:
      USE_SQLITE: "False"
      DB_HOST: db
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/1
    depends_on:
      - worker

volumes:
  pgdata:
'@
$compose | Set-Content (Join-Path $ProjectRoot "docker-compose.yml") -Encoding UTF8
Write-Host "  ✓ docker-compose.yml" -ForegroundColor Green

# ── nginx.conf básico ────────────────────────────────────────
$nginxDir = Join-Path $ProjectRoot "nginx"
New-Item -ItemType Directory -Path $nginxDir -Force | Out-Null
$nginx = @'
upstream bitacora {
    server web:8000;
}

server {
    listen 80;
    server_name _;
    client_max_body_size 20M;

    location /static/ {
        alias /app/staticfiles/;
        expires 7d;
    }

    location /media/ {
        alias /app/media/;
    }

    location / {
        proxy_pass http://bitacora;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
'@
$nginx | Set-Content (Join-Path $nginxDir "nginx.conf") -Encoding UTF8
Write-Host "  ✓ nginx/nginx.conf" -ForegroundColor Green

# Recordatorio .env para Docker
Write-Host ""
Write-Host "  Para usar Docker, asegúrate de que .env tenga:" -ForegroundColor Yellow
Write-Host "    USE_SQLITE=False"
Write-Host "    DB_HOST=db"
Write-Host "    REDIS_URL=redis://redis:6379/0"
Write-Host ""
Write-Host "  Comandos:" -ForegroundColor Cyan
Write-Host "    docker compose up -d --build"
Write-Host "    docker compose logs -f web"
Write-Host "    docker compose down"
Write-Host ""
Write-Host "✓ Script 05 completado." -ForegroundColor Green
Write-Host ""
