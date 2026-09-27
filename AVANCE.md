# Avance del proyecto Bitácora E.E

| ID | Tarea | Depto | Estado | Fecha |
|----|-------|-------|--------|-------|
| T0.1 | Proyecto Django + apps | ARQ/OPS | ✅ Hecho (base previa) | 2026-09-25 |
| T0.2 | Settings (.env, TZ, logging) | ARQ | ✅ Hecho (base previa) | 2026-09-25 |
| T0.3 | Modelos Patio/Usuario/Config (password, rol, patio_asignado) | ARQ/BE | ✅ Hecho | 2026-09-26 |
| T0.4 | seed_initial (patios, users, config) | BE | ✅ Hecho | 2026-09-26 |
| T0.5 | Login robusto (password obligatorio, sesión, audit) | BE/SEC | ✅ Hecho | 2026-09-26 |
| T0.6 | bootstrap.ps1 | OPS | ✅ Hecho | 2026-09-26 |
| T0.7 | Privacidad + enlace en login | SEC | ✅ Hecho | 2026-09-26 |
| T1.1 | InventarioFlota | DATA/ARQ | ⬜ Pendiente | |
| T1.2 | import_matriz | DATA | 🟡 Existe (validar post-migrate) | |
| T1.3 | DatosBusae + DatosGenesis | DATA | 🟡 Modelos listos | |
| T1.4 | Import prueba BUSAE/Genesis | DATA | ⬜ Pendiente | |
| T1.5 | DispositivoGPS | DATA | 🟡 Modelos listos | |
| T1.6 | Admin Django | BE | 🟡 Parcial | |
| T2.1–T2.7 | Cola Bitácora + Atender | BE/FE | 🟡 Parcial (ajustar filtro patio) | |
| T3.x | Motor formulario avanzado | FE/BE | ⬜ Pendiente | |
| T4.x | Poller | DATA | ⬜ Pendiente | |
| T5.x | Configuración UI | CFG | ⬜ Pendiente | |
| T6.x | Tickets | CFG | ⬜ Pendiente | |
| T7.x | Hardening + deploy | SEC/OPS | ⬜ Pendiente | |

**Leyenda:** ⬜ Pendiente · 🟡 En curso · ✅ Hecho · ⛔ Bloqueado

## FASE 0 — Criterio de cierre

- [x] Usuario con rol, patio_asignado, password_hash
- [x] Login exige contraseña + bloqueo + audit
- [x] seed crea 13283/admin123
- [x] /privacidad/ publicada
- [x] bootstrap.ps1 disponible
- [ ] **Pendiente en tu PC:** `makemigrations` + `migrate` + `seed_initial` + probar login

## Notas
- Departamentos: ver `DEPARTAMENTOS.md`
- Plan: ver `PLAN_IMPLEMENTACION.md`
- Tras migrar en Windows, marcar FASE 0 cerrada y pasar a T1/T2 (filtro patio en cola)
