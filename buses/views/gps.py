# buses/views/gps.py — generado por 04_dividir_views.ps1

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
def api_gps(request):
    qs = DispositivoGPS.objects.select_related('bus_asignado').all()
    estado = request.GET.get('estado')
    q = request.GET.get('q')
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(
            Q(imei__icontains=q) | Q(serie__icontains=q) |
            Q(telefono_sim__icontains=q) | Q(bus_asignado__bus_movil__icontains=q)
        )
    data = [{
        'imei': d.imei,
        'serie': d.serie or '',
        'modelo': d.modelo or '',
        'telefono_sim': d.telefono_sim or '',
        'estado': d.estado,
        'bus_asignado': d.bus_asignado_id,
        'fecha_instalacion': d.fecha_instalacion.isoformat() if d.fecha_instalacion else '',
        'notas': d.notas or '',
    } for d in qs]
    return JsonResponse({'status': 'ok', 'data': data, 'total': len(data)})

@require_admin
@require_POST
def api_gps_accion(request):
    body = json.loads(request.body.decode('utf-8'))
    accion = body.get('accion')  # alta | asignar | desasignar | baja | estado
    imei = str(body.get('imei', '')).strip()
    codigo = request.session.get('tecnico_codigo', '')

    if accion == 'alta':
        if DispositivoGPS.objects.filter(imei=imei).exists():
            return JsonResponse({'status': 'error', 'message': 'IMEI ya existe'})
        d = DispositivoGPS.objects.create(
            imei=imei,
            serie=body.get('serie', ''),
            modelo=body.get('modelo', ''),
            telefono_sim=body.get('telefono_sim', ''),
            estado=body.get('estado', 'BODEGA'),
            notas=body.get('notas', ''),
        )
        registrar_auditoria(request, 'CREATE', 'DispositivoGPS', imei)
        return JsonResponse({'status': 'success', 'message': f'GPS {imei} registrado.'})

    try:
        d = DispositivoGPS.objects.get(imei=imei)
    except DispositivoGPS.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'GPS no encontrado'})

    if accion == 'asignar':
        bus_num = int(body.get('bus_movil', 0))
        try:
            bus = InventarioFlota.objects.get(bus_movil=bus_num)
        except InventarioFlota.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Bus no existe en flota'})
        d.bus_asignado = bus
        d.estado = 'INSTALADO'
        d.fecha_instalacion = timezone.now().date()
        d.save()
        MovimientoFlota.objects.create(
            tipo='ASIGNAR_GPS', bus_movil=bus_num, gps_imei=imei,
            detalle=f'GPS {imei} → Bus {bus_num}', realizado_por=codigo,
        )
        registrar_auditoria(request, 'ASIGNAR', 'DispositivoGPS', imei, f'→ Bus {bus_num}')
        return JsonResponse({'status': 'success', 'message': f'GPS asignado a Bus {bus_num}.'})

    if accion == 'desasignar':
        bus_num = d.bus_asignado_id
        d.bus_asignado = None
        d.estado = 'BODEGA'
        d.save()
        MovimientoFlota.objects.create(
            tipo='DESASIGNAR_GPS', bus_movil=bus_num, gps_imei=imei,
            detalle=f'GPS {imei} desasignado', realizado_por=codigo,
        )
        registrar_auditoria(request, 'UPDATE', 'DispositivoGPS', imei, 'Desasignado')
        return JsonResponse({'status': 'success', 'message': 'GPS desasignado.'})

    if accion == 'baja':
        d.estado = 'BAJA'
        d.fecha_baja = timezone.now().date()
        d.bus_asignado = None
        d.save()
        registrar_auditoria(request, 'BAJA', 'DispositivoGPS', imei)
        return JsonResponse({'status': 'success', 'message': 'GPS dado de baja.'})

    return JsonResponse({'status': 'error', 'message': 'Acción no reconocida'})

@require_admin
@require_POST
def api_gps_import(request):
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'status': 'error', 'message': 'No se recibió archivo'})
    try:
        text = f.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        created = updated = 0
        with transaction.atomic():
            for row in reader:
                imei = str(row.get('imei') or '').strip()
                if not imei:
                    continue
                defaults = {
                    'serie': (row.get('serie') or '').strip(),
                    'modelo': (row.get('modelo') or '').strip(),
                    'telefono_sim': (row.get('telefono') or row.get('telefono_sim') or '').strip(),
                    'estado': (row.get('estado') or 'BODEGA').strip().upper(),
                }
                bus = row.get('bus_movil') or row.get('bus')
                if bus:
                    try:
                        defaults['bus_asignado'] = InventarioFlota.objects.get(bus_movil=int(bus))
                        defaults['estado'] = 'INSTALADO'
                    except (InventarioFlota.DoesNotExist, ValueError):
                        pass
                _, was_created = DispositivoGPS.objects.update_or_create(imei=imei, defaults=defaults)
                if was_created:
                    created += 1
                else:
                    updated += 1
        registrar_auditoria(request, 'IMPORT', 'DispositivoGPS',
                            descripcion=f'CSV GPS: {created} nuevos, {updated} actualizados')
        return JsonResponse({'status': 'success', 'message': f'GPS: {created} nuevos, {updated} actualizados.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
