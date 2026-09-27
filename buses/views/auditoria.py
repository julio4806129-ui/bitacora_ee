# buses/views/auditoria.py — generado por 04_dividir_views.ps1

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
def api_auditoria(request):
    qs = AuditLog.objects.all()
    accion = request.GET.get('accion')
    usuario = request.GET.get('usuario')
    modelo = request.GET.get('modelo')
    desde = request.GET.get('desde')
    hasta = request.GET.get('hasta')
    if accion:
        qs = qs.filter(accion=accion)
    if usuario:
        qs = qs.filter(usuario_codigo=usuario)
    if modelo:
        qs = qs.filter(modelo__icontains=modelo)
    if desde:
        qs = qs.filter(timestamp__date__gte=desde)
    if hasta:
        qs = qs.filter(timestamp__date__lte=hasta)
    data = [{
        'id': str(a.id),
        'timestamp': a.timestamp.isoformat(),
        'usuario_codigo': a.usuario_codigo,
        'usuario_nombre': a.usuario_nombre,
        'accion': a.accion,
        'modelo': a.modelo,
        'objeto_id': a.objeto_id,
        'descripcion': a.descripcion,
        'ip': a.ip or '',
    } for a in qs[:500]]
    return JsonResponse({'status': 'ok', 'data': data, 'total': len(data)})
