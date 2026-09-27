# Bitácora E.E — Arquitectura de datos

## Panorama

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  BUSAE GPS  │────▶│   Poller     │────▶│  DatosBusae     │
│  (login)    │     │  (Celery)    │     │  ReportePendiente│
└─────────────┘     └──────┬───────┘     └────────┬────────┘
                           │                      │
┌─────────────┐            │                      ▼
│  Genesis    │────────────┘              ┌───────────────┐
│  JSON-RPC   │  patio + hora_entrada     │  Dashboard    │
└─────────────┘                           │  Atender ▶    │
                                          │  BitacoraReg. │
┌─────────────┐     import_matriz         └───────────────┘
│ MATRIZ.xlsx │──────────────────────────▶ InventarioFlota
│ FLOTA+EE    │                            DispositivoGPS
└─────────────┘
```

## Tablas principales

| Tabla | Origen | Rol |
|-------|--------|-----|
| **Patio** | seed | Catálogo 6 patios + COE |
| **Usuario** | GAS / admin | Técnicos, cuota, roles |
| **InventarioFlota** | MATRIZ.xlsx | Bus + placa + estado EE completo |
| **DispositivoGPS** | admin / CSV | IMEI, asignación a bus |
| **DatosBusae** | Poller BUSAE | GPS live |
| **DatosGenesis** | Poller / CSV manual | Patio, hora entrada |
| **ReportePendiente** | Poller (GPS offline) | Cola de atención |
| **BitacoraRegistro** | Formulario 2026 | Cada revisión |
| **HistorialAtencion** | Al atender | Archivo de reportes cerrados |
| **AuditLog** | Todo | Trazabilidad |
| **MovimientoFlota** | Flota/GPS | Alta, baja, asignar, mover |

## Formulario de atención (8 bloques)

1. **Tipo** — Inventario | Bitácora  
2. **Bus + Patio + Técnico**  
3. **GPS** — Funciona | Corto | Mojado  
4. **Vandalismo** — Ninguno | Pérdida GPS | Corte arnés | Robo SIM  
5. **SIMCARD** — Deterioro-Reemplazo  
6. **Adecuación eléctrica** — Adecuada | No adecuada  
7. **CTAP** — Funciona | Dañada | No tiene  
8. **Radio base** — matriz 5×5 (Conexión, Instalación, Perilla, Pedal, Pantalla)  
9. **Informe técnico** (texto obligatorio)

## Flujo de atención

1. Poller detecta bus offline → crea `ReportePendiente` (con patio/hora de Genesis)
2. Técnico ve lista → **Atender**
3. Formulario precarga bus + patio
4. Guarda `BitacoraRegistro` + marca reporte ATENDIDO + `HistorialAtencion`
5. Contador diario del técnico sube (día laboral desde 08:00)

## Arranque rápido

```powershell
python manage.py migrate
python manage.py seed_initial
python manage.py import_matriz .\data_matriz.xlsx
python manage.py runserver
```
