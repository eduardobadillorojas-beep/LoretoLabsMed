from django.contrib import admin

from .models import (
    CargoPaciente,
    Cobro,
    Estudio,
    Institucion,
    MembresiaInstitucion,
    Paciente,
    PagoCobro,
    Servicio,
)


class PagoCobroInline(admin.TabularInline):
    model = PagoCobro
    extra = 0
    readonly_fields = (
        'forma_pago',
        'monto',
        'referencia',
        'creado_el',
    )
    can_delete = False


@admin.register(Cobro)
class CobroAdmin(admin.ModelAdmin):
    list_display = (
        'folio',
        'paciente',
        'total',
        'forma_pago',
        'estado',
        'institucion',
        'creado_el',
    )
    list_filter = (
        'institucion',
        'forma_pago',
        'estado',
        'creado_el',
    )
    search_fields = (
        'folio',
        'paciente__identificacion',
        'paciente__nombre',
        'paciente__apellido',
    )
    readonly_fields = (
        'folio',
        'token_publico',
        'total',
        'monto_recibido',
        'cambio',
        'cancelado_por',
        'cancelado_el',
        'motivo_cancelacion',
        'forma_reembolso',
        'monto_reembolsado',
        'destino_cargos_cancelacion',
        'creado_el',
    )
    inlines = (PagoCobroInline,)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Institucion)
class InstitucionAdmin(admin.ModelAdmin):
    list_display = (
        'nombre',
        'nombre_comercial',
        'telefono',
        'email',
        'activa',
        'creada_el',
    )

    search_fields = (
        'nombre',
        'nombre_comercial',
        'telefono',
        'email',
    )

    list_filter = (
        'activa',
    )


@admin.register(MembresiaInstitucion)
class MembresiaInstitucionAdmin(admin.ModelAdmin):
    list_display = (
        'usuario',
        'institucion',
        'rol',
        'activa',
        'creada_el',
    )

    search_fields = (
        'usuario__username',
        'usuario__first_name',
        'usuario__last_name',
        'institucion__nombre',
    )

    list_filter = (
        'institucion',
        'rol',
        'activa',
    )


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = (
        'identificacion',
        'nombre',
        'apellido',
        'genero',
        'fecha_nacimiento',
    )

    search_fields = (
        'nombre',
        'apellido',
        'identificacion',
    )


@admin.register(Estudio)
class EstudioAdmin(admin.ModelAdmin):
    list_display = (
        'tipo_estudio',
        'paciente',
        'estado',
        'fecha_creacion',
    )

    list_filter = (
        'estado',
        'fecha_creacion',
    )

    search_fields = (
        'paciente__nombre',
        'paciente__apellido',
        'tipo_estudio__nombre',
    )


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = (
        'nombre',
        'tipo',
        'institucion',
        'tipo_estudio',
        'precio_base',
        'precio_editable',
        'activo',
    )

    list_filter = (
        'institucion',
        'tipo',
        'precio_editable',
        'activo',
    )

    search_fields = (
        'nombre',
        'institucion__nombre',
        'tipo_estudio__nombre',
    )

    list_select_related = (
        'institucion',
        'tipo_estudio',
    )

    readonly_fields = (
        'creado_el',
        'actualizado_el',
    )

    ordering = (
        'tipo',
        'nombre',
    )


@admin.register(CargoPaciente)
class CargoPacienteAdmin(admin.ModelAdmin):
    list_display = (
        'paciente',
        'descripcion',
        'cantidad',
        'precio_unitario',
        'subtotal',
        'estado',
        'origen',
        'institucion',
        'creado_el',
    )

    list_filter = (
        'institucion',
        'estado',
        'origen',
        'creado_el',
    )

    search_fields = (
        'paciente__identificacion',
        'paciente__nombre',
        'paciente__apellido',
        'descripcion',
        'servicio__nombre',
    )

    list_select_related = (
        'institucion',
        'paciente',
        'servicio',
        'consulta',
        'estudio',
        'agregado_por',
    )

    readonly_fields = (
        'subtotal',
        'creado_el',
        'actualizado_el',
    )

    ordering = (
        '-creado_el',
    )
