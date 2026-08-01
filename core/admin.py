from django.contrib import admin
from .models import Paciente, Estudio

@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ('identificacion', 'nombre', 'apellido', 'genero', 'fecha_nacimiento')
    search_fields = ('nombre', 'apellido', 'identificacion')

@admin.register(Estudio)
class EstudioAdmin(admin.ModelAdmin):
    list_display = ('tipo_estudio', 'paciente', 'estado', 'fecha_creacion')
    list_filter = ('estado', 'fecha_creacion')
    search_fields = ('paciente__nombre', 'paciente__apellido', 'tipo_estudio')