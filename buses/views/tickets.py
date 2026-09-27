# buses/views/tickets.py — generado por 04_dividir_views.ps1

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

@require_tecnico
def api_tickets(request):
    """
    GET → lista tickets filtrados según rol y parámetros.
    Técnico: ve tickets creados por él o asignados a él (o todos si admin/supervisor).
    Admin / Supervisor: ve todos los tickets con filtros completos.
    """
    is_admin_or_super = bool(request.session.get('is_admin') or request.session.get('rol') == 'SUPERVISOR')
    tecnico_codigo = str(request.session.get('tecnico_codigo', '')).strip()

    qs = Ticket.objects.select_related('patio', 'creado_por', 'asignado_a').all()

    # Si es técnico estándar o si se pasa ?solo_mios=1
    solo_mios = request.GET.get('solo_mios') == '1' or not is_admin_or_super
    if solo_mios:
        qs = qs.filter(Q(creado_por_codigo=tecnico_codigo) | Q(asignado_a_codigo=tecnico_codigo))

    # Filtros
    estado = request.GET.get('estado', '').strip()
    if estado:
        qs = qs.filter(estado=estado)

    prioridad = request.GET.get('prioridad', '').strip()
    if prioridad:
        qs = qs.filter(prioridad=prioridad)

    categoria = request.GET.get('categoria', '').strip()
    if categoria:
        qs = qs.filter(categoria=categoria)

    patio_id = request.GET.get('patio_id', '').strip()
    if patio_id:
        qs = qs.filter(patio_id=patio_id)

    q = request.GET.get('q', '').strip()
    if q:
        if q.isdigit():
            qs = qs.filter(Q(bus_movil=int(q)) | Q(id=int(q)) | Q(titulo__icontains=q))
        else:
            qs = qs.filter(
                Q(titulo__icontains=q) |
                Q(descripcion__icontains=q) |
                Q(creado_por_nombre__icontains=q) |
                Q(asignado_a_nombre__icontains=q)
            )

    # Conteo por estado para métricas rápidas (KPIs)
    base_qs = Ticket.objects.all() if is_admin_or_super else Ticket.objects.filter(
        Q(creado_por_codigo=tecnico_codigo) | Q(asignado_a_codigo=tecnico_codigo)
    )
    counts = {
        'total': base_qs.count(),
        'abiertos': base_qs.filter(estado='ABIERTO').count(),
        'en_progreso': base_qs.filter(estado='EN_PROGRESO').count(),
        'resueltos': base_qs.filter(estado='RESUELTO').count(),
        'cerrados': base_qs.filter(estado='CERRADO').count(),
    }

    tickets = []
    for t in qs[:150]:
        tickets.append({
            'id': t.id,
            'titulo': t.titulo,
            'descripcion': t.descripcion,
            'prioridad': t.prioridad,
            'prioridad_display': t.get_prioridad_display(),
            'estado': t.estado,
            'estado_display': t.get_estado_display(),
            'categoria': t.categoria,
            'categoria_display': t.get_categoria_display(),
            'bus_movil': t.bus_movil,
            'patio_id': t.patio_id,
            'patio_nombre': t.patio.nombre if t.patio else '',
            'creado_por_codigo': t.creado_por_codigo,
            'creado_por_nombre': t.creado_por_nombre,
            'asignado_a_codigo': t.asignado_a_codigo,
            'asignado_a_nombre': t.asignado_a_nombre,
            'comentarios': t.comentarios or [],
            'resolucion': t.resolucion,
            'creado_en': t.creado_en.strftime('%d/%m/%Y %H:%M') if t.creado_en else '',
            'actualizado_en': t.actualizado_en.strftime('%d/%m/%Y %H:%M') if t.actualizado_en else '',
            'resuelto_en': t.resuelto_en.strftime('%d/%m/%Y %H:%M') if t.resuelto_en else '',
            'es_mio': t.creado_por_codigo == tecnico_codigo,
        })

    return JsonResponse({
        'status': 'ok',
        'counts': counts,
        'tickets': tickets,
        'is_admin': bool(is_admin_or_super),
    })

