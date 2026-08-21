from datetime import date
from pathlib import Path
import logging

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    CitaForm,
    ConsultaForm,
    DestinoAtencionForm,
    EstudioForm,
    PacienteForm,
)

from .models import (
    ArchivoEstudio,
    BitacoraRadiologica,
    Cita,
    Consulta,
    Estudio,
    MembresiaInstitucion,
    Paciente,
    SesionTrabajo,
)


logger = logging.getLogger(__name__)


# =========================================================
# UTILIDADES
# =========================================================

def obtener_membresia_usuario(request):
    return (
        MembresiaInstitucion.objects
        .select_related('institucion')
        .filter(
            usuario=request.user,
            activa=True,
            institucion__activa=True,
        )
        .first()
    )


def obtener_institucion_usuario(request):
    membresia = obtener_membresia_usuario(request)

    if not membresia:
        return None

    return membresia.institucion


def obtener_ip(request):
    forwarded_for = request.META.get(
        'HTTP_X_FORWARDED_FOR'
    )

    if forwarded_for:
        ip = forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')

    return ip


def calcular_edad(
    fecha_nacimiento,
    fecha_referencia=None
):
    if not fecha_nacimiento:
        return None

    if fecha_referencia is None:
        fecha_referencia = timezone.localdate()

    return (
        fecha_referencia.year
        - fecha_nacimiento.year
        - (
            (
                fecha_referencia.month,
                fecha_referencia.day,
            )
            <
            (
                fecha_nacimiento.month,
                fecha_nacimiento.day,
            )
        )
    )


def obtener_nombre_usuario(usuario):
    if not usuario:
        return ''

    nombre_completo = (
        usuario.get_full_name().strip()
    )

    if nombre_completo:
        return nombre_completo

    return usuario.username


def detectar_tipo_archivo(nombre):
    extension = Path(
        nombre
    ).suffix.lower()

    if extension in [
        '.dcm',
        '.dicom',
    ]:
        return 'DICOM'

    if extension in [
        '.jpg',
        '.jpeg',
        '.png',
        '.webp',
        '.bmp',
    ]:
        return 'IMAGEN'

    if extension in [
        '.pdf',
        '.doc',
        '.docx',
        '.txt',
    ]:
        return 'DOCUMENTO'

    return 'OTRO'


def crear_bitacora_radiologica(estudio):
    modalidad_original = (
        estudio.tipo_estudio.modalidad
    )

    modalidades_bitacora = {
        'RX': 'RX',
        'TAC': 'TAC',
        'FLUORO': 'FLUORO',
        'MASTO': 'MASTO',
    }

    if (
        modalidad_original
        not in modalidades_bitacora
    ):
        return None

    paciente = estudio.paciente

    fecha_realizacion = (
        estudio.fecha_finalizacion
        or timezone.now()
    )

    fecha_local = timezone.localtime(
        fecha_realizacion
    ).date()

    edad = calcular_edad(
        paciente.fecha_nacimiento,
        fecha_local
    )

    genero = (
        paciente.get_genero_display()
    )

    tecnico_nombre = (
        obtener_nombre_usuario(
            estudio.tecnico
        )
    )

    equipo_nombre = ''

    if estudio.equipo:
        equipo_nombre = (
            estudio.equipo.nombre
        )

    bitacora, creada = (
        BitacoraRadiologica.objects.get_or_create(
            estudio=estudio,
            defaults={
                'fecha_realizacion':
                    fecha_realizacion,

                'paciente_nombre':
                    (
                        f'{paciente.nombre} '
                        f'{paciente.apellido}'
                    ),

                'paciente_registro':
                    paciente.identificacion,

                'fecha_nacimiento':
                    paciente.fecha_nacimiento,

                'edad':
                    edad,

                'genero':
                    genero,

                'modalidad':
                    modalidades_bitacora[
                        modalidad_original
                    ],

                'estudio_nombre':
                    estudio.tipo_estudio.nombre,

                'medico_solicitante':
                    estudio.medico_solicitante,

                'tecnico':
                    estudio.tecnico,

                'tecnico_nombre':
                    tecnico_nombre,

                'equipo':
                    estudio.equipo,

                'equipo_nombre':
                    equipo_nombre,

                'observaciones':
                    estudio.descripcion,
            }
        )
    )

    return bitacora


# =========================================================
# INICIO
# =========================================================

def inicio(request):
    return render(
        request,
        'core/inicio.html'
    )


# =========================================================
# LOGIN
# =========================================================

