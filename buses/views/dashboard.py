# buses/views/dashboard.py — generado por 04_dividir_views.ps1

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
def dashboard(request):
    codigo = request.session['tecnico_codigo']
    contador = get_contador_hoy(codigo)
    cuota = request.session.get('cuota_diaria', 0)
    pendientes = ReportePendiente.objects.filter(estado='PENDIENTE').count()
    context = {
        'tecnico_nombre': request.session.get('tecnico_nombre'),
        'tecnico_codigo': codigo,
        'rol': request.session.get('rol', 'TECNICO'),
        'is_admin': request.session.get('is_admin', False),
        'is_supervisor': request.session.get('is_supervisor', False),
        'patio_asignado_nombre': request.session.get('patio_asignado_nombre', ''),
        'contador_hoy': contador,
        'cuota_diaria': cuota,
        'progreso': min(100, int(contador / cuota * 100)) if cuota else 0,
        'pendientes_count': pendientes,
        'patios': list(Patio.objects.filter(activo=True).values('id', 'codigo', 'nombre')),
        'tecnicos': list(Usuario.objects.filter(activo=True).values('codigo', 'nombre')),
    }
    return render(request, 'dashboard.html', context)

def get_contador_hoy(tecnico_codigo):
    if not tecnico_codigo:
        return 0
    now = timezone.localtime(timezone.now())
    effective = now.date()
    if now.hour < 8:
        effective = (now - timedelta(days=1)).date()
    start = timezone.make_aware(datetime.combine(effective, time(0, 0)))
    end = start + timedelta(days=1)
    return BitacoraRegistro.objects.filter(
        codigo_tecnico=str(tecnico_codigo).strip(),
        marca_temporal__gte=start,
        marca_temporal__lt=end,
    ).count()

@require_tecnico
@require_GET
def api_contador(request):
    codigo = request.session.get('tecnico_codigo')
    return JsonResponse({
        'status': 'ok',
        'contador': get_contador_hoy(codigo),
        'cuota': request.session.get('cuota_diaria', 0),
    })

@require_tecnico
@require_GET
def api_resumen(request):
    fecha = request.GET.get('fecha')
    qs = BitacoraRegistro.objects.all()
    if fecha:
        try:
            d = datetime.strptime(fecha, '%Y-%m-%d').date()
            qs = qs.filter(marca_temporal__date=d)
        except ValueError:
            pass

    def agg(field):
        return list(qs.exclude(**{field: ''}).values(field).annotate(total=Count('id')).order_by('-total')[:20])

    por_tecnico = list(qs.values('tecnico_nombre').annotate(total=Count('id')).order_by('-total')[:15])
    por_patio = list(qs.values('patio').annotate(total=Count('id')).order_by('-total'))
    por_tipo = list(qs.values('tipo_revision').annotate(total=Count('id')).order_by('-total'))
    por_gps = agg('gps')

    return JsonResponse({
        'status': 'ok',
        'atencionesPorTecnico': [['Técnico', 'Total']] + [[r['tecnico_nombre'] or 'N/A', r['total']] for r in por_tecnico],
        'atencionesPorPatio': [['Patio', 'Total']] + [[r['patio'] or 'N/A', r['total']] for r in por_patio],
        'tiposMantenimiento': [['Tipo', 'Total']] + [[r['tipo_revision'] or 'N/A', r['total']] for r in por_tipo],
        'estadoGPS': [['GPS', 'Total']] + [[r['gps'] or 'N/A', r['total']] for r in por_gps],
    })
