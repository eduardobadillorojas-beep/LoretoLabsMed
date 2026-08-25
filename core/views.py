from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import logging
from urllib.parse import quote
from xml.sax.saxutils import escape

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Q
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

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
    CargoPaciente,
    Cita,
    Cobro,
    Consulta,
    Estudio,
    EstudioSolicitado,
    IndicacionMedica,
    MedicamentoReceta,
    MembresiaInstitucion,
    Paciente,
    PagoCobro,
    PerfilMedico,
    RecetaMedica,
    SesionTrabajo,
    SolicitudEstudio,
    Servicio,
    TipoEstudio,
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


def puede_administrar_configuracion(request, membresia=None):
    if request.user.is_superuser:
        return True

    if membresia is None:
        membresia = obtener_membresia_usuario(request)

    return bool(
        membresia
        and membresia.rol == 'ADMIN'
    )


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

            membresia = (
                MembresiaInstitucion.objects
                .select_related('institucion')
                .filter(
                    usuario=user,
                    activa=True,
                    institucion__activa=True,
                )
                .first()
            )

            if user.is_superuser:
                return redirect(
                    'panel_config'
                )

            if membresia is None:
                return redirect(
                    'panel_config'
                )

            if membresia.rol == 'RECEPCION':
                return redirect(
                    'panel_recepcion'
                )

            if membresia.rol == 'MEDICO':
                return redirect(
                    'panel_medico'
                )

            if membresia.rol in [
                'RADIOLOGIA',
                'TECNICO',
            ]:
                return redirect(
                    'panel_radiologo'
                )

            if membresia.rol == 'ADMIN':
                return redirect(
                    'panel_config'
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
def perfil_medico(request):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    perfil, _ = PerfilMedico.objects.get_or_create(
        institucion=membresia.institucion,
        usuario=request.user,
        defaults={
            'activo': True,
        }
    )

    guardado = False

    if request.method == 'POST':
        perfil.especialidad = (
            request.POST.get(
                'especialidad',
                ''
            )
            .strip()
            or None
        )

        perfil.cedula_profesional = (
            request.POST.get(
                'cedula_profesional',
                ''
            )
            .strip()
            or None
        )

        perfil.telefono_profesional = (
            request.POST.get(
                'telefono_profesional',
                ''
            )
            .strip()
            or None
        )

        firma = request.FILES.get(
            'firma'
        )

        if firma:
            perfil.firma = firma

        if request.POST.get(
            'eliminar_firma'
        ) == '1':
            if perfil.firma:
                perfil.firma.delete(
                    save=False
                )

            perfil.firma = None

        perfil.activo = True
        perfil.save()

        guardado = True

    context = {
        'membresia': membresia,
        'institucion': membresia.institucion,
        'perfil': perfil,
        'guardado': guardado,
    }

    return render(
        request,
        'core/perfil_medico.html',
        context
    )


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
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        return redirect('panel_config')

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
def caja_recepcion(request):
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

    fecha_texto = request.GET.get(
        'fecha',
        ''
    ).strip()

    try:
        fecha_consulta = date.fromisoformat(
            fecha_texto
        )
    except ValueError:
        fecha_consulta = timezone.localdate()

    busqueda = request.GET.get(
        'buscar',
        ''
    ).strip()

    cobros_queryset = (
        Cobro.objects
        .filter(
            institucion=membresia.institucion,
            creado_el__date=fecha_consulta,
        )
        .select_related(
            'paciente',
            'creado_por',
        )
        .prefetch_related(
            'cargos',
            'pagos',
        )
        .order_by('-creado_el')
    )

    if busqueda:
        cobros_queryset = cobros_queryset.filter(
            Q(folio__icontains=busqueda)
            | Q(paciente__nombre__icontains=busqueda)
            | Q(paciente__apellido__icontains=busqueda)
            | Q(paciente__identificacion__icontains=busqueda)
        )

    cobros = list(cobros_queryset)
    cobros_pagados = [
        cobro
        for cobro in cobros
        if cobro.estado == 'PAGADO'
    ]

    total_general = sum(
        (cobro.total for cobro in cobros_pagados),
        Decimal('0.00')
    )

    totales_forma = {
        'EFECTIVO': Decimal('0.00'),
        'TARJETA': Decimal('0.00'),
        'TRANSFERENCIA': Decimal('0.00'),
        'OTRO': Decimal('0.00'),
    }

    for cobro in cobros:
        pagos_cobro = list(cobro.pagos.all())
        cobro.pagos_mostrables = pagos_cobro

        if cobro.estado != 'PAGADO':
            continue

        if pagos_cobro:
            for pago in pagos_cobro:
                if pago.forma_pago in totales_forma:
                    totales_forma[pago.forma_pago] += pago.monto
        elif cobro.forma_pago in totales_forma:
            totales_forma[cobro.forma_pago] += cobro.total

    context = {
        'membresia': membresia,
        'fecha_consulta': fecha_consulta,
        'fecha_texto': fecha_consulta.isoformat(),
        'busqueda': busqueda,
        'cobros': cobros,
        'total_general': total_general,
        'total_efectivo': totales_forma['EFECTIVO'],
        'total_tarjeta': totales_forma['TARJETA'],
        'total_transferencia': totales_forma['TRANSFERENCIA'],
        'total_otro': totales_forma['OTRO'],
        'numero_cobros': len(cobros_pagados),
    }

    return render(
        request,
        'core/caja_recepcion.html',
        context
    )

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

    if request.method == 'POST':
        accion = request.POST.get(
            'accion',
            ''
        ).strip()

        if accion == 'AGREGAR':
            servicio = get_object_or_404(
                Servicio,
                pk=request.POST.get('servicio_id'),
                institucion=membresia.institucion,
                activo=True,
            )

            try:
                cantidad = Decimal(
                    request.POST.get(
                        'cantidad',
                        '1'
                    )
                )

                if cantidad <= 0:
                    raise InvalidOperation

                if cantidad > Decimal('99999999.99'):
                    raise InvalidOperation

                cantidad = cantidad.quantize(
                    Decimal('0.01')
                )
            except (InvalidOperation, ValueError):
                messages.error(
                    request,
                    'Escribe una cantidad válida mayor que cero.'
                )
                return redirect(
                    'servicios_paciente_recepcion',
                    paciente_id=paciente.id,
                )

            try:
                precio_unitario = Decimal(
                    request.POST.get(
                        'precio_unitario',
                        str(servicio.precio_base)
                    )
                )

                if precio_unitario < 0:
                    raise InvalidOperation

                if precio_unitario > Decimal(
                    '9999999999.99'
                ):
                    raise InvalidOperation

                precio_unitario = precio_unitario.quantize(
                    Decimal('0.01')
                )
            except (InvalidOperation, ValueError):
                messages.error(
                    request,
                    'Escribe un precio válido mayor o igual a cero.'
                )
                return redirect(
                    'servicios_paciente_recepcion',
                    paciente_id=paciente.id,
                )

            CargoPaciente.objects.create(
                institucion=membresia.institucion,
                paciente=paciente,
                servicio=servicio,
                descripcion=servicio.nombre,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                estado='PENDIENTE',
                origen='RECEPCION',
                agregado_por=request.user,
                notas=(
                    request.POST.get(
                        'notas',
                        ''
                    ).strip()
                    or None
                ),
            )

            messages.success(
                request,
                'Servicio agregado a la cuenta del paciente.'
            )

        elif accion == 'COBRAR':
            modo_cobro = request.POST.get(
                'modo_cobro',
                'TOTAL'
            ).strip()

            cargos_ids = request.POST.getlist(
                'cargos_ids'
            )

            tipo_pago = request.POST.get(
                'tipo_pago',
                'UNICO'
            ).strip()

            forma_pago_solicitada = request.POST.get(
                'forma_pago',
                'EFECTIVO'
            ).strip()

            formas_validas = {
                valor
                for valor, etiqueta
                in PagoCobro.FORMA_PAGO_CHOICES
            }

            if forma_pago_solicitada not in formas_validas:
                forma_pago_solicitada = 'OTRO'

            forma_pago = (
                'MIXTO'
                if tipo_pago == 'MIXTO'
                else forma_pago_solicitada
            )

            telefono_envio = (
                request.POST.get(
                    'telefono_envio',
                    ''
                ).strip()
                or paciente.telefono
                or None
            )

            with transaction.atomic():
                cargos_queryset = (
                    CargoPaciente.objects
                    .select_for_update()
                    .filter(
                        institucion=membresia.institucion,
                        paciente=paciente,
                        estado='PENDIENTE',
                        cobro__isnull=True,
                    )
                    .order_by('creado_el', 'pk')
                )

                if modo_cobro != 'TOTAL':
                    cargos_queryset = cargos_queryset.filter(
                        pk__in=cargos_ids
                    )

                cargos_seleccionados = list(
                    cargos_queryset
                )

                if not cargos_seleccionados:
                    messages.error(
                        request,
                        (
                            'La cuenta no tiene cargos pendientes.'
                            if modo_cobro == 'TOTAL'
                            else 'Selecciona al menos un cargo pendiente.'
                        )
                    )
                    return redirect(
                        'servicios_paciente_recepcion',
                        paciente_id=paciente.id,
                    )

                total_cobro = sum(
                    (
                        cargo.subtotal
                        for cargo in cargos_seleccionados
                    ),
                    Decimal('0.00')
                ).quantize(Decimal('0.01'))

                monto_recibido = None
                cambio = Decimal('0.00')
                pagos_a_registrar = []

                if forma_pago == 'MIXTO':
                    nombres_formas = {
                        'EFECTIVO': 'monto_efectivo',
                        'TARJETA': 'monto_tarjeta',
                        'TRANSFERENCIA': 'monto_transferencia',
                        'OTRO': 'monto_otro',
                    }

                    try:
                        for forma, campo in nombres_formas.items():
                            texto_monto = request.POST.get(
                                campo,
                                '0'
                            ).strip() or '0'

                            monto = Decimal(texto_monto).quantize(
                                Decimal('0.01')
                            )

                            if monto < 0 or monto > Decimal('9999999999.99'):
                                raise InvalidOperation

                            if monto > 0:
                                pagos_a_registrar.append({
                                    'forma_pago': forma,
                                    'monto': monto,
                                    'referencia': (
                                        request.POST.get(
                                            f'referencia_{forma.lower()}',
                                            ''
                                        ).strip()
                                        or None
                                    ),
                                })

                        total_distribuido = sum(
                            (
                                pago['monto']
                                for pago in pagos_a_registrar
                            ),
                            Decimal('0.00')
                        ).quantize(Decimal('0.01'))

                        if (
                            len(pagos_a_registrar) < 2
                            or total_distribuido != total_cobro
                        ):
                            raise InvalidOperation
                    except (InvalidOperation, ValueError):
                        messages.error(
                            request,
                            (
                                'En un pago mixto utiliza al menos dos formas '
                                'y asegúrate de que los importes sumen exactamente '
                                f'${total_cobro:.2f}.'
                            )
                        )
                        return redirect(
                            'servicios_paciente_recepcion',
                            paciente_id=paciente.id,
                        )

                    efectivo_aplicado = next(
                        (
                            pago['monto']
                            for pago in pagos_a_registrar
                            if pago['forma_pago'] == 'EFECTIVO'
                        ),
                        Decimal('0.00')
                    )

                    if efectivo_aplicado > 0:
                        try:
                            monto_recibido = Decimal(
                                request.POST.get(
                                    'monto_recibido',
                                    str(efectivo_aplicado)
                                )
                            ).quantize(Decimal('0.01'))

                            if monto_recibido < efectivo_aplicado:
                                raise InvalidOperation

                            cambio = (
                                monto_recibido
                                - efectivo_aplicado
                            ).quantize(Decimal('0.01'))
                        except (InvalidOperation, ValueError):
                            messages.error(
                                request,
                                'El efectivo recibido debe cubrir la parte pagada en efectivo.'
                            )
                            return redirect(
                                'servicios_paciente_recepcion',
                                paciente_id=paciente.id,
                            )

                elif forma_pago == 'EFECTIVO':
                    try:
                        monto_recibido = Decimal(
                            request.POST.get(
                                'monto_recibido',
                                str(total_cobro)
                            )
                        ).quantize(
                            Decimal('0.01')
                        )

                        if monto_recibido < total_cobro:
                            raise InvalidOperation

                        if monto_recibido > Decimal('9999999999.99'):
                            raise InvalidOperation

                        cambio = (
                            monto_recibido
                            - total_cobro
                        ).quantize(
                            Decimal('0.01')
                        )
                    except (InvalidOperation, ValueError):
                        messages.error(
                            request,
                            'El efectivo recibido debe cubrir el total de la cuenta.'
                        )
                        return redirect(
                            'servicios_paciente_recepcion',
                            paciente_id=paciente.id,
                        )

                    pagos_a_registrar.append({
                        'forma_pago': forma_pago,
                        'monto': total_cobro,
                        'referencia': None,
                    })
                else:
                    pagos_a_registrar.append({
                        'forma_pago': forma_pago,
                        'monto': total_cobro,
                        'referencia': (
                            request.POST.get(
                                f'referencia_{forma_pago.lower()}',
                                ''
                            ).strip()
                            or None
                        ),
                    })

                cobro = Cobro.objects.create(
                    institucion=membresia.institucion,
                    paciente=paciente,
                    forma_pago=forma_pago,
                    total=total_cobro,
                    monto_recibido=monto_recibido,
                    cambio=cambio,
                    telefono_envio=telefono_envio,
                    creado_por=request.user,
                )

                PagoCobro.objects.bulk_create([
                    PagoCobro(
                        cobro=cobro,
                        forma_pago=pago['forma_pago'],
                        monto=pago['monto'],
                        referencia=pago['referencia'],
                    )
                    for pago in pagos_a_registrar
                ])

                CargoPaciente.objects.filter(
                    pk__in=[
                        cargo.pk
                        for cargo in cargos_seleccionados
                    ]
                ).update(
                    estado='PAGADO',
                    cobro=cobro,
                    actualizado_el=timezone.now(),
                )

            messages.success(
                request,
                (
                    f'Cuenta cobrada en un solo comprobante con '
                    f'{len(cargos_seleccionados)} concepto(s).'
                )
            )

            salida = request.POST.get(
                'salida',
                'DIGITAL'
            ).strip()

            destino = reverse(
                'cobro_exitoso',
                kwargs={
                    'cobro_id': cobro.id,
                }
            )

            return redirect(
                f'{destino}?salida={salida}'
            )

        elif accion in [
            'PAGAR',
            'CANCELAR',
        ]:
            cargo = get_object_or_404(
                CargoPaciente,
                pk=request.POST.get('cargo_id'),
                institucion=membresia.institucion,
                paciente=paciente,
            )

            if cargo.estado != 'PENDIENTE':
                messages.warning(
                    request,
                    'Ese cargo ya no está pendiente.'
                )
            else:
                cargo.estado = (
                    'PAGADO'
                    if accion == 'PAGAR'
                    else 'CANCELADO'
                )
                cargo.save(
                    update_fields=[
                        'estado',
                        'actualizado_el',
                    ]
                )

                messages.success(
                    request,
                    (
                        'Cargo marcado como pagado.'
                        if accion == 'PAGAR'
                        else 'Cargo cancelado correctamente.'
                    )
                )

        return redirect(
            'servicios_paciente_recepcion',
            paciente_id=paciente.id,
        )

    cargos = list(
        CargoPaciente.objects
        .filter(
            institucion=membresia.institucion,
            paciente=paciente,
        )
        .select_related(
            'servicio',
            'agregado_por',
            'cobro',
        )
        .order_by('-creado_el')
    )

    cargos_pendientes = [
        cargo
        for cargo in cargos
        if cargo.estado == 'PENDIENTE'
    ]

    cargos_pagados = [
        cargo
        for cargo in cargos
        if cargo.estado == 'PAGADO'
    ]

    cargos_pagados_con_cobro = [
        cargo
        for cargo in cargos_pagados
        if cargo.cobro_id
    ]

    total_pendiente = sum(
        (
            cargo.subtotal
            for cargo in cargos_pendientes
        ),
        Decimal('0.00')
    )

    total_pagado = sum(
        (
            cargo.subtotal
            for cargo in cargos_pagados
        ),
        Decimal('0.00')
    )

    servicios_catalogo = (
        Servicio.objects
        .filter(
            institucion=membresia.institucion,
            activo=True,
        )
        .select_related('tipo_estudio')
        .order_by(
            'tipo',
            'nombre',
        )
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
        'cargos': cargos,
        'cargos_pendientes': cargos_pendientes,
        'cargos_pagados': cargos_pagados,
        'cargos_pagados_con_cobro': cargos_pagados_con_cobro,
        'total_pendiente': total_pendiente,
        'total_pagado': total_pagado,
        'servicios_catalogo': servicios_catalogo,
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


def construir_pdf_cobro(cobro):
    buffer = BytesIO()

    documento = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title=f'Comprobante {cobro.folio}',
    )

    estilos = getSampleStyleSheet()

    titulo = ParagraphStyle(
        'TituloCobro',
        parent=estilos['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#17365d'),
    )

    normal = ParagraphStyle(
        'NormalCobro',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
    )

    pequeno = ParagraphStyle(
        'PequenoCobro',
        parent=normal,
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor('#475569'),
    )

    institucion = cobro.institucion
    paciente = cobro.paciente
    historia = []

    logo = None

    if institucion.logo:
        try:
            institucion.logo.open('rb')
            datos_logo = institucion.logo.read()
            institucion.logo.close()

            if datos_logo:
                logo = Image(
                    BytesIO(datos_logo),
                    width=2.2 * cm,
                    height=1.5 * cm,
                    kind='proportional',
                )
        except Exception:
            logo = None

    nombre_institucion = (
        institucion.nombre_comercial
        or institucion.nombre
    )

    datos_institucion = [
        Paragraph(
            escape(nombre_institucion),
            titulo
        )
    ]

    if institucion.rfc:
        datos_institucion.append(
            Paragraph(
                f'RFC: {escape(institucion.rfc)}',
                pequeno
            )
        )

    if institucion.direccion:
        datos_institucion.append(
            Paragraph(
                escape(institucion.direccion),
                pequeno
            )
        )

    if institucion.telefono:
        datos_institucion.append(
            Paragraph(
                f'Tel. {escape(institucion.telefono)}',
                pequeno
            )
        )

    encabezado = Table(
        [[logo or '', datos_institucion]],
        colWidths=[2.6 * cm, 15.4 * cm],
    )

    encabezado.setStyle(
        TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#17365d')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ])
    )

    historia.append(encabezado)
    historia.append(Spacer(1, 10))
    historia.append(
        Paragraph(
            'COMPROBANTE DE CUENTA',
            titulo
        )
    )
    historia.append(Spacer(1, 6))

    fecha_local = timezone.localtime(
        cobro.creado_el
    )

    datos_cobro = [
        ['Folio', cobro.folio],
        ['Fecha', fecha_local.strftime('%d/%m/%Y %H:%M')],
        [
            'Paciente',
            f'{paciente.nombre} {paciente.apellido}'
        ],
        ['Registro', paciente.identificacion],
        ['Conceptos incluidos', str(cobro.cargos.count())],
        ['Forma de pago', cobro.get_forma_pago_display()],
    ]

    tabla_datos = Table(
        datos_cobro,
        colWidths=[3.2 * cm, 14.8 * cm],
    )

    tabla_datos.setStyle(
        TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])
    )

    historia.append(tabla_datos)
    historia.append(Spacer(1, 10))

    filas = [[
        'Concepto',
        'Cantidad',
        'Precio',
        'Subtotal',
    ]]

    for cargo in cobro.cargos.all():
        filas.append([
            Paragraph(
                escape(cargo.descripcion),
                normal
            ),
            f'{cargo.cantidad:.2f}',
            f'${cargo.precio_unitario:.2f}',
            f'${cargo.subtotal:.2f}',
        ])

    tabla_cargos = Table(
        filas,
        colWidths=[10.2 * cm, 2.2 * cm, 2.8 * cm, 2.8 * cm],
        repeatRows=1,
    )

    tabla_cargos.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#17365d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ])
    )

    historia.append(tabla_cargos)
    historia.append(Spacer(1, 10))

    totales = [
        ['TOTAL PAGADO', f'${cobro.total:.2f}'],
    ]

    pagos_cobro = list(cobro.pagos.all())

    for pago in pagos_cobro:
        totales.append([
            pago.get_forma_pago_display().upper(),
            f'${pago.monto:.2f}',
        ])

    if cobro.monto_recibido is not None:
        totales.extend([
            [
                'EFECTIVO RECIBIDO',
                f'${cobro.monto_recibido:.2f}'
            ],
            ['CAMBIO', f'${cobro.cambio:.2f}'],
        ])

    tabla_totales = Table(
        totales,
        colWidths=[14.5 * cm, 3.5 * cm],
    )

    tabla_totales.setStyle(
        TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('LINEABOVE', (0, 0), (-1, 0), 1, colors.HexColor('#17365d')),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ])
    )

    historia.append(tabla_totales)
    historia.append(Spacer(1, 18))
    historia.append(
        Paragraph(
            'Este documento es un comprobante interno de pago y no sustituye un CFDI.',
            pequeno
        )
    )

    if institucion.pie_documentos:
        historia.append(Spacer(1, 6))
        historia.append(
            Paragraph(
                escape(institucion.pie_documentos),
                pequeno
            )
        )

    documento.build(historia)
    contenido = buffer.getvalue()
    buffer.close()
    return contenido


