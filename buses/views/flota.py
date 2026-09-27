# buses/views/flota.py — generado por 04_dividir_views.ps1

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
def api_flota(request):
    qs = InventarioFlota.objects.select_related('patio_base').all()
    estado = request.GET.get('estado')
    patio = request.GET.get('patio')
    q = request.GET.get('q')
    if estado:
        qs = qs.filter(estado_operativo=estado)
    if patio:
        qs = qs.filter(Q(patio_base__codigo=patio) | Q(patio_actual__icontains=patio))
    if q:
        qs = qs.filter(Q(bus_movil__icontains=q) | Q(placa__icontains=q))
    data = [{
        'bus_movil': b.bus_movil,
        'placa': b.placa or '',
        'estado_operativo': b.estado_operativo,
        'patio_base': b.patio_base.nombre if b.patio_base else '',
        'patio_actual': b.patio_actual or '',
        'coe': b.coe or '',
        'estado_genesis': b.estado_genesis or '',
        'estado_sistema': b.estado_sistema or '',
        'sistema_instalado': b.sistema_instalado or '',
        'estado_busae': b.estado_busae or '',
        'estado_fw': b.estado_fw or '',
        'estado_bocina': b.estado_bocina or '',
        'adecuacion_bocina': b.adecuacion_bocina or '',
        'adecuacion_electrica': b.adecuacion_electrica or '',
        'anclaje_bocinas': b.anclaje_bocinas or '',
        'comentarios': b.comentarios or '',
        'tecnico_asignado': getattr(b, 'tecnico_asignado', '') or '',
        'mes_instalado': b.mes_instalado or '',
        'mes_revisado': b.mes_revisado or '',
        'marca_modelo': getattr(b, 'marca_modelo', '') or '',
        'anio': getattr(b, 'anio', None),
        'fecha_baja': b.fecha_baja.isoformat() if getattr(b, 'fecha_baja', None) else '',
        'notas': getattr(b, 'notas', '') or '',
    } for b in qs]
    return JsonResponse({'status': 'ok', 'data': data, 'total': len(data)})

@require_admin
@require_POST
def api_flota_accion(request):
    """Acciones: alta, baja, mover patio, cambiar estado."""
    body = json.loads(request.body.decode('utf-8'))
    accion = body.get('accion')  # alta | baja | mover | estado
    bus_num = int(body.get('bus_movil', 0))
    codigo = request.session.get('tecnico_codigo', '')

    if accion == 'alta':
        if InventarioFlota.objects.filter(bus_movil=bus_num).exists():
            return JsonResponse({'status': 'error', 'message': 'Bus ya existe'})
        patio = None
        if body.get('patio_base'):
            patio = Patio.objects.filter(codigo=body['patio_base']).first()
        b = InventarioFlota.objects.create(
            bus_movil=bus_num,
            placa=body.get('placa', ''),
            marca_modelo=body.get('marca_modelo', ''),
            anio=body.get('anio') or None,
            estado_operativo=body.get('estado_operativo', 'ACTIVO'),
            patio_base=patio,
            fecha_alta=timezone.now().date(),
            notas=body.get('notas', ''),
        )
        MovimientoFlota.objects.create(
            tipo='ALTA', bus_movil=bus_num, detalle=f'Alta bus {bus_num}',
            datos={'placa': b.placa}, realizado_por=codigo,
        )
        registrar_auditoria(request, 'CREATE', 'InventarioFlota', bus_num, f'Alta bus {bus_num}')
        return JsonResponse({'status': 'success', 'message': f'Bus {bus_num} dado de alta.'})

    try:
        b = InventarioFlota.objects.get(bus_movil=bus_num)
    except InventarioFlota.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Bus no encontrado'})

    if accion == 'baja':
        b.estado_operativo = 'BAJA'
        b.fecha_baja = timezone.now().date()
        b.motivo_baja = body.get('motivo', '')
        b.save()
        MovimientoFlota.objects.create(
            tipo='BAJA', bus_movil=bus_num, detalle=b.motivo_baja, realizado_por=codigo,
        )
        registrar_auditoria(request, 'BAJA', 'InventarioFlota', bus_num, b.motivo_baja)
        return JsonResponse({'status': 'success', 'message': f'Bus {bus_num} dado de baja.'})

    if accion == 'mover':
        patio_cod = body.get('patio_base', '')
        patio = Patio.objects.filter(codigo=patio_cod).first()
        antes = b.patio_base.codigo if b.patio_base else ''
        b.patio_base = patio
        b.save(update_fields=['patio_base', 'actualizado_en'])
        MovimientoFlota.objects.create(
            tipo='MOVER_PATIO', bus_movil=bus_num,
            detalle=f'{antes} → {patio_cod}', realizado_por=codigo,
        )
        registrar_auditoria(request, 'MOVER', 'InventarioFlota', bus_num, f'Patio {antes}→{patio_cod}')
        return JsonResponse({'status': 'success', 'message': 'Patio actualizado.'})

    if accion == 'estado':
        nuevo = body.get('estado_operativo', b.estado_operativo)
        antes = b.estado_operativo
        b.estado_operativo = nuevo
        b.save(update_fields=['estado_operativo', 'actualizado_en'])
        MovimientoFlota.objects.create(
            tipo='CAMBIO_ESTADO', bus_movil=bus_num,
            detalle=f'{antes} → {nuevo}', realizado_por=codigo,
        )
        registrar_auditoria(request, 'UPDATE', 'InventarioFlota', bus_num, f'Estado {antes}→{nuevo}')
        return JsonResponse({'status': 'success', 'message': 'Estado actualizado.'})

    if accion == 'asignar_tecnico':
        nombre = (body.get('tecnico') or '').strip()
        b.tecnico_asignado = nombre
        b.save(update_fields=['tecnico_asignado', 'actualizado_en'])
        MovimientoFlota.objects.create(
            tipo='OTRO', bus_movil=bus_num,
            detalle=f'Técnico asignado: {nombre or "(ninguno)"}', realizado_por=codigo,
        )
        registrar_auditoria(request, 'ASIGNAR', 'InventarioFlota', bus_num, f'Técnico → {nombre}')
        return JsonResponse({'status': 'success', 'message': f'Técnico asignado: {nombre or "—"}.'})

    return JsonResponse({'status': 'error', 'message': 'Acción no reconocida'})

