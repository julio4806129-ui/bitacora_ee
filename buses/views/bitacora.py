# buses/views/bitacora.py — generado por 04_dividir_views.ps1

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

MAP_GPS = {'FUNCIONA': 'Funciona', 'CORTO': 'Corto', 'MOJADO': 'Mojado'}
MAP_VAND = {
    '': 'Ninguno',
    'NINGUNO': 'Ninguno',
    'PERDIDA_GPS': 'Pérdida de GPS',
    'CORTE_ARNES': 'Corte de arnés',
    'ROBO_SIMCARD': 'Robo de SIMCARD',
}
MAP_SIM = {
    '': '—',
    'DETERIORO_REEMPLAZO': 'Deterioro / Reemplazo',
    'OK': 'OK',
    'NO_APLICA': 'No aplica',
}
MAP_ADEC = {
    '': '—',
    'ADECUADA': 'Adecuada',
    'NO_ADECUADA': 'No adecuada',
}
MAP_CTAP = {
    '': '—',
    'FUNCIONA': 'Funciona',
    'DANADA': 'Dañada',
    'DAÑADA': 'Dañada',
    'NO_TIENE': 'No tiene',
}
MAP_ESTADO = {
    '': '—',
    'FUNCIONA': 'Funciona',
    'DANADA': 'Dañada',
    'DAÑADA': 'Dañada',
    'SI': 'Sí',
    'NO': 'No',
}

from .auth import require_tecnico, require_admin

from ..models import (
    Usuario, Patio, InventarioFlota, DispositivoGPS, MovimientoFlota,
    DatosBusae, DatosGenesis, EEMovil, UnidadFueraServicio,
    ReportePendiente, HistorialAtencion, BitacoraRegistro, InventarioItem,
    ConfiguracionSistema, AuditLog, FormularioPlantilla, Ticket, registrar_auditoria,
)


# ── Auth helpers ────────────────────────────────────────────────────────────

