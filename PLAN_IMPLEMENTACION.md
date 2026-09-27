# Plan de Implementación — Bitácora E.E (Django)

**Versión:** 1.0  
**Fecha:** 2026-09-26  
**Objetivo:** App web robusta de bitácora de equipo embarcado, superior a Google Forms, con poller BUSAE/Genesis, matriz de flota, tickets y configuración central.

---

## 0. Visión del producto

El técnico entra con su código, ve **solo los buses de su patio** (o los asignados), con:

| TECNICO ASIGNADO | BUS | ESTADO GENESIS | ESTADO BUSAE | PATIO UBICACION | HORA DE ENTRADA | ACCION |
|------------------|-----|----------------|--------------|-----------------|-----------------|--------|

Pulsa **Atender** → formulario avanzado de revisión → se guarda bitácora, se actualiza flota y auditoría.

El admin configura todo el sistema, gestiona flota/GPS, ve tickets y reportes.

---

## 1. Estructura de datos objetivo (fuente de verdad)

### 1.1 USUARIOS
| Campo | Tipo | Notas |
|-------|------|-------|
| ID (codigo) | string PK | ej. 13283 |
| NOMBRE | string | |
| PATIO ASIGNADO | FK Patio | filtra la cola Bitácora |
| CONTRASEÑA | hash | login robusto |
| ROL | ADMIN / SUPERVISOR / TECNICO | |
| CUOTA DIARIA | int | |

### 1.2 BITACORA (vista cola, no tabla física única)
Se **calcula** cruzando:
- `InventarioFlota` (bus, tecnico_asignado)
- `DatosGenesis` (estado, patio, hora entrada)
- `DatosBusae` (estado GPS)
- Filtro: patio del usuario logueado (salvo admin)

### 1.3 DATOS BUSAE
bus, placa, estado, hora, manos_libres, telefono, latitud, longitud

### 1.4 DATOS GENESIS
Bus, Estado, PatioUbica, Origen, Destino, Opreal, Horafin, FechaEstado

### 1.5 FLOTA / MATRIZ EE
Todo lo de MATRIZ.xlsx (estado bocina, FW, adecuaciones, etc.)

### 1.6 BITACORA REGISTRO (formulario enviado)
Campos del form 2026 + trazabilidad

### 1.7 TICKETS
Problemas reportados por técnicos → admin

### 1.8 CONFIGURACION
Clave/valor JSON de todo lo configurable

---

## 2. Pilares técnicos (obligatorios en cada fase)

| Pilar | Cómo se aplica |
|-------|----------------|
| **Seguridad** | Passwords hasheados (PBKDF2/Argon2), CSRF, sesiones seguras, rate-limit login, roles, HTTPS en prod, secrets en .env, audit log |
| **Rendimiento** | Índices DB, select_related/prefetch, paginación, caché Redis, poller async (Celery) |
| **Renderizado** | Templates ligeros, JS modular, Bootstrap 5, carga diferida de tablas grandes |
| **Optimización** | Queries N+1 evitadas, CSV/Excel en streaming, static con WhiteNoise/CDN |
| **Buenas prácticas** | Apps por dominio, services.py, forms.py, tests, type hints donde aporte, sin lógica pesada en templates |
| **Privacidad** | Política de privacidad visible, mínimo de datos personales, logs sin contraseñas, retención configurable |
| **Manejo de errores** | try/except en poller y APIs, mensajes claros al usuario, Sentry opcional, códigos HTTP correctos |

---

## 3. Módulos del sistema

```
01 AUTH + ROLES
02 BITACORA (cola + atender)
03 FORMULARIO AVANZADO (motor de edición)
04 FLOTA + MATRIZ + GPS
05 POLLER BUSAE + GENESIS
06 CONFIGURACIÓN GLOBAL
07 TICKETS / SOPORTE
08 RESUMEN + REPORTES
09 AUDITORÍA
10 ADMIN DJANGO + HARDENING
```

---

## 4. Lista de tareas (checklist de avance)

Marca `[x]` cuando esté hecho. Orden recomendado de construcción.

### FASE 0 — Cimientos (semana 1)
- [ ] **T0.1** Crear proyecto Django + apps `buses`, `poller`, `soporte`, `configuracion`
- [ ] **T0.2** settings: Postgres/SQLite, Redis, TZ America/Panama, .env, logging
- [ ] **T0.3** Modelos base: Patio, Usuario (con password hash + patio_asignado + rol), ConfiguracionSistema
- [ ] **T0.4** seed_initial: 6 patios + usuarios admin
- [ ] **T0.5** Login robusto (código + password, bloqueo, sesión 8h, audit)
- [ ] **T0.6** Script PowerShell de bootstrap (`scripts/bootstrap.ps1`)
- [ ] **T0.7** README + política de privacidad estática (`/privacidad/`)

### FASE 1 — Datos maestros (semana 1-2)
- [ ] **T1.1** Modelo InventarioFlota completo (matriz EE + tecnico_asignado)
- [ ] **T1.2** Comando `import_matriz` (MATRIZ.xlsx)
- [ ] **T1.3** Modelos DatosBusae + DatosGenesis
- [ ] **T1.4** Import CSV/Excel de BUSAE y Genesis de prueba
- [ ] **T1.5** DispositivoGPS + MovimientoFlota
- [ ] **T1.6** Admin Django con list filters y búsqueda

