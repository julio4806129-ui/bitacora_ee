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

from .models import (
    Usuario, Patio, InventarioFlota, DispositivoGPS, MovimientoFlota,
    DatosBusae, DatosGenesis, EEMovil, UnidadFueraServicio,
    ReportePendiente, HistorialAtencion, BitacoraRegistro, InventarioItem,
    ConfiguracionSistema, AuditLog, FormularioPlantilla, Ticket, registrar_auditoria,
)


# ── Auth helpers ────────────────────────────────────────────────────────────

def require_tecnico(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get('tecnico_codigo'):
            return redirect('login')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def require_admin(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get('tecnico_codigo'):
            return redirect('login')
        if not request.session.get('is_admin'):
            return JsonResponse({'status': 'error', 'message': 'No autorizado'}, status=403)
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')


# ── LOGIN ROBUSTO ───────────────────────────────────────────────────────────


@ensure_csrf_cookie
def login_view(request):
    """
    Login robusto: código + contraseña.
    - Bloqueo tras N intentos
    - Sesión según config (default 8h)
    - Audit LOGIN / LOGIN_FAIL
    """
    if request.session.get('tecnico_codigo'):
        return redirect('dashboard')

    from buses.models import ConfiguracionSistema
    max_intentos = 5
    bloqueo_min = 15
    sesion_horas = 8
    try:
        cfg_login = ConfiguracionSistema.objects.filter(clave='login_max_intentos').first()
        if cfg_login and isinstance(cfg_login.valor, dict):
            max_intentos = int(cfg_login.valor.get('max', 5))
            bloqueo_min = int(cfg_login.valor.get('bloqueo_minutos', 15))
        cfg_ses = ConfiguracionSistema.objects.filter(clave='sesion_horas').first()
        if cfg_ses and isinstance(cfg_ses.valor, dict):
            sesion_horas = int(cfg_ses.valor.get('horas', 8))
    except Exception:
        pass

    if request.method == 'POST':
        codigo = request.POST.get('codigo', '').strip()
        password = request.POST.get('password', '').strip()

        if not codigo or not password:
            messages.error(request, 'Ingrese código y contraseña.')
            return render(request, 'login.html')

        try:
            user = Usuario.objects.select_related('patio_asignado').get(codigo=codigo)
        except Usuario.DoesNotExist:
            registrar_auditoria(request, 'LOGIN_FAIL', descripcion=f'Código inexistente: {codigo}')
            messages.error(request, 'Código o contraseña incorrectos.')
            return render(request, 'login.html')

        if not user.activo:
            messages.error(request, 'Usuario inactivo. Contacte al administrador.')
            return render(request, 'login.html')

        if user.esta_bloqueado:
            mins = int((user.bloqueado_hasta - timezone.now()).total_seconds() / 60) + 1
            messages.error(request, f'Usuario bloqueado. Intente en {mins} minutos.')
            return render(request, 'login.html')

        if not user.check_password(password):
            user.intentos_fallidos += 1
            if user.intentos_fallidos >= max_intentos:
                user.bloqueado_hasta = timezone.now() + timedelta(minutes=bloqueo_min)
                user.intentos_fallidos = 0
                user.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])
                registrar_auditoria(request, 'LOGIN_FAIL', descripcion=f'Bloqueo por intentos: {codigo}')
                messages.error(request, f'Demasiados intentos. Bloqueado {bloqueo_min} minutos.')
            else:
                user.save(update_fields=['intentos_fallidos'])
                registrar_auditoria(request, 'LOGIN_FAIL', descripcion=f'Password incorrecto: {codigo}')
                messages.error(request, 'Código o contraseña incorrectos.')
            return render(request, 'login.html')

        # OK
        user.intentos_fallidos = 0
        user.bloqueado_hasta = None
        user.ultimo_acceso = timezone.now()
        user.save(update_fields=['intentos_fallidos', 'bloqueado_hasta', 'ultimo_acceso'])

        request.session['tecnico_codigo'] = user.codigo
        request.session['tecnico_nombre'] = user.nombre
        request.session['rol'] = user.rol
        request.session['is_admin'] = user.is_admin
        request.session['is_supervisor'] = user.is_supervisor
        request.session['cuota_diaria'] = user.cuota_diaria
        request.session['patio_asignado_id'] = user.patio_asignado_id
        request.session['patio_asignado_nombre'] = (
            user.patio_asignado.nombre if user.patio_asignado_id else ''
        )
        request.session.set_expiry(sesion_horas * 3600)

        registrar_auditoria(request, 'LOGIN', descripcion=f'Login OK: {user.nombre} ({user.rol})')
        return redirect('dashboard')

    return render(request, 'login.html')


