# buses/views/auth.py — generado por 04_dividir_views.ps1

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

from ..models import (
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
