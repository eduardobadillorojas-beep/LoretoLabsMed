from django.shortcuts import render
from pacientes.models import Paciente

def recepcion_dashboard(request):
    query = request.GET.get('q', '')
    if query:
        pacientes = Paciente.objects.filter(nombre__icontains=query) | Paciente.objects.filter(apellidos__icontains=query)
    else:
        pacientes = Paciente.objects.all()[:10]  # Muestra los últimos 10 por defecto

    return render(request, 'recepcion/dashboard.html', {'pacientes': pacientes, 'query': query})