@require_tecnico
@require_http_methods(['POST'])
def api_ticket_crear(request):
    """
    POST → crea un nuevo ticket (T6.2).
    Accesible para técnicos, supervisores y administradores.
    """
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    titulo = body.get('titulo', '').strip()
    descripcion = body.get('descripcion', '').strip()
    if not titulo or not descripcion:
        return JsonResponse({'status': 'error', 'message': 'Título y descripción son requeridos'}, status=400)

    prioridad = body.get('prioridad', 'MEDIA').strip().upper()
    if prioridad not in ['BAJA', 'MEDIA', 'ALTA', 'CRITICA']:
        prioridad = 'MEDIA'

    categoria = body.get('categoria', 'OTRO').strip().upper()
    if categoria not in ['GPS', 'EQUIPO_EMBARCADO', 'APLICACION', 'PATIO', 'OTRO']:
        categoria = 'OTRO'

    bus_movil = body.get('bus_movil')
    if bus_movil:
        try:
            bus_movil = int(bus_movil)
        except (ValueError, TypeError):
            bus_movil = None
    else:
        bus_movil = None

    patio = None
    patio_id = body.get('patio_id')
    if patio_id:
        try:
            patio = Patio.objects.filter(id=patio_id).first()
        except Exception:
            patio = None

    tecnico_codigo = str(request.session.get('tecnico_codigo', '')).strip()
    tecnico_nombre = str(request.session.get('tecnico_nombre', 'Técnico')).strip()
    user_obj = Usuario.objects.filter(codigo=tecnico_codigo).first()
    if not patio and user_obj and user_obj.patio_asignado:
        patio = user_obj.patio_asignado

    ticket = Ticket.objects.create(
        titulo=titulo,
        descripcion=descripcion,
        prioridad=prioridad,
        estado='ABIERTO',
        categoria=categoria,
        bus_movil=bus_movil,
        patio=patio,
        creado_por=user_obj,
        creado_por_codigo=tecnico_codigo,
        creado_por_nombre=tecnico_nombre,
        comentarios=[],
    )

    # T6.5: Auditoría
    registrar_auditoria(
        request, 'TICKET_CREAR', modelo='Ticket', objeto_id=str(ticket.id),
        descripcion=f'Ticket #{ticket.id} creado: {ticket.titulo} (Prioridad: {ticket.prioridad})',
    )

    # T6.4: Notificación Slack/Email
    try:
        from .notificaciones import enviar_notificacion_ticket
        enviar_notificacion_ticket(ticket, accion='creado')
    except Exception:
        pass

    return JsonResponse({
        'status': 'ok',
        'message': f'Ticket #{ticket.id} creado exitosamente',
        'ticket_id': ticket.id,
    })

