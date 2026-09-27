"""
poller/scheduler.py
APScheduler: Genesis primero (patio / hora) y luego BUSAE para el cruce.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.conf import settings

logger = logging.getLogger('poller.scheduler')

_scheduler = None


def start():
    # DESACTIVADO: ahora se usa solo Celery Beat (evitar doble polling)
    logger.warning('APScheduler desactivado. Usando solo Celery Beat.')
    return

    # --- código original queda debajo, no se ejecuta ---
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info('Scheduler ya está corriendo')
        return

    from poller.busae_service import run as run_busae
    from poller.genesis_service import run as run_genesis

    interval = int(getattr(settings, 'POLL_INTERVAL_MINUTES', 5) or 5)

    _scheduler = BackgroundScheduler(
        timezone='America/Panama',
        job_defaults={
            'coalesce': True,
            'max_instances': 1,
        }
    )

    _scheduler.add_job(
        run_genesis,
        trigger=IntervalTrigger(minutes=interval),
        id='genesis_poll',
        name='Actualizar datos Genesis',
        replace_existing=True,
        misfire_grace_time=120,
        next_run_time=None,
    )

    _scheduler.add_job(
        run_busae,
        trigger=IntervalTrigger(minutes=interval),
        id='busae_poll',
        name='Actualizar estado GPS (BUSAE)',
        replace_existing=True,
        misfire_grace_time=120,
        next_run_time=None,
    )

    _scheduler.start()
    logger.info(
        'Scheduler iniciado — ciclos cada %s min (Genesis + BUSAE)',
        interval,
    )

    try:
        from datetime import timedelta
        from django.utils import timezone as dj_tz
        _scheduler.add_job(
            run_now,
            trigger='date',
            run_date=dj_tz.now() + timedelta(seconds=12),
            id='poller_bootstrap',
            name='Ciclo inicial Genesis + BUSAE',
            replace_existing=True,
        )
    except Exception as e:
        logger.warning('No se pudo encolar el ciclo inicial: %s', e)


def stop():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info('Scheduler detenido')


def run_now():
    from poller.busae_service import run as run_busae
    from poller.genesis_service import run as run_genesis

    logger.info('Ejecutando ciclo (Genesis → BUSAE)...')
    res_genesis = run_genesis()
    res_busae = run_busae()
    logger.info('Ciclo completado')
    return {
        'genesis': res_genesis,
        'busae': res_busae
    }
