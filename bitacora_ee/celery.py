import os
from celery import Celery

# Set default Django settings module for 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bitacora_ee.settings')

app = Celery('bitacora_ee')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat schedule for poller tasks
app.conf.beat_schedule = {
    'poll-genesis-every-5-min': {
        'task': 'poller.tasks.task_poll_genesis',
        'schedule': 300.0,
    },
    'poll-busae-every-5-min': {
        'task': 'poller.tasks.task_poll_busae',
        'schedule': 300.0,
    },
}