@require_admin
@require_POST
def api_flota_import(request):
    """Importar matriz de buses desde CSV (columnas: bus_movil,placa,patio,estado,marca_modelo,anio)."""
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'status': 'error', 'message': 'No se recibió archivo'})
    try:
        text = f.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        created = updated = 0
        codigo = request.session.get('tecnico_codigo', '')
        with transaction.atomic():
            for row in reader:
                bus = int(str(row.get('bus_movil') or row.get('bus') or row.get('movil') or '0').strip())
                if not bus:
                    continue
                placa = (row.get('placa') or '').strip()
                estado = (row.get('estado') or row.get('estado_operativo') or 'ACTIVO').strip().upper()
                if estado not in dict(InventarioFlota.ESTADO_CHOICES):
                    estado = 'ACTIVO'
                patio_cod = (row.get('patio') or row.get('patio_base') or '').strip()
                patio = Patio.objects.filter(Q(codigo__iexact=patio_cod) | Q(nombre__iexact=patio_cod)).first()
                defaults = {
                    'placa': placa,
                    'estado_operativo': estado,
                    'marca_modelo': (row.get('marca_modelo') or row.get('modelo') or '').strip(),
                    'anio': int(row['anio']) if row.get('anio') and str(row['anio']).isdigit() else None,
                    'patio_base': patio,
                }
                obj, was_created = InventarioFlota.objects.update_or_create(
                    bus_movil=bus, defaults=defaults
                )
                if was_created:
                    created += 1
                    MovimientoFlota.objects.create(
                        tipo='ALTA', bus_movil=bus, detalle='Import CSV', realizado_por=codigo
                    )
                else:
                    updated += 1
        registrar_auditoria(request, 'IMPORT', 'InventarioFlota',
                            descripcion=f'CSV: {created} nuevos, {updated} actualizados')
        return JsonResponse({
            'status': 'success',
            'message': f'Importados: {created} nuevos, {updated} actualizados.',
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_admin
@require_POST
def api_flota_import_matriz(request):
    """Importa archivo MATRIZ.xlsx (hojas MATRIZ FLOTA + BUSES TMP)."""
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'status': 'error', 'message': 'No se recibió archivo'})
    if not f.name.lower().endswith(('.xlsx', '.xls')):
        return JsonResponse({'status': 'error', 'message': 'Debe ser un archivo Excel (.xlsx)'})
    try:
        from django.core.management import call_command
        from io import StringIO
        # Guardar temporalmente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            for chunk in f.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        out = StringIO()
        call_command('import_matriz', tmp_path, stdout=out)
        os.unlink(tmp_path)
        msg = out.getvalue().strip().split('\n')[-1] if out.getvalue() else 'Importación completada'
        registrar_auditoria(request, 'IMPORT', 'InventarioFlota', descripcion=f'Matriz Excel: {f.name} — {msg}')
        return JsonResponse({'status': 'success', 'message': msg})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