def privacidad_view(request):
    return render(request, 'privacidad.html')


def logout_view(request):
    registrar_auditoria(request, 'LOGOUT')
    request.session.flush()
    return redirect('login')


# ── DASHBOARD ───────────────────────────────────────────────────────────────

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


# ── API REPORTES / INVENTARIO ───────────────────────────────────────────────

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


# ── GUARDAR BITÁCORA 2026 ───────────────────────────────────────────────────

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


# ── CRUD USUARIOS ───────────────────────────────────────────────────────────

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


# ── MÓDULO FLOTA ────────────────────────────────────────────────────────────

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


# ── MÓDULO DISPOSITIVOS GPS ─────────────────────────────────────────────────

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


# ── CARGA MANUAL GENESIS ────────────────────────────────────────────────────

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


# ── CARGA MANUAL BUSAE + POLER HEALTH & SYNC ───────────────────────────────

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


# ── AUDITORÍA ───────────────────────────────────────────────────────────────

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


# ── Helpers ─────────────────────────────────────────────────────────────────


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
        FormularioPlantilla.objects.filter(codigo=plantilla.codigo).update(activa=False)
        plantilla = FormularioPlantilla.objects.create(
            codigo=plantilla.codigo,
            nombre=nombre,
            version=plantilla.version + 1,
            activa=True,
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


# ═══════════════════════════════════════════════════════════════════════════
# FASE 5 — Configuración Global (T5.1–T5.6)
# ═══════════════════════════════════════════════════════════════════════════

# Claves permitidas y sus metadatos (descripción, tipo de valor esperado)
CONFIG_SCHEMA = {
    # General
    'app_nombre':               {'desc': 'Nombre visible de la aplicación', 'group': 'general'},
    # Turno / Poller
    'turno_corte_hora':         {'desc': 'Hora de corte del contador diario (0-23)', 'group': 'turno'},
    'poller_intervalo_minutos': {'desc': 'Intervalo del poller en minutos', 'group': 'poller'},
    'poller_busae_activo':      {'desc': 'Activar sincronización BUSAE', 'group': 'poller'},
    'poller_genesis_activo':    {'desc': 'Activar sincronización Genesis', 'group': 'poller'},
    # Bitácora
    'bitacora_cuota_default':   {'desc': 'Cuota diaria por defecto para nuevos usuarios', 'group': 'bitacora'},
    'bitacora_solo_mi_patio':   {'desc': 'Técnico solo ve buses de su patio', 'group': 'bitacora'},
    # Seguridad
    'login_max_intentos':       {'desc': 'Intentos fallidos antes de bloqueo y minutos de bloqueo', 'group': 'seguridad'},
    'sesion_horas':             {'desc': 'Duración de sesión en horas', 'group': 'seguridad'},
    # Feature flags
    'ff_tickets':               {'desc': 'Activar módulo de tickets', 'group': 'flags'},
    'ff_borradores':            {'desc': 'Activar guardado de borradores de formulario', 'group': 'flags'},
    'ff_exportar_excel':        {'desc': 'Activar exportación a Excel', 'group': 'flags'},
    # Notificaciones Tickets (T6.4)
    'notif_ticket_email':       {'desc': 'Email de alertas para tickets nuevos/actualizados', 'group': 'tickets'},
    'notif_ticket_webhook':     {'desc': 'URL de Webhook Slack/Teams para tickets', 'group': 'tickets'},
    # Privacidad
    'privacidad_retencion_dias': {'desc': 'Días de retención de logs de auditoría', 'group': 'privacidad'},
}


@require_admin
@require_http_methods(['GET', 'POST'])
def api_config(request):
    """
    GET  → devuelve todas las configuraciones con metadatos del esquema
    POST → actualiza una o varias claves (body JSON {clave: valor, ...})
           Solo claves en CONFIG_SCHEMA son aceptadas.
    """
    if request.method == 'GET':
        cfgs = {c.clave: c.valor for c in ConfiguracionSistema.objects.all()}
        resultado = {}
        for clave, meta in CONFIG_SCHEMA.items():
            resultado[clave] = {
                'valor': cfgs.get(clave, None),
                'desc': meta['desc'],
                'group': meta['group'],
            }
        # Incluir claves extra que no estén en el schema (solo lectura)
        for clave, valor in cfgs.items():
            if clave not in resultado:
                resultado[clave] = {'valor': valor, 'desc': '', 'group': 'otros'}
        return JsonResponse({'status': 'ok', 'config': resultado})

    # POST
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    actualizados = []
    errores = []
    for clave, valor in body.items():
        if clave not in CONFIG_SCHEMA:
            errores.append(f'Clave no permitida: {clave}')
            continue
        ConfiguracionSistema.objects.update_or_create(
            clave=clave,
            defaults={
                'valor': valor,
                'descripcion': CONFIG_SCHEMA[clave]['desc'],
            }
        )
        actualizados.append(clave)

    registrar_auditoria(
        request, 'CONFIG_UPDATE',
        descripcion=f'Actualización de configuración: {", ".join(actualizados)}',
    )
    return JsonResponse({
        'status': 'ok',
        'actualizados': actualizados,
        'errores': errores,
    })


@require_admin
@require_http_methods(['GET', 'POST', 'PUT', 'DELETE'])
def api_patios(request):
    """
    GET    → lista todos los patios
    POST   → crea patio nuevo  {codigo, nombre, coe, orden}
    PUT    → edita patio       {id, nombre, coe, orden, activo}
    DELETE → elimina/desactiva {id}
    """
    if request.method == 'GET':
        patios = list(
            Patio.objects.order_by('orden', 'nombre')
            .values('id', 'codigo', 'nombre', 'coe', 'activo', 'orden')
        )
        return JsonResponse({'status': 'ok', 'patios': patios})

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    if request.method == 'POST':
        codigo = body.get('codigo', '').strip().upper().replace(' ', '_')
        nombre = body.get('nombre', '').strip()
        if not codigo or not nombre:
            return JsonResponse({'status': 'error', 'message': 'codigo y nombre son requeridos'}, status=400)
        if Patio.objects.filter(codigo=codigo).exists():
            return JsonResponse({'status': 'error', 'message': f'Ya existe el código {codigo}'}, status=400)
        patio = Patio.objects.create(
            codigo=codigo,
            nombre=nombre,
            coe=body.get('coe', '').strip(),
            orden=int(body.get('orden', 99)),
            activo=True,
        )
        registrar_auditoria(request, 'PATIO_CREAR', descripcion=f'Patio creado: {patio.codigo}')
        return JsonResponse({'status': 'ok', 'id': patio.id, 'codigo': patio.codigo})

    if request.method == 'PUT':
        patio_id = body.get('id')
        try:
            patio = Patio.objects.get(id=patio_id)
        except Patio.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Patio no encontrado'}, status=404)
        patio.nombre = body.get('nombre', patio.nombre).strip()
        patio.coe = body.get('coe', patio.coe).strip()
        patio.orden = int(body.get('orden', patio.orden))
        patio.activo = bool(body.get('activo', patio.activo))
        patio.save()
        registrar_auditoria(request, 'PATIO_EDITAR', descripcion=f'Patio editado: {patio.codigo}')
        return JsonResponse({'status': 'ok'})

    if request.method == 'DELETE':
        patio_id = body.get('id')
        try:
            patio = Patio.objects.get(id=patio_id)
        except Patio.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Patio no encontrado'}, status=404)
        # Si tiene usuarios asignados, solo desactivar
        usuarios_count = patio.usuarios.count() if hasattr(patio, 'usuarios') else 0
        if usuarios_count > 0:
            patio.activo = False
            patio.save(update_fields=['activo'])
            registrar_auditoria(request, 'PATIO_DESACTIVAR', descripcion=f'Patio desactivado (tiene usuarios): {patio.codigo}')
            return JsonResponse({'status': 'ok', 'accion': 'desactivado', 'razon': f'Tiene {usuarios_count} usuario(s) asignado(s)'})
        patio.delete()
        registrar_auditoria(request, 'PATIO_ELIMINAR', descripcion=f'Patio eliminado: {patio_id}')
        return JsonResponse({'status': 'ok', 'accion': 'eliminado'})

    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)


# ═══════════════════════════════════════════════════════════════════════════
# FASE 6 — Tickets / Soporte (T6.1–T6.5)
# ═══════════════════════════════════════════════════════════════════════════

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


