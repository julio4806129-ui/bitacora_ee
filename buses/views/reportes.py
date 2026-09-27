# buses/views/reportes.py — generado por 04_dividir_views.ps1

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
@require_GET
def api_reportes(request):
    qs = ReportePendiente.objects.filter(estado='PENDIENTE').order_by('-fecha_reporte', '-creado_en')
    patio = request.GET.get('patio')
    if patio:
        qs = qs.filter(patio__icontains=patio)
    data = [{
        'bus_movil': r.bus_movil,
        'estado_gps': r.estado_gps,
        'patio': r.patio,
        'fecha_reporte': r.fecha_reporte.isoformat() if r.fecha_reporte else '',
        'hora_reporte': r.hora_reporte or '',
        'diagnostico': r.diagnostico,
        'report_id': r.report_id,
    } for r in qs[:300]]
    return JsonResponse({'status': 'ok', 'data': data, 'total': len(data)})

@require_tecnico
@require_GET
def api_inventario(request):
    qs = InventarioItem.objects.all().order_by('patio', 'bus_movil')
    patio = request.GET.get('patio')
    q = request.GET.get('q')
    if patio:
        qs = qs.filter(patio__icontains=patio)
    if q:
        qs = qs.filter(Q(bus_movil__icontains=q) | Q(diagnostico__icontains=q) | Q(estado__icontains=q))
    data = [{
        'patio': i.patio, 'bus_movil': i.bus_movil, 'hora': i.hora or '',
        'estado': i.estado or '',
        'ultima_atencion': i.ultima_atencion.strftime('%d/%m/%Y') if i.ultima_atencion else '',
        'fecha_actual': i.fecha_actual.strftime('%d/%m/%Y') if i.fecha_actual else '',
        'diagnostico': i.diagnostico or '',
    } for i in qs]
    return JsonResponse({'status': 'ok', 'data': data, 'total': len(data)})
