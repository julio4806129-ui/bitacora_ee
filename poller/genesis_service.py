"""
poller/genesis_service.py
Sincronización JSON-RPC de Genesis con sesión persistente y cruce hacia
reportes pendientes / patio en EEMovil.
"""
import logging
import datetime
import requests
from django.conf import settings
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.core.exceptions import MultipleObjectsReturned

from poller.utils import record_success, record_failure, refresh_pending_cross
from buses.bus_number import extract_bus_number

logger = logging.getLogger('poller.genesis')

GENESIS_URL = (
    getattr(settings, 'GENESIS_URL', '') or 'http://genesis.mibus.com/tic/oi/gateway.php'
).strip()
if not GENESIS_URL:
    GENESIS_URL = 'http://genesis.mibus.com/tic/oi/gateway.php'


def _credentials():
    try:
        from decouple import config
        from buses.models import ConfiguracionSistema
        conf = ConfiguracionSistema.objects.filter(clave='genesis_credenciales').first()
        if conf and isinstance(conf.valor, dict):
            user = conf.valor.get('user') or conf.valor.get('usuario') or ''
            pwd = conf.valor.get('password') or ''
            if user and pwd:
                return str(user).strip(), str(pwd).strip()
        user = config('GENESIS_USER', default='').strip() or getattr(settings, 'GENESIS_USER', '').strip() or '10844'
        pwd = config('GENESIS_PASSWORD', default='').strip() or getattr(settings, 'GENESIS_PASSWORD', '').strip() or 'Mibus2017'
        return str(user).strip(), str(pwd).strip()
    except Exception:
        return ('10844', 'Mibus2017')


def _login(session):
    user, pwd = _credentials()
    url = GENESIS_URL or 'http://genesis.mibus.com/tic/oi/gateway.php'
    try:
        res = session.post(url, json={
            'jsonrpc': '2.0',
            'method': 'login',
            'params': [user, pwd],
            'id': 1
        }, timeout=(4, 8))
        data = res.json()
        if data.get('result'):
            logger.info('Login Genesis exitoso')
            return True, None
        logger.error('Login Genesis fallido: %s', data)
        return False, 'Credenciales incorrectas'
    except requests.exceptions.ConnectionError as e:
        err = str(e)
        if 'getaddrinfo failed' in err or 'NameResolutionError' in err or 'Failed to resolve' in err:
            logger.warning('Genesis no alcanzable — DNS no resuelve. Verificar VPN MiBus.')
            return False, 'Sin conexion (requiere VPN MiBus)'
        logger.warning('No se pudo conectar a Genesis: %s', err[:120])
        return False, 'Sin conexion a Genesis'
    except requests.exceptions.Timeout:
        logger.warning('Genesis timeout al intentar login')
        return False, 'Timeout de conexion a Genesis'
    except Exception as e:
        logger.error('Error login Genesis: %s', e)
        return False, f'Error: {str(e)[:80]}'


def _fetch_monitoreo(session):
    try:
        res = session.post(GENESIS_URL, json={
            'jsonrpc': '2.0',
            'method': 'US_Monitoreo',
            'params': [],
            'id': 2
        }, timeout=45)
        data = res.json()
        result = data.get('result', [])
        if isinstance(result, dict) and isinstance(result.get('buses'), dict):
            result = list(result['buses'].values())
        elif isinstance(result, dict):
            result = list(result.values())
        if not isinstance(result, list):
            logger.warning('Genesis US_Monitoreo con estructura inesperada')
            return []
        logger.info('Genesis monitoreo: %s registros', len(result))
        return result
    except Exception as e:
        logger.error('Error US_Monitoreo Genesis: %s', e)
        return []


def _str(val):
    if val is None or val in (0, '0', '', 'None'):
        return ''
    return str(val).strip()


def _calcular_patio_ubicacion(item):
    """Patio más preciso: inoperativo→origen; en vía→destino o 'En vía'; vacío→origen."""
    estado = _str(item.get('Estado')).lower()
    origen = _str(item.get('Origen'))
    destino = _str(item.get('Destino'))

    if estado == 'inoperativo':
        return origen
    if estado in ('en via', 'en vía', 'operativo'):
        if destino and destino.lower() not in ('en via', 'en vía', ''):
            return destino
        return origen or destino
    if not destino:
        return origen
    return destino or origen