@require_tecnico
@require_http_methods(['POST'])
def api_ticket_accion(request):
    """
    POST → realizar acciones sobre un ticket:
    - accion='estado': cambiar estado (ABIERTO, EN_PROGRESO, RESUELTO, CERRADO)
    - accion='comentar': agregar un comentario al ticket
    - accion='asignar': asignar ticket a un técnico/usuario
    - accion='resolver': marcar como resuelto con detalle de solución
    """
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    ticket_id = body.get('ticket_id')
    accion = body.get('accion', '').strip().lower()

    if not ticket_id:
        return JsonResponse({'status': 'error', 'message': 'ticket_id es requerido'}, status=400)

    try:
        ticket = Ticket.objects.get(id=ticket_id)
    except Ticket.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Ticket no encontrado'}, status=404)

    is_admin = bool(request.session.get('is_admin'))
    is_super = bool(request.session.get('is_admin') or request.session.get('rol') in ('ADMIN', 'SUPERVISOR'))
    tecnico_codigo = str(request.session.get('tecnico_codigo', '')).strip()
    tecnico_nombre = str(request.session.get('tecnico_nombre', 'Usuario')).strip()

    from .notificaciones import enviar_notificacion_ticket

    if accion == 'estado':
        nuevo_estado = body.get('nuevo_estado', '').strip().upper()
        if nuevo_estado not in ['ABIERTO', 'EN_PROGRESO', 'RESUELTO', 'CERRADO']:
            return JsonResponse({'status': 'error', 'message': 'Estado inválido'}, status=400)

        # Si no es admin/super, solo puede cerrar o resolver sus propios tickets
        if not is_super and ticket.creado_por_codigo != tecnico_codigo:
            return JsonResponse({'status': 'error', 'message': 'No tienes permiso para cambiar el estado'}, status=403)

        estado_anterior = ticket.estado
        ticket.estado = nuevo_estado
        now = timezone.now()
        if nuevo_estado == 'RESUELTO' and not ticket.resuelto_en:
            ticket.resuelto_en = now
        elif nuevo_estado == 'CERRADO' and not ticket.cerrado_en:
            ticket.cerrado_en = now

        ticket.save()

        registrar_auditoria(
            request, 'TICKET_ESTADO', modelo='Ticket', objeto_id=str(ticket.id),
            descripcion=f'Ticket #{ticket.id} cambio estado: {estado_anterior} → {nuevo_estado}',
        )
        try:
            enviar_notificacion_ticket(ticket, accion='actualizado')
        except Exception:
            pass
        return JsonResponse({'status': 'ok', 'mensaje': f'Estado actualizado a {nuevo_estado}'})

    elif accion == 'comentar':
        texto = body.get('texto', '').strip()
        if not texto:
            return JsonResponse({'status': 'error', 'message': 'El comentario no puede estar vacío'}, status=400)

        comentario = {
            'autor_codigo': tecnico_codigo,
            'autor_nombre': tecnico_nombre,
            'es_admin': is_admin or is_super,
            'texto': texto,
            'fecha': timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M'),
        }
        comentarios = list(ticket.comentarios or [])
        comentarios.append(comentario)
        ticket.comentarios = comentarios
        ticket.save(update_fields=['comentarios', 'actualizado_en'])

        registrar_auditoria(
            request, 'TICKET_COMENTARIO', modelo='Ticket', objeto_id=str(ticket.id),
            descripcion=f'Comentario en ticket #{ticket.id} por {tecnico_nombre}',
        )
        try:
            enviar_notificacion_ticket(ticket, accion='comentario', comentario=comentario)
        except Exception:
            pass
        return JsonResponse({'status': 'ok', 'comentario': comentario})

    elif accion == 'asignar':
        if not is_super:
            return JsonResponse({'status': 'error', 'message': 'Solo administradores o supervisores pueden asignar tickets'}, status=403)

        usuario_codigo = body.get('usuario_codigo', '').strip()
        if usuario_codigo:
            dest_user = Usuario.objects.filter(codigo=usuario_codigo).first()
            if not dest_user:
                return JsonResponse({'status': 'error', 'message': 'Usuario no encontrado'}, status=404)
            ticket.asignado_a = dest_user
            ticket.asignado_a_codigo = dest_user.codigo
            ticket.asignado_a_nombre = dest_user.nombre
            if ticket.estado == 'ABIERTO':
                ticket.estado = 'EN_PROGRESO'
        else:
            ticket.asignado_a = None
            ticket.asignado_a_codigo = ''
            ticket.asignado_a_nombre = ''

        ticket.save()

        registrar_auditoria(
            request, 'TICKET_ASIGNAR', modelo='Ticket', objeto_id=str(ticket.id),
            descripcion=f'Ticket #{ticket.id} asignado a: {ticket.asignado_a_nombre or "Sin asignar"}',
        )
        try:
            enviar_notificacion_ticket(ticket, accion='actualizado')
        except Exception:
            pass
        return JsonResponse({'status': 'ok', 'asignado_a_nombre': ticket.asignado_a_nombre})

    elif accion == 'resolver':
        resolucion = body.get('resolucion', '').strip()
        ticket.estado = 'RESUELTO'
        ticket.resuelto_en = timezone.now()
        if resolucion:
            ticket.resolucion = resolucion
            comentarios = list(ticket.comentarios or [])
            comentarios.append({
                'autor_codigo': tecnico_codigo,
                'autor_nombre': tecnico_nombre,
                'es_admin': is_admin or is_super,
                'texto': f'Resolución: {resolucion}',
                'fecha': timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M'),
            })
            ticket.comentarios = comentarios
        ticket.save()

        registrar_auditoria(
            request, 'TICKET_RESOLVER', modelo='Ticket', objeto_id=str(ticket.id),
            descripcion=f'Ticket #{ticket.id} resuelto por {tecnico_nombre}',
        )
        try:
            enviar_notificacion_ticket(ticket, accion='resuelto')
        except Exception:
            pass
        return JsonResponse({'status': 'ok', 'mensaje': f'Ticket #{ticket.id} resuelto'})

    return JsonResponse({'status': 'error', 'message': f'Acción no reconocida: {accion}'}, status=400)
