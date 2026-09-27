# buses/views/usuarios.py — generado por 04_dividir_views.ps1

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
from .auth import require_tecnico, require_admin

from ..models import (
    Usuario, Patio, InventarioFlota, DispositivoGPS, MovimientoFlota,
    DatosBusae, DatosGenesis, EEMovil, UnidadFueraServicio,
    ReportePendiente, HistorialAtencion, BitacoraRegistro, InventarioItem,
    ConfiguracionSistema, AuditLog, FormularioPlantilla, Ticket, registrar_auditoria,
)


# ── Auth helpers ────────────────────────────────────────────────────────────

@require_admin
@require_GET
def api_usuarios(request):
    users = [{
        'codigo': u.codigo,
        'nombre': u.nombre,
        'cuota_diaria': u.cuota_diaria,
        'rol': u.rol,
        'is_admin': u.is_admin,
        'is_supervisor': u.is_supervisor,
        'patio_asignado': u.patio_asignado.nombre if u.patio_asignado else '—',
        'patio_id': u.patio_asignado_id,
        'email': u.email or '',
        'esta_bloqueado': u.esta_bloqueado,
    } for u in Usuario.objects.select_related('patio_asignado').filter(activo=True).order_by('nombre')]
    return JsonResponse({'status': 'ok', 'data': users})

@require_admin
@require_POST
def api_usuario_crear(request):
    body = json.loads(request.body.decode('utf-8'))
    codigo = str(body.get('codigo', '')).strip()
    nombre = str(body.get('nombre', '')).strip()
    password = str(body.get('password', '')).strip()
    if not codigo or not nombre:
        return JsonResponse({'status': 'error', 'message': 'Código y nombre requeridos'})
    if Usuario.objects.filter(codigo=codigo).exists():
        return JsonResponse({'status': 'error', 'message': f'El código {codigo} ya existe.'})
    rol = body.get('rol') or ('ADMIN' if body.get('is_admin') else 'TECNICO')
    patio_id = body.get('patio_id')
    u = Usuario(
        codigo=codigo,
        nombre=nombre,
        cuota_diaria=int(body.get('cuota', 0) or 0),
        rol=rol,
        email=body.get('email', ''),
    )
    if patio_id:
        try:
            if str(patio_id).isdigit():
                u.patio_asignado = Patio.objects.get(pk=int(patio_id))
            else:
                u.patio_asignado = Patio.objects.get(codigo=str(patio_id).strip())
        except (Patio.DoesNotExist, ValueError):
            pass
    u.set_password(password or '123456')
    u.save()
    registrar_auditoria(request, 'CREATE', 'Usuario', u.codigo, f'Alta usuario {nombre} ({rol})')
    return JsonResponse({'status': 'success', 'message': 'Usuario agregado con éxito.'})

@require_admin
@require_POST
def api_usuario_editar(request):
    body = json.loads(request.body.decode('utf-8'))
    codigo = str(body.get('codigo', '')).strip()
    try:
        u = Usuario.objects.get(codigo=codigo)
        antes = {'nombre': u.nombre, 'cuota': u.cuota_diaria, 'rol': u.rol}
        u.nombre = str(body.get('nombre', u.nombre)).strip()
        u.cuota_diaria = int(body.get('cuota', u.cuota_diaria) or 0)
        if 'rol' in body and body['rol']:
            u.rol = body['rol']
        elif 'is_admin' in body:
            u.rol = 'ADMIN' if body['is_admin'] else 'TECNICO'
        if 'email' in body:
            u.email = body.get('email', u.email)
        if 'patio_id' in body:
            pid = body.get('patio_id')
            if pid:
                try:
                    if str(pid).isdigit():
                        u.patio_asignado = Patio.objects.get(pk=int(pid))
                    else:
                        u.patio_asignado = Patio.objects.get(codigo=str(pid).strip())
                except (Patio.DoesNotExist, ValueError):
                    pass
            else:
                u.patio_asignado = None
        password = str(body.get('password', '')).strip()
        if password:
            u.set_password(password)
        u.save()
        registrar_auditoria(request, 'UPDATE', 'Usuario', codigo, datos_antes=antes,
                            datos_despues={'nombre': u.nombre, 'cuota': u.cuota_diaria, 'rol': u.rol})
        return JsonResponse({'status': 'success', 'message': 'Usuario actualizado con éxito.'})
    except Usuario.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'No encontrado.'})

@require_admin
@require_POST
def api_usuario_eliminar(request):
    body = json.loads(request.body.decode('utf-8'))
    codigo = str(body.get('codigo', '')).strip()
    try:
        u = Usuario.objects.get(codigo=codigo)
        u.activo = False
        u.save(update_fields=['activo'])
        registrar_auditoria(request, 'DELETE', 'Usuario', codigo, f'Baja lógica {u.nombre}')
        return JsonResponse({'status': 'success', 'message': 'Usuario eliminado.'})
    except Usuario.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'No encontrado.'})

@require_admin
@require_POST
def api_usuario_reset_password(request):
    body = json.loads(request.body.decode('utf-8'))
    codigo = str(body.get('codigo', '')).strip()
    password = str(body.get('password', '')).strip()
    if not codigo or not password:
        return JsonResponse({'status': 'error', 'message': 'Código y nueva contraseña requeridos'})
    try:
        u = Usuario.objects.get(codigo=codigo)
        u.set_password(password)
        u.intentos_fallidos = 0
        u.bloqueado_hasta = None
        u.save(update_fields=['password_hash', 'intentos_fallidos', 'bloqueado_hasta'])
        registrar_auditoria(request, 'UPDATE', 'Usuario', codigo,
                            descripcion=f'Restablecimiento de contraseña para usuario {u.codigo} ({u.nombre})')
        return JsonResponse({'status': 'success', 'message': f'Contraseña restablecida exitosamente para {u.nombre}.'})
    except Usuario.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Usuario no encontrado.'})
