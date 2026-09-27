"""Cliente HTTP/Playwright para el mapa GPS v2 de BUSAE."""
import json
import logging
import os
import re

from django.conf import settings

logger = logging.getLogger('poller.busae')

DEFAULT_LOGIN_PAGE = 'https://login.busae.com/site/login'
DEFAULT_LOGIN_POST = 'https://login.busae.com/user-management/auth/login'
DEFAULT_MAP_PAGE = 'https://login.busae.com/live-gps-map/live-gps-map'
DEFAULT_DATA_URL = 'https://login.busae.com/live-gps-map/update-gps-map-v2'
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


def login_page_url():
    return (getattr(settings, 'BUSAE_URL', '') or DEFAULT_LOGIN_PAGE).strip()


def data_url():
    return (getattr(settings, 'BUSAE_DATA_URL', '') or DEFAULT_DATA_URL).strip()


def map_page_url():
    url = data_url()
    if '/live-gps-map/' in url:
        return url.rsplit('/', 1)[0] + '/live-gps-map'
    return DEFAULT_MAP_PAGE


def get_credentials():
    email = ''
    password = ''
    try:
        from buses.models import ConfiguracionSistema
        conf = ConfiguracionSistema.objects.filter(clave='busae_credenciales').first()
        if conf and isinstance(conf.valor, dict):
            email = str(conf.valor.get('email') or '').strip()
            password = str(conf.valor.get('password') or '').strip()
    except Exception:
        pass

    if not email or not password:
        email = (
            os.environ.get('BUSAE_EMAIL')
            or getattr(settings, 'BUSAE_EMAIL', '')
            or ''
        ).strip()
        password = (
            os.environ.get('BUSAE_PASSWORD')
            or getattr(settings, 'BUSAE_PASSWORD', '')
            or ''
        ).strip()
    return email, password


def _is_login_url(url):
    text = (url or '').lower()
    return 'auth/login' in text or 'site/login' in text


def _extract_csrf(html):
    if not html:
        return ''
    match = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    if match:
        return match.group(1)
    match = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    return match.group(1) if match else ''


