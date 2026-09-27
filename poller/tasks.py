"""
poller/tasks.py
Tareas periódicas y asíncronas de Celery para el Poller (Genesis y BUSAE).
"""
import logging
from celery import shared_task

logger = logging.getLogger('poller.tasks')


@shared_task(name='poller.tasks.task_poll_genesis', bind=True, max_retries=2, default_retry_delay=60)
def task_poll_genesis(self):
    """Sincroniza datos de Genesis (patio, hora, estado)."""
    logger.info('[Celery] Ejecutando sincronización de Genesis...')
    try:
        from poller.genesis_service import run
        res = run()
        logger.info('[Celery] Sincronización Genesis finalizada: %s', res)
        return res
    except Exception as exc:
        logger.error('[Celery] Error en sincronización Genesis: %s', exc)
        raise self.retry(exc=exc)


@shared_task(name='poller.tasks.task_poll_busae', bind=True, max_retries=2, default_retry_delay=60)
def task_poll_busae(self):
    """Sincroniza telemetría BUSAE y actualiza reportes pendientes."""
    logger.info('[Celery] Ejecutando sincronización de BUSAE...')
    try:
        from poller.busae_service import run
        res = run()
        logger.info('[Celery] Sincronización BUSAE finalizada: %s', res)
        return res
    except Exception as exc:
        logger.error('[Celery] Error en sincronización BUSAE: %s', exc)
        raise self.retry(exc=exc)


@shared_task(name='poller.tasks.task_poll_all')
def task_poll_all():
    """Ejecuta ciclo completo: Genesis primero, luego BUSAE para cruzar patios."""
    logger.info('[Celery] Ejecutando ciclo completo (Genesis -> BUSAE)...')
    from poller.scheduler import run_now
    return run_now()
