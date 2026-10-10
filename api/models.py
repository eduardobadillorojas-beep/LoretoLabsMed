import uuid

from django.conf import settings
from django.db import models


class SyncOutbox(models.Model):
    ENTIDAD_CHOICES = [
        ('PACIENTE', 'Paciente'),
        ('ESTUDIO', 'Estudio'),
    ]

    entidad = models.CharField(max_length=20, choices=ENTIDAD_CHOICES)
    sync_id = models.UUIDField()
    objeto_id = models.PositiveBigIntegerField()
    creado_el = models.DateTimeField(auto_now_add=True)
    actualizado_el = models.DateTimeField(auto_now=True)
    enviado_el = models.DateTimeField(blank=True, null=True)
    intentos = models.PositiveIntegerField(default=0)
    ultimo_error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entidad', 'sync_id'],
                name='sync_outbox_entidad_syncid_unico',
            ),
        ]
        indexes = [
            models.Index(fields=['enviado_el', 'creado_el']),
        ]

    def __str__(self):
        return f'{self.entidad} {self.sync_id}'


class SyncCursor(models.Model):
    clave = models.CharField(max_length=80, unique=True)
    valor = models.DateTimeField(blank=True, null=True)
    actualizado_el = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.clave


class DispositivoSync(models.Model):
    """Computadora autorizada para sincronizar una institución."""

    institucion = models.ForeignKey(
        'core.Institucion',
        on_delete=models.CASCADE,
        related_name='dispositivos_sync',
    )
    dispositivo_id = models.UUIDField(default=uuid.uuid4)
    nombre = models.CharField(max_length=150)
    token_hash = models.CharField(max_length=64, unique=True)
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='dispositivos_sync_autorizados',
        blank=True,
        null=True,
    )
    activo = models.BooleanField(default=True)
    creado_el = models.DateTimeField(auto_now_add=True)
    actualizado_el = models.DateTimeField(auto_now=True)
    ultima_conexion = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['institucion', 'dispositivo_id'],
                name='sync_dispositivo_institucion_id_unico',
            ),
        ]
        indexes = [
            models.Index(
                fields=['activo', 'ultima_conexion'],
                name='api_disposi_activo_83d793_idx',
            ),
        ]

    def __str__(self):
        return f'{self.nombre} - {self.institucion}'
