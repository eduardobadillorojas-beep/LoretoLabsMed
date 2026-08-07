from django.conf import settings
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

            Paciente.objects.filter(
                pk=self.pk
            ).update(
                identificacion=self.identificacion
            )

    def __str__(self):
        return (
            f'{self.identificacion} - '
            f'{self.nombre} {self.apellido}'
        )


class TipoEstudio(models.Model):
    MODALIDAD_CHOICES = [
        ('RX', 'Radiografía'),
        ('TAC', 'Tomografía'),
        ('USG', 'Ultrasonido'),
        ('MASTO', 'Mastografía'),
        ('FLUORO', 'Fluoroscopia'),
        ('RM', 'Resonancia magnética'),
        ('DXA', 'Densitometría'),
    ]

    codigo = models.CharField(
        max_length=20,
        unique=True
    )

    nombre = models.CharField(
        max_length=150
    )

    modalidad = models.CharField(
        max_length=20,
        choices=MODALIDAD_CHOICES
    )

    activo = models.BooleanField(
        default=True
    )

    tiempo_estimado = models.PositiveIntegerField(
        default=10,
        verbose_name='Tiempo estimado en minutos'
    )

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'


class Consulta(models.Model):
    ESTADO_CHOICES = [
        ('EN_ESPERA', 'En espera'),
        ('EN_CONSULTA', 'En consulta'),
        ('FINALIZADA', 'Finalizada'),
        ('CANCELADA', 'Cancelada'),
    ]

    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.CASCADE,
        related_name='consultas'
    )

    medico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='consultas_medicas',
        blank=True,
        null=True
    )

    motivo_consulta = models.TextField(
        blank=True,
        null=True,
        verbose_name='Motivo de consulta'
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='EN_ESPERA'
    )

    fecha_llegada = models.DateTimeField(auto_now_add=True)

    fecha_inicio = models.DateTimeField(
        blank=True,
        null=True
    )

    fecha_finalizacion = models.DateTimeField(
        blank=True,
        null=True
    )

    def __str__(self):
        return (
            f'{self.paciente.nombre} '
            f'{self.paciente.apellido} - '
            f'{self.get_estado_display()}'
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

    consulta = models.ForeignKey(
        Consulta,
        on_delete=models.SET_NULL,
        related_name='estudios',
        blank=True,
        null=True
    )

    tipo_estudio = models.ForeignKey(
        TipoEstudio,
        on_delete=models.PROTECT,
        related_name='estudios'
    )

    medico_solicitante = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Médico solicitante'
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
            f'{self.tipo_estudio.nombre} - '
            f'{self.paciente.identificacion}'
        )


class Cita(models.Model):
    AREA_CHOICES = [
        ('CONSULTA', 'Consulta médica'),
        ('TRAUMATOLOGIA', 'Traumatología'),
        ('DERMATOLOGIA', 'Dermatología'),
        ('ENDOCRINOLOGIA', 'Endocrinología'),
        ('RADIOLOGIA', 'Radiología'),
    ]

    ESTADO_CHOICES = [
        ('PROGRAMADA', 'Programada'),
        ('CONFIRMADA', 'Confirmada'),
        ('LLEGO', 'Paciente llegó'),
        ('EN_ESPERA', 'En espera'),
        ('EN_ATENCION', 'En atención'),
        ('FINALIZADA', 'Finalizada'),
        ('CANCELADA', 'Cancelada'),
        ('NO_ASISTIO', 'No asistió'),
    ]

    nombre_paciente = models.CharField(
        max_length=200,
        verbose_name='Nombre del paciente'
    )

    telefono = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Teléfono'
    )

    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.SET_NULL,
        related_name='citas',
        blank=True,
        null=True
    )

    area = models.CharField(
        max_length=30,
        choices=AREA_CHOICES,
        verbose_name='Área de atención'
    )

    medico_nombre = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Médico'
    )

    tipo_estudio = models.ForeignKey(
        TipoEstudio,
        on_delete=models.PROTECT,
        related_name='citas',
        blank=True,
        null=True,
        verbose_name='Estudio programado'
    )

    fecha_hora = models.DateTimeField(
        verbose_name='Fecha y hora'
    )

    duracion_minutos = models.PositiveIntegerField(
        default=30,
        verbose_name='Duración estimada en minutos'
    )

    motivo = models.TextField(
        blank=True,
        null=True,
        verbose_name='Motivo de la cita'
    )

    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name='Observaciones internas'
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PROGRAMADA'
    )

    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='citas_creadas',
        blank=True,
        null=True
    )

    creado_el = models.DateTimeField(auto_now_add=True)
    actualizado_el = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            'fecha_hora',
        ]

        indexes = [
            models.Index(
                fields=['fecha_hora']
            ),
            models.Index(
                fields=['area', 'estado']
            ),
        ]

    def __str__(self):
        return (
            f'{self.nombre_paciente} - '
            f'{self.get_area_display()} - '
            f'{self.fecha_hora:%d/%m/%Y %H:%M}'
        )


class SesionTrabajo(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sesiones_trabajo'
    )

    inicio = models.DateTimeField(
        auto_now_add=True
    )

    ultima_actividad = models.DateTimeField(
        auto_now=True
    )

    fin = models.DateTimeField(
        blank=True,
        null=True
    )

    activa = models.BooleanField(
        default=True
    )

    ip_inicio = models.GenericIPAddressField(
        blank=True,
        null=True
    )

    ip_fin = models.GenericIPAddressField(
        blank=True,
        null=True
    )

    user_agent = models.TextField(
        blank=True,
        null=True
    )

    class Meta:
        ordering = [
            '-inicio',
        ]

        indexes = [
            models.Index(
                fields=['usuario', 'activa']
            ),
            models.Index(
                fields=['inicio']
            ),
        ]

    def __str__(self):
        return (
            f'{self.usuario.username} - '
            f'{self.inicio:%d/%m/%Y %H:%M}'
        )

    @property
    def duracion(self):
        if self.fin:
            return self.fin - self.inicio

        return None