from django import forms
from .models import Paciente, Estudio

class PacienteForm(forms.ModelForm):
    class Meta:
        model = Paciente
        fields = ['identificacion', 'nombre', 'apellido', 'genero', 'fecha_nacimiento']
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'identificacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cédula o ID'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellido'}),
            'genero': forms.Select(attrs={'class': 'form-control'}),
        }

class EstudioForm(forms.ModelForm):
    class Meta:
        model = Estudio
        fields = ['paciente', 'medico_solicitante', 'tipo_estudio', 'descripcion', 'estado']
        widgets = {
            'paciente': forms.Select(attrs={'class': 'form-control'}),
            'medico_solicitante': forms.Select(attrs={'class': 'form-control'}),
            'tipo_estudio': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. RX Tórax'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Observaciones'}),
            'estado': forms.Select(attrs={'class': 'form-control'}),
        }