@login_required
def cobro_exitoso(
    request,
    cobro_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None or membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        return redirect('inicio')

    cobro = get_object_or_404(
        Cobro.objects.select_related(
            'institucion',
            'paciente',
            'creado_por',
        ).prefetch_related(
            'cargos',
            'pagos',
        ),
        pk=cobro_id,
        institucion=membresia.institucion,
    )

    enlace_pdf = request.build_absolute_uri(
        reverse(
            'comprobante_cobro_pdf',
            kwargs={
                'token': cobro.token_publico,
            }
        )
    )

    telefono = ''.join(
        caracter
        for caracter in (cobro.telefono_envio or '')
        if caracter.isdigit()
    )

    if len(telefono) == 10:
        telefono = f'52{telefono}'

    mensaje = (
        f'Hola. Compartimos su comprobante de pago '
        f'{cobro.folio} de '
        f'{cobro.institucion.nombre_comercial or cobro.institucion.nombre}: '
        f'{enlace_pdf}'
    )

    enlace_whatsapp = ''

    if telefono:
        enlace_whatsapp = (
            f'https://wa.me/{telefono}?text={quote(mensaje)}'
        )

    context = {
        'cobro': cobro,
        'enlace_pdf': enlace_pdf,
        'enlace_whatsapp': enlace_whatsapp,
        'salida': request.GET.get('salida', 'DIGITAL'),
    }

    return render(
        request,
        'core/cobro_exitoso.html',
        context
    )


@login_required
def ticket_cobro(
    request,
    cobro_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None or membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        return redirect('inicio')

    cobro = get_object_or_404(
        Cobro.objects.select_related(
            'institucion',
            'paciente',
            'creado_por',
        ).prefetch_related(
            'cargos',
            'pagos',
        ),
        pk=cobro_id,
        institucion=membresia.institucion,
    )

    return render(
        request,
        'core/ticket_cobro.html',
        {
            'cobro': cobro,
        }
    )


@login_required
def ticket_cargos_agrupados(
    request,
    paciente_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None or membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        return redirect('inicio')

    paciente = get_object_or_404(
        Paciente,
        pk=paciente_id,
        institucion=membresia.institucion,
    )

    if request.method != 'POST':
        return redirect(
            'servicios_paciente_recepcion',
            paciente_id=paciente.id,
        )

    accion_agrupado = request.POST.get(
        'accion_agrupado',
        'SELECCIONADOS'
    ).strip()

    cargos_queryset = (
        CargoPaciente.objects
        .filter(
            institucion=membresia.institucion,
            paciente=paciente,
            estado='PAGADO',
            cobro__isnull=False,
            cobro__estado='PAGADO',
        )
        .select_related(
            'cobro',
            'cobro__creado_por',
        )
        .order_by(
            'cobro__creado_el',
            'creado_el',
            'pk',
        )
    )

    if accion_agrupado != 'TODOS':
        cargos_ids = request.POST.getlist(
            'cargos_pagados_ids'
        )
        cargos_queryset = cargos_queryset.filter(
            pk__in=cargos_ids
        )

    cargos = list(cargos_queryset)

    if not cargos:
        messages.error(
            request,
            'Selecciona al menos un servicio pagado para imprimirlo.'
        )
        return redirect(
            'servicios_paciente_recepcion',
            paciente_id=paciente.id,
        )

    total = sum(
        (cargo.subtotal for cargo in cargos),
        Decimal('0.00')
    ).quantize(Decimal('0.01'))

    folios = []

    for cargo in cargos:
        if cargo.cobro.folio not in folios:
            folios.append(cargo.cobro.folio)

    return render(
        request,
        'core/ticket_cargos_agrupados.html',
        {
            'institucion': membresia.institucion,
            'paciente': paciente,
            'cargos': cargos,
            'folios': folios,
            'total': total,
            'fecha_emision': timezone.now(),
            'emitido_por': request.user,
        }
    )


def comprobante_cobro_pdf(
    request,
    token
):
    cobro = get_object_or_404(
        Cobro.objects.select_related(
            'institucion',
            'paciente',
            'creado_por',
        ).prefetch_related(
            'cargos',
            'pagos',
        ),
        token_publico=token,
        estado='PAGADO',
    )

    contenido = construir_pdf_cobro(cobro)

    response = HttpResponse(
        contenido,
        content_type='application/pdf'
    )

    response['Content-Disposition'] = (
        f'inline; filename="comprobante-{cobro.folio}.pdf"'
    )

    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response


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

    receta_activa = None
    indicacion_activa = None
    solicitudes_activas = []

    if consulta_activa and puede_editar_clinica:
        receta_activa = (
            RecetaMedica.objects
            .filter(
                consulta=consulta_activa
            )
            .prefetch_related(
                'medicamentos'
            )
            .first()
        )

        indicacion_activa = (
            IndicacionMedica.objects
            .filter(
                consulta=consulta_activa
            )
            .first()
        )

        solicitudes_activas = (
            SolicitudEstudio.objects
            .filter(
                consulta=consulta_activa
            )
            .prefetch_related(
                'estudios_solicitados'
            )
            .order_by(
                '-creada_el'
            )
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
        'receta_activa': receta_activa,
        'indicacion_activa': indicacion_activa,
        'solicitudes_activas': solicitudes_activas,
    }

    return render(
        request,
        'core/detalle_paciente.html',
        context
    )



@login_required
def generar_documentos_clinicos_pdf(
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
            'paciente__institucion',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
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

    incluir_receta = (
        request.GET.get('receta') == '1'
    )

    incluir_solicitudes = (
        request.GET.get('solicitudes') == '1'
    )

    incluir_indicaciones = (
        request.GET.get('indicaciones') == '1'
    )

    incluir_resumen = (
        request.GET.get('resumen') == '1'
    )

    if not any([
        incluir_receta,
        incluir_solicitudes,
        incluir_indicaciones,
        incluir_resumen,
    ]):
        incluir_receta = True

    institucion = consulta.paciente.institucion

    medico_documento = (
        consulta.medico
        or request.user
    )

    perfil_medico = (
        PerfilMedico.objects
        .filter(
            institucion=institucion,
            usuario=medico_documento,
            activo=True,
        )
        .first()
    )

    receta = (
        RecetaMedica.objects
        .filter(
            consulta=consulta
        )
        .prefetch_related(
            'medicamentos'
        )
        .first()
    )

    indicacion = (
        IndicacionMedica.objects
        .filter(
            consulta=consulta
        )
        .first()
    )

    solicitudes = list(
        SolicitudEstudio.objects
        .filter(
            consulta=consulta
        )
        .prefetch_related(
            'estudios_solicitados'
        )
        .order_by(
            'creada_el'
        )
    )

    buffer = BytesIO()

    response_disposition = (
        'attachment'
        if request.GET.get('descargar') == '1'
        else 'inline'
    )

    nombre_archivo = (
        'documentos_'
        f'{consulta.paciente.identificacion}_'
        f'{timezone.localdate():%Y%m%d}.pdf'
    )

    documento = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=1.05 * cm,
        leftMargin=1.05 * cm,
        topMargin=0.8 * cm,
        bottomMargin=0.85 * cm,
        title='Documentos clínicos',
        author=obtener_nombre_usuario(
            medico_documento
        ),
    )

    estilos_base = getSampleStyleSheet()

    estilo_institucion = ParagraphStyle(
        'InstitucionCompacta',
        parent=estilos_base['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=11.5,
        leading=13,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#0f2747'),
        spaceAfter=1,
    )

    estilo_institucion_sub = ParagraphStyle(
        'InstitucionSub',
        parent=estilos_base['Normal'],
        fontName='Helvetica',
        fontSize=6.7,
        leading=8.2,
        textColor=colors.HexColor('#334155'),
    )

    estilo_titulo = ParagraphStyle(
        'TituloCompacto',
        parent=estilos_base['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=9.2,
        leading=10.5,
        textColor=colors.HexColor('#0f2747'),
        spaceBefore=2,
        spaceAfter=3,
    )

    estilo_texto = ParagraphStyle(
        'TextoCompacto',
        parent=estilos_base['Normal'],
        fontName='Helvetica',
        fontSize=7.0,
        leading=8.5,
        textColor=colors.HexColor('#111827'),
    )

    estilo_texto_65 = ParagraphStyle(
        'Texto65',
        parent=estilo_texto,
        fontSize=6.5,
        leading=7.7,
    )

    estilo_pequeno = ParagraphStyle(
        'PequenoCompacto',
        parent=estilos_base['Normal'],
        fontName='Helvetica',
        fontSize=5.8,
        leading=6.8,
        textColor=colors.HexColor('#475569'),
    )

    estilo_tabla = ParagraphStyle(
        'TablaCompacta',
        parent=estilos_base['Normal'],
        fontName='Helvetica',
        fontSize=5.8,
        leading=6.7,
        textColor=colors.HexColor('#111827'),
    )

    estilo_tabla_negrita = ParagraphStyle(
        'TablaCompactaNegrita',
        parent=estilo_tabla,
        fontName='Helvetica-Bold',
    )

    estilo_centrado = ParagraphStyle(
        'CentradoCompacto',
        parent=estilo_pequeno,
        alignment=TA_CENTER,
    )

    historia = []

    def limpio(valor):
        if valor is None:
            return ''
        return escape(str(valor))

    def parrafo(valor, estilo=estilo_texto):
        return Paragraph(
            limpio(valor).replace('\n', '<br/>'),
            estilo
        )

    def imagen_desde_campo(campo, ancho, alto):
        if not campo:
            return None

        try:
            campo.open('rb')
            datos = campo.read()
            campo.close()

            if not datos:
                return None

            return Image(
                BytesIO(datos),
                width=ancho,
                height=alto,
                kind='proportional',
            )
        except Exception:
            return None

    def nombre_institucion():
        return (
            institucion.nombre_comercial
            or institucion.nombre
        )

    telefonos = [
        valor
        for valor in [
            institucion.telefono,
            institucion.telefono_secundario,
        ]
        if valor
    ]

    logo = imagen_desde_campo(
        institucion.logo,
        2.15 * cm,
        1.65 * cm,
    )

    bloque_institucion = [
        Paragraph(
            limpio(nombre_institucion()),
            estilo_institucion
        )
    ]

    if institucion.direccion:
        bloque_institucion.append(
            parrafo(
                institucion.direccion,
                estilo_institucion_sub
            )
        )

    if telefonos:
        bloque_institucion.append(
            parrafo(
                'Tel. ' + ' / '.join(telefonos),
                estilo_institucion_sub
            )
        )

    if institucion.email:
        bloque_institucion.append(
            parrafo(
                institucion.email,
                estilo_institucion_sub
            )
        )

    bloque_horarios = []

    if institucion.horarios_servicio:
        bloque_horarios.extend([
            Paragraph(
                '<b>HORARIO DE ATENCIÓN</b>',
                estilo_institucion_sub
            ),
            parrafo(
                institucion.horarios_servicio,
                estilo_institucion_sub
            ),
        ])

    encabezado = Table(
        [[
            logo or '',
            bloque_institucion,
            bloque_horarios,
        ]],
        colWidths=[
            2.5 * cm,
            10.4 * cm,
            6.25 * cm,
        ],
    )

    encabezado.setStyle(
        TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            (
                'LINEBELOW',
                (0, 0),
                (-1, -1),
                1.1,
                colors.HexColor('#17365d')
            ),
        ])
    )

    historia.append(encabezado)
    historia.append(Spacer(1, 0.12 * cm))

    edad = calcular_edad(
        consulta.paciente.fecha_nacimiento
    )

    paciente_info = [
        [
            Paragraph(
                '<b>PACIENTE:</b> '
                + limpio(
                    f'{consulta.paciente.nombre} '
                    f'{consulta.paciente.apellido}'
                ),
                estilo_texto_65
            ),
            Paragraph(
                '<b>REGISTRO:</b> '
                + limpio(
                    consulta.paciente.identificacion
                ),
                estilo_texto_65
            ),
        ],
        [
            Paragraph(
                '<b>FECHA DE NACIMIENTO:</b> '
                + limpio(
                    f'{consulta.paciente.fecha_nacimiento:%d/%m/%Y}'
                )
                + (
                    ' &nbsp;|&nbsp; '
                    + limpio(f'{edad} años')
                    if edad is not None
                    else ''
                ),
                estilo_texto_65
            ),
            Paragraph(
                '<b>FECHA:</b> '
                + limpio(
                    f'{timezone.localdate():%d/%m/%Y}'
                ),
                estilo_texto_65
            ),
        ],
    ]

    tabla_paciente = Table(
        paciente_info,
        colWidths=[
            12.7 * cm,
            6.45 * cm,
        ],
    )

    tabla_paciente.setStyle(
        TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            (
                'BACKGROUND',
                (0, 0),
                (-1, -1),
                colors.HexColor('#fbfdff')
            ),
            (
                'BOX',
                (0, 0),
                (-1, -1),
                0.45,
                colors.HexColor('#94a3b8')
            ),
            (
                'INNERGRID',
                (0, 0),
                (-1, -1),
                0.25,
                colors.HexColor('#cbd5e1')
            ),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])
    )

    historia.append(tabla_paciente)
    historia.append(Spacer(1, 0.16 * cm))

    secciones_agregadas = 0

    if incluir_resumen:
        historia.append(
            Paragraph(
                'RESUMEN CLÍNICO / REFERENCIA',
                estilo_titulo
            )
        )

        datos_resumen = []

        fecha_atencion = (
            consulta.fecha_inicio
            or consulta.fecha_llegada
        )

        if fecha_atencion:
            try:
                fecha_atencion = timezone.localtime(
                    fecha_atencion
                )
            except Exception:
                pass

            datos_resumen.append(
                '<b>Fecha y hora de atención:</b> '
                + limpio(
                    fecha_atencion.strftime(
                        '%d/%m/%Y %H:%M'
                    )
                )
            )

        if consulta.motivo_consulta:
            datos_resumen.append(
                '<b>Motivo de consulta:</b> '
                + limpio(
                    consulta.motivo_consulta
                )
            )

        for dato in datos_resumen:
            historia.append(
                Paragraph(
                    dato,
                    estilo_texto_65
                )
            )
            historia.append(
                Spacer(1, 0.05 * cm)
            )

        signos = []

        if (
            consulta.presion_sistolica is not None
            or consulta.presion_diastolica is not None
        ):
            sistolica = (
                str(consulta.presion_sistolica)
                if consulta.presion_sistolica is not None
                else '—'
            )
            diastolica = (
                str(consulta.presion_diastolica)
                if consulta.presion_diastolica is not None
                else '—'
            )
            signos.append(
                ('TA', f'{sistolica}/{diastolica} mmHg')
            )

        if consulta.frecuencia_cardiaca is not None:
            signos.append(
                ('FC', f'{consulta.frecuencia_cardiaca} lpm')
            )

        if consulta.frecuencia_respiratoria is not None:
            signos.append(
                ('FR', f'{consulta.frecuencia_respiratoria} rpm')
            )

        if consulta.temperatura is not None:
            signos.append(
                ('Temp.', f'{consulta.temperatura} °C')
            )

        if consulta.saturacion_oxigeno is not None:
            signos.append(
                ('SpO₂', f'{consulta.saturacion_oxigeno}%')
            )

        if consulta.peso_kg is not None:
            signos.append(
                ('Peso', f'{consulta.peso_kg} kg')
            )

        if consulta.talla_cm is not None:
            signos.append(
                ('Talla', f'{consulta.talla_cm} cm')
            )

        if signos:
            celdas = []

            for etiqueta, valor in signos:
                celdas.append(
                    Paragraph(
                        '<b>'
                        + limpio(etiqueta)
                        + '</b><br/>'
                        + limpio(valor),
                        estilo_centrado
                    )
                )

            ancho_total = 19.15 * cm
            ancho_columna = ancho_total / len(celdas)

            tabla_signos = Table(
                [celdas],
                colWidths=[
                    ancho_columna
                    for _ in celdas
                ],
            )

            tabla_signos.setStyle(
                TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    (
                        'BACKGROUND',
                        (0, 0),
                        (-1, -1),
                        colors.HexColor('#f4f7fb')
                    ),
                    (
                        'BOX',
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.HexColor('#7b95b7')
                    ),
                    (
                        'INNERGRID',
                        (0, 0),
                        (-1, -1),
                        0.3,
                        colors.HexColor('#aebdd0')
                    ),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ])
            )

            historia.append(
                Spacer(1, 0.05 * cm)
            )
            historia.append(tabla_signos)

        secciones_agregadas += 1

    if incluir_receta:
        if secciones_agregadas:
            historia.append(
                Spacer(1, 0.12 * cm)
            )

        historia.append(
            Paragraph(
                'RECETA MÉDICA',
                estilo_titulo
            )
        )

        if receta and receta.medicamentos.exists():
            encabezados = [
                'Medicamento',
                'Presentación',
                'Dosis',
                'Vía',
                'Frecuencia',
                'Cantidad',
                'Duración',
                'Indicaciones',
            ]

            filas = [[
                Paragraph(
                    '<b>' + titulo + '</b>',
                    estilo_tabla_negrita
                )
                for titulo in encabezados
            ]]

            for medicamento in receta.medicamentos.all():
                via = (
                    medicamento.get_via_display()
                    if medicamento.via
                    else ''
                )

                filas.append([
                    parrafo(
                        medicamento.medicamento,
                        estilo_tabla_negrita
                    ),
                    parrafo(
                        medicamento.presentacion,
                        estilo_tabla
                    ),
                    parrafo(
                        medicamento.dosis,
                        estilo_tabla
                    ),
                    parrafo(
                        via,
                        estilo_tabla
                    ),
                    parrafo(
                        medicamento.frecuencia,
                        estilo_tabla
                    ),
                    parrafo(
                        medicamento.cantidad,
                        estilo_tabla
                    ),
                    parrafo(
                        medicamento.duracion,
                        estilo_tabla
                    ),
                    parrafo(
                        medicamento.indicaciones,
                        estilo_tabla
                    ),
                ])

            tabla_receta = Table(
                filas,
                colWidths=[
                    3.2 * cm,
                    2.45 * cm,
                    2.05 * cm,
                    1.55 * cm,
                    2.2 * cm,
                    1.85 * cm,
                    1.65 * cm,
                    4.2 * cm,
                ],
                repeatRows=1,
            )

            tabla_receta.setStyle(
                TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    (
                        'BACKGROUND',
                        (0, 0),
                        (-1, 0),
                        colors.HexColor('#e9eff6')
                    ),
                    (
                        'BOX',
                        (0, 0),
                        (-1, -1),
                        0.45,
                        colors.HexColor('#7b95b7')
                    ),
                    (
                        'INNERGRID',
                        (0, 0),
                        (-1, -1),
                        0.22,
                        colors.HexColor('#c7d2e0')
                    ),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2.6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2.6),
                    ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ])
            )

            historia.append(tabla_receta)

            if receta.observaciones:
                historia.append(
                    Spacer(1, 0.06 * cm)
                )
                historia.append(
                    Paragraph(
                        '<b>Observaciones:</b> '
                        + limpio(
                            receta.observaciones
                        ),
                        estilo_pequeno
                    )
                )
        else:
            historia.append(
                Paragraph(
                    'No hay medicamentos guardados en esta consulta.',
                    estilo_texto_65
                )
            )

        secciones_agregadas += 1

    if incluir_solicitudes:
        if secciones_agregadas:
            historia.append(
                Spacer(1, 0.12 * cm)
            )

        historia.append(
            Paragraph(
                'SOLICITUD DE ESTUDIOS',
                estilo_titulo
            )
        )

        if solicitudes:
            for numero, solicitud in enumerate(
                solicitudes,
                start=1
            ):
                linea_solicitud = (
                    '<b>Solicitud '
                    + limpio(numero)
                    + ':</b> '
                    + limpio(
                        solicitud.get_tipo_display()
                    )
                    + ' · '
                    + limpio(
                        solicitud.get_prioridad_display()
                    )
                )

                historia.append(
                    Paragraph(
                        linea_solicitud,
                        estilo_texto_65
                    )
                )

                if solicitud.motivo_clinico:
                    historia.append(
                        Paragraph(
                            '<b>Motivo clínico:</b> '
                            + limpio(
                                solicitud.motivo_clinico
                            ),
                            estilo_pequeno
                        )
                    )

                estudios_texto = []

                for estudio_solicitado in (
                    solicitud.estudios_solicitados.all()
                ):
                    item = (
                        '• '
                        + limpio(
                            estudio_solicitado.nombre
                        )
                    )

                    if estudio_solicitado.region_o_detalle:
                        item += (
                            ' — '
                            + limpio(
                                estudio_solicitado.region_o_detalle
                            )
                        )

                    if estudio_solicitado.indicaciones:
                        item += (
                            ' | '
                            + limpio(
                                estudio_solicitado.indicaciones
                            )
                        )

                    estudios_texto.append(item)

                if estudios_texto:
                    historia.append(
                        Paragraph(
                            '<br/>'.join(
                                estudios_texto
                            ),
                            estilo_pequeno
                        )
                    )

                if solicitud.observaciones:
                    historia.append(
                        Paragraph(
                            '<b>Obs.:</b> '
                            + limpio(
                                solicitud.observaciones
                            ),
                            estilo_pequeno
                        )
                    )

                if numero < len(solicitudes):
                    historia.append(
                        Spacer(1, 0.05 * cm)
                    )
        else:
            historia.append(
                Paragraph(
                    'No hay solicitudes de estudio guardadas en esta consulta.',
                    estilo_texto_65
                )
            )

        secciones_agregadas += 1

    if incluir_indicaciones:
        if secciones_agregadas:
            historia.append(
                Spacer(1, 0.12 * cm)
            )

        historia.append(
            Paragraph(
                'INDICACIONES MÉDICAS',
                estilo_titulo
            )
        )

        if indicacion and indicacion.indicaciones:
            historia.append(
                Paragraph(
                    limpio(
                        indicacion.indicaciones
                    ).replace(
                        '\n',
                        '<br/>'
                    ),
                    estilo_texto_65
                )
            )
        else:
            historia.append(
                Paragraph(
                    'No hay indicaciones médicas guardadas en esta consulta.',
                    estilo_texto_65
                )
            )

        secciones_agregadas += 1

    historia.append(
        Spacer(1, 0.18 * cm)
    )

    firma = None

    if perfil_medico:
        firma = imagen_desde_campo(
            perfil_medico.firma,
            3.4 * cm,
            1.05 * cm,
        )

    firma_contenido = []

    if firma:
        firma_contenido.append(firma)
    else:
        firma_contenido.append(
            Spacer(1, 0.75 * cm)
        )

    firma_contenido.extend([
        Paragraph(
            '_______________________________',
            estilo_centrado
        ),
        Paragraph(
            '<b>'
            + limpio(
                obtener_nombre_usuario(
                    medico_documento
                )
            )
            + '</b>',
            estilo_centrado
        ),
    ])

    datos_medico = []

    if perfil_medico and perfil_medico.especialidad:
        datos_medico.append(
            limpio(
                perfil_medico.especialidad
            )
        )

    if perfil_medico and perfil_medico.cedula_profesional:
        datos_medico.append(
            'Céd. Prof. '
            + limpio(
                perfil_medico.cedula_profesional
            )
        )

    if datos_medico:
        firma_contenido.append(
            Paragraph(
                ' | '.join(datos_medico),
                estilo_centrado
            )
        )

    tabla_firma = Table(
        [['', firma_contenido, '']],
        colWidths=[
            5.5 * cm,
            8.15 * cm,
            5.5 * cm,
        ],
    )

    tabla_firma.setStyle(
        TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ])
    )

    historia.append(
        KeepTogether([tabla_firma])
    )

    pie = []

    if institucion.direccion:
        pie.append(
            limpio(institucion.direccion)
        )

    if telefonos:
        pie.append(
            limpio(
                'Tel. ' + ' / '.join(telefonos)
            )
        )

    if institucion.email:
        pie.append(
            limpio(institucion.email)
        )

    if institucion.pie_documentos:
        pie.append(
            limpio(
                institucion.pie_documentos
            )
        )

    if pie:
        historia.append(
            Spacer(1, 0.08 * cm)
        )
        historia.append(
            Paragraph(
                ' · '.join(pie),
                estilo_centrado
            )
        )

    documento.build(historia)

    pdf = buffer.getvalue()
    buffer.close()

    respuesta = HttpResponse(
        pdf,
        content_type='application/pdf'
    )

    respuesta[
        'Content-Disposition'
    ] = (
        f'{response_disposition}; '
        f'filename="{nombre_archivo}"'
    )

    return respuesta