### FASE 2 — Bitácora cola + Atender (semana 2)
- [ ] **T2.1** API `GET /api/bitacora/cola/` (cruce flota+genesis+busae)
- [ ] **T2.2** Filtro automático por `patio_asignado` del usuario (admin ve todo)
- [ ] **T2.3** UI tabla: TECNICO | BUS | ESTADO GENESIS | ESTADO BUSAE | PATIO | HORA | ACCION
- [ ] **T2.4** Modelo BitacoraRegistro (campos form 2026)
- [ ] **T2.5** POST guardar bitácora + contador diario + audit
- [ ] **T2.6** Al guardar: opcional actualizar campos EE en InventarioFlota
- [ ] **T2.7** ReportePendiente + Historial (cierre al atender desde reportes GPS)

### FASE 3 — Motor de formulario avanzado (semana 2-3)
> Objetivo: superar Google Forms en UX y control.

- [ ] **T3.1** Definición JSON del formulario (secciones, tipos de campo, validaciones, obligatoriedad condicional)
- [ ] **T3.2** Motor de render: radio, select, matriz (grid), texto, número, fecha, archivo
- [ ] **T3.3** Lógica condicional (ej. si GPS=MOJADO → mostrar campos extra)
- [ ] **T3.4** Validación cliente + servidor
- [ ] **T3.5** Guardado parcial / borrador (opcional)
- [ ] **T3.6** Plantillas de formulario versionables (admin puede clonar/editar estructura sin deploy)
- [ ] **T3.7** Preview en vivo del formulario (admin)
- [ ] **T3.8** Formulario 2026 como primera plantilla cargada por seed

### FASE 4 — Poller (semana 3)
- [x] **T4.1** busae_client + busae_parse + busae_service alineados a modelos
- [x] **T4.2** genesis_service: patio/hora precisos (Inoperativo→origen; En Via→destino/horafin) y sincronización con InventarioFlota
- [x] **T4.3** Celery + Redis: tasks periódicas (`poller.tasks`, `bitacora_ee.celery`, comando `run_poller`)
- [x] **T4.4** Health checks (`api/poller/health/`, persistencia en `ConfiguracionSistema` y caché)
- [x] **T4.5** Carga manual Genesis/BUSAE por CSV en UI admin (`/api/genesis/import/`, `/api/busae/import/`)
- [x] **T4.6** No crear reportes si bus DESCARTADO/BAJA o UnidadFueraServicio

### FASE 5 — Configuración global (semana 3-4)
- [x] **T5.1** Pantalla `/config/` (solo admin) — sección en dashboard con tabs
- [x] **T5.2** Parámetros: cuota default, horarios día laboral (corte 8am), interval poller, textos UI
- [x] **T5.3** Credenciales externas cifradas o solo por .env (nunca en front)
- [x] **T5.4** Feature flags (activar tickets, activar borradores, activar Excel)
- [x] **T5.5** Lista de patios editable (CRUD completo: crear, editar, eliminar/desactivar)
- [x] **T5.6** Opciones del formulario editables — config `bitacora_solo_mi_patio`, cuota, corte hora

### FASE 6 — Tickets / soporte (semana 4)
- [x] **T6.1** Modelo Ticket: titulo, descripcion, prioridad, estado, creado_por, asignado_a, bus_relacionado opcional
- [x] **T6.2** Técnico: “Reportar problema” desde cualquier pantalla
- [x] **T6.3** Admin: bandeja de tickets, cambiar estado, comentar
- [x] **T6.4** Notificación opcional email/Slack al crear ticket
- [x] **T6.5** Audit de cambios de ticket

### FASE 7 — Resumen, seguridad y hardening (semana 4-5)
- [ ] **T7.1** Dashboard resumen + gráficos
- [ ] **T7.2** Export Excel bitácoras / reportes
- [ ] **T7.3** Rate limit, headers seguridad, CSRF, cookies secure
- [ ] **T7.4** Página Política de privacidad + términos de uso
- [ ] **T7.5** Manejo de errores 400/403/404/500 amigables
- [ ] **T7.6** Tests críticos (login, cola, guardar bitácora, import matriz)
- [ ] **T7.7** Docker Compose (web + postgres + redis + worker)
- [ ] **T7.8** Script de deploy PowerShell documentado

---

## 5. Motor de formulario avanzado (detalle)

No es un Google Form embebido: es un **motor propio**.

### Idea
1. Admin define (o seed carga) un `FormularioPlantilla` en JSON.
2. El front renderiza según el JSON.
3. Las respuestas se guardan normalizadas en `BitacoraRegistro` (campos fijos 2026) + `respuestas_json` para campos extra futuros.

### Tipos de campo soportados (v1)
- `single_choice` (radio / botones)
- `select`
- `text` / `textarea`
- `number`
- `matrix` (filas × columnas, como Radio base)
- `file` (foto opcional, fase 2)

