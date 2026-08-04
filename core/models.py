from django.db import models


class Paciente(models.Model):
    GENERO_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Femenino'),
        ('O', 'Otro'),
    ]

    identificacion = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
        verbose_name='Registro interno'
    )

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)

    fecha_nacimiento = models.DateField()

    genero = models.CharField(
        max_length=1,
        choices=GENERO_CHOICES
    )

    telefono = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    creado_el = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        nuevo_paciente = self.pk is None

        super().save(*args, **kwargs)

        if nuevo_paciente and not self.identificacion:
            numero_registro = self.pk + 99999
            self.identificacion = str(numero_registro)

            Paciente.objects.filter(pk=self.pk).update(
                identificacion=self.identificacion
            )

    def __str__(self):
        return (
            f'{self.identificacion} - '
            f'{self.nombre} {self.apellido}'
        )


class Estudio(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En proceso'),
        ('COMPLETADO', 'Completado'),
    ]

    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.CASCADE,
        related_name='estudios'
    )

    medico_solicitante = models.CharField(
    max_length=150,
    blank=True,
    null=True,
    verbose_name='Médico solicitante'
)

    tipo_estudio = models.CharField(
        max_length=100,
        help_text=(
            'Ejemplo: Radiografía de tórax, '
            'tomografía o ultrasonido'
        )
    )

    descripcion = models.TextField(
        blank=True,
        null=True
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE'
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f'{self.tipo_estudio} - '
            f'{self.paciente.identificacion}'
        )