def login_view(request):
    error_message = None

    if request.method == 'POST':
        usuario = request.POST.get(
            'username'
        )

        clave = request.POST.get(
            'password'
        )

        user = authenticate(
            request,
            username=usuario,
            password=clave
        )

        if user is not None:

            sesiones_anteriores = (
                SesionTrabajo.objects.filter(
                    usuario=user,
                    activa=True
                )
            )

            momento_actual = timezone.now()

            sesiones_anteriores.update(
                activa=False,
                fin=momento_actual
            )

            login(
                request,
                user
            )

            sesion_trabajo = (
                SesionTrabajo.objects.create(
                    usuario=user,
                    ip_inicio=obtener_ip(
                        request
                    ),
                    user_agent=(
                        request.META.get(
                            'HTTP_USER_AGENT',
                            ''
                        )
                    ),
                    activa=True
                )
            )

            request.session[
                'sesion_trabajo_id'
            ] = sesion_trabajo.id

            if user.groups.filter(
                name='Médico'
            ).exists():

                return redirect(
                    'panel_medico'
                )

            if user.groups.filter(
                name='Radiólogo'
            ).exists():

                return redirect(
                    'panel_radiologo'
                )

            if user.groups.filter(
                name='Recepción'
            ).exists():

                return redirect(
                    'panel_recepcion'
                )

            return redirect(
                'panel_config'
            )

        error_message = (
            'Usuario o contraseña incorrectos'
        )

    return render(
        request,
        'core/login.html',
        {
            'error': error_message,
        }
    )


# =========================================================
# LOGOUT
# =========================================================

@login_required
def logout_view(request):
    momento_actual = timezone.now()

    sesion_trabajo_id = (
        request.session.get(
            'sesion_trabajo_id'
        )
    )

    if sesion_trabajo_id:

        sesion_trabajo = (
            SesionTrabajo.objects
            .filter(
                id=sesion_trabajo_id,
                usuario=request.user,
                activa=True
            )
            .first()
        )

    else:

        sesion_trabajo = (
            SesionTrabajo.objects
            .filter(
                usuario=request.user,
                activa=True
            )
            .order_by(
                '-inicio'
            )
            .first()
        )

    if sesion_trabajo:
        sesion_trabajo.fin = (
            momento_actual
        )

        sesion_trabajo.ultima_actividad = (
            momento_actual
        )

        sesion_trabajo.activa = False

        sesion_trabajo.ip_fin = (
            obtener_ip(request)
        )

        sesion_trabajo.save(
            update_fields=[
                'fin',
                'ultima_actividad',
                'activa',
                'ip_fin',
            ]
        )

    logout(request)

    return redirect(
        'inicio'
    )


# =========================================================
# MÉDICOS
# =========================================================

@login_required
def panel_medico(request):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    institucion = membresia.institucion
    hoy = timezone.localdate()

    areas_medicas = [
        'CONSULTA',
        'TRAUMATOLOGIA',
        'DERMATOLOGIA',
        'ENDOCRINOLOGIA',
    ]

    consultas_en_espera = (
        Consulta.objects
        .select_related(
            'paciente',
            'medico',
        )
        .filter(
            paciente__institucion=institucion,
            estado='EN_ESPERA',
        )
        .order_by(
            'fecha_llegada'
        )
    )

    consultas_en_curso = (
        Consulta.objects
        .select_related(
            'paciente',
            'medico',
        )
        .filter(
            paciente__institucion=institucion,
            estado='EN_CONSULTA',
        )
        .order_by(
            'fecha_inicio',
            'fecha_llegada',
        )
    )

    citas_medicas_hoy = (
        Cita.objects
        .select_related(
            'paciente',
            'tipo_estudio',
        )
        .filter(
            institucion=institucion,
            area__in=areas_medicas,
            fecha_hora__date=hoy,
        )
        .exclude(
            estado__in=[
                'CANCELADA',
                'NO_ASISTIO',
                'FINALIZADA',
            ]
        )
        .order_by(
            'fecha_hora'
        )
    )

    proximas_citas_medicas = (
        Cita.objects
        .select_related(
            'paciente',
            'tipo_estudio',
        )
        .filter(
            institucion=institucion,
            area__in=areas_medicas,
            fecha_hora__date__gt=hoy,
        )
        .exclude(
            estado__in=[
                'CANCELADA',
                'NO_ASISTIO',
                'FINALIZADA',
            ]
        )
        .order_by(
            'fecha_hora'
        )[:20]
    )

    pacientes_atendidos = (
        Consulta.objects
        .select_related(
            'paciente',
            'medico',
        )
        .filter(
            paciente__institucion=institucion,
            estado='FINALIZADA',
        )
        .order_by(
            '-fecha_finalizacion',
            '-fecha_llegada',
        )[:10]
    )

    estudios_recientes = (
        Estudio.objects
        .select_related(
            'paciente',
            'tipo_estudio',
            'reporte_final_por',
        )
        .filter(
            paciente__institucion=institucion,
        )
        .order_by(
            '-fecha_creacion'
        )[:15]
    )

    context = {
        'membresia': membresia,
        'institucion': institucion,
        'consultas_en_espera':
            consultas_en_espera,
        'consultas_en_curso':
            consultas_en_curso,
        'citas_medicas_hoy':
            citas_medicas_hoy,
        'proximas_citas_medicas':
            proximas_citas_medicas,
        'pacientes_atendidos':
            pacientes_atendidos,
        'estudios_recientes':
            estudios_recientes,
    }

    return render(
        request,
        'core/panel_medico.html',
        context
    )


