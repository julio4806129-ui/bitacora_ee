"""
buses/management/commands/run_poller.py
Comando de administración para ejecutar el Poller de forma manual o en loop.
"""
import time
from django.core.management.base import BaseCommand
from django.conf import settings
from poller.busae_service import run as run_busae
from poller.genesis_service import run as run_genesis
from poller.utils import get_poller_health


class Command(BaseCommand):
    help = 'Ejecuta el ciclo de sincronización del Poller (Genesis y BUSAE)'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Ejecuta un único ciclo y termina')
        parser.add_argument('--genesis-only', action='store_true', help='Ejecuta solo la sincronización de Genesis')
        parser.add_argument('--busae-only', action='store_true', help='Ejecuta solo la sincronización de BUSAE')
        parser.add_argument('--loop', action='store_true', help='Ejecuta en bucle continuo cada N minutos')
        parser.add_argument('--interval', type=int, default=0, help='Intervalo en minutos para el modo loop')
        parser.add_argument('--status', action='store_true', help='Muestra el estado de salud actual del Poller')

    def handle(self, *args, **options):
        if options['status']:
            health = get_poller_health()
            self.stdout.write(self.style.SUCCESS(f"Estado Poller: {health}"))
            return

        interval = options['interval'] or getattr(settings, 'POLL_INTERVAL_MINUTES', 5) or 5
        genesis_only = options['genesis_only']
        busae_only = options['busae_only']
        loop = options['loop']

        def _do_cycle():
            self.stdout.write(self.style.NOTICE("--- Iniciando ciclo de Poller ---"))
            if not busae_only:
                self.stdout.write("Ejecutando Genesis...")
                g_res = run_genesis()
                self.stdout.write(f"Genesis resultado: {g_res}")

            if not genesis_only:
                self.stdout.write("Ejecutando BUSAE...")
                b_res = run_busae()
                self.stdout.write(f"BUSAE resultado: {b_res}")
            self.stdout.write(self.style.SUCCESS("--- Ciclo completado ---"))

        if loop:
            self.stdout.write(self.style.SUCCESS(f"Iniciando Poller en modo bucle (cada {interval} min). CTRL+C para detener."))
            while True:
                try:
                    _do_cycle()
                    time.sleep(interval * 60)
                except KeyboardInterrupt:
                    self.stdout.write(self.style.WARNING("Poller detenido por usuario."))
                    break
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error en ciclo: {e}"))
                    time.sleep(30)
        else:
            _do_cycle()
