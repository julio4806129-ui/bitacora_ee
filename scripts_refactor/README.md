# Scripts de refactor — Bitácora E.E.

Pack de scripts PowerShell 7 para aplicar mejoras de arquitectura, seguridad, Docker y CI **sin editar a mano**.

## Requisitos

- PowerShell 7 (`pwsh`)
- Proyecto en: `C:\Proyectos\bitacora_ee\`
- (Opcional) Git, Docker Desktop, venv Python

## Instalación de los scripts

1. Copia **toda** la carpeta `scripts_refactor` dentro de:

```
C:\Proyectos\bitacora_ee\scripts_refactor\
```

2. Abre PowerShell 7 en esa ruta:

```powershell
cd C:\Proyectos\bitacora_ee
pwsh
```

## Ejecución

### Opción A — Todo de una vez

```powershell
.\scripts_refactor\RUN_ALL.ps1
```

### Opción B — Uno por uno (recomendado la primera vez)

```powershell
.\scripts_refactor\00_backup.ps1
.\scripts_refactor\01_seguridad_gitignore.ps1
.\scripts_refactor\02_settings_seguridad.ps1
.\scripts_refactor\03_estructura_apps.ps1
.\scripts_refactor\04_dividir_views.ps1      # el más delicado
.\scripts_refactor\05_docker_scaffold.ps1
.\scripts_refactor\06_ci_tests.ps1
```

### Opción C — Saltar o detener

```powershell
# Solo hasta el 03
.\scripts_refactor\RUN_ALL.ps1 -Until 3

# Saltar el 04 (dividir views)
.\scripts_refactor\RUN_ALL.ps1 -Skip 4
```

## Qué hace cada script

| Script | Acción | Riesgo |
|--------|--------|--------|
| **00** | Backup completo a `C:\Proyectos\backups_bitacora_ee\` | Ninguno |
| **01** | `.gitignore` profesional + untrack de `.env`, `db.sqlite3`, etc. | Bajo |
| **02** | Cabeceras HTTPS/HSTS/CSP en `settings.py` (solo si `DEBUG=False`) | Bajo |
| **03** | Crea `apps/` (core, usuarios, flota…) + `services.py` / `selectors.py` | Bajo |
| **04** | Divide `buses/views.py` en `buses/views/*.py` por dominio | **Medio** |
| **05** | `Dockerfile`, `docker-compose.yml`, `nginx/nginx.conf` | Bajo |
| **06** | pytest, black, flake8, pre-commit, GitHub Actions CI | Bajo |

## Si el script 04 falla

```powershell
Copy-Item buses\views.py.bak buses\views.py -Force
Remove-Item -Recurse -Force buses\views
python manage.py check
```

## Verificación después del pack

```powershell
cd C:\Proyectos\bitacora_ee
.\venv\Scripts\Activate.ps1
python manage.py check
python manage.py migrate
pip install -r requirements-dev.txt
pytest -q
```

## Docker (después del script 05)

```powershell
# Ajusta .env: USE_SQLITE=False, DB_HOST=db, REDIS_URL=redis://redis:6379/0
docker compose up -d --build
docker compose logs -f web
```

## Notas

- Los scripts **no borran datos de negocio**. El 01 solo deja de trackear secretos en Git.
- El 04 hace backup en `buses\views.py.bak` antes de partir el monolito.
- Tras el 01, haz commit de `.gitignore` cuando estés listo.
'@
