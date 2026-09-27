from django.contrib import admin
from .models import FormularioPlantilla  # noqa
from .models import (
    Usuario, Patio, InventarioFlota, DispositivoGPS, MovimientoFlota,
    DatosBusae, DatosGenesis, EEMovil, UnidadFueraServicio,
    ReportePendiente, HistorialAtencion, BitacoraRegistro, InventarioItem,
    ConfiguracionSistema, AuditLog,
)

@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'rol', 'patio_asignado', 'cuota_diaria', 'activo', 'ultimo_acceso')
    list_filter = ('rol', 'activo', 'patio_asignado')
    search_fields = ('codigo', 'nombre')
    readonly_fields = ('password_hash', 'ultimo_acceso', 'intentos_fallidos', 'bloqueado_hasta')



@admin.register(InventarioFlota)
class FlotaAdmin(admin.ModelAdmin):
    list_display = ('bus_movil', 'placa', 'estado_operativo', 'estado_genesis', 'estado_busae',
                    'estado_bocina', 'patio_base', 'coe')
    list_filter = ('estado_operativo', 'estado_genesis', 'estado_busae', 'estado_sistema', 'coe')
    search_fields = ('bus_movil', 'placa', 'comentarios')
    fieldsets = (
        ('Identificación', {'fields': ('bus_movil', 'placa', 'coe', 'patio_base', 'patio_actual', 'estado_operativo')}),
        ('Estado EE', {'fields': (
            'estado_genesis', 'estado_sistema', 'sistema_instalado', 'estado_busae',
            'estado_fw', 'estado_bocina', 'adecuacion_bocina', 'adecuacion_electrica',
            'anclaje_bocinas', 'sistema_secundario',
        )}),
        ('Fechas y notas', {'fields': ('mes_instalado', 'mes_revisado', 'fecha_revision', 'comentarios', 'notas',
                                       'fecha_alta', 'fecha_baja', 'motivo_baja')}),
    )

@admin.register(DispositivoGPS)
class GPSAdmin(admin.ModelAdmin):
    list_display = ('imei', 'modelo', 'estado', 'bus_asignado', 'telefono_sim')
    list_filter = ('estado',)
    search_fields = ('imei', 'serie')

@admin.register(AuditLog)
class AuditAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'usuario_codigo', 'accion', 'modelo', 'objeto_id', 'descripcion', 'ip')
    list_filter = ('accion', 'modelo')
    search_fields = ('usuario_codigo', 'descripcion', 'objeto_id')
    readonly_fields = [f.name for f in AuditLog._meta.fields]

@admin.register(BitacoraRegistro)
class BitacoraAdmin(admin.ModelAdmin):
    list_display = ('marca_temporal', 'numero_bus', 'tipo_revision', 'patio', 'tecnico_nombre', 'gps')
    list_filter = ('tipo_revision', 'patio', 'gps')
    search_fields = ('numero_bus', 'codigo_tecnico')
    date_hierarchy = 'marca_temporal'

@admin.register(ReportePendiente)
class ReporteAdmin(admin.ModelAdmin):
    list_display = ('report_id', 'bus_movil', 'estado_gps', 'patio', 'fecha_reporte', 'estado')
    list_filter = ('estado',)

admin.site.register(Patio)
admin.site.register(MovimientoFlota)
admin.site.register(DatosBusae)
admin.site.register(DatosGenesis)
admin.site.register(EEMovil)
admin.site.register(UnidadFueraServicio)
admin.site.register(HistorialAtencion)
admin.site.register(InventarioItem)
admin.site.register(ConfiguracionSistema)

admin.site.site_header = 'Bitácora E.E — MiBus'
admin.site.site_title = 'Bitácora E.E'
admin.site.index_title = 'Administración'


@admin.register(FormularioPlantilla)
class FormularioPlantillaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'version', 'activa', 'actualizado_en')
    list_filter = ('activa',)
    search_fields = ('codigo', 'nombre')
    readonly_fields = ('creado_en', 'actualizado_en')
