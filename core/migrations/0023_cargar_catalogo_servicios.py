from django.db import migrations


def cargar_servicios(apps, schema_editor):
    Institucion = apps.get_model('core', 'Institucion')
    TipoEstudio = apps.get_model('core', 'TipoEstudio')
    Servicio = apps.get_model('core', 'Servicio')

    tipos_permitidos = {
        'RX': 'RX',
        'USG': 'USG',
        'TAC': 'TAC',
        'FLUORO': 'FLUORO',
    }

    for institucion in Institucion.objects.all():
        for tipo_estudio in TipoEstudio.objects.filter(activo=True):
            Servicio.objects.get_or_create(
                institucion=institucion,
                tipo_estudio=tipo_estudio,
                defaults={
                    'nombre': tipo_estudio.nombre,
                    'tipo': tipos_permitidos.get(
                        tipo_estudio.modalidad,
                        'OTRO'
                    ),
                    'precio_base': 0,
                    'precio_editable': True,
                    'activo': True,
                }
            )


class Migration(migrations.Migration):

    dependencies = [
        (
            'core',
            '0022_alter_bitacoraradiologica_fecha_realizacion_and_more'
        ),
    ]

    operations = [
        migrations.RunPython(
            cargar_servicios,
            migrations.RunPython.noop,
        ),
    ]
