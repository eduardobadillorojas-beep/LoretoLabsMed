import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_sync'),
        ('core', '0045_sincronizacion_pacientes_estudios'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='syncoutbox',
            old_name='api_syncout_enviado_5a7e2a_idx',
            new_name='api_syncout_enviado_ccd0e4_idx',
        ),
        migrations.CreateModel(
            name='DispositivoSync',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('dispositivo_id', models.UUIDField(default=uuid.uuid4)),
                ('nombre', models.CharField(max_length=150)),
                ('token_hash', models.CharField(max_length=64, unique=True)),
                ('activo', models.BooleanField(default=True)),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('actualizado_el', models.DateTimeField(auto_now=True)),
                ('ultima_conexion', models.DateTimeField(blank=True, null=True)),
                (
                    'autorizado_por',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='dispositivos_sync_autorizados',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'institucion',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='dispositivos_sync',
                        to='core.institucion',
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name='dispositivosync',
            constraint=models.UniqueConstraint(
                fields=('institucion', 'dispositivo_id'),
                name='sync_dispositivo_institucion_id_unico',
            ),
        ),
        migrations.AddIndex(
            model_name='dispositivosync',
            index=models.Index(
                fields=['activo', 'ultima_conexion'],
                name='api_disposi_activo_83d793_idx',
            ),
        ),
    ]
