# Bitácora E.E - MiBus

Sistema web de bitácora de revisiones diarias de equipos electrónicos (BUSAE) convertido desde Google Apps Script a **Django + PostgreSQL**.

## Características

- Login por código de técnico (como el GAS original)
- Reportes de GPS Offline (generados por poller BUSAE + Genesis)
- Inventario de flota
- Formulario de bitácora de componentes (Modem, Bocina, SIM, CTAP, etc.)
- Resumen con gráficos (Google Charts)
- Gestión de usuarios (admin)
- Poller automático BUSAE (GPS) + Genesis (patio/hora)
- UI moderna inspirada en dashboards Bootstrap admin

## Requisitos

- Python 3.11+
- PostgreSQL 14+ (o SQLite para desarrollo)
- Redis (para Celery / caché)
- PowerShell 7.6+

## Instalación en Windows (PowerShell 7)

```powershell
# 1. Crear carpeta del proyecto
New-Item -ItemType Directory -Path "C:\Proyectos\bitacora_ee" -Force
Set-Location "C:\Proyectos\bitacora_ee"

# 2. Copiar todos los archivos del proyecto a esta carpeta
# (o clonar desde GitHub cuando esté listo)

# 3. Crear entorno virtual
python -m venv venv
.\venv\Scripts\Activate.ps1

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Configurar .env (copiar y ajustar)
Copy-Item .env.example .env   # o editar el .env existente
# Editar DB_*, BUSAE_*, GENESIS_* según tu entorno
# Para desarrollo local con SQLite:
# USE_SQLITE=True

# 6. Migraciones
python manage.py makemigrations buses
python manage.py migrate

# 7. Crear superusuario Django (opcional, para /admin/)
python manage.py createsuperuser

# 8. Cargar usuarios iniciales (códigos admin del GAS)
python manage.py shell -c "
from buses.models import Usuario
admins = [('13283','Admin 13283',10,True),('10844','Admin 10844',10,True),('9335','Admin 9335',10,True),('12517','Admin 12517',10,True),('12505','Admin 12505',10,True)]
for c,n,q,a in admins:
    Usuario.objects.update_or_create(codigo=c, defaults={'nombre':n,'cuota_diaria':q,'is_admin':a})
print('Usuarios admin cargados')
"

# 9. Ejecutar servidor de desarrollo
python manage.py runserver 0.0.0.0:8000
```

Abrir en el navegador: http://localhost:8000  
Login con código de admin (ej. `10844`).

## Poller (BUSAE + Genesis)

El poller se puede ejecutar manualmente o con Celery Beat:

```powershell
# Manual (un ciclo)
python manage.py shell -c "from poller.scheduler import run_now; print(run_now())"

# O con APScheduler (si se habilita en scheduler.py)
# Por defecto está desactivado a favor de Celery Beat
```

Configurar credenciales en `.env` o en el modelo `ConfiguracionSistema`.

## Estructura

```
bitacora_ee/          # Settings del proyecto
buses/                # App principal (modelos, vistas, templates)
  models.py           # Usuario, ReportePendiente, BitacoraRegistro, etc.
  views.py            # Login, dashboard, APIs
  bus_number.py       # Utilidades de número de bus
poller/               # Sincronización externa
  busae_client.py     # HTTP + Playwright login BUSAE
  busae_parse.py      # Normalización JSON BUSAE
  busae_service.py    # Guardado + generación de reportes
  genesis_service.py  # JSON-RPC Genesis
  scheduler.py        # Orquestación
  utils.py            # Helpers de cruce
templates/            # HTML (Bootstrap 5)
static/               # CSS/JS
```

## Mapeo GAS → Django

| GAS (hoja / función)       | Django                          |
|----------------------------|---------------------------------|
| Usuarios                   | `Usuario`                       |
| Reportes                   | `ReportePendiente`              |
| Historial                  | `HistorialAtencion`             |
| RepuestasForms             | `BitacoraRegistro`              |
| Inventario                 | `InventarioItem` / `EEMovil`    |
| getUserInfo / login        | `login_view` + session          |
| guardarBitacoraYAtender    | `api_guardar_bitacora`          |
| obtenerDatosDeReportes     | `api_reportes`                  |
| getContador / getCuotaDiaria | `get_contador_hoy`            |

## GitHub

```powershell
git init
git add .
git commit -m "Initial: Bitácora E.E Django conversion from GAS"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/bitacora-ee.git
git push -u origin main
```

## Producción (resumen)

- PostgreSQL + Redis
- Gunicorn + Nginx
- Celery worker + beat para el poller
- Variables de entorno seguras (nunca subir `.env` con passwords reales)

---
Convertido desde Google Apps Script · MiBus E.E

## Módulos avanzados (v2)

### Formulario Revisión Equip. Embarcado 2026
Campos alineados al Google Form:
- Tipo: Inventario / Bitácora
- Patio (6 opciones)
- GPS (Funciona / Corto / Mojado)
- Vandalismo, SIMCARD, Adecuación eléctrica
- Matriz Radio Base (Conexión, Instalación, Perilla, Pedal, Pantalla)
- CTAP, Informe técnico

### Flota / Buses
- Alta, baja, cambio de patio, cambio de estado
- Import CSV: `bus_movil,placa,patio,estado,marca_modelo,anio`

### Dispositivos GPS
- Alta, asignar a bus, desasignar, baja
- Import CSV: `imei,serie,modelo,telefono,bus_movil,estado`

### Genesis manual
- Cuando el poller o la VPN fallen
- CSV: `bus_movil,origen,destino,patio,hora_entrada,estado,ruta`
- Actualiza patio en EEMovil y reportes pendientes

### Auditoría
- Login/logout, altas, bajas, asignaciones, atenciones, importaciones
- Filtros por acción, usuario, fecha
- IP y user-agent

### Login robusto
- Bloqueo tras 5 intentos fallidos (15 min)
- Sesión de 8 horas
- Password opcional si hay User Django vinculado

## Importar MATRIZ.xlsx

El archivo tiene dos hojas:

| Hoja | Contenido |
|------|-----------|
| **MATRIZ FLOTA** | COE (patio), BUS, PLACA |
| **BUSES TMP** | Estado completo EE: Genesis, Sistema, BUSAE, FW, Bocina, Adecuaciones, Anclaje, Comentarios, Meses |

```powershell
# Desde PowerShell (con venv activo)
python manage.py makemigrations buses
python manage.py migrate
python manage.py seed_initial
python manage.py import_matriz .\data_matriz.xlsx

# O desde la UI (admin): Flota → botón "Matriz Excel"
```

Campos que se cargan en cada bus:
- Patio base (desde COE: P-NDONA→La Doña, P-CHORRILLO→Chorrillo, etc.)
- estado_genesis, estado_sistema, sistema_instalado, estado_busae
- estado_fw, estado_bocina, adecuacion_bocina, adecuacion_electrica
- anclaje_bocinas, comentarios, mes_instalado, mes_revisado
- estado_operativo se deriva automáticamente (DESCARTADO / POR_INSTALAR / MANTENIMIENTO / ACTIVO)
