# Scripts PowerShell — Bitácora E.E

Ejecutar siempre desde `C:\Proyectos\bitacora_ee` con **PowerShell 7+**.

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # solo la primera vez
cd C:\Proyectos\bitacora_ee
.\scripts\bootstrap.ps1
```

| Script | Cuándo usarlo |
|--------|----------------|
| `bootstrap.ps1` | Primera instalación o máquina nueva |
| `import_all.ps1` | (Fase 1) Cargar matriz + datos prueba |
| `run_poller.ps1` | (Fase 4) Un ciclo manual Genesis+BUSAE |
| `check_health.ps1` | Verificar migrate y tests |
| `reset_dev.ps1` | Solo desarrollo: reset DB sqlite |

Los scripts usan `$ErrorActionPreference = 'Stop'` para fallar en el primer error.
