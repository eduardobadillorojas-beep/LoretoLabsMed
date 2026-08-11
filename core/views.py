from datetime import date
from pathlib import Path

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
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


# =========================================================
# UTILIDADES
# =========================================================

def obtener_institucion_usuario(request):
    membresia = (
        MembresiaInstitucion.objects
        .select_related('institucion')
        .filter(
            usuario=request.user,
            activa=True,
            institucion__activa=True,
        )
        .first()
    )

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
            estado='EN_ESPERA'
        )
        .order_by(
            'fecha_llegada'
        )
    )

    citas_medicas_hoy = (
        Cita.objects
        .select_related(
            'tipo_estudio'
        )
        .filter(
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
            'tipo_estudio'
        )
        .filter(
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
        )
    )

    context = {
        'consultas_en_espera':
            consultas_en_espera,

        'citas_medicas_hoy':
            citas_medicas_hoy,

        'proximas_citas_medicas':
            proximas_citas_medicas,
    }

    return render(
        request,
        'core/panel_medico.html',
        context
    )


# =========================================================
# PANEL RADIOLOGÍA
# =========================================================

@login_required
def panel_radiologo(request):
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
            estado='PENDIENTE'
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
            estado='EN_PROCESO'
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

    context = {
        'estudios_pendientes':
            estudios_pendientes,

        'estudios_en_proceso':
            estudios_en_proceso,

        'estudios_realizados_hoy':
            estudios_realizados_hoy,

        'citas_radiologia_hoy':
            citas_radiologia_hoy,
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
    estudio = get_object_or_404(
        Estudio.objects.select_related(
            'paciente',
            'tipo_estudio',
            'tecnico',
            'equipo',
        ),
        pk=estudio_id
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

    context = {
        'estudio': estudio,
        'paciente': estudio.paciente,
        'archivos': archivos,
        'antecedentes': antecedentes,
        'edad': edad,
    }

    return render(
        request,
        'core/estudio_radiologia.html',
        context
    )


# =========================================================
# INICIAR ESTUDIO
# =========================================================

@login_required
def iniciar_estudio_radiologia(
    request,
    estudio_id
):
    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id
    )

    if request.method == 'POST':

        if estudio.estado == 'PENDIENTE':

            estudio.estado = (
                'EN_PROCESO'
            )

            estudio.fecha_inicio = (
                timezone.now()
            )

            estudio.tecnico = (
                request.user
            )

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
    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id
    )

    if request.method == 'POST':

        archivos = (
            request.FILES.getlist(
                'archivos'
            )
        )

        if estudio.estado == 'PENDIENTE':

            estudio.estado = (
                'EN_PROCESO'
            )

            estudio.fecha_inicio = (
                timezone.now()
            )

            estudio.tecnico = (
                request.user
            )

            estudio.save(
                update_fields=[
                    'estado',
                    'fecha_inicio',
                    'tecnico',
                ]
            )

        for archivo in archivos:

            ArchivoEstudio.objects.create(
                estudio=estudio,
                archivo=archivo,
                tipo_archivo=(
                    detectar_tipo_archivo(
                        archivo.name
                    )
                ),
                nombre_original=(
                    archivo.name
                ),
                subido_por=request.user
            )

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
    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id
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
# FINALIZAR ESTUDIO
# =========================================================

@login_required
def finalizar_estudio_radiologia(
    request,
    estudio_id
):
    estudio = get_object_or_404(
        Estudio.objects.select_related(
            'paciente',
            'tipo_estudio',
            'tecnico',
            'equipo',
        ),
        pk=estudio_id
    )

    if request.method == 'POST':

        momento_actual = (
            timezone.now()
        )

        if not estudio.fecha_inicio:
            estudio.fecha_inicio = (
                momento_actual
            )

        if not estudio.tecnico:
            estudio.tecnico = (
                request.user
            )

        estudio.estado = (
            'COMPLETADO'
        )

        estudio.fecha_finalizacion = (
            momento_actual
        )

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
    ahora = timezone.now()

    institucion = obtener_institucion_usuario(request)

    if institucion is None:
        return redirect('panel_config')

    pacientes = (
        Paciente.objects
        .filter(
            institucion=institucion
        )
        .order_by(
            '-creado_el'
        )
    )

    if busqueda:
        pacientes = pacientes.filter(
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

    pacientes_de_hoy = (
        Paciente.objects
        .filter(
            institucion=institucion,
            creado_el__date=hoy
        )
        .order_by(
            '-creado_el'
        )
    )

    pacientes_hoy = (
        pacientes_de_hoy.count()
    )

    consultas_en_espera_lista = (
        Consulta.objects
        .select_related(
            'paciente',
            'medico',
        )
        .filter(
            paciente__institucion=institucion,
            estado='EN_ESPERA'
        )
        .order_by(
            'fecha_llegada'
        )
    )

    consultas_espera = (
        consultas_en_espera_lista.count()
    )

    estudios_pendientes_lista = (
        Estudio.objects
        .select_related(
            'paciente',
            'tipo_estudio',
        )
        .filter(
            paciente__institucion=institucion,
            estado='PENDIENTE'
        )
        .order_by(
            'fecha_creacion'
        )
    )

    estudios_pendientes = (
        estudios_pendientes_lista.count()
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

    proximas_citas = (
        Cita.objects
        .select_related(
            'tipo_estudio'
        )
        .filter(
            institucion=institucion,
            fecha_hora__gte=ahora
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

        'consultas_espera':
            consultas_espera,

        'consultas_en_espera_lista':
            consultas_en_espera_lista,

        'estudios_pendientes':
            estudios_pendientes,

        'estudios_pendientes_lista':
            estudios_pendientes_lista,

        'citas_de_hoy':
            citas_de_hoy,

        'proximas_citas':
            proximas_citas,
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
def detalle_paciente(
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

    estudios = (
        paciente.estudios
        .select_related(
            'tipo_estudio'
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

    hoy = date.today()

    edad = calcular_edad(
        paciente.fecha_nacimiento,
        hoy
    )

    context = {
        'paciente':
            paciente,

        'estudios':
            estudios,

        'consultas':
            consultas,

        'citas':
            citas,

        'edad':
            edad,
    }

    return render(
        request,
        'core/detalle_paciente.html',
        context
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