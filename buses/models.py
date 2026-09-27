"""
Bitácora E.E — Modelos definitivos
===================================
Fuentes de verdad:
  - MATRIZ.xlsx (MATRIZ FLOTA + BUSES TMP)
  - Formulario Google «REVISIÓN EQUIP. EMBARCADO 2026»
  - Poller BUSAE (GPS) + Genesis (patio / hora)
  - App GAS original (usuarios, reportes, bitácora, historial)
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


# ═══════════════════════════════════════════════════════════════════════════
# 1. CATÁLOGOS
# ═══════════════════════════════════════════════════════════════════════════

class Patio(models.Model):
    codigo = models.CharField(max_length=30, unique=True)   # CHORRILLO, LA_DONA…
    nombre = models.CharField(max_length=80)                # Chorrillo, La Doña…
    coe = models.CharField(max_length=20, blank=True)       # P-CHORRILLO, P-NDONA…
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'patios'
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre


# ═══════════════════════════════════════════════════════════════════════════
# 2. USUARIOS
# ═══════════════════════════════════════════════════════════════════════════

class Usuario(models.Model):
    """
    Técnico / supervisor / admin.
    Estructura alineada a hoja USUARIOS:
    ID | NOMBRE | PATIO ASIGNADO | CONTRASEÑA | ROL | CUOTA DIARIA
    """
    ROL_CHOICES = [
        ('TECNICO', 'Técnico'),
        ('SUPERVISOR', 'Supervisor'),
        ('ADMIN', 'Administrador'),
    ]
    codigo = models.CharField(max_length=20, primary_key=True)  # ID técnico (PK)
    nombre = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    patio_asignado = models.ForeignKey(
        'Patio', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='usuarios', verbose_name='Patio asignado',
    )
    password_hash = models.CharField(max_length=128, blank=True)  # nunca texto plano
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default='TECNICO', db_index=True)
    cuota_diaria = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    django_user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='perfil_tecnico',
    )
    ultimo_acceso = models.DateTimeField(null=True, blank=True)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'usuarios'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.codigo} — {self.nombre}'

    @property
    def is_admin(self):
        return self.rol == 'ADMIN'

    @property
    def is_supervisor(self):
        return self.rol in ('ADMIN', 'SUPERVISOR')

    @property
    def esta_bloqueado(self):
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > timezone.now())

    def set_password(self, raw_password: str):
        from django.contrib.auth.hashers import make_password
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        from django.contrib.auth.hashers import check_password
        if not self.password_hash or not raw_password:
            return False
        return check_password(raw_password, self.password_hash)


# ═══════════════════════════════════════════════════════════════════════════
# 3. FLOTA (matriz de buses + estado EE)
# ═══════════════════════════════════════════════════════════════════════════

class InventarioFlota(models.Model):
    """Un bus de la flota con su estado de equipo embarcado (MATRIZ.xlsx)."""

    ESTADO_OP = [
        ('ACTIVO', 'Activo'),
        ('MANTENIMIENTO', 'Mantenimiento / Inoperativo'),
        ('POR_INSTALAR', 'Por instalar'),
        ('DESCARTADO', 'Descartado'),
        ('BAJA', 'Baja'),
        ('RESERVA', 'Reserva'),
    ]

    bus_movil = models.PositiveIntegerField(primary_key=True)
    placa = models.CharField(max_length=20, blank=True, db_index=True)
    coe = models.CharField(max_length=30, blank=True, db_index=True)
    patio_base = models.ForeignKey(
        Patio, null=True, blank=True, on_delete=models.SET_NULL, related_name='buses',
    )
    patio_actual = models.CharField(max_length=80, blank=True)  # último Genesis
    tecnico_asignado = models.CharField(max_length=120, blank=True, db_index=True)  # nombre técnico cola bitácora
    estado_operativo = models.CharField(
        max_length=20, choices=ESTADO_OP, default='ACTIVO', db_index=True,
    )

    # ── Columnas BUSES TMP ──
    estado_genesis = models.CharField(max_length=40, blank=True)      # Operativo / Inoperativo
    estado_sistema = models.CharField(max_length=40, blank=True)      # Instalado / Por instalar / DESCARTADO
    sistema_instalado = models.CharField(max_length=40, blank=True)   # BUSAE / BIMS / AVL
    estado_busae = models.CharField(max_length=40, blank=True)
    estado_fw = models.CharField(max_length=40, blank=True)
    estado_bocina = models.CharField(max_length=60, blank=True)
    adecuacion_bocina = models.CharField(max_length=40, blank=True)
    adecuacion_electrica = models.CharField(max_length=60, blank=True)
    anclaje_bocinas = models.CharField(max_length=30, blank=True)
    sistema_secundario = models.CharField(max_length=40, blank=True)  # 2ª col SISTEMA INSTALADO
    comentarios = models.TextField(blank=True)
    mes_instalado = models.CharField(max_length=40, blank=True)
    mes_revisado = models.CharField(max_length=40, blank=True)
    fecha_revision = models.DateField(null=True, blank=True)

    fecha_alta = models.DateField(null=True, blank=True)
    fecha_baja = models.DateField(null=True, blank=True)
    motivo_baja = models.TextField(blank=True)
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventario_flota'
        ordering = ['bus_movil']
        indexes = [
            models.Index(fields=['estado_operativo', 'coe']),
            models.Index(fields=['estado_genesis']),
            models.Index(fields=['estado_busae']),
        ]

    def __str__(self):
        return f'Bus {self.bus_movil} ({self.placa or "s/p"})'

    def sincronizar_estado_operativo(self):
        sis = (self.estado_sistema or '').upper()
        gen = (self.estado_genesis or '').lower()
        if 'DESCARTADO' in sis:
            self.estado_operativo = 'DESCARTADO'
        elif 'POR INSTALAR' in sis:
            self.estado_operativo = 'POR_INSTALAR'
        elif 'inoperativo' in gen:
            self.estado_operativo = 'MANTENIMIENTO'
        elif 'INSTALADO' in sis:
            self.estado_operativo = 'ACTIVO'
        return self.estado_operativo


class DispositivoGPS(models.Model):
    ESTADO = [
        ('INSTALADO', 'Instalado'),
        ('BODEGA', 'Bodega'),
        ('REPARACION', 'Reparación'),
        ('BAJA', 'Baja'),
        ('PERDIDO', 'Perdido / Robado'),
    ]
    imei = models.CharField(max_length=20, unique=True, db_index=True)
    serie = models.CharField(max_length=40, blank=True)
    modelo = models.CharField(max_length=60, blank=True)
    telefono_sim = models.CharField(max_length=30, blank=True)
    sim_serie = models.CharField(max_length=40, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO, default='BODEGA', db_index=True)
    bus_asignado = models.ForeignKey(
        InventarioFlota, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='gps_devices',
    )
    fecha_instalacion = models.DateField(null=True, blank=True)
    fecha_baja = models.DateField(null=True, blank=True)
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dispositivo_gps'
        ordering = ['imei']

    def __str__(self):
        dest = f' → {self.bus_asignado_id}' if self.bus_asignado_id else ''
        return f'GPS {self.imei}{dest} [{self.estado}]'


class MovimientoFlota(models.Model):
    TIPO = [
        ('ALTA', 'Alta'), ('BAJA', 'Baja'), ('MOVER_PATIO', 'Cambio patio'),
        ('ASIGNAR_GPS', 'Asignar GPS'), ('DESASIGNAR_GPS', 'Desasignar GPS'),
        ('CAMBIO_ESTADO', 'Cambio estado'), ('IMPORT', 'Importación'), ('OTRO', 'Otro'),
    ]
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    tipo = models.CharField(max_length=20, choices=TIPO)
    bus_movil = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    gps_imei = models.CharField(max_length=20, blank=True)
    detalle = models.TextField(blank=True)
    datos = models.JSONField(default=dict, blank=True)
    realizado_por = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = 'movimiento_flota'
        ordering = ['-timestamp']


# ═══════════════════════════════════════════════════════════════════════════
# 4. TELEMETRÍA (poller)
# ═══════════════════════════════════════════════════════════════════════════

class DatosBusae(models.Model):
    bus_movil = models.PositiveIntegerField(primary_key=True)
    latitud = models.FloatField(null=True, blank=True)
    longitud = models.FloatField(null=True, blank=True)
    velocidad = models.FloatField(default=0)
    estado = models.CharField(max_length=30, default='Offline')  # Active/Stopped/Offline/No records
    manos_libres = models.BooleanField(default=False)
    telefono = models.CharField(max_length=30, blank=True)
    ultima_transmision = models.DateTimeField(null=True, blank=True)
    sincronizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'datos_busae'

    def __str__(self):
        return f'BUSAE {self.bus_movil} — {self.estado}'


class DatosGenesis(models.Model):
    FUENTE = [('POLLER', 'Poller'), ('MANUAL', 'Manual'), ('CSV', 'CSV/Excel')]
    bus_movil = models.PositiveIntegerField(db_index=True)
    origen = models.CharField(max_length=80, blank=True)
    destino = models.CharField(max_length=80, blank=True)
    hora_entrada = models.DateTimeField(null=True, blank=True)
    patio_ubicacion = models.CharField(max_length=80, blank=True, db_index=True)
    estado_bus = models.CharField(max_length=40, blank=True)
    ruta = models.CharField(max_length=40, blank=True)
    opreal = models.CharField(max_length=40, blank=True)
    datos_extra = models.JSONField(default=dict, blank=True)
    fuente = models.CharField(max_length=10, choices=FUENTE, default='POLLER')
    sincronizado_en = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = 'datos_genesis'
        ordering = ['-sincronizado_en']
        indexes = [models.Index(fields=['bus_movil', '-sincronizado_en'])]

    def __str__(self):
        return f'Genesis {self.bus_movil} @ {self.patio_ubicacion}'


class EEMovil(models.Model):
    """Snapshot rápido patio/diagnóstico por bus (cruce operativo)."""
    bus_movil = models.PositiveIntegerField(primary_key=True)
    patio = models.CharField(max_length=80, blank=True)
    estado = models.CharField(max_length=40, blank=True)
    ultima_atencion = models.DateField(null=True, blank=True)
    diagnostico = models.TextField(blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ee_movil'


class UnidadFueraServicio(models.Model):
    bus_movil = models.PositiveIntegerField(db_index=True)
    motivo = models.TextField(blank=True)
    estado = models.CharField(max_length=20, default='ACTIVO')  # ACTIVO | CERRADO
    fecha_inicio = models.DateField(default=timezone.now)
    fecha_fin = models.DateField(null=True, blank=True)
    creado_por = models.CharField(max_length=20, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'unidad_fuera_servicio'


# ═══════════════════════════════════════════════════════════════════════════
# 5. REPORTES PENDIENTES + HISTORIAL
# ═══════════════════════════════════════════════════════════════════════════

class ReportePendiente(models.Model):
    ESTADO = [('PENDIENTE', 'Pendiente'), ('ATENDIDO', 'Atendido'), ('CANCELADO', 'Cancelado')]
    report_id = models.CharField(max_length=40, unique=True)
    bus_movil = models.PositiveIntegerField(db_index=True)
    estado_gps = models.CharField(max_length=30, default='OFF')
    patio = models.CharField(max_length=80, blank=True)
    fecha_reporte = models.DateField(default=timezone.now, db_index=True)
    hora_reporte = models.CharField(max_length=20, blank=True)
    diagnostico = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO, default='PENDIENTE', db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reporte_pendiente'
        ordering = ['-fecha_reporte', '-creado_en']
        indexes = [models.Index(fields=['estado', 'fecha_reporte'])]

    def __str__(self):
        return f'{self.report_id} Bus {self.bus_movil}'


class HistorialAtencion(models.Model):
    bus_movil = models.PositiveIntegerField(db_index=True)
    estado_gps = models.CharField(max_length=30, blank=True)
    patio = models.CharField(max_length=80, blank=True)
    fecha_reporte = models.DateField(null=True, blank=True)
    hora_reporte = models.CharField(max_length=20, blank=True)
    diagnostico = models.TextField(blank=True)
    tecnico_nombre = models.CharField(max_length=120, blank=True)
    tecnico_codigo = models.CharField(max_length=20, blank=True)
    fecha_atencion = models.DateTimeField(default=timezone.now)
    report_id_origen = models.CharField(max_length=40, blank=True)
    bitacora = models.ForeignKey(
        'BitacoraRegistro', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='historial',
    )

    class Meta:
        db_table = 'historial_atencion'
        ordering = ['-fecha_atencion']


# ═══════════════════════════════════════════════════════════════════════════
# 6. BITÁCORA — Formulario «REVISIÓN EQUIP. EMBARCADO 2026»
# ═══════════════════════════════════════════════════════════════════════════

class BitacoraRegistro(models.Model):
    """
    Una atención / revisión.
    Campos = Google Form 2026 + trazabilidad de origen.
    """
    TIPO = [('INVENTARIO', 'Inventario'), ('BITACORA', 'Bitácora')]
    GPS = [('FUNCIONA', 'Funciona'), ('CORTO', 'Corto'), ('MOJADO', 'Mojado')]
    VANDALISMO = [
        ('', '— Ninguno —'),
        ('PERDIDA_GPS', 'Pérdida de GPS'),
        ('CORTE_ARNES', 'Corte de arnés'),
        ('ROBO_SIMCARD', 'Robo de SIMCARD'),
    ]
    SIM = [('', '—'), ('DETERIORO_REEMPLAZO', 'Deterioro — Reemplazo')]
    ADECUACION = [('', '—'), ('ADECUADA', 'Adecuada'), ('NO_ADECUADA', 'No adecuada')]
    CTAP = [('', '—'), ('FUNCIONA', 'Funciona'), ('DAÑADA', 'Dañada'), ('NO_TIENE', 'No tiene')]
    RADIO = [
        ('', '—'), ('SIMCARD', 'SIMCARD'), ('SI', 'Sí'), ('NO', 'No'),
        ('FUNCIONA', 'Funciona'), ('DAÑADA', 'Dañada'),
    ]

    marca_temporal = models.DateTimeField(default=timezone.now, db_index=True)
    tipo_revision = models.CharField(max_length=20, choices=TIPO)
    patio = models.CharField(max_length=50, db_index=True)
    numero_bus = models.PositiveIntegerField(db_index=True)
    tecnico_nombre = models.CharField(max_length=120)
    codigo_tecnico = models.CharField(max_length=20, blank=True, db_index=True)

    gps = models.CharField(max_length=20, choices=GPS, blank=True)
    vandalismo = models.CharField(max_length=30, choices=VANDALISMO, blank=True)
    simcard = models.CharField(max_length=30, choices=SIM, blank=True)
    adecuacion_electrica = models.CharField(max_length=20, choices=ADECUACION, blank=True)

    radio_conexion = models.CharField(max_length=20, choices=RADIO, blank=True)
    radio_instalacion = models.CharField(max_length=20, choices=RADIO, blank=True)
    radio_perilla = models.CharField(max_length=20, choices=RADIO, blank=True)
    radio_pedal = models.CharField(max_length=20, choices=RADIO, blank=True)
    radio_pantalla = models.CharField(max_length=20, choices=RADIO, blank=True)

    ctap = models.CharField(max_length=20, choices=CTAP, blank=True)
    informe_tecnico = models.TextField(blank=True)

    source = models.CharField(max_length=20, blank=True)   # reportes | inventario | manual
    report_id = models.CharField(max_length=40, blank=True)

    class Meta:
        db_table = 'bitacora_registro'
        ordering = ['-marca_temporal']
        indexes = [
            models.Index(fields=['codigo_tecnico', 'marca_temporal']),
            models.Index(fields=['numero_bus', '-marca_temporal']),
            models.Index(fields=['patio', '-marca_temporal']),
        ]

    def __str__(self):
        return f'Bus {self.numero_bus} — {self.marca_temporal:%Y-%m-%d %H:%M}'


# ═══════════════════════════════════════════════════════════════════════════
# 7. AUDITORÍA + CONFIG
# ═══════════════════════════════════════════════════════════════════════════

class AuditLog(models.Model):
    ACCION = [
        ('LOGIN', 'Login'), ('LOGIN_FAIL', 'Login fallido'), ('LOGOUT', 'Logout'),
        ('CREATE', 'Crear'), ('UPDATE', 'Actualizar'), ('DELETE', 'Eliminar'),
        ('BAJA', 'Baja'), ('ASIGNAR', 'Asignar'), ('MOVER', 'Mover'),
        ('ATENDER', 'Atender'), ('IMPORT', 'Importación'), ('EXPORT', 'Exportación'),
        ('CONFIG', 'Config'), ('OTHER', 'Otro'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    usuario_codigo = models.CharField(max_length=20, blank=True, db_index=True)
    usuario_nombre = models.CharField(max_length=120, blank=True)
    accion = models.CharField(max_length=20, choices=ACCION, db_index=True)
    modelo = models.CharField(max_length=60, blank=True, db_index=True)
    objeto_id = models.CharField(max_length=60, blank=True)
    descripcion = models.TextField(blank=True)
    datos_antes = models.JSONField(null=True, blank=True)
    datos_despues = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.timestamp:%Y-%m-%d %H:%M} | {self.accion} | {self.modelo}'


def registrar_auditoria(request, accion, modelo='', objeto_id='', descripcion='',
                        datos_antes=None, datos_despues=None):
    ip = ua = codigo = nombre = ''
    if request:
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')
        ua = (request.META.get('HTTP_USER_AGENT') or '')[:255]
        codigo = request.session.get('tecnico_codigo', '')
        nombre = request.session.get('tecnico_nombre', '')
    AuditLog.objects.create(
        usuario_codigo=codigo, usuario_nombre=nombre, accion=accion,
        modelo=modelo, objeto_id=str(objeto_id or ''), descripcion=descripcion,
        datos_antes=datos_antes, datos_despues=datos_despues, ip=ip or None, user_agent=ua,
    )



class FormularioPlantilla(models.Model):
    """
    Motor de formularios avanzado (superior a Google Forms).
    definición JSON versionable: secciones, campos, opciones, condicionales.
    """
    codigo = models.CharField(max_length=60, unique=True, db_index=True)  # ej. revision_2026
    nombre = models.CharField(max_length=120)
    version = models.PositiveIntegerField(default=1)
    activa = models.BooleanField(default=False, db_index=True)
    definicion = models.JSONField(default=dict, help_text='Schema JSON del formulario')
    descripcion = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'formulario_plantilla'
        ordering = ['-activa', '-version', 'codigo']
        verbose_name = 'Plantilla de formulario'
        verbose_name_plural = 'Plantillas de formulario'

    def __str__(self):
        return f'{self.nombre} v{self.version}' + (' [ACTIVA]' if self.activa else '')


class ConfiguracionSistema(models.Model):
    clave = models.CharField(max_length=100, unique=True)
    valor = models.JSONField(default=dict, blank=True)
    descripcion = models.TextField(blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'configuracion_sistema'

    def __str__(self):
        return self.clave


class InventarioItem(models.Model):
    """Fila operativa de inventario diario (lista corta para atender en patio)."""
    patio = models.CharField(max_length=50)
    bus_movil = models.PositiveIntegerField()
    hora = models.CharField(max_length=20, blank=True)
    estado = models.CharField(max_length=40, blank=True)
    ultima_atencion = models.DateField(null=True, blank=True)
    fecha_actual = models.DateField(null=True, blank=True)
    diagnostico = models.TextField(blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventario_item'
        unique_together = [['patio', 'bus_movil']]


# ═══════════════════════════════════════════════════════════════════════════
# 7. TICKETS Y SOPORTE (FASE 6)
# ═══════════════════════════════════════════════════════════════════════════

class Ticket(models.Model):
    """
    Fase 6 — Sistema de Tickets / Soporte para incidencias técnicas en buses o sistema.
    """
    PRIORIDAD_CHOICES = [
        ('BAJA', 'Baja'),
        ('MEDIA', 'Media'),
        ('ALTA', 'Alta'),
        ('CRITICA', 'Crítica'),
    ]
    ESTADO_CHOICES = [
        ('ABIERTO', 'Abierto'),
        ('EN_PROGRESO', 'En Progreso'),
        ('RESUELTO', 'Resuelto'),
        ('CERRADO', 'Cerrado'),
    ]
    CATEGORIA_CHOICES = [
        ('GPS', 'GPS / Conectividad'),
        ('EQUIPO_EMBARCADO', 'Equipo Embarcado / Hardware'),
        ('APLICACION', 'Aplicación / Software'),
        ('PATIO', 'Patio / Operaciones'),
        ('OTRO', 'Otro'),
    ]

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    prioridad = models.CharField(max_length=15, choices=PRIORIDAD_CHOICES, default='MEDIA')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='ABIERTO', db_index=True)
    categoria = models.CharField(max_length=30, choices=CATEGORIA_CHOICES, default='OTRO')
    bus_movil = models.PositiveIntegerField(null=True, blank=True, help_text='Móvil relacionado si aplica')
    patio = models.ForeignKey('Patio', null=True, blank=True, on_delete=models.SET_NULL, related_name='tickets')

    # Creador
    creado_por = models.ForeignKey(
        'Usuario', null=True, blank=True, on_delete=models.SET_NULL, related_name='tickets_creados'
    )
    creado_por_codigo = models.CharField(max_length=20)
    creado_por_nombre = models.CharField(max_length=120)

    # Asignado
    asignado_a = models.ForeignKey(
        'Usuario', null=True, blank=True, on_delete=models.SET_NULL, related_name='tickets_asignados'
    )
    asignado_a_codigo = models.CharField(max_length=20, blank=True)
    asignado_a_nombre = models.CharField(max_length=120, blank=True)

    # Historial de comentarios: [{autor_codigo, autor_nombre, texto, fecha, es_admin}]
    comentarios = models.JSONField(default=list, blank=True)
    resolucion = models.TextField(blank=True, help_text='Detalle de resolución de la incidencia')

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    resuelto_en = models.DateTimeField(null=True, blank=True)
    cerrado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tickets'
        ordering = ['-creado_en']

    def __str__(self):
        return f'#{self.id} [{self.estado}] {self.titulo}'