def _parse_json(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        alt = text.find('[')
        if start < 0 and alt < 0:
            return None
        if start < 0:
            start = alt
        elif alt >= 0:
            start = min(start, alt)
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            return None


def fetch_via_http(email, password):
    """
    Login HTTP robusto a BUSAE (Yii2) con:
    - Aceptación de cookies
    - CSRF fresco
    - Sesión en caché Redis
    - Validación real de sesión
    """
    import requests
    from django.core.cache import cache

    session = requests.Session()
    session.headers.update({
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
    })

    cookie_key = 'busae:auth:cookies'
    base = 'https://login.busae.com'
    login_get = login_page_url() or f'{base}/site/login'
    login_post = f'{base}/user-management/auth/login'
    map_url = map_page_url()
    data_endpoint = data_url()

    def _request_payload(csrf_token):
        headers = {
            'Referer': map_url,
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }
        # Preferir POST (como hace el mapa real)
        res = session.post(
            data_endpoint,
            data={'refreshnocache': '1', '_csrf': csrf_token or ''},
            headers=headers,
            timeout=25,
            allow_redirects=True,
        )
        if res.status_code == 200 and not _is_login_url(res.url):
            payload = _parse_json(res.text)
            if payload is not None:
                return payload

        # Fallback GET
        res = session.get(
            data_endpoint,
            headers={'Referer': map_url, 'X-Requested-With': 'XMLHttpRequest'},
            timeout=25,
            allow_redirects=True,
        )
        if res.status_code == 200 and not _is_login_url(res.url):
            return _parse_json(res.text)
        return None

    def _session_looks_valid():
        """Comprueba si la sesión actual ya está autenticada."""
        try:
            r = session.get(map_url, timeout=15, allow_redirects=True)
            if r.status_code == 200 and not _is_login_url(r.url):
                return True, _extract_csrf(r.text) or session.cookies.get('_csrf', '')
        except Exception:
            pass
        return False, ''

    # ── 1) Intentar reutilizar cookies en caché ──────────────────────────────
    cached = cache.get(cookie_key)
    if cached:
        session.cookies.update(cached)
        ok, csrf = _session_looks_valid()
        if ok:
            payload = _request_payload(csrf)
            if payload is not None:
                try:
                    from poller.busae_parse import coerce_bus_items
                    n_buses = len(coerce_bus_items(payload))
                except Exception:
                    n_buses = -1
                if n_buses != 0:
                    logger.info('BUSAE - datos via HTTP con sesion en cache (%s buses)', n_buses)
                    return payload
                logger.warning('BUSAE - sesion valida pero payload sin buses, reintentando login fresco')
        # Cache invalida o payload vacio
        cache.delete(cookie_key)
        session.cookies.clear()

    # ── 2) Cargar página de login y obtener CSRF ─────────────────────────────
    try:
        login_page = session.get(login_get, timeout=20, allow_redirects=True)
    except Exception as e:
        logger.warning('BUSAE HTTP — no se pudo cargar página de login: %s', e)
        return None

    csrf = _extract_csrf(login_page.text) or session.cookies.get('_csrf') or ''
    if not csrf:
        # Fallback: meta csrf-token
        match = re.search(r'name="csrf-token"\s+content="([^"]+)"', login_page.text or '')
        if match:
            csrf = match.group(1)

    # ── 3) Aceptar cookies (banner) si existe endpoint simple ────────────────
    # Yii / Busae suele guardar preferencia en cookie; intentamos setear una básica
    session.cookies.set('cookie_consent', 'accepted', domain='login.busae.com')
    session.cookies.set('cookieConsent', 'true', domain='login.busae.com')

    # ── 4) POST de login ─────────────────────────────────────────────────────
    login_data = {
        '_csrf': csrf,
        'LoginForm[username]': email,
        'LoginForm[password]': password,
        'LoginForm[rememberMe]': '1',
    }
    headers_login = {
        'Referer': login_get,
        'Origin': base,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    try:
        login_res = session.post(
            login_post,
            data=login_data,
            headers=headers_login,
            timeout=30,
            allow_redirects=True,
        )
    except Exception as e:
        logger.warning('BUSAE HTTP — error en POST login: %s', e)
        return None

    final_url = (login_res.url or '').lower()
    if _is_login_url(final_url):
        # A veces el form action relativo redirige distinto; reintentar con URL de la página
        form_action = None
        m = re.search(r'<form[^>]+id="login-page"[^>]+action="([^"]+)"', login_page.text or '')
        if m:
            form_action = m.group(1)
            if form_action.startswith('/'):
                form_action = base + form_action
        if form_action and form_action != login_post:
            try:
                login_res = session.post(
                    form_action,
                    data=login_data,
                    headers=headers_login,
                    timeout=30,
                    allow_redirects=True,
                )
                final_url = (login_res.url or '').lower()
            except Exception:
                pass

    if _is_login_url(final_url):
        logger.error('Login BUSAE HTTP fallido — sigue en página de login')
        return None

    # ── 5) Entrar al mapa y pedir datos ──────────────────────────────────────
    try:
        map_res = session.get(map_url, timeout=20, allow_redirects=True)
        if _is_login_url(map_res.url):
            logger.error('Login BUSAE HTTP fallido — redirigido al login al abrir mapa')
            return None
        csrf = _extract_csrf(map_res.text) or session.cookies.get('_csrf') or csrf
    except Exception as e:
        logger.warning('BUSAE HTTP — error al abrir mapa: %s', e)
        return None

    # Guardar sesion valida (45 min para evitar expiracion en servidor)
    cache.set(cookie_key, session.cookies.get_dict(), timeout=2700)

    payload = _request_payload(csrf)
    if payload is not None:
        try:
            from poller.busae_parse import coerce_bus_items
            n = len(coerce_bus_items(payload))
        except Exception:
            n = '?'
        logger.info('BUSAE - login HTTP OK y datos descargados (%s buses)', n)
    else:
        logger.warning('BUSAE HTTP - login OK pero no se pudo parsear payload GPS')
    return payload

def fetch_via_playwright(email, password):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
        )
        page = browser.new_page()
        page.goto(login_page_url(), wait_until='domcontentloaded', timeout=35000)
        try:
            accept_btn = page.locator('button:has-text("Accept all")')
            if accept_btn.count() > 0:
                accept_btn.first.click(timeout=3000)
                page.wait_for_timeout(500)
        except Exception:
            pass

        user_field = page.locator(
            '#loginform-username, input[name="LoginForm[username]"], input[name="username"]'
        )
        if user_field.count() == 0:
            page.goto(DEFAULT_LOGIN_POST, wait_until='domcontentloaded', timeout=30000)
            user_field = page.locator('#loginform-username, input[name="LoginForm[username]"]')

        user_field.first.fill(email, timeout=10000)
        page.locator(
            '#loginform-password, input[name="LoginForm[password]"], input[type="password"]'
        ).first.fill(password)
        page.locator('#submit_login, button[type="submit"]').first.click()
        page.wait_for_timeout(4000)
        page.wait_for_load_state('domcontentloaded', timeout=15000)

        if _is_login_url(page.url):
            browser.close()
            raise RuntimeError('Credenciales incorrectas en el portal BUSAE.')

        page.goto(map_page_url(), wait_until='domcontentloaded', timeout=35000)
        csrf = page.get_attribute('meta[name="csrf-token"]', 'content') or ''
        result_str = page.evaluate(
            '''async ({ csrf, url }) => {
                const headers = {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                };
                let res = await fetch(url, {
                    method: 'POST',
                    headers,
                    body: new URLSearchParams({ refreshnocache: '1', _csrf: csrf || '' }).toString(),
                    credentials: 'same-origin',
                });
                if (!res.ok) {
                    res = await fetch(url, { method: 'GET', headers, credentials: 'same-origin' });
                }
                return await res.text();
            }''',
            {'csrf': csrf, 'url': data_url()},
        )
        browser.close()
        return _parse_json(result_str)


def fetch_payload():
    email, password = get_credentials()
    if not email or not password:
        logger.warning('BUSAE_EMAIL o BUSAE_PASSWORD no configurados')
        return None

    try:
        payload = fetch_via_http(email, password)
        if payload is not None:
            return payload
    except Exception as exc:
        logger.warning('Falló intento HTTP directo BUSAE (%s)', exc)

    try:
        logger.info('BUSAE — extrayendo con Playwright...')
        return fetch_via_playwright(email, password)
    except Exception as exc:
        logger.error('Error Playwright BUSAE: %s', exc)
        return None
