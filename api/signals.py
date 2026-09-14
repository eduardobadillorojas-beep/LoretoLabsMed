import os

from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Estudio, Paciente

from .models import SyncOutbox
from .sync_context import esta_importando


def escritorio_activo():
    return os.environ.get('LORETO_DESKTOP_MODE') == '1'


def registrar_outbox(entidad, instancia):
    if not escritorio_activo() or esta_importando():
        return

    SyncOutbox.objects.update_or_create(
        entidad=entidad,
        sync_id=instancia.sync_id,
        defaults={
            'objeto_id': instancia.pk,
            'enviado_el': None,
            'ultimo_error': '',
        },
    )


@receiver(post_save, sender=Paciente)
def paciente_guardado(sender, instance, **kwargs):
    registrar_outbox('PACIENTE', instance)


@receiver(post_save, sender=Estudio)
def estudio_guardado(sender, instance, **kwargs):
    registrar_outbox('ESTUDIO', instance)