def _calcular_hora_entrada(item):
    estado = _str(item.get('Estado'))
    origen = _str(item.get('Origen'))
    horafin = _str(item.get('Horafin'))

    if not estado or estado.lower() == 'inoperativo':
        return ''
    if not horafin:
        return 'Relevo' if origen.lower() == 'en via' else ''
    return horafin


def _upsert_genesis(bus_num, defaults):
    from buses.models import DatosGenesis
    try:
        DatosGenesis.objects.update_or_create(bus_movil=bus_num, defaults=defaults)
    except (MultipleObjectsReturned, IntegrityError):
        obj = (
            DatosGenesis.objects.filter(bus_movil=bus_num)
            .order_by('-sincronizado_en', '-id')
            .first()
        )
        if obj:
            for key, value in defaults.items():
                setattr(obj, key, value)
            obj.save()


def _save_to_db(items):
    from buses.models import EEMovil

    saved = 0
    now_dt = timezone.now()
    bus_ids = []

    with transaction.atomic():
        for item in items:
            try:
                bus_num = extract_bus_number(item)
                if not bus_num:
                    continue

                patio_calc = _calcular_patio_ubicacion(item)
                hora_calc = _calcular_hora_entrada(item)
                estado_bus = _str(item.get('Estado')) or 'Operativo'

                hora_entrada_dt = now_dt
                if hora_calc and ':' in hora_calc and hora_calc.lower() != 'relevo':
                    try:
                        partes = [int(p) for p in hora_calc.split(':')[:3]]
                        while len(partes) < 3:
                            partes.append(0)
                        hora_entrada_dt = timezone.make_aware(
                            datetime.datetime.combine(
                                now_dt.date(),
                                datetime.time(*partes)
                            )
                        )
                    except Exception:
                        hora_entrada_dt = now_dt

                _upsert_genesis(bus_num, {
                    'origen': _str(item.get('Origen')),
                    'destino': _str(item.get('Destino')),
                    'hora_entrada': hora_entrada_dt,
                    'patio_ubicacion': patio_calc,
                    'datos_extra': {
                        'estado': estado_bus,
                        'estado_bus': estado_bus,
                        'origen': _str(item.get('Origen')),
                        'destino': _str(item.get('Destino')),
                        'opreal': _str(item.get('Opreal')),
                        'horafin': _str(item.get('Horafin')),
                        'ruta': _str(item.get('Ruta', '')),
                        'hora_entrada_patio': hora_calc,
                    }
                })

                if patio_calc:
                    EEMovil.objects.filter(bus_movil=bus_num).update(patio=patio_calc)
                    from buses.models import InventarioFlota
                    InventarioFlota.objects.filter(bus_movil=bus_num).update(
                        patio_actual=patio_calc,
                        estado_genesis=estado_bus
                    )

                bus_ids.append(bus_num)
                saved += 1
            except Exception as e:
                logger.warning('Error guardando Genesis bus %s: %s', item.get('Bus'), e)

    if bus_ids:
        refresh_pending_cross(bus_ids)
    return saved


def run():
    logger.info('Genesis — iniciando ciclo de extraccion...')
    session = requests.Session()
    session.headers.update({'Content-Type': 'application/json'})
    ok, err_msg = _login(session)
    if not ok:
        logger.warning('Genesis — ciclo omitido (%s)', err_msg)
        record_failure('genesis', err_msg or 'Login Genesis fallido')
        return {'status': 'error', 'message': err_msg or 'Login Genesis fallido'}

    items = _fetch_monitoreo(session)
    if not items:
        logger.warning('Genesis — sin datos recibidos')
        record_failure('genesis', 'Sin datos')
        return {'status': 'empty', 'message': 'Sin datos'}

    saved = _save_to_db(items)
    record_success('genesis', extra={'guardados': saved})
    logger.info('Genesis — %s buses actualizados en BD', saved)
    return {'status': 'ok', 'saved': saved}
