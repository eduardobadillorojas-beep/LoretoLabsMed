from datetime import date

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
    Cita,
    Consulta,
    Estudio,
    Paciente,
    SesionTrabajo,
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


def inicio(request):
    return render(
        request,
        'core/inicio.html'
    )


def login_view(request):
    error_message = None

    if request.method == 'POST':
        usuario = request.POST.get('username')
        clave = request.POST.get('password')

        user = authenticate(
            request,
            username=usuario,
            password=clave
        )

        if user is not None:

            # Cerrar sesiones anteriores que hayan quedado abiertas.
            sesiones_anteriores = SesionTrabajo.objects.filter(
                usuario=user,
                activa=True
            )

            momento_actual = timezone.now()

            sesiones_anteriores.update(
                activa=False,
                fin=momento_actual
            )

            # Iniciar sesión de Django.
            login(
                request,
                user
            )

            # Crear nuevo turno / sesión de trabajo.
            sesion_trabajo = SesionTrabajo.objects.create(
                usuario=user,
                ip_inicio=obtener_ip(request),
                user_agent=request.META.get(
                    'HTTP_USER_AGENT',
                    ''
                ),
                activa=True
            )

            # Guardamos el ID en la sesión de Django.
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


@login_required
def logout_view(request):

    momento_actual = timezone.now()

    sesion_trabajo_id = request.session.get(
        'sesion_trabajo_id'
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
        sesion_trabajo.fin = momento_actual
        sesion_trabajo.ultima_actividad = momento_actual
        sesion_trabajo.activa = False
        sesion_trabajo.ip_fin = obtener_ip(request)

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


@login_required
def panel_radiologo(request):
    hoy = timezone.localdate()

    estudios_pendientes = (
        Estudio.objects
        .select_related(
            'paciente',
            'consulta',
            'tipo_estudio',
        )
        .filter(
            estado='PENDIENTE'
        )
        .order_by(
            'fecha_creacion'
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

    proximas_citas_radiologia = (
        Cita.objects
        .select_related(
            'tipo_estudio'
        )
        .filter(
            area='RADIOLOGIA',
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
        'estudios_pendientes':
            estudios_pendientes,

        'citas_radiologia_hoy':
            citas_radiologia_hoy,

        'proximas_citas_radiologia':
            proximas_citas_radiologia,
    }

    return render(
        request,
        'core/panel_radiologo.html',
        context
    )


@login_required
def panel_recepcion(request):
    busqueda = request.GET.get(
        'buscar',
        ''
    ).strip()

    hoy = timezone.localdate()
    ahora = timezone.now()

    pacientes = (
        Paciente.objects
        .all()
        .order_by(
            '-creado_el'
        )
    )

    if busqueda:
        pacientes = pacientes.filter(
            Q(
                identificacion__icontains=busqueda
            )
            | Q(
                nombre__icontains=busqueda
            )
            | Q(
                apellido__icontains=busqueda
            )
            | Q(
                telefono__icontains=busqueda
            )
        )

    pacientes_de_hoy = (
        Paciente.objects
        .filter(
            creado_el__date=hoy
        )
        .order_by(
            '-creado_el'
        )
    )

    pacientes_hoy = (
        pacientes_de_hoy.count()
    )

    consultas_espera = (
        Consulta.objects
        .filter(
            estado='EN_ESPERA'
        )
        .count()
    )

    estudios_pendientes = (
        Estudio.objects
        .filter(
            estado='PENDIENTE'
        )
        .count()
    )

    citas_hoy = (
        Cita.objects
        .filter(
            fecha_hora__date=hoy
        )
        .exclude(
            estado__in=[
                'CANCELADA',
                'NO_ASISTIO',
            ]
        )
        .count()
    )

    proximas_citas = (
        Cita.objects
        .select_related(
            'tipo_estudio'
        )
        .filter(
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

        'estudios_pendientes':
            estudios_pendientes,

        'proximas_citas':
            proximas_citas,
    }

    return render(
        request,
        'core/panel_recepcion.html',
        context
    )


@login_required
def nueva_cita(request):

    if request.method == 'POST':

        cita_form = CitaForm(
            request.POST
        )

        if cita_form.is_valid():

            cita = cita_form.save(
                commit=False
            )

            cita.creada_por = request.user
            cita.save()

            return redirect(
                'panel_recepcion'
            )

    else:

        cita_form = CitaForm(
            initial={
                'estado': 'PROGRAMADA',
                'duracion_minutos': 30,
            }
        )

    context = {
        'cita_form': cita_form,
    }

    return render(
        request,
        'core/nueva_cita.html',
        context
    )


@login_required
def detalle_paciente(
    request,
    paciente_id
):

    paciente = get_object_or_404(
        Paciente,
        pk=paciente_id
    )

    estudios = (
        paciente.estudios
        .select_related(
            'tipo_estudio'
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

    edad = (
        hoy.year
        - paciente.fecha_nacimiento.year
        - (
            (hoy.month, hoy.day)
            < (
                paciente.fecha_nacimiento.month,
                paciente.fecha_nacimiento.day,
            )
        )
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


@login_required
def nuevo_estudio_paciente(
    request,
    paciente_id
):

    paciente = get_object_or_404(
        Paciente,
        pk=paciente_id
    )

    if request.method == 'POST':

        estudio_form = EstudioForm(
            request.POST
        )

        if estudio_form.is_valid():

            estudio = estudio_form.save(
                commit=False
            )

            estudio.paciente = paciente
            estudio.save()

            return redirect(
                'detalle_paciente',
                paciente_id=paciente.id
            )

    else:

        estudio_form = EstudioForm(
            initial={
                'estado': 'PENDIENTE',
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


@login_required
def panel_config(request):

    return render(
        request,
        'core/panel_config.html'
    )


@login_required
def registrar_estudio_recepcion(request):

    if request.method == 'POST':

        paciente_form = PacienteForm(
            request.POST
        )

        destino_form = DestinoAtencionForm(
            request.POST
        )

        consulta_form = ConsultaForm(
            request.POST
        )

        estudio_form = EstudioForm(
            request.POST
        )

        formularios_principales_validos = (
            paciente_form.is_valid()
            and destino_form.is_valid()
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
                        paciente_form.save()
                    )

                    if tipo_atencion == 'CONSULTA':

                        consulta = (
                            consulta_form.save(
                                commit=False
                            )
                        )

                        consulta.paciente = paciente
                        consulta.estado = 'EN_ESPERA'

                        consulta.save()

                    elif tipo_atencion == 'RADIOLOGIA':

                        estudio = (
                            estudio_form.save(
                                commit=False
                            )
                        )

                        estudio.paciente = paciente
                        estudio.estado = 'PENDIENTE'

                        estudio.save()

                return redirect(
                    'detalle_paciente',
                    paciente_id=paciente.id
                )

    else:

        paciente_form = PacienteForm()

        destino_form = DestinoAtencionForm(
            initial={
                'tipo_atencion':
                    'CONSULTA',
            }
        )

        consulta_form = ConsultaForm()

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