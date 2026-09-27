# Departamentos virtuales — Bitácora E.E

Cada departamento tiene **misión**, **skills**, **roles** y **tareas** del plan.
No avanzamos de fase hasta que el departamento responsable cierre su checklist.

---

## Organigrama

```
                    ┌─────────────────────┐
                    │  DIR. DE PROYECTO   │
                    │  (Orquestación)     │
                    └──────────┬──────────┘
         ┌───────────┬─────────┼─────────┬───────────┐
         ▼           ▼         ▼         ▼           ▼
   ┌──────────┐ ┌────────┐ ┌───────┐ ┌────────┐ ┌─────────┐
   │ARQUITEC- │ │BACKEND │ │FRONTEND│ │DATOS & │ │SEGURIDAD│
   │TURA      │ │        │ │UX      │ │POLLER  │ │& CALIDAD│
   └──────────┘ └────────┘ └───────┘ └────────┘ └─────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              ┌──────────┐        ┌──────────┐
              │OPS &     │        │SOPORTE & │
              │DEPLOY    │        │CONFIG    │
              └──────────┘        └──────────┘
```

---

## 1. Dirección de Proyecto (DIR)

| | |
|--|--|
| **Misión** | Orden de fases, criterios de “hecho”, no saltar pasos |
| **Skills** | Planificación, priorización, aceptación |
| **Roles** | Project Lead |
| **Entrega** | `PLAN_IMPLEMENTACION.md`, `AVANCE.md`, go/no-go por fase |

**Regla de oro:** no se inicia Fase N+1 si Fase N tiene tareas críticas abiertas.

---

## 2. Arquitectura (ARQ)

| | |
|--|--|
| **Misión** | Modelos, límites de apps, contratos API, pilares técnicos |
| **Skills** | Django domain design, normalización, índices, versionado de schemas |
| **Roles** | Architect, Data Modeler |
| **Fases** | 0 (modelos base), 1 (flota/busae/genesis), 3 (schema formulario JSON), 5 (config) |

**Skills concretas**
- Diseño de `Usuario` (código, password hash, patio, rol)
- Separación apps: `buses`, `poller`, `soporte`, `configuracion`
- Contratos: cola Bitácora 7 columnas, plantilla formulario versionable

---

## 3. Backend (BE)

| | |
|--|--|
| **Misión** | Views, services, commands, Celery, reglas de negocio |
| **Skills** | Django views/APIs, transactions, Celery, import Excel/CSV |
| **Roles** | Backend Dev, API Owner |
| **Fases** | 0–7 (núcleo en 0, 2, 4, 6) |

**Skills concretas**
- Login con bloqueo y audit
- `api_bitacora_cola` (cruce flota+genesis+busae)
- Guardar bitácora + contador + feedback a flota
- Tickets CRUD
- Management commands (`seed`, `import_matriz`)

---

## 4. Frontend / UX (FE)

| | |
|--|--|
| **Misión** | Pantallas claras, formulario avanzado, rendimiento de render |
| **Skills** | Bootstrap 5, JS modular, accesibilidad, matrices/forms dinámicos |
| **Roles** | Frontend Dev, UX |
| **Fases** | 0 (login/shell), 2 (tabla bitácora), 3 (motor forms), 5–6 (config/tickets UI) |

**Skills concretas**
- Tabla Bitácora (7 columnas + Atender)
- Motor de render por JSON (radios, select, matrix, condicionales)
- Loading, toasts, errores legibles
- Responsive / mobile usable en patio

---

## 5. Datos & Poller (DATA)

| | |
|--|--|
| **Misión** | BUSAE, Genesis, matriz, consistencia de estados |
| **Skills** | HTTP/Playwright, JSON-RPC, openpyxl, normalización, idempotencia |
| **Roles** | Integration Engineer |
| **Fases** | 1 (imports), 4 (poller Celery) |

**Skills concretas**
- `busae_client` / `busae_parse` / `genesis_service`
- Reglas patio/hora (Inoperativo, En Via, Horafin)
- No crear reportes si bus BAJA/DESCARTADO
- Health: última sync OK/FAIL

---

## 6. Seguridad & Calidad (SEC)

| | |
|--|--|
| **Misión** | Auth, roles, privacidad, errores, tests |
| **Skills** | OWASP básico, hashing, CSRF, rate limit, pytest/Django tests |
| **Roles** | Security Reviewer, QA |
| **Fases** | 0 (login), continuo, cierre en 7 |

**Skills concretas**
- Passwords hasheados, nunca en claro en API
- Roles: ADMIN / SUPERVISOR / TECNICO
- Política de privacidad
- Páginas 403/404/500
- Tests: login, cola, guardar bitácora, import

---

## 7. Ops & Deploy (OPS)

| | |
|--|--|
| **Misión** | Scripts PowerShell, Docker, entornos, backups |
| **Skills** | PowerShell 7, Docker Compose, Gunicorn, env management |
| **Roles** | DevOps |
| **Fases** | 0 (bootstrap), 7 (docker/deploy) |

**Skills concretas**
- `scripts/bootstrap.ps1`, `import_all.ps1`, `run_poller.ps1`
- Compose: web + postgres + redis + worker
- Documentar restore y variables .env

---

## 8. Soporte & Configuración (CFG)

| | |
|--|--|
| **Misión** | Config global + tickets |
| **Skills** | Feature flags, catálogos editables, workflow tickets |
| **Roles** | Product Config, Support Module Owner |
| **Fases** | 5 (config), 6 (tickets) |

**Skills concretas**
- UI `/config/` (cuotas, corte 8am, interval poller, opciones form)
- Ticket: abrir → en progreso → resuelto
- Notificación admin (email/Slack opcional)

---

## Matriz RACI por fase (resumen)

| Fase | Lead | Apoyan | Criterio de salida |
|------|------|--------|--------------------|
| 0 Cimientos | ARQ + BE | FE, SEC, OPS | Login OK + seed + bootstrap |
| 1 Datos maestros | DATA + BE | ARQ | Matriz + modelos busae/genesis |
| 2 Cola Bitácora | BE + FE | ARQ | Tabla 7 cols + Atender guarda |
| 3 Form avanzado | FE + BE | ARQ, CFG | Plantilla JSON renderiza y valida |
| 4 Poller | DATA | BE, OPS | Sync automática + health |
| 5 Config | CFG | BE, FE | Admin cambia params en UI |
| 6 Tickets | CFG | BE, FE, SEC | Flujo ticket completo |
| 7 Hardening | SEC + OPS | todos | Tests + docker + privacidad |

---

## Protocolo de avance

1. **DIR** declara inicio de fase.
2. Departamentos ejecutan solo sus tareas de esa fase.
3. **SEC** revisa seguridad mínima antes de cerrar.
4. **DIR** marca `AVANCE.md` y autoriza siguiente fase.

---

## Estado actual

| Departamento | Estado |
|--------------|--------|
| DIR | Plan y departamentos definidos |
| ARQ / BE / FE / DATA / SEC / OPS / CFG | Listos para **FASE 0** |
