from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Cita,
    Consulta,
    Estudio,
    Paciente,
    TipoEstudio,
)


class PacienteForm(forms.ModelForm):
    class Meta:
        model = Paciente

        fields = [
            'nombre',
            'apellido',
            'genero',
            'fecha_nacimiento',
            'telefono',
        ]

        widgets = {
            'nombre': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nombre',
                    'autocomplete': 'given-name',
                }
            ),
            'apellido': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Apellidos',
                    'autocomplete': 'family-name',
                }
            ),
            'genero': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),
            'fecha_nacimiento': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                }
            ),
            'telefono': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Teléfono',
                    'autocomplete': 'tel',
                }
            ),
        }


class DestinoAtencionForm(forms.Form):
    TIPO_ATENCION_CHOICES = [
        ('CONSULTA', 'Consulta médica'),
        ('RADIOLOGIA', 'Radiología e imagen'),
    ]

    tipo_atencion = forms.ChoiceField(
        label='¿A qué área será enviado el paciente?',
        choices=TIPO_ATENCION_CHOICES,
        widget=forms.Select(
            attrs={
                'class': 'form-select',
                'id': 'id_tipo_atencion',
            }
        )
    )


class ConsultaForm(forms.ModelForm):
    class Meta:
        model = Consulta

        fields = [
            'motivo_consulta',
        ]

        widgets = {
            'motivo_consulta': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': (
                        'Ej. Dolor abdominal, fiebre, '
                        'consulta general o seguimiento'
                    ),
                }
            ),
        }


class EstudioForm(forms.ModelForm):

    tipo_estudio = forms.ModelChoiceField(
        label='Tipo de estudio',
        queryset=TipoEstudio.objects.none(),
        empty_label='Selecciona un estudio',
        widget=forms.Select(
            attrs={
                'class': 'form-select',
            }
        )
    )

    class Meta:
        model = Estudio

        fields = [
            'medico_solicitante',
            'tipo_estudio',
            'descripcion',
            'estado',
        ]

        widgets = {
            'medico_solicitante': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej. Dr. José Martínez López',
                }
            ),
            'descripcion': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': (
                        'Diagnóstico presuntivo, indicaciones '
                        'u observaciones del estudio'
                    ),
                }
            ),
            'estado': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['tipo_estudio'].queryset = (
            TipoEstudio.objects
            .filter(activo=True)
            .order_by('modalidad', 'nombre')
        )


class CitaForm(forms.ModelForm):

    tipo_estudio = forms.ModelChoiceField(
        label='Estudio programado',
        queryset=TipoEstudio.objects.none(),
        required=False,
        empty_label='Selecciona un estudio',
        widget=forms.Select(
            attrs={
                'class': 'form-select',
                'id': 'id_tipo_estudio',
            }
        )
    )

    fecha_hora = forms.DateTimeField(
        label='Fecha y hora',
        input_formats=[
            '%Y-%m-%dT%H:%M',
        ],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={
                'type': 'datetime-local',
                'class': 'form-control',
            }
        )
    )

    class Meta:
        model = Cita

        fields = [
            'nombre_paciente',
            'telefono',
            'area',
            'medico_nombre',
            'tipo_estudio',
            'fecha_hora',
            'duracion_minutos',
            'motivo',
            'observaciones',
            'estado',
        ]

        widgets = {

            'nombre_paciente': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej. María López Hernández',
                    'autocomplete': 'name',
                }
            ),

            'telefono': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej. 449 123 4567',
                    'autocomplete': 'tel',
                }
            ),

            'area': forms.Select(
                attrs={
                    'class': 'form-select',
                    'id': 'id_area',
                }
            ),

            'medico_nombre': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej. Dr. Carlos Hernández',
                }
            ),

            'duracion_minutos': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': 5,
                    'step': 5,
                }
            ),

            'motivo': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': (
                        'Ej. Consulta de seguimiento, '
                        'dolor de rodilla, revisión de fractura...'
                    ),
                }
            ),

            'observaciones': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': (
                        'Notas internas para Recepción, '
                        'Médicos o Radiología'
                    ),
                }
            ),

            'estado': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),
        }

        labels = {
            'nombre_paciente': 'Nombre del paciente',
            'telefono': 'Teléfono',
            'area': 'Área de atención',
            'medico_nombre': 'Médico o responsable',
            'duracion_minutos': 'Duración estimada',
            'motivo': 'Motivo de la cita',
            'observaciones': 'Observaciones',
            'estado': 'Estado',
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['tipo_estudio'].queryset = (
            TipoEstudio.objects
            .filter(activo=True)
            .order_by('modalidad', 'nombre')
        )

        self.fields['duracion_minutos'].initial = 30
        self.fields['estado'].initial = 'PROGRAMADA'


    def clean_fecha_hora(self):
        fecha_hora = self.cleaned_data.get('fecha_hora')

        if fecha_hora and fecha_hora < timezone.now():
            raise ValidationError(
                'La fecha y hora de la cita no puede estar en el pasado.'
            )

        return fecha_hora


    def clean(self):
        cleaned_data = super().clean()

        area = cleaned_data.get('area')
        tipo_estudio = cleaned_data.get('tipo_estudio')
        duracion_minutos = cleaned_data.get('duracion_minutos')

        # Radiología requiere especificar el estudio.
        if area == 'RADIOLOGIA' and not tipo_estudio:
            self.add_error(
                'tipo_estudio',
                'Selecciona el estudio que será programado.'
            )

        # Las demás especialidades no necesitan un estudio
        # radiológico al momento de crear la cita.
        if area != 'RADIOLOGIA':
            cleaned_data['tipo_estudio'] = None

        if duracion_minutos is not None:

            if duracion_minutos < 5:
                self.add_error(
                    'duracion_minutos',
                    'La duración mínima es de 5 minutos.'
                )

            if duracion_minutos > 480:
                self.add_error(
                    'duracion_minutos',
                    'La duración máxima permitida es de 480 minutos.'
                )

        return cleaned_data