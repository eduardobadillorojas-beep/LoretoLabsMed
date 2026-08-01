from django.db import models
from django.contrib.auth.models import User

class Paciente(models.Model):
    GENERO_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Femenino'),
        ('O', 'Otro'),
    ]

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    identificacion = models.CharField(max_length=20, unique=True, help_text="DNI, Cédula o Expediente")
    fecha_nacimiento = models.DateField()
    genero = models.CharField(max_length=1, choices=GENERO_CHOICES)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    creado_el = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.identificacion})"

class Estudio(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En Proceso'),
        ('COMPLETADO', 'Completado'),
    ]

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='estudios')
    medico_solicitante = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='estudios_solicitados')
    tipo_estudio = models.CharField(max_length=100, help_text="Ej: Radiografía RX Tórax, Tomografía, Ecografía")
    descripcion = models.TextField(blank=True, null=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tipo_estudio} - {self.paciente.nombre} {self.paciente.apellido}"