@login_required
def guardar_receta_medica(
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
        observaciones = (
            request.POST.get(
                'observaciones_receta',
                ''
            )
            .strip()
            or None
        )

        receta, _ = (
            RecetaMedica.objects
            .update_or_create(
                consulta=consulta,
                defaults={
                    'medico': request.user,
                    'observaciones': observaciones,
                }
            )
        )

        receta.medicamentos.all().delete()

        medicamentos = request.POST.getlist(
            'medicamento'
        )
        presentaciones = request.POST.getlist(
            'presentacion'
        )
        dosis = request.POST.getlist(
            'dosis'
        )
        vias = request.POST.getlist(
            'via'
        )
        frecuencias = request.POST.getlist(
            'frecuencia'
        )
        cantidades = request.POST.getlist(
            'cantidad'
        )
        duraciones = request.POST.getlist(
            'duracion'
        )
        indicaciones = request.POST.getlist(
            'indicaciones_medicamento'
        )

        for indice, nombre in enumerate(
            medicamentos,
            start=1
        ):
            nombre = nombre.strip()

            if not nombre:
                continue

            def valor_lista(lista, posicion):
                try:
                    valor = lista[posicion].strip()
                except IndexError:
                    return None

                return valor or None

            posicion = indice - 1

            MedicamentoReceta.objects.create(
                receta=receta,
                medicamento=nombre,
                presentacion=valor_lista(
                    presentaciones,
                    posicion
                ),
                dosis=valor_lista(
                    dosis,
                    posicion
                ),
                via=valor_lista(
                    vias,
                    posicion
                ),
                frecuencia=valor_lista(
                    frecuencias,
                    posicion
                ),
                cantidad=valor_lista(
                    cantidades,
                    posicion
                ),
                duracion=valor_lista(
                    duraciones,
                    posicion
                ),
                indicaciones=valor_lista(
                    indicaciones,
                    posicion
                ),
                orden=indice,
            )

    return redirect(
        'detalle_paciente',
        paciente_id=consulta.paciente_id
    )


@login_required
def guardar_indicacion_medica(
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
        indicaciones = (
            request.POST.get(
                'indicaciones_medicas',
                ''
            )
            .strip()
        )

        if indicaciones:
            IndicacionMedica.objects.update_or_create(
                consulta=consulta,
                defaults={
                    'medico': request.user,
                    'indicaciones': indicaciones,
                }
            )
        else:
            IndicacionMedica.objects.filter(
                consulta=consulta
            ).delete()

    return redirect(
        'detalle_paciente',
        paciente_id=consulta.paciente_id
    )


@login_required
def guardar_solicitud_estudio(
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
        tipo = (
            request.POST.get(
                'tipo_solicitud',
                ''
            )
            .strip()
        )

        prioridad = (
            request.POST.get(
                'prioridad_solicitud',
                'RUTINA'
            )
            .strip()
            or 'RUTINA'
        )

        motivo_clinico = (
            request.POST.get(
                'motivo_clinico',
                ''
            )
            .strip()
            or None
        )

        observaciones = (
            request.POST.get(
                'observaciones_solicitud',
                ''
            )
            .strip()
            or None
        )

        tipos_validos = {
            opcion[0]
            for opcion in SolicitudEstudio.TIPO_CHOICES
        }

        prioridades_validas = {
            opcion[0]
            for opcion in SolicitudEstudio.PRIORIDAD_CHOICES
        }

        if tipo in tipos_validos:
            if prioridad not in prioridades_validas:
                prioridad = 'RUTINA'

            nombres = request.POST.getlist(
                'estudio_nombre'
            )
            detalles = request.POST.getlist(
                'estudio_detalle'
            )
            indicaciones = request.POST.getlist(
                'estudio_indicaciones'
            )

            nombres_limpios = [
                nombre.strip()
                for nombre in nombres
                if nombre.strip()
            ]

            if nombres_limpios:
                with transaction.atomic():
                    solicitud = (
                        SolicitudEstudio.objects
                        .create(
                            consulta=consulta,
                            medico=request.user,
                            tipo=tipo,
                            prioridad=prioridad,
                            motivo_clinico=motivo_clinico,
                            observaciones=observaciones,
                        )
                    )

                    for indice, nombre in enumerate(
                        nombres,
                        start=1
                    ):
                        nombre = nombre.strip()

                        if not nombre:
                            continue

                        posicion = indice - 1

                        def valor_lista(lista):
                            try:
                                valor = (
                                    lista[posicion]
                                    .strip()
                                )
                            except IndexError:
                                return None

                            return valor or None

                        EstudioSolicitado.objects.create(
                            solicitud=solicitud,
                            nombre=nombre,
                            region_o_detalle=valor_lista(
                                detalles
                            ),
                            indicaciones=valor_lista(
                                indicaciones
                            ),
                            orden=indice,
                        )

    return redirect(
        'detalle_paciente',
        paciente_id=consulta.paciente_id
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
    membresia = obtener_membresia_usuario(request)

    if membresia is not None:
        if membresia.rol == 'RECEPCION':
            return redirect(
                'panel_recepcion'
            )

        if membresia.rol == 'MEDICO':
            return redirect(
                'panel_medico'
            )

        if membresia.rol in [
            'RADIOLOGIA',
            'TECNICO',
        ]:
            return redirect(
                'panel_radiologo'
            )

        if (
            membresia.rol != 'ADMIN'
            and not request.user.is_superuser
        ):
            return redirect(
                'inicio'
            )

    elif not request.user.is_superuser:
        return redirect(
            'inicio'
        )

    institucion = (
        membresia.institucion
        if membresia is not None
        else None
    )

    guardado = False

    if (
        request.method == 'POST'
        and institucion is not None
    ):
        institucion.nombre = (
            request.POST.get(
                'nombre',
                ''
            )
            .strip()
            or institucion.nombre
        )

        institucion.nombre_comercial = (
            request.POST.get(
                'nombre_comercial',
                ''
            )
            .strip()
            or None
        )

        institucion.rfc = (
            request.POST.get(
                'rfc',
                ''
            )
            .strip()
            .upper()
            or None
        )

        institucion.telefono = (
            request.POST.get(
                'telefono',
                ''
            )
            .strip()
            or None
        )

        institucion.telefono_secundario = (
            request.POST.get(
                'telefono_secundario',
                ''
            )
            .strip()
            or None
        )

        institucion.email = (
            request.POST.get(
                'email',
                ''
            )
            .strip()
            or None
        )

        institucion.direccion = (
            request.POST.get(
                'direccion',
                ''
            )
            .strip()
            or None
        )

        institucion.horarios_servicio = (
            request.POST.get(
                'horarios_servicio',
                ''
            )
            .strip()
            or None
        )

        institucion.pie_documentos = (
            request.POST.get(
                'pie_documentos',
                ''
            )
            .strip()
            or None
        )

        logo = request.FILES.get(
            'logo'
        )

        if logo:
            institucion.logo = logo

        if request.POST.get(
            'eliminar_logo'
        ) == '1':
            if institucion.logo:
                institucion.logo.delete(
                    save=False
                )

            institucion.logo = None

        institucion.save()

        guardado = True

    context = {
        'membresia': membresia,
        'institucion': institucion,
        'guardado': guardado,
    }

    return render(
        request,
        'core/panel_config.html',
        context
    )


@login_required
def catalogo_servicios(request):
    membresia = obtener_membresia_usuario(request)

    if not puede_administrar_configuracion(
        request,
        membresia
    ):
        return redirect('panel_config')

    institucion = (
        membresia.institucion
        if membresia is not None
        else None
    )

    if institucion is None:
        messages.warning(
            request,
            'Tu usuario no tiene una institución asociada.'
        )
        return redirect('panel_config')

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    tipo = request.GET.get(
        'tipo',
        ''
    ).strip()

    estado = request.GET.get(
        'estado',
        ''
    ).strip()

    servicios = (
        Servicio.objects
        .filter(institucion=institucion)
        .select_related(
            'institucion',
            'tipo_estudio',
        )
    )

    if busqueda:
        servicios = servicios.filter(
            Q(nombre__icontains=busqueda)
            | Q(tipo_estudio__codigo__icontains=busqueda)
            | Q(tipo_estudio__nombre__icontains=busqueda)
        )

    tipos_validos = {
        valor
        for valor, etiqueta
        in Servicio.TIPO_CHOICES
    }

    if tipo in tipos_validos:
        servicios = servicios.filter(tipo=tipo)

    if estado == 'ACTIVOS':
        servicios = servicios.filter(activo=True)
    elif estado == 'INACTIVOS':
        servicios = servicios.filter(activo=False)

    servicios = servicios.order_by(
        'tipo',
        'nombre',
    )

    paginador = Paginator(
        servicios,
        50
    )

    pagina = paginador.get_page(
        request.GET.get('pagina')
    )

    servicio_edicion = None
    servicio_edicion_id = request.GET.get(
        'editar'
    )

    if servicio_edicion_id:
        servicio_edicion = get_object_or_404(
            Servicio,
            pk=servicio_edicion_id,
            institucion=institucion,
        )

    resumen = {
        'total': Servicio.objects.filter(
            institucion=institucion
        ).count(),
        'activos': Servicio.objects.filter(
            institucion=institucion,
            activo=True,
        ).count(),
        'inactivos': Servicio.objects.filter(
            institucion=institucion,
            activo=False,
        ).count(),
    }

    context = {
        'membresia': membresia,
        'institucion': institucion,
        'pagina': pagina,
        'resumen': resumen,
        'busqueda': busqueda,
        'tipo_seleccionado': tipo,
        'estado_seleccionado': estado,
        'tipos_servicio': Servicio.TIPO_CHOICES,
        'tipos_estudio': TipoEstudio.objects.filter(
            activo=True
        ).order_by(
            'modalidad',
            'nombre',
        ),
        'servicio_edicion': servicio_edicion,
    }

    return render(
        request,
        'core/catalogo_servicios.html',
        context
    )


@login_required
def guardar_servicio(
    request,
    servicio_id=None
):
    if request.method != 'POST':
        return redirect('catalogo_servicios')

    membresia = obtener_membresia_usuario(request)

    if not puede_administrar_configuracion(
        request,
        membresia
    ):
        return redirect('panel_config')

    institucion = (
        membresia.institucion
        if membresia is not None
        else None
    )

    if institucion is None:
        messages.warning(
            request,
            'Tu usuario no tiene una institución asociada.'
        )
        return redirect('panel_config')

    servicio = None

    if servicio_id is not None:
        servicio = get_object_or_404(
            Servicio,
            pk=servicio_id,
            institucion=institucion,
        )

    nombre = request.POST.get(
        'nombre',
        ''
    ).strip()

    tipo = request.POST.get(
        'tipo',
        'OTRO'
    ).strip()

    precio_texto = request.POST.get(
        'precio_base',
        '0'
    ).strip()

    tipo_estudio_id = request.POST.get(
        'tipo_estudio',
        ''
    ).strip()

    tipos_validos = {
        valor
        for valor, etiqueta
        in Servicio.TIPO_CHOICES
    }

    errores = []

    if not nombre:
        errores.append(
            'Escribe el nombre del servicio.'
        )

    if tipo not in tipos_validos:
        errores.append(
            'Selecciona un tipo de servicio válido.'
        )

    try:
        precio_base = Decimal(precio_texto)

        if precio_base < 0:
            raise InvalidOperation

        if precio_base > Decimal('9999999999.99'):
            raise InvalidOperation

        precio_base = precio_base.quantize(
            Decimal('0.01')
        )
    except (InvalidOperation, ValueError):
        precio_base = Decimal('0.00')
        errores.append(
            'Escribe un precio válido mayor o igual a cero.'
        )

    tipo_estudio = None

    if tipo_estudio_id:
        tipo_estudio = TipoEstudio.objects.filter(
            pk=tipo_estudio_id,
            activo=True,
        ).first()

        if tipo_estudio is None:
            errores.append(
                'El tipo de estudio seleccionado no es válido.'
            )

    if errores:
        for error in errores:
            messages.error(
                request,
                error
            )

        return redirect('catalogo_servicios')

    if servicio is None:
        servicio = Servicio(
            institucion=institucion
        )

    servicio.nombre = nombre
    servicio.tipo = tipo
    servicio.tipo_estudio = tipo_estudio
    servicio.precio_base = precio_base
    servicio.precio_editable = (
        request.POST.get('precio_editable') == '1'
    )
    servicio.activo = (
        request.POST.get('activo') == '1'
    )
    servicio.save()

    messages.success(
        request,
        (
            'Servicio actualizado correctamente.'
            if servicio_id is not None
            else 'Servicio creado correctamente.'
        )
    )

    return redirect('catalogo_servicios')


@login_required
def cambiar_estado_servicio(
    request,
    servicio_id
):
    if request.method != 'POST':
        return redirect('catalogo_servicios')

    membresia = obtener_membresia_usuario(request)

    if not puede_administrar_configuracion(
        request,
        membresia
    ):
        return redirect('panel_config')

    institucion = (
        membresia.institucion
        if membresia is not None
        else None
    )

    if institucion is None:
        return redirect('panel_config')

    servicio = get_object_or_404(
        Servicio,
        pk=servicio_id,
        institucion=institucion,
    )

    servicio.activo = not servicio.activo
    servicio.save(
        update_fields=[
            'activo',
            'actualizado_el',
        ]
    )

    messages.success(
        request,
        (
            'Servicio activado correctamente.'
            if servicio.activo
            else 'Servicio desactivado correctamente.'
        )
    )

    return redirect('catalogo_servicios')


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
