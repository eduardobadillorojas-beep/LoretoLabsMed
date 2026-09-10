from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0037_fallas_equipo_y_rol_mantenimiento'),
    ]

    operations = [
        migrations.AddField(
            model_name='equiporadiologico',
            name='estado_operativo',
            field=models.CharField(
                choices=[
                    ('OPERATIVO', 'Operativo'),
                    ('OBSERVACION', 'Operativo con observaciones'),
                    ('EN_REVISION', 'En revisión'),
                    ('FUERA_SERVICIO', 'Fuera de servicio'),
                ],
                default='OPERATIVO',
                max_length=20,
            ),
        ),
    ]
