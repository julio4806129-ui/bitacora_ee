# Apps — Dominios de Bitácora E.E.

Esta carpeta es el **scaffold** de la arquitectura modular.

| App | Responsabilidad |
|-----|-----------------|
| core | Patio, ConfiguracionSistema, utilidades compartidas |
| usuarios | Usuario, login, roles, cuotas |
| flota | InventarioFlota, DispositivoGPS, MovimientoFlota |
| telemetria | DatosBusae, DatosGenesis |
| reportes | ReportePendiente, HistorialAtencion, UnidadFueraServicio |
| bitacora | BitacoraRegistro, FormularioPlantilla |
| auditoria | AuditLog |
| tickets | Ticket |

## Capas dentro de cada app

- `models.py` — modelos Django
- `selectors.py` — lecturas optimizadas (sin efectos secundarios)
- `services.py` — lógica de negocio (crear, actualizar, orquestar)
- `views` / `urls` — presentación / HTTP
- `tests/` — pytest

## Estado actual

Todavía la lógica vive en `buses/`.  
Los scripts siguientes moverán código de forma gradual.
