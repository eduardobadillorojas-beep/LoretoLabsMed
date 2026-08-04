from django import forms
from .models import Paciente, Estudio


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
                }
            ),
            'apellido': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Apellido',
                }
            ),
            'genero': forms.Select(
                attrs={
                    'class': 'form-control',
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
                }
            ),
        }


class EstudioForm(forms.ModelForm):
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
            'tipo_estudio': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej. RX de tórax PA',
                }
            ),
            'descripcion': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Diagnóstico u observaciones',
                }
            ),
            'estado': forms.Select(
                attrs={
                    'class': 'form-control',
                }
            ),
        }