@login_required
def atender_consulta_medica(
    request,
    consulta_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente',
            'medico',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        if consulta.estado == 'EN_ESPERA':
            consulta.estado = 'EN_CONSULTA'
            consulta.medico = request.user
            consulta.fecha_inicio = timezone.now()

            consulta.save(
                update_fields=[
                    'estado',
                    'medico',
                    'fecha_inicio',
                ]
            )

    return redirect(
        'detalle_paciente',
        paciente_id=consulta.paciente_id
    )


@login_required
def finalizar_consulta_medica(
    request,
    consulta_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente',
            'medico',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        if consulta.estado == 'EN_CONSULTA':
            if (
                membresia.rol == 'ADMIN'
                or consulta.medico_id == request.user.id
                or consulta.medico_id is None
            ):
                if consulta.medico_id is None:
                    consulta.medico = request.user

                consulta.estado = 'FINALIZADA'
                consulta.fecha_finalizacion = timezone.now()

                consulta.save(
                    update_fields=[
                        'estado',
                        'medico',
                        'fecha_finalizacion',
                    ]
                )

    return redirect(
        'panel_medico'
    )


# =========================================================
# PANEL RADIOLOGÍA
# =========================================================

@login_required
def panel_radiologo(request):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
        'ADMIN',
    ]:
        return redirect('panel_config')

    institucion = membresia.institucion
    hoy = timezone.localdate()

    estudios_pendientes = (
        Estudio.objects
        .select_related(
            'paciente',
            'consulta',
            'tipo_estudio',
            'tecnico',
            'equipo',
        )
        .filter(
            paciente__institucion=institucion,
            estado='PENDIENTE',
        )
        .order_by(
            'fecha_creacion'
        )
    )

    estudios_en_proceso = (
        Estudio.objects
        .select_related(
            'paciente',
            'consulta',
            'tipo_estudio',
            'tecnico',
            'equipo',
        )
        .filter(
            paciente__institucion=institucion,
            estado='EN_PROCESO',
        )
        .order_by(
            'fecha_inicio',
            'fecha_creacion'
        )
    )

    estudios_realizados_hoy = (
        Estudio.objects
        .select_related(
            'paciente',
            'consulta',
            'tipo_estudio',
            'tecnico',
            'equipo',
        )
        .filter(
            paciente__institucion=institucion,
            estado='COMPLETADO',
            fecha_finalizacion__date=hoy,
        )
        .order_by(
            '-fecha_finalizacion'
        )
    )

    citas_radiologia_hoy = (
        Cita.objects
        .select_related(
            'tipo_estudio'
        )
        .filter(
            institucion=institucion,
            area='RADIOLOGIA',
            fecha_hora__date=hoy,
        )
        .exclude(
            estado__in=[
                'CANCELADA',
                'NO_ASISTIO',
                'FINALIZADA',
            ]
        )
        .order_by(
            'fecha_hora'
        )
    )

    # -----------------------------------------------------
    # BUSCADOR / HISTORIAL DE PACIENTES
    # -----------------------------------------------------

    busqueda_paciente = (
        request.GET.get('q', '').strip()
    )

    estudios_historial = (
        Estudio.objects
        .select_related(
            'tipo_estudio'
        )
        .order_by(
            '-fecha_creacion'
        )
    )

    pacientes_historial = (
        Paciente.objects
        .filter(
            institucion=institucion
        )
        .prefetch_related(
            Prefetch(
                'estudios',
                queryset=estudios_historial,
                to_attr='estudios_radiologia_historial',
            )
        )
        .order_by(
            '-creado_el'
        )
    )

    if busqueda_paciente:
        pacientes_historial = (
            pacientes_historial.filter(
                Q(
                    identificacion__icontains=
                    busqueda_paciente
                )
                |
                Q(
                    nombre__icontains=
                    busqueda_paciente
                )
                |
                Q(
                    apellido__icontains=
                    busqueda_paciente
                )
                |
                Q(
                    telefono__icontains=
                    busqueda_paciente
                )
            )
        )

    # Evita cargar una tabla enorme de una sola vez.
    # La búsqueda sigue funcionando sobre todos los pacientes
    # de la institución antes de aplicar este límite.
    pacientes_historial = (
        pacientes_historial[:50]
    )

    context = {
        'membresia': membresia,
        'institucion': institucion,
        'estudios_pendientes':
            estudios_pendientes,
        'estudios_en_proceso':
            estudios_en_proceso,
        'estudios_realizados_hoy':
            estudios_realizados_hoy,
        'citas_radiologia_hoy':
            citas_radiologia_hoy,
        'busqueda_paciente':
            busqueda_paciente,
        'pacientes_historial':
            pacientes_historial,
    }

    return render(
        request,
        'core/panel_radiologo.html',
        context
    )

# =========================================================
# ESTACIÓN DE TRABAJO RADIOLOGÍA
# =========================================================

@login_required
def estudio_radiologia(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
        'ADMIN',
    ]:
        return redirect('panel_config')

    estudio = get_object_or_404(
        Estudio.objects.select_related(
            'paciente',
            'tipo_estudio',
            'tecnico',
            'equipo',
            'pre_reporte_por',
            'reporte_final_por',
        ),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    archivos = (
        estudio.archivos
        .select_related(
            'subido_por'
        )
        .all()
    )

    antecedentes = (
        estudio.paciente.estudios
        .select_related(
            'tipo_estudio'
        )
        .exclude(
            pk=estudio.pk
        )
        .order_by(
            '-fecha_creacion'
        )
    )

    edad = calcular_edad(
        estudio.paciente.fecha_nacimiento
    )

    puede_pre_reportar = (
        membresia.rol
        in [
            'TECNICO',
            'RADIOLOGIA',
        ]
    )

    puede_emitir_reporte_final = (
        membresia.rol
        == 'RADIOLOGIA'
    )

    estudio_adicional_form = EstudioForm(
        initial={
            'estado': 'PENDIENTE',
            'medico_solicitante':
                estudio.medico_solicitante,
        }
    )

    context = {
        'estudio': estudio,
        'paciente': estudio.paciente,
        'archivos': archivos,
        'antecedentes': antecedentes,
        'edad': edad,
        'membresia': membresia,
        'puede_pre_reportar':
            puede_pre_reportar,
        'puede_emitir_reporte_final':
            puede_emitir_reporte_final,
        'estudio_adicional_form':
            estudio_adicional_form,
    }

    return render(
        request,
        'core/estudio_radiologia.html',
        context
    )

@login_required
def nuevo_estudio_desde_radiologia(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
        'ADMIN',
    ]:
        return redirect('panel_config')

    estudio_origen = get_object_or_404(
        Estudio.objects.select_related(
            'paciente',
            'tipo_estudio',
        ),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method != 'POST':
        return redirect(
            'estudio_radiologia',
            estudio_id=estudio_origen.id
        )

    estudio_form = EstudioForm(
        request.POST
    )

    if estudio_form.is_valid():
        estudio_nuevo = estudio_form.save(
            commit=False
        )

        estudio_nuevo.paciente = (
            estudio_origen.paciente
        )

        estudio_nuevo.estado = 'PENDIENTE'

        if not estudio_nuevo.descripcion:
            estudio_nuevo.descripcion = (
                'Estudio adicional generado desde Radiología.'
            )

        estudio_nuevo.save()

        return redirect(
            'estudio_radiologia',
            estudio_id=estudio_nuevo.id
        )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio_origen.id
    )


# =========================================================
# INICIAR ESTUDIO
# =========================================================

@login_required
def iniciar_estudio_radiologia(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
    ]:
        return redirect('panel_radiologo')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        if estudio.estado == 'PENDIENTE':
            estudio.estado = 'EN_PROCESO'
            estudio.fecha_inicio = timezone.now()
            estudio.tecnico = request.user

            estudio.save(
                update_fields=[
                    'estado',
                    'fecha_inicio',
                    'tecnico',
                ]
            )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )

# =========================================================
# CARGAR ARCHIVOS
# =========================================================

@login_required
def cargar_archivos_estudio(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
    ]:
        return redirect('panel_radiologo')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        archivos = request.FILES.getlist(
            'archivos'
        )

        if estudio.estado == 'PENDIENTE':
            estudio.estado = 'EN_PROCESO'
            estudio.fecha_inicio = timezone.now()
            estudio.tecnico = request.user

            estudio.save(
                update_fields=[
                    'estado',
                    'fecha_inicio',
                    'tecnico',
                ]
            )

        for archivo in archivos:
            try:
                ArchivoEstudio.objects.create(
                    estudio=estudio,
                    archivo=archivo,
                    tipo_archivo=(
                        detectar_tipo_archivo(
                            archivo.name
                        )
                    ),
                    nombre_original=archivo.name,
                    subido_por=request.user
                )

            except Exception as exc:
                logger.exception(
                    (
                        'Error al subir archivo de estudio '
                        'al almacenamiento. estudio_id=%s '
                        'archivo=%s tipo_error=%s mensaje=%s'
                    ),
                    estudio.id,
                    archivo.name,
                    type(exc).__name__,
                    str(exc),
                )

                raise

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )

