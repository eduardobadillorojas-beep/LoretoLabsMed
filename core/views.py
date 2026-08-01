from django.shortcuts import render, redirect

def inicio(request):
    return render(request, 'core/inicio.html')

def login_view(request):
    if request.method == 'POST':
        # Por ahora redirigimos al menú principal de paneles
        return redirect('inicio')
    return render(request, 'core/login.html')

# Paneles
def panel_medico(request):
    return render(request, 'core/panel_medico.html')

def panel_radiologo(request):
    return render(request, 'core/panel_radiologo.html')

def panel_recepcion(request):
    return render(request, 'core/panel_recepcion.html')

def panel_config(request):
    return render(request, 'core/panel_config.html')