### Ejemplo de definición (simplificado)
```json
{
  "id": "revision_2026",
  "version": 1,
  "sections": [
    {
      "title": "GPS",
      "fields": [
        {
          "key": "gps",
          "type": "single_choice",
          "label": "Estado GPS",
          "required": true,
          "options": ["FUNCIONA", "CORTO", "MOJADO"]
        }
      ]
    },
    {
      "title": "Radio base",
      "fields": [
        {
          "key": "radio",
          "type": "matrix",
          "rows": ["CONEXION", "INSTALACION", "PERILLA", "PEDAL", "PANTALLA"],
          "columns": ["SIMCARD", "SI", "NO", "FUNCIONA", "DAÑADA"]
        }
      ]
    }
  ]
}
```

### Ventajas vs Google Forms
- Integrado a buses, patios, cuota, auditoría
- Condicionales y validaciones de negocio
- Actualiza flota al enviar
- Offline-ready futuro (PWA)
- Versionado de plantillas
- Sin dependencia de Google / privacidad de datos en tu servidor

---

## 6. Módulo de configuración (qué se puede configurar)

| Área | Ejemplos |
|------|----------|
| General | Nombre app, logo URL, zona horaria |
| Turnos | Hora corte contador diario (08:00) |
| Poller | Intervalo minutos, activar/desactivar BUSAE o Genesis |
| Bitácora | Cuota default, mostrar solo patio propio sí/no |
| Formulario | Opciones de listas, plantilla activa |
| Seguridad | Intentos login, minutos bloqueo, duración sesión |
| Tickets | Categorías, prioridades, email destino |
| Privacidad | Texto política, días retención logs |

Todo en `ConfiguracionSistema` (clave → JSON) + UI admin.

---

## 7. Módulo de tickets

**Estados:** ABIERTO → EN_PROGRESO → RESUELTO → CERRADO  

**Campos:** id, titulo, descripcion, prioridad (BAJA/MEDIA/ALTA), categoria, bus_movil opcional, creado_por, asignado_a, creado_en, actualizado_en, comentarios[]

**UI técnico:** botón flotante o menú “Reportar problema”.  
**UI admin:** lista + detalle + cambio de estado.

---

## 8. Scripts que usaremos (sin errores)

Todos bajo `scripts/`:

| Script | Función |
|--------|---------|
| `bootstrap.ps1` | venv, pip, migrate, seed, runserver |
| `import_all.ps1` | matriz + opcional genesis/busae de prueba |
| `run_poller.ps1` | un ciclo Genesis → BUSAE |
| `check_health.ps1` | migrate --check, tests rápidos |
| `reset_dev.ps1` | cuidado: borra sqlite y re-seed (solo dev) |

Cada fase del plan se ejecuta con comandos concretos que yo te iré dando para copiar/pegar en PowerShell 7.

---

## 9. Criterios de “terminado” por fase

| Fase | Criterio de aceptación |
|------|------------------------|
| 0 | Login con 13283 / admin123, dashboard carga |
| 1 | Matriz importada, se ven buses en admin |
| 2 | Cola Bitácora muestra cruce real; Atender guarda registro |
| 3 | Formulario renderizado por plantilla JSON; validaciones OK |
| 4 | Poller actualiza BUSAE/Genesis; reportes offline aparecen |
| 5 | Admin cambia cuota/corte horario desde UI y aplica |
| 6 | Técnico crea ticket; admin lo resuelve |
| 7 | Export, privacidad, docker, tests verdes |

---

## 10. Orden de construcción acordado

```
FASE 0  Cimientos + scripts bootstrap
   ↓
FASE 1  Datos maestros (usuarios con patio, flota, busae, genesis)
   ↓
FASE 2  Cola Bitácora + Atender (estructura exacta del Excel)
   ↓
FASE 3  Motor formulario avanzado
   ↓
FASE 4  Poller automático
   ↓
FASE 5  Configuración global
   ↓
FASE 6  Tickets
   ↓
FASE 7  Hardening + deploy
```

---

## 11. Decisiones ya tomadas (contexto conversación)

1. UI estilo admin dashboard (Bootstrap), no Apps Script.
2. Cola Bitácora = vista calculada (no solo Reportes offline).
3. Usuario tiene **patio asignado** → filtra cola.
4. Formulario alineado a “Revisión Equip. Embarcado 2026”.
5. Matriz Excel es fuente de estado EE de flota.
6. Genesis da patio/hora; BUSAE da estado GPS.
7. PowerShell 7 + ruta `C:\Proyectos\bitacora_ee`.
8. Seguridad, auditoría y configuración son de primera clase.

---

## 12. Próximo paso inmediato

**Empezar FASE 0** con el script `bootstrap.ps1` y ajustar modelos a:

- Usuario: `patio_asignado`, `password` (hash), `rol`
- Cola Bitácora columnas exactas del Excel nuevo
- App `soporte` (tickets) y ampliación de configuración

Cuando confirmes, genero los scripts PowerShell y el código de la FASE 0 listos para ejecutar paso a paso.
