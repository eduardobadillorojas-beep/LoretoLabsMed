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
