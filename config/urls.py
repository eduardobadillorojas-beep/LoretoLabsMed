from django.conf import settings
from django.conf.urls.static import static
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

    path(
        'medicos/perfil/',
        views.perfil_medico,
        name='perfil_medico'
    ),

    path(
        'medicos/consulta/<int:consulta_id>/atender/',
        views.atender_consulta_medica,
        name='atender_consulta_medica'
    ),

    path(
        'medicos/consulta/<int:consulta_id>/finalizar/',
        views.finalizar_consulta_medica,
        name='finalizar_consulta_medica'
    ),

    path(
        'medicos/consulta/<int:consulta_id>/guardar/',
        views.guardar_consulta_clinica,
        name='guardar_consulta_clinica'
    ),

    path(
        'medicos/consulta/<int:consulta_id>/receta/guardar/',
        views.guardar_receta_medica,
        name='guardar_receta_medica'
    ),

    path(
        'medicos/consulta/<int:consulta_id>/documentos/pdf/',
        views.generar_documentos_clinicos_pdf,
        name='generar_documentos_clinicos_pdf'
    ),

    path(
        'medicos/consulta/<int:consulta_id>/indicaciones/guardar/',
        views.guardar_indicacion_medica,
        name='guardar_indicacion_medica'
    ),

    path(
        'medicos/consulta/<int:consulta_id>/solicitud-estudio/guardar/',
        views.guardar_solicitud_estudio,
        name='guardar_solicitud_estudio'
    ),

    path(
        'medicos/estudio/<int:estudio_id>/reporte-final/',
        views.guardar_reporte_final_medico,
        name='guardar_reporte_final_medico'
    ),

    # =========================
    # RADIOLOGÍA
    # =========================

    path(
        'radiologia/',
        views.panel_radiologo,
        name='panel_radiologo'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/',
        views.estudio_radiologia,
        name='estudio_radiologia'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/nuevo-estudio/',
        views.nuevo_estudio_desde_radiologia,
        name='nuevo_estudio_desde_radiologia'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/iniciar/',
        views.iniciar_estudio_radiologia,
        name='iniciar_estudio_radiologia'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/cargar/',
        views.cargar_archivos_estudio,
        name='cargar_archivos_estudio'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/dicom/<int:instancia_id>/',
        views.visor_instancia_dicom,
        name='visor_instancia_dicom'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/dicom/<int:instancia_id>/imagen/',
        views.imagen_instancia_dicom,
        name='imagen_instancia_dicom'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/dicom/<int:instancia_id>/medir/',
        views.medir_instancia_dicom,
        name='medir_instancia_dicom'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/pre-reporte/',
        views.guardar_pre_reporte_estudio,
        name='guardar_pre_reporte_estudio'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/reporte-final/',
        views.guardar_reporte_final_estudio,
        name='guardar_reporte_final_estudio'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/archivo/<int:archivo_id>/eliminar/',
        views.eliminar_archivo_estudio,
        name='eliminar_archivo_estudio'
    ),

    path(
        'radiologia/estudio/<int:estudio_id>/finalizar/',
        views.finalizar_estudio_radiologia,
        name='finalizar_estudio_radiologia'
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
        'recepcion/caja/',
        views.caja_recepcion,
        name='caja_recepcion'
    ),

    path('recepcion/caja/abrir/', views.abrir_caja_recepcion, name='abrir_caja_recepcion'),
    path('recepcion/caja/<int:corte_id>/movimiento/', views.registrar_movimiento_caja, name='registrar_movimiento_caja'),
    path('recepcion/caja/<int:corte_id>/cerrar/', views.cerrar_caja_recepcion, name='cerrar_caja_recepcion'),
    path('recepcion/caja/<int:corte_id>/ticket/', views.ticket_corte_caja, name='ticket_corte_caja'),
    path('configuracion/auditoria-cajas/', views.auditoria_cajas, name='auditoria_cajas'),

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
    # SERVICIOS / CUENTA
    # =========================

    path(
        'recepcion/paciente/<int:paciente_id>/servicios/',
        views.servicios_paciente_recepcion,
        name='servicios_paciente_recepcion'
    ),

    path(
        'recepcion/cobro/<int:cobro_id>/completado/',
        views.cobro_exitoso,
        name='cobro_exitoso'
    ),

    path(
        'recepcion/cobro/<int:cobro_id>/cancelar/',
        views.cancelar_cobro_recepcion,
        name='cancelar_cobro_recepcion'
    ),

    path(
        'recepcion/cobro/<int:cobro_id>/ticket/',
        views.ticket_cobro,
        name='ticket_cobro'
    ),

    path(
        'recepcion/credito/<int:credito_id>/abonar/',
        views.registrar_abono_credito,
        name='registrar_abono_credito'
    ),

    path(
        'recepcion/credito/abono/<int:abono_id>/ticket/',
        views.ticket_abono_credito,
        name='ticket_abono_credito'
    ),

    path(
        'recepcion/paciente/<int:paciente_id>/ticket-agrupado/',
        views.ticket_cargos_agrupados,
        name='ticket_cargos_agrupados'
    ),

    path(
        'comprobante/<uuid:token>/pdf/',
        views.comprobante_cobro_pdf,
        name='comprobante_cobro_pdf'
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

    path(
        'configuracion/servicios/',
        views.catalogo_servicios,
        name='catalogo_servicios'
    ),

    path(
        'configuracion/servicios/nuevo/',
        views.guardar_servicio,
        name='nuevo_servicio'
    ),

    path(
        'configuracion/servicios/<int:servicio_id>/guardar/',
        views.guardar_servicio,
        name='guardar_servicio'
    ),

    path(
        'configuracion/servicios/<int:servicio_id>/estado/',
        views.cambiar_estado_servicio,
        name='cambiar_estado_servicio'
    ),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
