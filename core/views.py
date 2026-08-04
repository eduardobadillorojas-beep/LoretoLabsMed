from datetime import date

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import EstudioForm, PacienteForm
from .models import Estudio, Paciente


def inicio(request):
    return render(request, 'core/inicio.html')


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
            login(request, user)

            if user.groups.filter(name='Médico').exists():
                return redirect('panel_medico')

            if user.groups.filter(name='Radiólogo').exists():
                return redirect('panel_radiologo')

            if user.groups.filter(name='Recepción').exists():
                return redirect('panel_recepcion')

            return redirect('panel_config')

        error_message = 'Usuario o contraseña incorrectos'

    return render(
        request,
        'core/login.html',
        {'error': error_message}
    )


def logout_view(request):
    logout(request)
    return redirect('inicio')


@login_required
def panel_medico(request):
    estudios = (
        Estudio.objects
        .select_related('paciente')
        .all()
        .order_by('-fecha_creacion')
    )

    return render(
        request,
        'core/panel_medico.html',
        {'estudios': estudios}
    )


@login_required
def panel_radiologo(request):
    return render(request, 'core/panel_radiologo.html')


@login_required
def panel_recepcion(request):
    busqueda = request.GET.get('buscar', '').strip()

    pacientes = Paciente.objects.all().order_by('-creado_el')

    if busqueda:
        pacientes = pacientes.filter(
            Q(identificacion__icontains=busqueda)
            | Q(nombre__icontains=busqueda)
            | Q(apellido__icontains=busqueda)
            | Q(telefono__icontains=busqueda)
        )

    context = {
        'pacientes': pacientes,
        'busqueda': busqueda,
    }

    return render(
        request,
        'core/panel_recepcion.html',
        context
    )


@login_required
def detalle_paciente(request, paciente_id):
    paciente = get_object_or_404(Paciente, pk=paciente_id)

    estudios = (
        paciente.estudios
        .all()
        .order_by('-fecha_creacion')
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
        'paciente': paciente,
        'estudios': estudios,
        'edad': edad,
    }

    return render(
        request,
        'core/detalle_paciente.html',
        context
    )


@login_required
def panel_config(request):
    return render(request, 'core/panel_config.html')


@login_required
def registrar_estudio_recepcion(request):
    if request.method == 'POST':
        paciente_form = PacienteForm(request.POST)
        estudio_form = EstudioForm(request.POST)

        if paciente_form.is_valid() and estudio_form.is_valid():
            with transaction.atomic():
                paciente = paciente_form.save()

                estudio = estudio_form.save(commit=False)
                estudio.paciente = paciente
                estudio.save()

            return redirect(
                'detalle_paciente',
                paciente_id=paciente.id
            )

    else:
        paciente_form = PacienteForm()
        estudio_form = EstudioForm()

    context = {
        'paciente_form': paciente_form,
        'estudio_form': estudio_form,
    }

    return render(
        request,
        'core/registrar_recepcion.html',
        context
    )