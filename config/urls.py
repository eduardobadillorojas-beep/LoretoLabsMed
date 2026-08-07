from django.contrib import admin
from django.urls import path

from core import views


urlpatterns = [
    path(
        'admin/',
        admin.site.urls
    ),

    path(
        '',
        views.inicio,
        name='inicio'
    ),

    path(
        'login/',
        views.login_view,
        name='login'
    ),

    path(
        'logout/',
        views.logout_view,
        name='logout'
    ),

    # =========================
    # MÉDICOS
    # =========================

    path(
        'medicos/',
        views.panel_medico,
        name='panel_medico'
    ),

    # =========================
    # RADIOLOGÍA
    # =========================

    path(
        'radiologia/',
        views.panel_radiologo,
        name='panel_radiologo'
    ),

    # =========================
    # RECEPCIÓN
    # =========================

    path(
        'recepcion/',
        views.panel_recepcion,
        name='panel_recepcion'
    ),

    path(
        'recepcion/registrar/',
        views.registrar_estudio_recepcion,
        name='registrar_recepcion'
    ),

    # =========================
    # CITAS
    # =========================

    path(
        'recepcion/citas/nueva/',
        views.nueva_cita,
        name='nueva_cita'
    ),

    # =========================
    # EXPEDIENTE DEL PACIENTE
    # =========================

    path(
        'recepcion/paciente/<int:paciente_id>/',
        views.detalle_paciente,
        name='detalle_paciente'
    ),

    path(
        'recepcion/paciente/<int:paciente_id>/nuevo-estudio/',
        views.nuevo_estudio_paciente,
        name='nuevo_estudio_paciente'
    ),

    # =========================
    # CONFIGURACIÓN
    # =========================

    path(
        'configuracion/',
        views.panel_config,
        name='panel_config'
    ),
]