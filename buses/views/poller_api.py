# buses/views/poller_api.py — generado por 04_dividir_views.ps1

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
@require_POST
def api_genesis_import(request):
    """
    CSV esperado: bus_movil, origen, destino, patio, hora_entrada, estado, ruta
    hora_entrada puede ser HH:MM o HH:MM:SS
    """
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'status': 'error', 'message': 'No se recibió archivo'})
    try:
        text = f.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        saved = 0
        now = timezone.now()
        with transaction.atomic():
            for row in reader:
                bus = int(str(row.get('bus_movil') or row.get('bus') or row.get('Bus') or '0').strip())
                if not bus:
                    continue
                patio = _calcular_patio_row(row)
                hora_str = (row.get('hora_entrada') or row.get('Horafin') or row.get('hora') or '').strip()
                hora_dt = _parse_hora_entrada(hora_str, now)

                DatosGenesis.objects.create(
                    bus_movil=bus,
                    origen=(row.get('origen') or row.get('Origen') or '').strip(),
                    destino=(row.get('destino') or row.get('Destino') or '').strip(),
                    hora_entrada=hora_dt,
                    patio_ubicacion=patio,
                    estado_bus=(row.get('estado') or row.get('Estado') or '').strip(),
                    ruta=(row.get('ruta') or row.get('Ruta') or '').strip(),
                    datos_extra={
                        'hora_entrada_patio': hora_str,
                        'fuente_manual': True,
                    },
                    fuente='CSV',
                )
                if patio:
                    EEMovil.objects.update_or_create(
                        bus_movil=bus, defaults={'patio': patio}
                    )
                    InventarioFlota.objects.filter(bus_movil=bus).update(patio_actual=patio)
                saved += 1

        # Refrescar reportes pendientes con patio/hora nuevos
        from poller.utils import refresh_pending_cross
        refresh_pending_cross()

        registrar_auditoria(request, 'IMPORT', 'DatosGenesis',
                            descripcion=f'Carga manual Genesis: {saved} registros')
        return JsonResponse({'status': 'success', 'message': f'{saved} registros Genesis importados.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

def _calcular_patio_row(row):
    """Lógica mejorada de patio desde fila Genesis/CSV."""
    estado = str(row.get('estado') or row.get('Estado') or '').strip().lower()
    origen = str(row.get('origen') or row.get('Origen') or '').strip()
    destino = str(row.get('destino') or row.get('Destino') or '').strip()
    patio_directo = str(row.get('patio') or row.get('patio_ubicacion') or '').strip()
    if patio_directo:
        return patio_directo
    if not estado:
        return origen or destino
    if estado == 'inoperativo':
        return origen
    if not destino:
        return origen
    return destino

def _parse_hora_entrada(hora_str, now):
    if not hora_str or hora_str.lower() in ('relevo', 'n/a', '-', ''):
        return None
    for fmt in ('%H:%M:%S', '%H:%M', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M'):
        try:
            parsed = datetime.strptime(hora_str, fmt)
            if fmt in ('%H:%M:%S', '%H:%M'):
                parsed = datetime.combine(now.date(), parsed.time())
            if timezone.is_naive(parsed):
                return timezone.make_aware(parsed)
            return parsed
        except ValueError:
            continue
    return None

@require_admin
@require_POST
def api_busae_import(request):
    """
    Carga manual de CSV de BUSAE.
    Columnas soportadas: bus_movil / bus / numero / bus_number, estado / status,
    latitud, longitud, velocidad, ultima_transmision, manos_libres, telefono.
    """
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'status': 'error', 'message': 'No se recibió archivo CSV'})
    try:
        from poller.utils import (
            parse_busae_datetime, latest_genesis, genesis_cross_fields,
            refresh_pending_cross, record_success
        )
        from buses.models import DatosBusae, ReportePendiente, UnidadFueraServicio, InventarioFlota

        text = f.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        saved = 0
        now = timezone.now()
        today = now.date()
        today_str = today.strftime('%Y%m%d')
        touched = []

        with transaction.atomic():
            for row in reader:
                bus_str = str(
                    row.get('bus_movil') or row.get('bus') or row.get('Bus') or
                    row.get('numero') or row.get('bus_number') or '0'
                ).strip()
                try:
                    bus = int(bus_str)
                except ValueError:
                    continue
                if not bus:
                    continue

                estado_raw = str(row.get('estado') or row.get('status') or row.get('Estado') or 'Offline').strip()
                st_lower = estado_raw.lower()
                if st_lower in ('active', 'activo', 'en ruta', 'moving', 'online', 'on'):
                    estado = 'Active'
                elif st_lower in ('stopped', 'detenido', 'idle'):
                    estado = 'Stopped'
                elif st_lower in ('no records', 'sin registros'):
                    estado = 'No records'
                else:
                    estado = 'Offline'

                lat = None
                lng = None
                try:
                    lat_str = row.get('latitud') or row.get('lat') or row.get('Latitud')
                    lng_str = row.get('longitud') or row.get('lng') or row.get('Longitud')
                    if lat_str: lat = float(lat_str)
                    if lng_str: lng = float(lng_str)
                except (ValueError, TypeError):
                    pass

                vel = 0.0
                try:
                    vel_str = row.get('velocidad') or row.get('speed') or row.get('Velocidad')
                    if vel_str: vel = float(vel_str)
                except (ValueError, TypeError):
                    pass

                ml_raw = str(row.get('manos_libres') or row.get('handsfree') or '').lower().strip()
                manos_libres = ml_raw in ('true', '1', 'si', 'sí', 'yes')

                tel = str(row.get('telefono') or row.get('phone') or '').strip()
                ult_str = row.get('ultima_transmision') or row.get('fecha') or row.get('timestamp') or ''
                ultima_dt = parse_busae_datetime(ult_str) or now

                DatosBusae.objects.update_or_create(
                    bus_movil=bus,
                    defaults={
                        'latitud': lat,
                        'longitud': lng,
                        'velocidad': vel,
                        'estado': estado,
                        'manos_libres': manos_libres,
                        'telefono': tel,
                        'ultima_transmision': ultima_dt,
                    }
                )
                touched.append(bus)

                # T4.6: No crear reportes si bus DESCARTADO/BAJA o UnidadFueraServicio
                flota = InventarioFlota.objects.filter(bus_movil=bus).first()
                if flota:
                    est_op = str(getattr(flota, 'estado_operativo', '') or '').upper()
                    if est_op in ('DESCARTADO', 'BAJA'):
                        saved += 1
                        continue

                is_offline = estado in ('Offline', 'No records')
                if is_offline:
                    if UnidadFueraServicio.objects.filter(bus_movil=bus, estado='ACTIVO').exists():
                        saved += 1
                        continue

                    genesis = latest_genesis(bus)
                    patio_entrada, hora_entrada = genesis_cross_fields(genesis)

                    diagnostico = f"Sin transmisión GPS en BUSAE ({estado}). Última: {ult_str or 'Desconocida'}"
                    rep_existente = ReportePendiente.objects.filter(bus_movil=bus, fecha_reporte=today).first()

                    if not rep_existente:
                        ReportePendiente.objects.create(
                            report_id=f"REP-{today_str}-{bus}",
                            bus_movil=bus,
                            estado_gps='OFF',
                            patio=patio_entrada,
                            fecha_reporte=today,
                            hora_reporte=hora_entrada,
                            diagnostico=diagnostico,
                            estado='PENDIENTE'
                        )
                    elif rep_existente.estado == 'PENDIENTE':
                        rep_existente.patio = patio_entrada
                        rep_existente.hora_reporte = hora_entrada
                        rep_existente.estado_gps = estado
                        rep_existente.diagnostico = diagnostico
                        rep_existente.save(update_fields=['patio', 'hora_reporte', 'estado_gps', 'diagnostico'])

                saved += 1

        if touched:
            refresh_pending_cross(touched)

        record_success('busae', extra={'guardados': saved, 'fuente': 'CSV'})
        registrar_auditoria(request, 'IMPORT', 'DatosBusae', descripcion=f'Carga manual BUSAE CSV: {saved} registros')
        return JsonResponse({'status': 'success', 'message': f'{saved} registros BUSAE importados correctamente.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_admin
@require_GET
def api_poller_health(request):
    """Consulta de salud del Poller."""
    from poller.utils import get_poller_health
    return JsonResponse(get_poller_health())

@require_admin
@require_POST
def api_poller_sync(request):
    """Ejecuta sincronización bajo demanda (Genesis + BUSAE)."""
    service = request.POST.get('service') or request.GET.get('service') or 'all'
    from poller.scheduler import run_now
    from poller.genesis_service import run as run_gen
    from poller.busae_service import run as run_bus

    if service == 'genesis':
        res = {'genesis': run_gen()}
    elif service == 'busae':
        res = {'busae': run_bus()}
    else:
        res = run_now()

    registrar_auditoria(request, 'SYNC', 'Poller', descripcion=f'Sincronización manual: {service}')
    return JsonResponse({'status': 'success', 'data': res})