# =========================================================
# ELIMINAR ARCHIVO
# =========================================================

@login_required
def eliminar_archivo_estudio(
    request,
    estudio_id,
    archivo_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
    ]:
        return redirect('panel_radiologo')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    archivo = get_object_or_404(
        ArchivoEstudio,
        pk=archivo_id,
        estudio=estudio
    )

    if request.method == 'POST':
        archivo.archivo.delete(
            save=False
        )
        archivo.delete()

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )

# =========================================================
# PRE-REPORTE TÉCNICO
# =========================================================

@login_required
def guardar_pre_reporte_estudio(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
    ]:
        return redirect(
            'estudio_radiologia',
            estudio_id=estudio.id
        )

    if request.method == 'POST':
        pre_reporte = (
            request.POST.get(
                'pre_reporte',
                ''
            )
            .strip()
        )

        estudio.pre_reporte = (
            pre_reporte
            or None
        )

        if pre_reporte:
            estudio.pre_reporte_por = (
                request.user
            )

            estudio.fecha_pre_reporte = (
                timezone.now()
            )

            estudio.estado_reporte = (
                'POR_VALIDAR'
            )
        else:
            estudio.pre_reporte_por = None
            estudio.fecha_pre_reporte = None

            if estudio.reporte_final:
                estudio.estado_reporte = (
                    'FINAL'
                )
            else:
                estudio.estado_reporte = (
                    'SIN_REPORTE'
                )

        estudio.save(
            update_fields=[
                'pre_reporte',
                'pre_reporte_por',
                'fecha_pre_reporte',
                'estado_reporte',
            ]
        )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )


