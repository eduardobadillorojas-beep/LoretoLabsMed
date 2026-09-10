from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0039_bitacora_radiologica_operativa'),
    ]

    operations = [
        migrations.AddField(
            model_name='tipoestudio',
            name='numero_exposiciones_sugerido',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Exposiciones sugeridas para bitácora'),
        ),
        migrations.AddField(
            model_name='tipoestudio',
            name='proyecciones_sugeridas',
            field=models.CharField(blank=True, max_length=250, verbose_name='Proyecciones sugeridas para bitácora'),
        ),
        migrations.AddField(
            model_name='bitacoraradiologica',
            name='parametros_dicom',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Valores técnicos originales extraídos de los encabezados DICOM.',
            ),
        ),
        migrations.AddField(
            model_name='bitacoraradiologica',
            name='origen_parametros',
            field=models.CharField(
                choices=[
                    ('PENDIENTE', 'Pendiente'),
                    ('DICOM', 'DICOM automático'),
                    ('PLANTILLA', 'Plantilla del estudio'),
                    ('MANUAL', 'Captura manual'),
                    ('MIXTO', 'Origen combinado'),
                ],
                default='PENDIENTE',
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name='bitacoraradiologica',
            name='parametros_extraidos_el',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
