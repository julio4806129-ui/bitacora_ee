"""
Módulo de notificaciones (T6.4) — Email / Webhook (Slack, Teams, Discord)
Permite enviar alertas automáticas cuando se crea o actualiza un ticket.
Es tolerante a fallos: si falla la red o el servicio externo, no detiene el flujo principal.
"""
import json
import logging
import urllib.request
import urllib.error
from django.conf import settings
from django.core.mail import send_mail
from .models import ConfiguracionSistema

logger = logging.getLogger(__name__)


def enviar_notificacion_ticket(ticket, accion='creado', comentario=None):
    """
    Envía notificación por Webhook (Slack/Teams) y/o Email según la configuración activa.
    accion: 'creado', 'actualizado', 'comentario', 'resuelto'
    """
    try:
        # 1. Obtener configuraciones
        cfgs = {c.clave: c.valor for c in ConfiguracionSistema.objects.filter(
            clave__in=['notif_ticket_webhook', 'notif_ticket_email', 'app_nombre']
        )}
        webhook_cfg = cfgs.get('notif_ticket_webhook', {})
        webhook_url = webhook_cfg.get('url', '').strip() if isinstance(webhook_cfg, dict) else ''

        email_cfg = cfgs.get('notif_ticket_email', {})
        dest_email = email_cfg.get('email', '').strip() if isinstance(email_cfg, dict) else ''

        app_name = 'Bitácora E.E'
        if isinstance(cfgs.get('app_nombre'), dict):
            app_name = cfgs['app_nombre'].get('nombre', app_name)

        # Si no hay destinos configurados, terminar silenciosamente
        if not webhook_url and not dest_email:
            return

        # 2. Construir mensaje
        bus_str = f' (Bus: {ticket.bus_movil})' if ticket.bus_movil else ''
        patio_str = f' | Patio: {ticket.patio.nombre}' if ticket.patio else ''
        prioridad_icon = {
            'CRITICA': '🚨 [CRÍTICA]',
            'ALTA': '⚠️ [ALTA]',
            'MEDIA': 'ℹ️ [MEDIA]',
            'BAJA': '🟢 [BAJA]'
        }.get(ticket.prioridad, f'[{ticket.prioridad}]')

        titulo_notif = f'[{app_name}] Ticket #{ticket.id} {accion.upper()}: {ticket.titulo}'

        lineas = [
            f"*{prioridad_icon} Ticket #{ticket.id} — {ticket.titulo}*",
            f"• Estado: {ticket.estado} | Categoría: {ticket.categoria}{bus_str}{patio_str}",
            f"• Reportado por: {ticket.creado_por_nombre} ({ticket.creado_por_codigo})",
        ]
        if ticket.asignado_a_nombre:
            lineas.append(f"• Asignado a: {ticket.asignado_a_nombre}")
        if accion == 'creado':
            lineas.append(f"\n*Descripción:*\n{ticket.descripcion}")
        elif accion == 'resuelto':
            lineas.append(f"\n*Resolución:*\n{ticket.resolucion or 'Sin detalle adicional'}")
        elif accion == 'comentario' and comentario:
            lineas.append(f"\n*Nuevo comentario de {comentario.get('autor_nombre', 'Usuario')}:*\n{comentario.get('texto', '')}")

        texto_plano = "\n".join(lineas)

        # 3. Enviar a Webhook (Slack / Teams / Discord / genérico)
        if webhook_url:
            try:
                payload = json.dumps({
                    'text': texto_plano,
                    'username': f'{app_name} Bot',
                    'icon_emoji': ':ticket:'
                }).encode('utf-8')
                req = urllib.request.Request(
                    webhook_url,
                    data=payload,
                    headers={'Content-Type': 'application/json', 'User-Agent': 'BitacoraEE-Notifier/1.0'}
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    logger.info("Notificación de ticket #%s enviada a webhook (status %s)", ticket.id, resp.status)
            except Exception as e_webhook:
                logger.warning("No se pudo enviar webhook para ticket #%s: %s", ticket.id, e_webhook)

        # 4. Enviar a Email si está configurado
        if dest_email and getattr(settings, 'EMAIL_HOST', None):
            try:
                send_mail(
                    subject=titulo_notif,
                    message=texto_plano,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'bitacora@mibus.com.pa'),
                    recipient_list=[dest_email],
                    fail_silently=True,
                )
                logger.info("Email de ticket #%s enviado a %s", ticket.id, dest_email)
            except Exception as e_email:
                logger.warning("No se pudo enviar email para ticket #%s: %s", ticket.id, e_email)

    except Exception as e:
        logger.exception("Error general al procesar notificación de ticket: %s", e)