# =========================================================
# REPORTE RADIOLÓGICO FINAL
# =========================================================

@login_required
def guardar_reporte_final_estudio(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    # RADIOLOGIA representa al médico radiólogo
    # dentro del flujo actual de membresías.
    if membresia.rol != 'RADIOLOGIA':
        return redirect(
            'estudio_radiologia',
            estudio_id=estudio.id
        )

    if request.method == 'POST':
        reporte_final = (
            request.POST.get(
                'reporte_final',
                ''
            )
            .strip()
        )

        if reporte_final:
            estudio.reporte_final = (
                reporte_final
            )

            estudio.reporte_final_por = (
                request.user
            )

            estudio.fecha_reporte_final = (
                timezone.now()
            )

            estudio.estado_reporte = (
                'FINAL'
            )

            estudio.save(
                update_fields=[
                    'reporte_final',
                    'reporte_final_por',
                    'fecha_reporte_final',
                    'estado_reporte',
                ]
            )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )


# =========================================================
# FINALIZAR ESTUDIO
# =========================================================

@login_required
def finalizar_estudio_radiologia(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
    ]:
        return redirect('panel_radiologo')

    estudio = get_object_or_404(
        Estudio.objects.select_related(
            'paciente',
            'tipo_estudio',
            'tecnico',
            'equipo',
        ),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        momento_actual = timezone.now()

        if not estudio.fecha_inicio:
            estudio.fecha_inicio = momento_actual

        if not estudio.tecnico:
            estudio.tecnico = request.user

        estudio.estado = 'COMPLETADO'
        estudio.fecha_finalizacion = momento_actual

        estudio.save(
            update_fields=[
                'estado',
                'fecha_inicio',
                'fecha_finalizacion',
                'tecnico',
            ]
        )

        crear_bitacora_radiologica(
            estudio
        )

        return redirect(
            'panel_radiologo'
        )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )

# =========================================================
# RECEPCIÓN
# =========================================================

