from django.contrib import admin

from .models import (
    Paciente,
    Estudio,
    Institucion,
    MembresiaInstitucion,
)


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