@require_tecnico
@require_POST
def api_guardar_bitacora(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'})

    tecnico_nombre = body.get('tecnico') or request.session.get('tecnico_nombre', '')
    tecnico_codigo = body.get('codigo_tecnico') or request.session.get('tecnico_codigo', '')

    try:
        numero_bus = int(str(body.get('movil', body.get('numero_bus', '0'))).strip())
    except (ValueError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Número de bus inválido'})

    if not body.get('patio'):
        return JsonResponse({'status': 'error', 'message': 'Patio es obligatorio'})
    if not body.get('tipo_revision') and not body.get('tipoInventario'):
        return JsonResponse({'status': 'error', 'message': 'Tipo de revisión obligatorio'})
    if not (body.get('gps') or '').strip():
        return JsonResponse({'status': 'error', 'message': 'Estado GPS es obligatorio'})
    informe = (body.get('informe_tecnico') or body.get('respuestaTecnica') or '').strip()
    if not informe:
        return JsonResponse({'status': 'error', 'message': 'Informe técnico es obligatorio'})

    tipo = body.get('tipo_revision') or body.get('tipoInventario', 'BITACORA')
    if tipo in ('INVENTARIO', 'REVISION POR BITACORA', 'BITACORA'):
        tipo = 'INVENTARIO' if 'INVENTARIO' in tipo.upper() else 'BITACORA'

    registro = BitacoraRegistro.objects.create(
        tipo_revision=tipo,
        patio=body.get('patio', ''),
        numero_bus=numero_bus,
        tecnico_nombre=tecnico_nombre,
        codigo_tecnico=tecnico_codigo,
        gps=body.get('gps', ''),
        vandalismo=body.get('vandalismo', ''),
        simcard=body.get('simcard', ''),
        adecuacion_electrica=body.get('adecuacion_electrica', ''),
        radio_conexion=body.get('radio_conexion', ''),
        radio_instalacion=body.get('radio_instalacion', ''),
        radio_perilla=body.get('radio_perilla', ''),
        radio_pedal=body.get('radio_pedal', ''),
        radio_pantalla=body.get('radio_pantalla', ''),
        ctap=body.get('ctap', ''),
        informe_tecnico=body.get('informe_tecnico') or body.get('respuestaTecnica', ''),
        source=body.get('source', ''),
        report_id=body.get('reportId') or body.get('report_id', ''),
    )

    source = body.get('source', '')
    report_id = body.get('reportId') or body.get('report_id', '')
    with transaction.atomic():
        reps = []
        if report_id:
            reps = list(ReportePendiente.objects.select_for_update().filter(
                report_id=report_id, estado='PENDIENTE'
            ))
        if not reps:
            # Cerrar pendientes del mismo bus al atender desde bitácora
            reps = list(ReportePendiente.objects.select_for_update().filter(
                bus_movil=numero_bus, estado='PENDIENTE'
            )[:5])
        for rep in reps:
            HistorialAtencion.objects.create(
                bus_movil=rep.bus_movil,
                estado_gps=rep.estado_gps,
                patio=rep.patio or body.get('patio', ''),
                fecha_reporte=rep.fecha_reporte,
                hora_reporte=rep.hora_reporte,
                diagnostico=rep.diagnostico,
                tecnico_nombre=tecnico_nombre,
                tecnico_codigo=tecnico_codigo,
                report_id_origen=rep.report_id,
                bitacora=registro,
            )
            rep.estado = 'ATENDIDO'
            rep.save(update_fields=['estado', 'actualizado_en'])

    # Feedback a flota: reflejar hallazgos EE en InventarioFlota
    flota_updates = {}
    if registro.gps:
        # Mapear GPS form → estado visible en cola BUSAE-ish
        gps_map = {
            'FUNCIONA': 'Active',
            'CORTO': 'NO GPS',
            'MOJADO': 'NO GPS',
        }
        flota_updates['estado_busae'] = gps_map.get(registro.gps.upper(), registro.gps)
    if registro.adecuacion_electrica:
        flota_updates['adecuacion_electrica'] = registro.adecuacion_electrica
    if registro.informe_tecnico:
        # Anexar comentario reciente (últimos 500 chars)
        prev = ''
        try:
            flota_obj = InventarioFlota.objects.filter(bus_movil=numero_bus).first()
            if flota_obj:
                prev = (flota_obj.comentarios or '').strip()
        except Exception:
            flota_obj = None
        nota = f'[{timezone.now():%Y-%m-%d %H:%M}] {tecnico_nombre}: {registro.informe_tecnico[:200]}'
        flota_updates['comentarios'] = (nota + (' | ' + prev if prev else ''))[:2000]
        flota_updates['fecha_revision'] = timezone.now().date()
        flota_updates['patio_actual'] = registro.patio or (flota_obj.patio_actual if flota_obj else '')

    if flota_updates:
        updated = InventarioFlota.objects.filter(bus_movil=numero_bus).update(**flota_updates)
        if updated:
            MovimientoFlota.objects.create(
                tipo='OTRO',
                bus_movil=numero_bus,
                detalle=f'Actualizado por bitácora #{registro.id}: {", ".join(flota_updates.keys())}',
                realizado_por=tecnico_codigo,
            )

    registrar_auditoria(
        request, 'ATENDER', modelo='BitacoraRegistro', objeto_id=str(registro.id),
        descripcion=f'Bitácora Bus {numero_bus} — {tipo}',
        datos_despues={
            'bus': numero_bus,
            'patio': registro.patio,
            'gps': registro.gps,
            'vandalismo': registro.vandalismo,
            'flota_updates': list(flota_updates.keys()),
        },
    )

    return JsonResponse({
        'status': 'success',
        'message': 'Bitácora guardada correctamente.',
        'id': registro.id,
        'contador': get_contador_hoy(tecnico_codigo),
    })

@require_tecnico
@require_GET
def api_bitacora_cola(request):
    """
    Cola BITÁCORA (estructura Excel):
    TECNICO ASIGNADO | BUS | ESTADO GENESIS | ESTADO BUSAE | PATIO UBICACION | HORA DE ENTRADA | ACCION
    Filtro automático: técnico solo ve su patio_asignado (admin/supervisor ven todo o filtro manual).
    """
    from django.db.models import OuterRef, Subquery

    patio_f = (request.GET.get('patio') or '').strip()
    tecnico_f = (request.GET.get('tecnico') or '').strip()
    q = (request.GET.get('q') or '').strip()

    is_admin = request.session.get('is_admin') or request.session.get('is_supervisor')
    patio_sesion = (request.session.get('patio_asignado_nombre') or '').strip()

    # Config: ¿forzar solo mi patio?
    solo_mi_patio = True
    try:
        cfg = ConfiguracionSistema.objects.filter(clave='bitacora_solo_mi_patio').first()
        if cfg and isinstance(cfg.valor, dict):
            solo_mi_patio = bool(cfg.valor.get('activo', True))
    except Exception:
        pass

    if not is_admin and solo_mi_patio and patio_sesion and not patio_f:
        patio_f = patio_sesion

    latest_g = DatosGenesis.objects.filter(
        bus_movil=OuterRef('bus_movil')
    ).order_by('-sincronizado_en')

    qs = InventarioFlota.objects.exclude(
        estado_operativo__in=['DESCARTADO', 'BAJA']
    ).select_related('patio_base').annotate(
        g_patio=Subquery(latest_g.values('patio_ubicacion')[:1]),
        g_hora=Subquery(latest_g.values('hora_entrada')[:1]),
        g_estado=Subquery(latest_g.values('estado_bus')[:1]),
    )

    if patio_f:
        qs = qs.filter(
            Q(patio_actual__icontains=patio_f)
            | Q(g_patio__icontains=patio_f)
            | Q(patio_base__nombre__icontains=patio_f)
            | Q(coe__icontains=patio_f)
        )
    if tecnico_f:
        qs = qs.filter(tecnico_asignado__icontains=tecnico_f)
    if q:
        qs = qs.filter(Q(bus_movil__icontains=q) | Q(placa__icontains=q))

    busae_map = {
        d.bus_movil: d
        for d in DatosBusae.objects.all().only('bus_movil', 'estado', 'ultima_transmision')
    }

    data = []
    for b in qs.order_by('bus_movil')[:800]:
        busae = busae_map.get(b.bus_movil)
        if not busae:
            estado_busae = 'NO GPS'
        else:
            st = (busae.estado or '').strip()
            low = st.lower()
            if low in ('offline', 'no records', 'off', '', 'none'):
                estado_busae = 'NO GPS'
            elif low == 'active':
                estado_busae = 'Active'
            elif low == 'stopped':
                estado_busae = 'Stopped'
            else:
                estado_busae = st
            com = (b.comentarios or '').upper()
            if 'MOOVIA' in com or 'REVISAR CONFI' in com:
                estado_busae = 'REVISAR CONFI MOOVIA'

        patio_eff = (
            b.g_patio
            or b.patio_actual
            or (b.patio_base.nombre if b.patio_base_id else '')
            or b.coe
            or ''
        )
        hora_str = ''
        if b.g_hora:
            try:
                hora_str = b.g_hora.strftime('%H:%M:%S')
            except Exception:
                hora_str = str(b.g_hora)[:8]

        estado_genesis = b.g_estado or b.estado_genesis or ''
        if not estado_genesis:
            estado_genesis = 'Operativo' if b.estado_operativo == 'ACTIVO' else (b.estado_operativo or '')

        data.append({
            'tecnico': b.tecnico_asignado or '',
            'bus_movil': b.bus_movil,
            'placa': b.placa or '',
            'estado_genesis': estado_genesis,
            'estado_busae': estado_busae,
            'patio': patio_eff,
            'hora': hora_str,
            'estado_operativo': b.estado_operativo,
            'comentarios': b.comentarios or '',
        })

    return JsonResponse({
        'status': 'ok',
        'data': data,
        'total': len(data),
        'filtro_patio': patio_f,
        'solo_mi_patio': (not is_admin and solo_mi_patio),
    })

@require_tecnico
@require_GET
def api_bitacoras_historial(request):
    """Lista + detalle de BitacoraRegistro (trazabilidad completa del formulario)."""
    detail_id = request.GET.get('id')
    if detail_id:
        try:
            r = BitacoraRegistro.objects.get(pk=int(detail_id))
        except (BitacoraRegistro.DoesNotExist, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Registro no encontrado'}, status=404)
        is_admin = request.session.get('is_admin') or request.session.get('is_supervisor')
        codigo = request.session.get('tecnico_codigo', '')
        if not is_admin and str(r.codigo_tecnico) != str(codigo):
            return JsonResponse({'status': 'error', 'message': 'Sin permiso'}, status=403)
        return JsonResponse({'status': 'ok', 'data': _bitacora_to_dict(r, full=True)})

    qs = BitacoraRegistro.objects.all().order_by('-marca_temporal')
    is_admin = request.session.get('is_admin') or request.session.get('is_supervisor')
    codigo = request.session.get('tecnico_codigo', '')
    solo_mios = request.GET.get('solo_mios') == '1'
    if solo_mios:
        qs = qs.filter(codigo_tecnico=str(codigo))
    bus = (request.GET.get('bus') or '').strip()
    if bus:
        qs = qs.filter(numero_bus__icontains=bus)

    data = [_bitacora_to_dict(r, full=False) for r in qs[:200]]
    return JsonResponse({'status': 'ok', 'data': data, 'total': len(data)})

def _bitacora_to_dict(r, full=False):
    # radio_conexion = SIMCARD answer for Conexión (SI/NO)
    # radio_instalacion = Instalación answer for Instalación (SI/NO)
    sim_conn = (r.radio_conexion or '').strip()
    inst_inst = (r.radio_instalacion or '').strip()

    # Radio base general status
    perilla_ok = r.radio_perilla == 'FUNCIONA'
    pedal_ok = r.radio_pedal == 'FUNCIONA'
    pantalla_ok = r.radio_pantalla == 'FUNCIONA'
    has_damage = any(x in ('DANADA', 'DAÑADA') for x in (r.radio_perilla, r.radio_pedal, r.radio_pantalla))

    if has_damage:
        radio_resumen = 'Con fallas'
        radio_badge = 'danger'
    elif perilla_ok or pedal_ok or pantalla_ok:
        radio_resumen = 'Funciona'
        radio_badge = 'success'
    else:
        radio_resumen = '—'
        radio_badge = 'secondary'

    base = {
        'id': r.id,
        'fecha': (timezone.localtime(r.marca_temporal).strftime('%Y-%m-%d %H:%M:%S') if timezone.is_aware(r.marca_temporal) else r.marca_temporal.strftime('%Y-%m-%d %H:%M:%S')) if r.marca_temporal else '',
        'bus': r.numero_bus,
        'patio': r.patio,
        'tipo': r.tipo_revision,
        'tipo_display': 'Inventario' if r.tipo_revision == 'INVENTARIO' else 'Bitácora',
        'tecnico': r.tecnico_nombre,
        'codigo_tecnico': r.codigo_tecnico,
        'gps': r.gps,
        'gps_display': MAP_GPS.get(r.gps, r.gps or '—'),
        'vandalismo': r.vandalismo,
        'vandalismo_display': MAP_VAND.get(r.vandalismo, r.vandalismo or 'Ninguno'),
        'simcard': r.simcard,
        'simcard_display': MAP_SIM.get(r.simcard, r.simcard or '—'),
        'adecuacion_electrica': r.adecuacion_electrica,
        'adecuacion_display': MAP_ADEC.get(r.adecuacion_electrica, r.adecuacion_electrica or '—'),
        'ctap': r.ctap,
        'ctap_display': MAP_CTAP.get(r.ctap, r.ctap or '—'),
        'radio_resumen': radio_resumen,
        'radio_badge': radio_badge,
        'radio_perilla': r.radio_perilla,
        'radio_perilla_display': MAP_ESTADO.get(r.radio_perilla, r.radio_perilla or '—'),
        'radio_pedal': r.radio_pedal,
        'radio_pedal_display': MAP_ESTADO.get(r.radio_pedal, r.radio_pedal or '—'),
        'radio_pantalla': r.radio_pantalla,
        'radio_pantalla_display': MAP_ESTADO.get(r.radio_pantalla, r.radio_pantalla or '—'),
        'radio_conexion': r.radio_conexion,
        'radio_instalacion': r.radio_instalacion,
        # radio1: Conexión -> SIMCARD (SI/NO)
        'conexion_simcard': MAP_ESTADO.get(sim_conn, sim_conn or '—'),
        'conexion_simcard_raw': sim_conn,
        # radio2: Instalación -> Instalación (SI/NO)
        'instalacion_val': MAP_ESTADO.get(inst_inst, inst_inst or '—'),
        'instalacion_val_raw': inst_inst,
        'informe': r.informe_tecnico or '',
        'source': r.source or '',
        'report_id': r.report_id or '',
    }
    if not full:
        base['informe_corto'] = (r.informe_tecnico or '')[:80]
    return base

@require_tecnico
def api_formulario_activo(request):
    """Devuelve la plantilla JSON activa del motor de formularios."""
    plantilla = FormularioPlantilla.objects.filter(activa=True).order_by('-version').first()
    if not plantilla:
        return JsonResponse({'status': 'error', 'message': 'No hay plantilla activa'}, status=404)
    patios = list(Patio.objects.filter(activo=True).order_by('orden').values_list('nombre', flat=True))
    return JsonResponse({
        'status': 'ok',
        'codigo': plantilla.codigo,
        'nombre': plantilla.nombre,
        'version': plantilla.version,
        'definicion': plantilla.definicion,
        'patios': patios,
        'tecnico_nombre': request.session.get('tecnico_nombre', ''),
        'tecnico_codigo': request.session.get('tecnico_codigo', ''),
    })

@require_admin
@require_http_methods(['GET', 'POST'])
def api_formulario_editor(request):
    """
    Editor visual de plantilla (sin JSON manual).
    GET: plantilla activa + lista.
    POST: guarda definicion enviada desde el constructor visual.
    """
    if request.method == 'GET':
        plantillas = list(
            FormularioPlantilla.objects.all().order_by('-activa', '-version')
            .values('id', 'codigo', 'nombre', 'version', 'activa')
        )
        pid = request.GET.get('id')
        if pid:
            plantilla = FormularioPlantilla.objects.filter(pk=pid).first()
        else:
            plantilla = FormularioPlantilla.objects.filter(activa=True).order_by('-version').first()
        if not plantilla:
            return JsonResponse({'status': 'error', 'message': 'No hay plantillas'}, status=404)
        return JsonResponse({
            'status': 'ok',
            'plantillas': plantillas,
            'actual': {
                'id': plantilla.id,
                'codigo': plantilla.codigo,
                'nombre': plantilla.nombre,
                'version': plantilla.version,
                'activa': plantilla.activa,
                'definicion': plantilla.definicion,
                'descripcion': plantilla.descripcion,
            },
        })

    # POST guardar
    try:
        body = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'})

    pid = body.get('id')
    plantilla = FormularioPlantilla.objects.filter(pk=pid).first() if pid else None
    if not plantilla:
        plantilla = FormularioPlantilla.objects.filter(activa=True).order_by('-version').first()
    if not plantilla:
        return JsonResponse({'status': 'error', 'message': 'Plantilla no encontrada'}, status=404)

    nombre = (body.get('nombre') or plantilla.nombre).strip()
    definicion = body.get('definicion')
    if not isinstance(definicion, dict) or not definicion.get('sections'):
        return JsonResponse({'status': 'error', 'message': 'La definición debe incluir sections'})

    nueva_version = bool(body.get('nueva_version'))
    if nueva_version:
        activar_nueva = bool(body.get('activar'))
        if activar_nueva:
            FormularioPlantilla.objects.filter(codigo=plantilla.codigo).update(activa=False)
        plantilla = FormularioPlantilla.objects.create(
            codigo=plantilla.codigo,
            nombre=nombre,
            version=plantilla.version + 1,
            activa=activar_nueva,
            definicion=definicion,
            descripcion=body.get('descripcion') or plantilla.descripcion,
        )
    else:
        plantilla.nombre = nombre
        plantilla.definicion = definicion
        if body.get('descripcion') is not None:
            plantilla.descripcion = body.get('descripcion')
        if body.get('activar'):
            FormularioPlantilla.objects.filter(codigo=plantilla.codigo).exclude(pk=plantilla.pk).update(activa=False)
            plantilla.activa = True
        plantilla.save()

    registrar_auditoria(
        request, 'CONFIG', modelo='FormularioPlantilla', objeto_id=str(plantilla.id),
        descripcion=f'Plantilla {plantilla.codigo} v{plantilla.version} actualizada',
    )
    return JsonResponse({
        'status': 'success',
        'message': f'Formulario guardado (v{plantilla.version})',
        'id': plantilla.id,
        'version': plantilla.version,
    })
