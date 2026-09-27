# buses/views/config.py — generado por 04_dividir_views.ps1

"""
Vistas robustas Bitácora E.E
- Login con bloqueo por intentos
- APIs flota / GPS / auditoría / Genesis manual
- Formulario atención 2026
"""
import csv
import io
import json
import tempfile
import os
from datetime import datetime, time, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.db import transaction
from django.conf import settings

CONFIG_SCHEMA = {
    # General
    'app_nombre':               {'desc': 'Nombre visible de la aplicación', 'group': 'general'},
    # Turno / Poller
    'turno_corte_hora':         {'desc': 'Hora de corte del contador diario (0-23)', 'group': 'turno'},
    'poller_intervalo_minutos': {'desc': 'Intervalo del poller en minutos', 'group': 'poller'},
    'poller_busae_activo':      {'desc': 'Activar sincronización BUSAE', 'group': 'poller'},
    'poller_genesis_activo':    {'desc': 'Activar sincronización Genesis', 'group': 'poller'},
    # Bitácora
    'bitacora_cuota_default':   {'desc': 'Cuota diaria por defecto para nuevos usuarios', 'group': 'bitacora'},
    'bitacora_solo_mi_patio':   {'desc': 'Técnico solo ve buses de su patio', 'group': 'bitacora'},
    # Seguridad
    'login_max_intentos':       {'desc': 'Intentos fallidos antes de bloqueo y minutos de bloqueo', 'group': 'seguridad'},
    'sesion_horas':             {'desc': 'Duración de sesión en horas', 'group': 'seguridad'},
    # Feature flags
    'ff_tickets':               {'desc': 'Activar módulo de tickets', 'group': 'flags'},
    'ff_borradores':            {'desc': 'Activar guardado de borradores de formulario', 'group': 'flags'},
    'ff_exportar_excel':        {'desc': 'Activar exportación a Excel', 'group': 'flags'},
    # Notificaciones Tickets (T6.4)
    'notif_ticket_email':       {'desc': 'Email de alertas para tickets nuevos/actualizados', 'group': 'tickets'},
    'notif_ticket_webhook':     {'desc': 'URL de Webhook Slack/Teams para tickets', 'group': 'tickets'},
    # Privacidad
    'privacidad_retencion_dias': {'desc': 'Días de retención de logs de auditoría', 'group': 'privacidad'},
}

from .auth import require_tecnico, require_admin

from ..models import (
    Usuario, Patio, InventarioFlota, DispositivoGPS, MovimientoFlota,
    DatosBusae, DatosGenesis, EEMovil, UnidadFueraServicio,
    ReportePendiente, HistorialAtencion, BitacoraRegistro, InventarioItem,
    ConfiguracionSistema, AuditLog, FormularioPlantilla, Ticket, registrar_auditoria,
)


# ── Auth helpers ────────────────────────────────────────────────────────────

@require_admin
@require_http_methods(['GET', 'POST'])
def api_config(request):
    """
    GET  → devuelve todas las configuraciones con metadatos del esquema
    POST → actualiza una o varias claves (body JSON {clave: valor, ...})
           Solo claves en CONFIG_SCHEMA son aceptadas.
    """
    if request.method == 'GET':
        cfgs = {c.clave: c.valor for c in ConfiguracionSistema.objects.all()}
        resultado = {}
        for clave, meta in CONFIG_SCHEMA.items():
            resultado[clave] = {
                'valor': cfgs.get(clave, None),
                'desc': meta['desc'],
                'group': meta['group'],
            }
        # Incluir claves extra que no estén en el schema (solo lectura)
        for clave, valor in cfgs.items():
            if clave not in resultado:
                resultado[clave] = {'valor': valor, 'desc': '', 'group': 'otros'}
        return JsonResponse({'status': 'ok', 'config': resultado})

    # POST
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    actualizados = []
    errores = []
    for clave, valor in body.items():
        if clave not in CONFIG_SCHEMA:
            errores.append(f'Clave no permitida: {clave}')
            continue
        ConfiguracionSistema.objects.update_or_create(
            clave=clave,
            defaults={
                'valor': valor,
                'descripcion': CONFIG_SCHEMA[clave]['desc'],
            }
        )
        actualizados.append(clave)

    registrar_auditoria(
        request, 'CONFIG_UPDATE',
        descripcion=f'Actualización de configuración: {", ".join(actualizados)}',
    )
    return JsonResponse({
        'status': 'ok',
        'actualizados': actualizados,
        'errores': errores,
    })

@require_admin
@require_http_methods(['GET', 'POST', 'PUT', 'DELETE'])
def api_patios(request):
    """
    GET    → lista todos los patios
    POST   → crea patio nuevo  {codigo, nombre, coe, orden}
    PUT    → edita patio       {id, nombre, coe, orden, activo}
    DELETE → elimina/desactiva {id}
    """
    if request.method == 'GET':
        patios = list(
            Patio.objects.order_by('orden', 'nombre')
            .values('id', 'codigo', 'nombre', 'coe', 'activo', 'orden')
        )
        return JsonResponse({'status': 'ok', 'patios': patios})

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    if request.method == 'POST':
        codigo = body.get('codigo', '').strip().upper().replace(' ', '_')
        nombre = body.get('nombre', '').strip()
        if not codigo or not nombre:
            return JsonResponse({'status': 'error', 'message': 'codigo y nombre son requeridos'}, status=400)
        if Patio.objects.filter(codigo=codigo).exists():
            return JsonResponse({'status': 'error', 'message': f'Ya existe el código {codigo}'}, status=400)
        patio = Patio.objects.create(
            codigo=codigo,
            nombre=nombre,
            coe=body.get('coe', '').strip(),
            orden=int(body.get('orden', 99)),
            activo=True,
        )
        registrar_auditoria(request, 'PATIO_CREAR', descripcion=f'Patio creado: {patio.codigo}')
        return JsonResponse({'status': 'ok', 'id': patio.id, 'codigo': patio.codigo})

    if request.method == 'PUT':
        patio_id = body.get('id')
        try:
            patio = Patio.objects.get(id=patio_id)
        except Patio.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Patio no encontrado'}, status=404)
        patio.nombre = body.get('nombre', patio.nombre).strip()
        patio.coe = body.get('coe', patio.coe).strip()
        patio.orden = int(body.get('orden', patio.orden))
        patio.activo = bool(body.get('activo', patio.activo))
        patio.save()
        registrar_auditoria(request, 'PATIO_EDITAR', descripcion=f'Patio editado: {patio.codigo}')
        return JsonResponse({'status': 'ok'})

    if request.method == 'DELETE':
        patio_id = body.get('id')
        try:
            patio = Patio.objects.get(id=patio_id)
        except Patio.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Patio no encontrado'}, status=404)
        # Si tiene usuarios asignados, solo desactivar
        usuarios_count = patio.usuarios.count() if hasattr(patio, 'usuarios') else 0
        if usuarios_count > 0:
            patio.activo = False
            patio.save(update_fields=['activo'])
            registrar_auditoria(request, 'PATIO_DESACTIVAR', descripcion=f'Patio desactivado (tiene usuarios): {patio.codigo}')
            return JsonResponse({'status': 'ok', 'accion': 'desactivado', 'razon': f'Tiene {usuarios_count} usuario(s) asignado(s)'})
        patio.delete()
        registrar_auditoria(request, 'PATIO_ELIMINAR', descripcion=f'Patio eliminado: {patio_id}')
        return JsonResponse({'status': 'ok', 'accion': 'eliminado'})

    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)
