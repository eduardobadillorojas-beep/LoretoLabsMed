from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .models import MembresiaInstitucion


CLAVE_INSTITUCION_SESION = 'institucion_activa_id'


def membresias_disponibles(usuario):
    if not usuario.is_authenticated:
        return MembresiaInstitucion.objects.none()

    return (
        MembresiaInstitucion.objects
        .select_related('institucion')
        .filter(
            usuario=usuario,
            activa=True,
            institucion__activa=True,
        )
        .order_by('institucion__nombre', 'pk')
    )


def membresia_activa(request):
    membresias = membresias_disponibles(request.user)

    institucion_id = request.session.get(
        CLAVE_INSTITUCION_SESION
    )

    if institucion_id is not None:
        membresia = membresias.filter(
            institucion_id=institucion_id
        ).first()

        if membresia:
            return membresia

        request.session.pop(
            CLAVE_INSTITUCION_SESION,
            None
        )

        return None

    primeras = list(membresias[:2])

    if len(primeras) == 1:
        membresia = primeras[0]
        request.session[
            CLAVE_INSTITUCION_SESION
        ] = membresia.institucion_id
        return membresia

    return None


@login_required
@require_http_methods(['GET', 'POST'])
def seleccionar_institucion(request):
    membresias = membresias_disponibles(request.user)

    if request.method == 'POST':
        institucion_id = request.POST.get('institucion_id')

        membresia = membresias.filter(
            institucion_id=institucion_id
        ).first()

        if not membresia:
            return HttpResponseForbidden(
                'No tienes acceso a esta institución.'
            )

        request.session[
            CLAVE_INSTITUCION_SESION
        ] = membresia.institucion_id

        return redirect('inicio')

    return render(
        request,
        'core/seleccionar_institucion.html',
        {
            'membresias': membresias,
        }
    )
