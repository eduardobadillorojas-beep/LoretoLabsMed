"""Administración global de instituciones; no contiene vistas clínicas."""
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import Institucion, MembresiaInstitucion


class AltaInstitucionForm(forms.ModelForm):
    admin_usuario = forms.CharField(max_length=150, label='Usuario del administrador')
    admin_password = forms.CharField(widget=forms.PasswordInput, min_length=12, label='Contraseña inicial (mínimo 12 caracteres)')
    admin_email = forms.EmailField(required=False, label='Correo del administrador')

    class Meta:
        model = Institucion
        fields = ['nombre', 'nombre_comercial', 'rfc', 'telefono', 'email', 'direccion', 'telefono_secundario', 'horarios_servicio', 'pie_documentos']
        widgets = {'direccion': forms.Textarea(attrs={'rows': 2}), 'horarios_servicio': forms.Textarea(attrs={'rows': 2}), 'pie_documentos': forms.Textarea(attrs={'rows': 2})}

    def clean_admin_usuario(self):
        username = self.cleaned_data['admin_usuario'].strip()
        User = get_user_model()
        if User.objects.filter(**{User.USERNAME_FIELD: username}).exists():
            raise forms.ValidationError('El usuario ya existe. Elige uno nuevo.')
        return username


    def clean_admin_password(self):
        password = self.cleaned_data['admin_password']
        validate_password(password)
        return password


@login_required
@require_http_methods(['GET', 'POST'])
def instituciones_plataforma(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Acceso exclusivo de administración general.')

    form = AltaInstitucionForm(request.POST or None)
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'crear':
            if form.is_valid():
                with transaction.atomic():
                    institucion = form.save(commit=False)
                    institucion.activa = False  # No habilitar hasta auditar aislamiento entre instituciones
                    institucion.save()
                    User = get_user_model()
                    kwargs = {User.USERNAME_FIELD: form.cleaned_data['admin_usuario'], 'password': form.cleaned_data['admin_password']}
                    if 'email' in [f.name for f in User._meta.fields]:
                        kwargs['email'] = form.cleaned_data['admin_email']
                    usuario = User.objects.create_user(**kwargs)
                    MembresiaInstitucion.objects.create(institucion=institucion, usuario=usuario, rol='ADMIN', activa=True)
                messages.success(request, 'Institución y administrador creados. Institución inactiva hasta la auditoría de seguridad.')
                return redirect('instituciones_plataforma')
        elif accion == 'desactivar':
            return HttpResponseForbidden(
                'La desactivaci?n est? temporalmente bloqueada '
                'hasta implementar la protecci?n de instituciones existentes.'
            )
        else:
            return HttpResponseForbidden('Acción no permitida. La activación requiere una auditoría previa.')

    instituciones = Institucion.objects.all().order_by('nombre').prefetch_related('membresias__usuario')
    return render(request, 'core/plataforma_instituciones.html', {'form': form, 'instituciones': instituciones})
