"""
Management command: normalizar_patios
------------------------------------------------------------
Arregla el bug de "La Doña" vs "LA DOÑA" (y similares) normalizando
todos los campos de texto libre de patio contra el catálogo real
Patio.nombre.

INSTALACIÓN:
    Copia este archivo a:
    buses/management/commands/normalizar_patios.py

    (si las carpetas management/ y management/commands/ no existen,
    créalas y agrega un __init__.py vacío en cada una)

USO:
    # 1. Simulación — no toca nada, solo te dice qué encontró:
    python manage.py normalizar_patios

    # 2. Aplica los cambios de verdad:
    python manage.py normalizar_patios --apply

    # 3. Si hay nombres que no matchean ningún patio del catálogo
    #    (typos, patios que ya no existen, etc.), los lista aparte
    #    para que tú decidas qué hacer — nunca inventa un match.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from buses.models import (
    Patio, InventarioFlota, BitacoraRegistro, DatosGenesis,
    ReportePendiente, HistorialAtencion, InventarioItem, EEMovil,
)

# (modelo, nombre_del_campo_de_patio)
CAMPOS_PATIO = [
    (InventarioFlota, 'patio_actual'),
    (BitacoraRegistro, 'patio'),
    (DatosGenesis, 'patio_ubicacion'),
    (ReportePendiente, 'patio'),
    (HistorialAtencion, 'patio'),
    (InventarioItem, 'patio'),
    (EEMovil, 'patio'),
]


def normalizar_texto(s: str) -> str:
    return ' '.join((s or '').strip().split())


class Command(BaseCommand):
    help = 'Normaliza campos de texto libre de patio contra el catálogo Patio.nombre'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Aplica los cambios de verdad (si no, solo simula)',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        # Mapa: version_normalizada_en_minuscula -> nombre_canonico
        catalogo = {}
        for p in Patio.objects.all():
            catalogo[normalizar_texto(p.nombre).lower()] = p.nombre
            # también aceptar el código como alias (CHORRILLO -> Chorrillo)
            catalogo[normalizar_texto(p.codigo).lower()] = p.nombre

        if not catalogo:
            self.stdout.write(self.style.ERROR(
                'No hay ningún Patio en el catálogo. Corre primero seed_initial / crea patios.'
            ))
            return

        modo = 'APLICANDO CAMBIOS' if apply_changes else 'SIMULACIÓN (usa --apply para aplicar)'
        self.stdout.write('=' * 70)
        self.stdout.write(f'NORMALIZACIÓN DE PATIOS — {modo}')
        self.stdout.write('=' * 70)

        total_cambios = 0
        sin_match = defaultdict(set)  # valor_crudo -> {modelos donde aparece}

        for modelo, campo in CAMPOS_PATIO:
            valores_en_bd = (
                modelo.objects.exclude(**{f'{campo}': ''})
                .exclude(**{f'{campo}__isnull': True})
                .values_list(campo, flat=True)
                .distinct()
            )

            cambios_este_modelo = []
            for valor_crudo in valores_en_bd:
                valor_norm = normalizar_texto(valor_crudo)
                if not valor_norm:
                    continue
                canonico = catalogo.get(valor_norm.lower())
                if canonico is None:
                    sin_match[valor_crudo].add(modelo.__name__)
                    continue
                if valor_crudo != canonico:
                    cambios_este_modelo.append((valor_crudo, canonico))

            if not cambios_este_modelo:
                continue

            self.stdout.write(f'\n— {modelo.__name__}.{campo}')
            for valor_crudo, canonico in cambios_este_modelo:
                qs = modelo.objects.filter(**{campo: valor_crudo})
                count = qs.count()
                self.stdout.write(
                    f'   "{valor_crudo}" → "{canonico}"  ({count} registros)'
                )
                total_cambios += count
                if apply_changes:
                    with transaction.atomic():
                        qs.update(**{campo: canonico})

        if sin_match:
            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(self.style.WARNING(
                'Valores que NO matchean ningún patio del catálogo (revisar a mano):'
            ))
            for valor_crudo, modelos in sin_match.items():
                self.stdout.write(f'   "{valor_crudo}"  — aparece en: {", ".join(sorted(modelos))}')
            self.stdout.write(
                '\nEstos pueden ser: typos, patios dados de baja, o patios que faltan '
                'en el catálogo. Créalos en /config/ → Patios si son válidos, o corrígelos '
                'a mano si son errores de tipeo.'
            )

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(f'Total de registros {"actualizados" if apply_changes else "a actualizar"}: {total_cambios}')
        if not apply_changes and total_cambios:
            self.stdout.write(self.style.WARNING(
                'Esto fue una simulación. Corre de nuevo con --apply para aplicar.'
            ))
        elif apply_changes:
            self.stdout.write(self.style.SUCCESS('Listo. Los patios quedaron normalizados.'))
