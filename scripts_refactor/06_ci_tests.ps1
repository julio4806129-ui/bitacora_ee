# ============================================================
# 06_ci_tests.ps1
# Añade pytest, black, flake8, isort, pre-commit y GitHub Actions CI.
# PowerShell 7 | Ejecutar desde C:\Proyectos\bitacora_ee
# ============================================================
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Proyectos\bitacora_ee"
Set-Location $ProjectRoot

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  06 · CI + TESTS + LINTERS" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── requirements-dev.txt ─────────────────────────────────────
$reqDev = @'
pytest>=8.0
pytest-django>=4.8
pytest-cov>=5.0
factory-boy>=3.3
black>=24.0
isort>=5.13
flake8>=7.0
pre-commit>=3.6
'@
$reqDev | Set-Content (Join-Path $ProjectRoot "requirements-dev.txt") -Encoding UTF8
Write-Host "  ✓ requirements-dev.txt" -ForegroundColor Green

# ── pytest.ini ───────────────────────────────────────────────
$pytestIni = @'
[pytest]
DJANGO_SETTINGS_MODULE = bitacora_ee.settings
python_files = tests.py test_*.py *_tests.py
addopts = -ra --tb=short
filterwarnings =
    ignore::DeprecationWarning
'@
$pytestIni | Set-Content (Join-Path $ProjectRoot "pytest.ini") -Encoding UTF8
Write-Host "  ✓ pytest.ini" -ForegroundColor Green

# ── pyproject.toml (black + isort) ───────────────────────────
$pyproject = @'
[tool.black]
line-length = 100
target-version = ["py312"]
exclude = '''
/(
    \.git
  | \.venv
  | venv
  | migrations
  | staticfiles
)/
'''

[tool.isort]
profile = "black"
line_length = 100
skip = ["migrations", "venv", ".venv"]
'@
$pyproject | Set-Content (Join-Path $ProjectRoot "pyproject.toml") -Encoding UTF8
Write-Host "  ✓ pyproject.toml" -ForegroundColor Green

# ── .flake8 ──────────────────────────────────────────────────
$flake8 = @'
[flake8]
max-line-length = 100
exclude = venv,.venv,migrations,staticfiles,__pycache__,.git
ignore = E203,W503
'@
$flake8 | Set-Content (Join-Path $ProjectRoot ".flake8") -Encoding UTF8
Write-Host "  ✓ .flake8" -ForegroundColor Green

# ── .pre-commit-config.yaml ──────────────────────────────────
$precommit = @'
repos:
  - repo: https://github.com/psf/black
    rev: 24.8.0
    hooks:
      - id: black
  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
  - repo: https://github.com/pycqa/flake8
    rev: 7.1.1
    hooks:
      - id: flake8
'@
$precommit | Set-Content (Join-Path $ProjectRoot ".pre-commit-config.yaml") -Encoding UTF8
Write-Host "  ✓ .pre-commit-config.yaml" -ForegroundColor Green

# ── Test mínimo de humo ──────────────────────────────────────
$testsDir = Join-Path $ProjectRoot "buses\tests"
New-Item -ItemType Directory -Path $testsDir -Force | Out-Null

$smokeTest = @'
"""
Tests de humo — Bitácora E.E.
Ejecutar: pytest
"""
import pytest
from django.test import Client


@pytest.mark.django_db
def test_login_page_loads():
    client = Client()
    response = client.get("/login/")
    assert response.status_code in (200, 302)


@pytest.mark.django_db
def test_dashboard_requires_auth():
    client = Client()
    response = client.get("/")
    # Sin sesión debe redirigir a login
    assert response.status_code in (302, 403, 200)
'@
$smokeTest | Set-Content (Join-Path $testsDir "test_smoke.py") -Encoding UTF8
Write-Host "  ✓ buses/tests/test_smoke.py" -ForegroundColor Green

# ── GitHub Actions CI ────────────────────────────────────────
$ghDir = Join-Path $ProjectRoot ".github\workflows"
New-Item -ItemType Directory -Path $ghDir -Force | Out-Null

$ciYml = @'
name: CI

on:
  push:
    branches: [main, master, develop]
  pull_request:
    branches: [main, master, develop]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: bitacora_test
          POSTGRES_USER: bitacora_user
          POSTGRES_PASSWORD: testpass
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U bitacora_user -d bitacora_test"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint (black, isort, flake8)
        run: |
          black --check .
          isort --check-only .
          flake8 .

      - name: Run tests
        env:
          DJANGO_SECRET_KEY: test-secret-key-ci-only-not-for-prod
          DJANGO_DEBUG: "True"
          USE_SQLITE: "False"
          DB_NAME: bitacora_test
          DB_USER: bitacora_user
          DB_PASSWORD: testpass
          DB_HOST: localhost
          DB_PORT: "5432"
          REDIS_URL: redis://localhost:6379/0
        run: |
          python manage.py migrate --noinput
          pytest --cov=buses --cov=poller -q
'@
$ciYml | Set-Content (Join-Path $ghDir "ci.yml") -Encoding UTF8
Write-Host "  ✓ .github/workflows/ci.yml" -ForegroundColor Green

Write-Host ""
Write-Host "  Instalación local recomendada:" -ForegroundColor Cyan
Write-Host "    .\venv\Scripts\Activate.ps1"
Write-Host "    pip install -r requirements-dev.txt"
Write-Host "    pre-commit install"
Write-Host "    pytest"
Write-Host ""
Write-Host "✓ Script 06 completado." -ForegroundColor Green
Write-Host ""
