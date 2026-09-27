from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('privacidad/', views.privacidad_view, name='privacidad'),

    # Core APIs
    path('api/reportes/', views.api_reportes, name='api_reportes'),
    path('api/inventario/', views.api_inventario, name='api_inventario'),
    path('api/bitacora/', views.api_guardar_bitacora, name='api_bitacora'),
    path('api/bitacora/cola/', views.api_bitacora_cola, name='api_bitacora_cola'),
    path('api/bitacoras/', views.api_bitacoras_historial, name='api_bitacoras_historial'),
    path('api/formulario/activo/', views.api_formulario_activo, name='api_formulario_activo'),
    path('api/formulario/editor/', views.api_formulario_editor, name='api_formulario_editor'),
    path('api/contador/', views.api_contador, name='api_contador'),
    path('api/resumen/', views.api_resumen, name='api_resumen'),

    # Usuarios
    path('api/usuarios/', views.api_usuarios, name='api_usuarios'),
    path('api/usuarios/crear/', views.api_usuario_crear, name='api_usuario_crear'),
    path('api/usuarios/editar/', views.api_usuario_editar, name='api_usuario_editar'),
    path('api/usuarios/eliminar/', views.api_usuario_eliminar, name='api_usuario_eliminar'),
    path('api/usuarios/reset-password/', views.api_usuario_reset_password, name='api_usuario_reset_password'),

    # Flota
    path('api/flota/', views.api_flota, name='api_flota'),
    path('api/flota/accion/', views.api_flota_accion, name='api_flota_accion'),
    path('api/flota/import/', views.api_flota_import, name='api_flota_import'),
    path('api/flota/import-matriz/', views.api_flota_import_matriz, name='api_flota_import_matriz'),

    # GPS
    path('api/gps/', views.api_gps, name='api_gps'),
    path('api/gps/accion/', views.api_gps_accion, name='api_gps_accion'),
    path('api/gps/import/', views.api_gps_import, name='api_gps_import'),

    # Poller & Cargas manuales
    path('api/genesis/import/', views.api_genesis_import, name='api_genesis_import'),
    path('api/busae/import/', views.api_busae_import, name='api_busae_import'),
    path('api/poller/health/', views.api_poller_health, name='api_poller_health'),
    path('api/poller/sync/', views.api_poller_sync, name='api_poller_sync'),

    # Auditoría
    path('api/auditoria/', views.api_auditoria, name='api_auditoria'),

    # Fase 5 — Configuración global y Patios
    path('api/config/', views.api_config, name='api_config'),
    path('api/patios/', views.api_patios, name='api_patios'),

    # Fase 6 — Tickets / Soporte
    path('api/tickets/', views.api_tickets, name='api_tickets'),
    path('api/tickets/crear/', views.api_ticket_crear, name='api_ticket_crear'),
    path('api/tickets/accion/', views.api_ticket_accion, name='api_ticket_accion'),
]
