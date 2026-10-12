from django.db import migrations, models


ESTUDIOS_NUEVOS = [
    ('RX106', 'RX muñeca AP'),
    ('RX107', 'RX muñeca LAT'),
    ('RX108', 'RX muñeca OBL'),
    ('RX109', 'RX muñeca AP/LAT'),
    ('RX110', 'RX muñeca AP/OBL'),
    ('RX111', 'RX muñeca AP/LAT/OBL'),
    ('RX112', 'RX mano AP'),
    ('RX113', 'RX mano LAT'),
    ('RX114', 'RX mano OBL'),
    ('RX115', 'RX mano AP/LAT'),
    ('RX116', 'RX mano AP/OBL'),
    ('RX117', 'RX mano AP/LAT/OBL'),
    ('RX118', 'RX hombro LAT'),
    ('RX119', 'RX hombro OBL'),
    ('RX120', 'RX hombro axial'),
    ('RX121', 'RX panorámica (ortopantomografía)'),
    ('RX122', 'RX lateral de cráneo'),
    ('RX123', 'RX panorámica + lateral de cráneo'),
]


def agregar_estudios(apps, schema_editor):
    TipoEstudio = apps.get_model('core', 'TipoEstudio')
    for codigo, nombre in ESTUDIOS_NUEVOS:
        TipoEstudio.objects.update_or_create(
            codigo=codigo,
            defaults={
                'nombre': nombre,
                'modalidad': 'RX',
                'activo': True,
                'tiempo_estimado': 10,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0045_sincronizacion_pacientes_estudios'),
    ]

    operations = [
        migrations.AddField(
            model_name='estudio',
            name='formato_entrega',
            field=models.CharField(
                choices=[
                    ('DIGITAL', 'Digital'),
                    ('IMPRESO', 'Impreso'),
                    ('AMBOS', 'Impreso y digital'),
                ],
                default='DIGITAL',
                max_length=10,
                verbose_name='Entrega solicitada',
            ),
        ),
        migrations.RunPython(agregar_estudios, migrations.RunPython.noop),
    ]