@login_required
def panel_recepcion(request):
    busqueda = request.GET.get(
        'buscar',
        ''
    ).strip()

    hoy = timezone.localdate()

    institucion = obtener_institucion_usuario(request)

    if institucion is None:
        return redirect('panel_config')

    consultas_estado = (
        Consulta.objects
        .select_related(
            'medico'
        )
        .order_by(
            '-fecha_llegada'
        )
    )

    estudios_estado = (
        Estudio.objects
        .select_related(
            'tipo_estudio'
        )
        .order_by(
            '-fecha_creacion'
        )
    )

    def preparar_estado_recepcion(
        lista_pacientes
    ):
        pacientes_preparados = list(
            lista_pacientes
        )

        for paciente in pacientes_preparados:
            consulta = None
            estudio = None

            if paciente.consultas_estado_recepcion:
                consulta = (
                    paciente
                    .consultas_estado_recepcion[0]
                )

            if paciente.estudios_estado_recepcion:
                estudio = (
                    paciente
                    .estudios_estado_recepcion[0]
                )

            actividad = None
            tipo_actividad = None

            if consulta and estudio:
                if (
                    consulta.fecha_llegada
                    >= estudio.fecha_creacion
                ):
                    actividad = consulta
                    tipo_actividad = 'CONSULTA'
                else:
                    actividad = estudio
                    tipo_actividad = 'ESTUDIO'

            elif consulta:
                actividad = consulta
                tipo_actividad = 'CONSULTA'

            elif estudio:
                actividad = estudio
                tipo_actividad = 'ESTUDIO'

            paciente.estado_atencion = 'Registrado'
            paciente.estado_atencion_clase = 'secondary'
            paciente.estado_atencion_area = ''

            if tipo_actividad == 'CONSULTA':
                paciente.estado_atencion_area = (
                    'Consulta médica'
                )

                if actividad.estado == 'EN_ESPERA':
                    paciente.estado_atencion = (
                        'En espera'
                    )
                    paciente.estado_atencion_clase = (
                        'warning'
                    )

                elif actividad.estado == 'EN_CONSULTA':
                    paciente.estado_atencion = (
                        'Siendo atendido'
                    )
                    paciente.estado_atencion_clase = (
                        'info'
                    )

                elif actividad.estado == 'FINALIZADA':
                    paciente.estado_atencion = (
                        'Atendido'
                    )
                    paciente.estado_atencion_clase = (
                        'success'
                    )

            elif tipo_actividad == 'ESTUDIO':
                paciente.estado_atencion_area = (
                    'Radiología'
                )

                if actividad.estado == 'PENDIENTE':
                    paciente.estado_atencion = (
                        'En espera'
                    )
                    paciente.estado_atencion_clase = (
                        'warning'
                    )

                elif actividad.estado == 'EN_PROCESO':
                    paciente.estado_atencion = (
                        'Siendo atendido'
                    )
                    paciente.estado_atencion_clase = (
                        'info'
                    )

                elif actividad.estado == 'COMPLETADO':
                    paciente.estado_atencion = (
                        'Atendido'
                    )
                    paciente.estado_atencion_clase = (
                        'success'
                    )

        return pacientes_preparados

    pacientes_queryset = (
        Paciente.objects
        .filter(
            institucion=institucion
        )
        .prefetch_related(
            Prefetch(
                'consultas',
                queryset=consultas_estado,
                to_attr='consultas_estado_recepcion',
            ),
            Prefetch(
                'estudios',
                queryset=estudios_estado,
                to_attr='estudios_estado_recepcion',
            ),
        )
        .order_by(
            '-creado_el'
        )
    )

    if busqueda:
        pacientes_queryset = (
            pacientes_queryset.filter(
                Q(
                    identificacion__icontains=
                    busqueda
                )
                |
                Q(
                    nombre__icontains=
                    busqueda
                )
                |
                Q(
                    apellido__icontains=
                    busqueda
                )
                |
                Q(
                    telefono__icontains=
                    busqueda
                )
            )
        )

    pacientes = preparar_estado_recepcion(
        pacientes_queryset
    )

    pacientes_de_hoy_queryset = (
        Paciente.objects
        .filter(
            institucion=institucion,
            creado_el__date=hoy
        )
        .prefetch_related(
            Prefetch(
                'consultas',
                queryset=consultas_estado,
                to_attr='consultas_estado_recepcion',
            ),
            Prefetch(
                'estudios',
                queryset=estudios_estado,
                to_attr='estudios_estado_recepcion',
            ),
        )
        .order_by(
            '-creado_el'
        )
    )

    pacientes_de_hoy = preparar_estado_recepcion(
        pacientes_de_hoy_queryset
    )

    pacientes_hoy = len(
        pacientes_de_hoy
    )

    citas_de_hoy = (
        Cita.objects
        .select_related(
            'tipo_estudio'
        )
        .filter(
            institucion=institucion,
            fecha_hora__date=hoy
        )
        .exclude(
            estado__in=[
                'CANCELADA',
                'NO_ASISTIO',
            ]
        )
        .order_by(
            'fecha_hora'
        )
    )

    citas_hoy = (
        citas_de_hoy.count()
    )

    context = {
        'pacientes':
            pacientes,

        'pacientes_de_hoy':
            pacientes_de_hoy,

        'busqueda':
            busqueda,

        'pacientes_hoy':
            pacientes_hoy,

        'total_citas_hoy':
            citas_hoy,

        'citas_de_hoy':
            citas_de_hoy,
    }

    return render(
        request,
        'core/panel_recepcion.html',
        context
    )


# =========================================================
# CITAS
# =========================================================

@login_required
def nueva_cita(request):
    institucion = obtener_institucion_usuario(request)

    if institucion is None:
        return redirect('panel_config')

    if request.method == 'POST':

        cita_form = CitaForm(
            request.POST
        )

        if cita_form.is_valid():

            cita = cita_form.save(
                commit=False
            )

            cita.creada_por = (
                request.user
            )

            cita.institucion = (
                institucion
            )

            cita.save()

            return redirect(
                'panel_recepcion'
            )

    else:

        cita_form = CitaForm(
            initial={
                'estado':
                    'PROGRAMADA',

                'duracion_minutos':
                    30,
            }
        )

    context = {
        'cita_form':
            cita_form,
    }

    return render(
        request,
        'core/nueva_cita.html',
        context
    )


# =========================================================
# EXPEDIENTE
# =========================================================

