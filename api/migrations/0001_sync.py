from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='SyncOutbox',
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
                ('entidad', models.CharField(max_length=20, choices=[('PACIENTE', 'Paciente'), ('ESTUDIO', 'Estudio')])),
                ('sync_id', models.UUIDField()),
                ('objeto_id', models.PositiveBigIntegerField()),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('actualizado_el', models.DateTimeField(auto_now=True)),
                ('enviado_el', models.DateTimeField(blank=True, null=True)),
                ('intentos', models.PositiveIntegerField(default=0)),
                ('ultimo_error', models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='SyncCursor',
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
                ('clave', models.CharField(max_length=80, unique=True)),
                ('valor', models.DateTimeField(blank=True, null=True)),
                ('actualizado_el', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name='syncoutbox',
            constraint=models.UniqueConstraint(
                fields=('entidad', 'sync_id'),
                name='sync_outbox_entidad_syncid_unico',
            ),
        ),
        migrations.AddIndex(
            model_name='syncoutbox',
            index=models.Index(fields=('enviado_el', 'creado_el'), name='api_syncout_enviado_5a7e2a_idx'),
        ),
    ]
