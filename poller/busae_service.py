"""
poller/busae_service.py
Telemetría BUSAE (HTTP + Playwright) y cruce con Genesis en ReportePendiente.
"""
import logging
from django.utils import timezone
from django.db import transaction

from poller.busae_client import fetch_payload
from poller.busae_parse import normalize_buses
from poller.utils import (
    record_success,
    record_failure,
    parse_busae_datetime,
    latest_genesis,
    genesis_cross_fields,
    refresh_pending_cross,
)

logger = logging.getLogger('poller.busae')

_state = {
    'ciclo': 0,
}

GPS_SIN_SENAL = frozenset({'Offline', 'No records'})


def _fetch_raw():
    payload = fetch_payload()
    if payload is None:
        return []
    buses = normalize_buses(payload)
    if not buses:
        logger.warning('Respuesta BUSAE sin buses reconocibles')
    return buses


def _save_buses_to_db(buses_data):
    from buses.models import DatosBusae, ReportePendiente, UnidadFueraServicio
    today = timezone.now().date()
    today_str = today.strftime('%Y%m%d')

    saved = 0
    touched = []
    with transaction.atomic():
        for b in buses_data:
            num = b['numero']
            if not num:
                continue

            lat = None
            lng = None
            try:
                if b['latitud']:
                    lat = float(b['latitud'])
                if b['longitud']:
                    lng = float(b['longitud'])
            except (ValueError, TypeError):
                pass

            is_offline = b['estado_gps'] in GPS_SIN_SENAL
            ultima = parse_busae_datetime(b.get('ultima_transmision'))

            DatosBusae.objects.update_or_create(
                bus_movil=num,
                defaults={
                    'latitud': lat,
                    'longitud': lng,
                    'velocidad': b.get('velocidad') or 0,
                    'estado': b['estado_gps'],
                    'manos_libres': b['manos_libres'],
                    'telefono': b['telefono'],
                    'ultima_transmision': ultima,
                }
            )
            touched.append(num)


            # T4.6: No crear reportes si bus DESCARTADO/BAJA o UnidadFueraServicio
            from buses.models import InventarioFlota
            flota = InventarioFlota.objects.filter(bus_movil=num).first()
            if flota:
                est_op = str(getattr(flota, 'estado_operativo', '') or '').upper()
                if est_op in ('DESCARTADO', 'BAJA'):
                    saved += 1
                    continue

            if is_offline:
                if UnidadFueraServicio.objects.filter(bus_movil=num, estado='ACTIVO').exists():
                    saved += 1
                    continue

                genesis = latest_genesis(num)
                patio_entrada, hora_entrada = genesis_cross_fields(genesis)

                rep_existente = ReportePendiente.objects.filter(
                    bus_movil=num,
                    fecha_reporte=today
                ).first()

                diagnostico = (
                    f"Sin transmisión GPS en BUSAE ({b['estado_gps']}). "
                    f"Última: {b['ultima_transmision'] or 'Desconocida'}"
                )

                if not rep_existente:
                    ReportePendiente.objects.create(
                        report_id=f"REP-{today_str}-{num}",
                        bus_movil=num,
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
                    rep_existente.estado_gps = b['estado_gps']
                    rep_existente.diagnostico = diagnostico
                    rep_existente.save(update_fields=[
                        'patio', 'hora_reporte', 'estado_gps', 'diagnostico'
                    ])

            saved += 1

    if touched:
        refresh_pending_cross(touched)
    return saved


def run():
    _state['ciclo'] += 1
    logger.info('BUSAE — ciclo %s', _state['ciclo'])
    try:
        buses = _fetch_raw()
        if buses:
            saved = _save_buses_to_db(buses)
            record_success('busae', extra={'guardados': saved})
            logger.info('BUSAE — %s buses guardados en BD', saved)
            return {'status': 'ok', 'saved': saved}

        logger.warning('BUSAE — sin datos en este ciclo')
        record_failure('busae', 'Sin datos en este ciclo')
        return {'status': 'empty', 'saved': 0}
    except Exception as e:
        logger.error('Error crítico en ciclo BUSAE: %s', e)
        record_failure('busae', str(e))
        return {'status': 'error', 'message': str(e)}