@login_required
def servicios_paciente_recepcion(
    request,
    paciente_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        if membresia.rol == 'MEDICO':
            return redirect('panel_medico')

        if membresia.rol in [
            'RADIOLOGIA',
            'TECNICO',
        ]:
            return redirect('panel_radiologo')

        return redirect('inicio')

    paciente = get_object_or_404(
        Paciente,
        pk=paciente_id,
        institucion=membresia.institucion,
    )

    estudios = list(
        Estudio.objects
        .select_related(
            'tipo_estudio'
        )
        .filter(
            paciente=paciente
        )
        .order_by(
            '-fecha_creacion'
        )
    )

    total_servicios = len(
        estudios
    )

    total_realizados = sum(
        1
        for estudio in estudios
        if estudio.estado == 'COMPLETADO'
    )

    total_en_proceso = sum(
        1
        for estudio in estudios
        if estudio.estado == 'EN_PROCESO'
    )

    total_pendientes = sum(
        1
        for estudio in estudios
        if estudio.estado == 'PENDIENTE'
    )

    resumen_por_tipo = {}

    for estudio in estudios:
        nombre = (
            estudio.tipo_estudio.nombre
            if estudio.tipo_estudio
            else 'Servicio sin especificar'
        )

        if nombre not in resumen_por_tipo:
            resumen_por_tipo[nombre] = {
                'nombre': nombre,
                'cantidad': 0,
                'realizados': 0,
            }

        resumen_por_tipo[nombre]['cantidad'] += 1

        if estudio.estado == 'COMPLETADO':
            resumen_por_tipo[nombre]['realizados'] += 1

    resumen_servicios = sorted(
        resumen_por_tipo.values(),
        key=lambda item: (
            -item['cantidad'],
            item['nombre'].lower(),
        )
    )

    context = {
        'paciente': paciente,
        'estudios': estudios,
        'total_servicios': total_servicios,
        'total_realizados': total_realizados,
        'total_en_proceso': total_en_proceso,
        'total_pendientes': total_pendientes,
        'resumen_servicios': resumen_servicios,
        'membresia': membresia,
    }

    return render(
        request,
        'core/servicios_paciente_recepcion.html',
        context
    )


@login_required
def detalle_paciente(
    request,
    paciente_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'RADIOLOGIA',
        'TECNICO',
        'ADMIN',
    ]:
        return redirect('panel_recepcion')

    paciente = get_object_or_404(
        Paciente,
        pk=paciente_id,
        institucion=membresia.institucion
    )

    estudios = (
        paciente.estudios
        .select_related(
            'tipo_estudio',
            'reporte_final_por',
            'pre_reporte_por',
        )
        .prefetch_related(
            'archivos'
        )
        .all()
        .order_by(
            '-fecha_creacion'
        )
    )

    consultas = (
        paciente.consultas
        .select_related(
            'medico'
        )
        .all()
        .order_by(
            '-fecha_llegada'
        )
    )

    citas = (
        paciente.citas
        .select_related(
            'tipo_estudio'
        )
        .all()
        .order_by(
            '-fecha_hora'
        )
    )

    consulta_activa = None

    if membresia.rol in [
        'MEDICO',
        'ADMIN',
    ]:
        consulta_activa = (
            paciente.consultas
            .select_related(
                'medico'
            )
            .filter(
                estado='EN_CONSULTA'
            )
            .filter(
                Q(
                    medico=request.user
                )
                |
                Q(
                    medico__isnull=True
                )
            )
            .order_by(
                '-fecha_inicio',
                '-fecha_llegada',
            )
            .first()
        )

    edad = calcular_edad(
        paciente.fecha_nacimiento
    )

    puede_editar_clinica = (
        membresia.rol
        in [
            'MEDICO',
            'ADMIN',
        ]
    )

    context = {
        'paciente': paciente,
        'estudios': estudios,
        'consultas': consultas,
        'citas': citas,
        'edad': edad,
        'membresia': membresia,
        'consulta_activa': consulta_activa,
        'puede_editar_clinica':
            puede_editar_clinica,
    }

    return render(
        request,
        'core/detalle_paciente.html',
        context
    )


@login_required
def guardar_consulta_clinica(
    request,
    consulta_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente',
            'medico',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
        estado='EN_CONSULTA',
    )

    if (
        membresia.rol != 'ADMIN'
        and consulta.medico_id
        and consulta.medico_id != request.user.id
    ):
        return redirect(
            'detalle_paciente',
            paciente_id=consulta.paciente_id
        )

    if request.method == 'POST':

        def entero(nombre):
            valor = (
                request.POST.get(
                    nombre,
                    ''
                )
                .strip()
            )

            if not valor:
                return None

            try:
                return int(valor)
            except (
                TypeError,
                ValueError,
            ):
                return None

        def decimal(nombre):
            valor = (
                request.POST.get(
                    nombre,
                    ''
                )
                .strip()
                .replace(
                    ',',
                    '.'
                )
            )

            if not valor:
                return None

            try:
                return float(valor)
            except (
                TypeError,
                ValueError,
            ):
                return None

        def texto(nombre):
            return (
                request.POST.get(
                    nombre,
                    ''
                )
                .strip()
                or None
            )

        consulta.medico = (
            consulta.medico
            or request.user
        )

        consulta.motivo_consulta = (
            texto('motivo_consulta')
        )

        consulta.presion_sistolica = (
            entero('presion_sistolica')
        )

        consulta.presion_diastolica = (
            entero('presion_diastolica')
        )

        consulta.frecuencia_cardiaca = (
            entero('frecuencia_cardiaca')
        )

        consulta.frecuencia_respiratoria = (
            entero('frecuencia_respiratoria')
        )

        consulta.temperatura = (
            decimal('temperatura')
        )

        consulta.saturacion_oxigeno = (
            entero('saturacion_oxigeno')
        )

        consulta.peso_kg = (
            decimal('peso_kg')
        )

        consulta.talla_cm = (
            decimal('talla_cm')
        )

        consulta.antecedentes = (
            texto('antecedentes')
        )

        consulta.exploracion_fisica = (
            texto('exploracion_fisica')
        )

        consulta.diagnostico = (
            texto('diagnostico')
        )

        consulta.plan_tratamiento = (
            texto('plan_tratamiento')
        )

        consulta.notas_medicas = (
            texto('notas_medicas')
        )

        consulta.save(
            update_fields=[
                'medico',
                'motivo_consulta',
                'presion_sistolica',
                'presion_diastolica',
                'frecuencia_cardiaca',
                'frecuencia_respiratoria',
                'temperatura',
                'saturacion_oxigeno',
                'peso_kg',
                'talla_cm',
                'antecedentes',
                'exploracion_fisica',
                'diagnostico',
                'plan_tratamiento',
                'notas_medicas',
            ]
        )

    return redirect(
        'detalle_paciente',
        paciente_id=consulta.paciente_id
    )


# =========================================================
# REPORTE FINAL DESDE EXPEDIENTE MÉDICO
# =========================================================

@login_required
def guardar_reporte_final_medico(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    estudio = get_object_or_404(
        Estudio.objects.select_related(
            'paciente',
            'tipo_estudio',
            'reporte_final_por',
        ),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        reporte_final = (
            request.POST.get(
                'reporte_final',
                ''
            )
            .strip()
        )

        if reporte_final:
            estudio.reporte_final = reporte_final
            estudio.reporte_final_por = request.user
            estudio.fecha_reporte_final = timezone.now()
            estudio.estado_reporte = 'FINAL'

            estudio.save(
                update_fields=[
                    'reporte_final',
                    'reporte_final_por',
                    'fecha_reporte_final',
                    'estado_reporte',
                ]
            )

    return redirect(
        'detalle_paciente',
        paciente_id=estudio.paciente_id
    )


# =========================================================
# NUEVO ESTUDIO
# =========================================================

@login_required
def nuevo_estudio_paciente(
    request,
    paciente_id
):
    institucion = obtener_institucion_usuario(request)

    if institucion is None:
        return redirect('panel_config')

    paciente = get_object_or_404(
        Paciente,
        pk=paciente_id,
        institucion=institucion
    )

    if request.method == 'POST':

        estudio_form = EstudioForm(
            request.POST
        )

        if estudio_form.is_valid():

            estudio = (
                estudio_form.save(
                    commit=False
                )
            )

            estudio.paciente = (
                paciente
            )

            estudio.save()

            return redirect(
                'detalle_paciente',
                paciente_id=paciente.id
            )

    else:

        estudio_form = EstudioForm(
            initial={
                'estado':
                    'PENDIENTE',
            }
        )

    context = {
        'paciente':
            paciente,

        'estudio_form':
            estudio_form,
    }

    return render(
        request,
        'core/nuevo_estudio.html',
        context
    )


# =========================================================
# CONFIGURACIÓN
# =========================================================

@login_required
def panel_config(request):
    return render(
        request,
        'core/panel_config.html'
    )


# =========================================================
# REGISTRO DESDE RECEPCIÓN
# =========================================================

@login_required
def registrar_estudio_recepcion(request):
    institucion = obtener_institucion_usuario(request)

    if institucion is None:
        return redirect('panel_config')

    if request.method == 'POST':

        paciente_form = PacienteForm(
            request.POST
        )

        destino_form = (
            DestinoAtencionForm(
                request.POST
            )
        )

        consulta_form = ConsultaForm(
            request.POST
        )

        estudio_form = EstudioForm(
            request.POST
        )

        formularios_principales_validos = (
            paciente_form.is_valid()
            and
            destino_form.is_valid()
        )

        if formularios_principales_validos:

            tipo_atencion = (
                destino_form.cleaned_data[
                    'tipo_atencion'
                ]
            )

            if tipo_atencion == 'CONSULTA':

                formulario_atencion_valido = (
                    consulta_form.is_valid()
                )

            else:

                formulario_atencion_valido = (
                    estudio_form.is_valid()
                )

            if formulario_atencion_valido:

                with transaction.atomic():

                    paciente = (
                        paciente_form.save(
                            commit=False
                        )
                    )

                    paciente.institucion = (
                        institucion
                    )

                    paciente.save()

                    if (
                        tipo_atencion
                        == 'CONSULTA'
                    ):

                        consulta = (
                            consulta_form.save(
                                commit=False
                            )
                        )

                        consulta.paciente = (
                            paciente
                        )

                        consulta.estado = (
                            'EN_ESPERA'
                        )

                        consulta.save()

                    elif (
                        tipo_atencion
                        == 'RADIOLOGIA'
                    ):

                        estudio = (
                            estudio_form.save(
                                commit=False
                            )
                        )

                        estudio.paciente = (
                            paciente
                        )

                        estudio.estado = (
                            'PENDIENTE'
                        )

                        estudio.save()

                return redirect(
                    'detalle_paciente',
                    paciente_id=paciente.id
                )

    else:

        paciente_form = PacienteForm()

        destino_form = (
            DestinoAtencionForm(
                initial={
                    'tipo_atencion':
                        'CONSULTA',
                }
            )
        )

        consulta_form = (
            ConsultaForm()
        )

        estudio_form = EstudioForm(
            initial={
                'estado':
                    'PENDIENTE',
            }
        )

    context = {
        'paciente_form':
            paciente_form,

        'destino_form':
            destino_form,

        'consulta_form':
            consulta_form,

        'estudio_form':
            estudio_form,
    }

    return render(
        request,
        'core/registrar_recepcion.html',
        context
    )