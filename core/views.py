from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import Paciente, Estudio

def inicio(request):
    return render(request, 'core/inicio.html')

def login_view(request):
    error_message = None
    if request.method == 'POST':
        usuario = request.POST.get('username')
        clave = request.POST.get('password')
        
        user = authenticate(request, username=usuario, password=clave)
        
        if user is not None:
            login(request, user)
            
            # Redirección según el rol/grupo del usuario
            if user.groups.filter(name='Médico').exists():
                return redirect('panel_medico')
            elif user.groups.filter(name='Radiólogo').exists():
                return redirect('panel_radiologo')
            elif user.groups.filter(name='Recepción').exists():
                return redirect('panel_recepcion')
            else:
                return redirect('panel_config') # Para admins o usuarios sin grupo
        else:
            error_message = "Usuario o contraseña incorrectos"

    return render(request, 'core/login.html', {'error': error_message})

def logout_view(request):
    logout(request)
    return redirect('inicio')

@login_required
def panel_medico(request):
    estudios = Estudio.objects.select_related('paciente').all().order_by('-fecha_creacion')
    return render(request, 'core/panel_medico.html', {'estudios': estudios})

@login_required
def panel_radiologo(request):
    return render(request, 'core/panel_radiologo.html')

@login_required
def panel_recepcion(request):
    return render(request, 'core/panel_recepcion.html')

@login_required
def panel_config(request):
    return render(request, 'core/panel_config.html')