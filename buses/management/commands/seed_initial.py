"""python manage.py seed_initial — patios, usuarios, config mínima."""
from django.core.management.base import BaseCommand
from buses.models import Patio, Usuario, ConfiguracionSistema, FormularioPlantilla
from buses.form_templates import REVISION_2026


class Command(BaseCommand):
    help = 'Carga patios (COE), usuarios iniciales y config por defecto'

    def handle(self, *args, **options):
        patios_data = [
            ('CHORRILLO', 'Chorrillo', 'P-CHORRILLO', 1),
            ('CURUNDU', 'Curundú', 'P-CURUNDU', 2),
            ('LA_DONA', 'La Doña', 'P-NDONA', 3),
            ('LOS_PUEBLOS', 'Los Pueblos', 'P-PUEBLOS', 4),
            ('LA_CABIMA', 'La Cabima', 'P-CABIMA', 5),
            ('OJO_DE_AGUA', 'Ojo de Agua', 'P-OAGUA', 6),
        ]
        patio_objs = {}
        for cod, nom, coe, ord_ in patios_data:
            obj, _ = Patio.objects.update_or_create(
                codigo=cod,
                defaults={'nombre': nom, 'coe': coe, 'orden': ord_, 'activo': True},
            )
            patio_objs[cod] = obj
        self.stdout.write(self.style.SUCCESS(f'Patios: {Patio.objects.count()}'))

        # ID | NOMBRE | PATIO | PASSWORD | ROL | CUOTA  (password solo en seed; luego hash)
        users = [
            ('13283', 'JULIO SANTAMARIA', 'LA_CABIMA', 'admin123', 'ADMIN', 20),
            ('10844', 'Lester Ballesteros', 'LA_DONA', 'admin123', 'ADMIN', 10),
            ('9335', 'Admin 9335', 'CHORRILLO', 'tecnico123', 'SUPERVISOR', 10),
            ('12517', 'Técnico 12517', 'LOS_PUEBLOS', 'tecnico123', 'TECNICO', 8),
            ('12505', 'Técnico 12505', 'OJO_DE_AGUA', 'tecnico123', 'TECNICO', 8),
        ]
        for cod, nom, patio_cod, raw_pw, rol, cuota in users:
            u, created = Usuario.objects.update_or_create(
                codigo=cod,
                defaults={
                    'nombre': nom,
                    'patio_asignado': patio_objs.get(patio_cod),
                    'rol': rol,
                    'cuota_diaria': cuota,
                    'activo': True,
                },
            )
            # Solo setear password si es nuevo o no tiene hash
            if created or not u.password_hash:
                u.set_password(raw_pw)
                u.save(update_fields=['password_hash'])
        self.stdout.write(self.style.SUCCESS(f'Usuarios: {Usuario.objects.count()}'))

        defaults_cfg = {
            'app_nombre':               {'valor': {'nombre': 'Bitácora E.E'}, 'desc': 'Nombre visible de la app'},
            'turno_corte_hora':         {'valor': {'hora': 8}, 'desc': 'Hora de corte del contador diario (0-23)'},
            'poller_intervalo_minutos': {'valor': {'minutos': 5}, 'desc': 'Intervalo poller en minutos'},
            'poller_busae_activo':      {'valor': {'activo': True}, 'desc': 'Activar sincronización BUSAE'},
            'poller_genesis_activo':    {'valor': {'activo': True}, 'desc': 'Activar sincronización Genesis'},
            'login_max_intentos':       {'valor': {'max': 5, 'bloqueo_minutos': 15}, 'desc': 'Seguridad login'},
            'sesion_horas':             {'valor': {'horas': 8}, 'desc': 'Duración de sesión'},
            'bitacora_cuota_default':   {'valor': {'cuota': 10}, 'desc': 'Cuota diaria por defecto'},
            'bitacora_solo_mi_patio':   {'valor': {'activo': True}, 'desc': 'Técnico solo ve su patio'},
            'ff_tickets':               {'valor': {'activo': True}, 'desc': 'Feature flag: módulo de tickets'},
            'ff_borradores':            {'valor': {'activo': False}, 'desc': 'Feature flag: borradores de formulario'},
            'ff_exportar_excel':        {'valor': {'activo': False}, 'desc': 'Feature flag: exportar a Excel'},
            'notif_ticket_email':       {'valor': {'email': ''}, 'desc': 'Email para recibir alertas de tickets'},
            'notif_ticket_webhook':     {'valor': {'url': ''}, 'desc': 'Webhook Slack/Teams para alertas de tickets'},
            'privacidad_retencion_dias': {'valor': {'dias': 90}, 'desc': 'Días de retención de logs de auditoría'},
        }
        for clave, meta in defaults_cfg.items():
            ConfiguracionSistema.objects.update_or_create(
                clave=clave,
                defaults={'valor': meta['valor'], 'descripcion': meta['desc']},
            )
        self.stdout.write(self.style.SUCCESS(f'Config: {ConfiguracionSistema.objects.count()} claves'))
        
        # Plantilla formulario activa
        FormularioPlantilla.objects.filter(codigo='revision_2026').update(activa=False)
        FormularioPlantilla.objects.update_or_create(
            codigo='revision_2026',
            version=1,
            defaults={
                'nombre': 'Revisión Equip. Embarcado 2026',
                'activa': True,
                'definicion': REVISION_2026,
                'descripcion': 'Formulario oficial de atención EE',
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f'Plantillas activas: {FormularioPlantilla.objects.filter(activa=True).count()}'
        ))

        self.stdout.write(self.style.WARNING('Login demo: 13283 / admin123  (cambiar en producción)'))
