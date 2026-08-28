from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def convertir_enlaces_activos_en_permanentes(apps, schema_editor):
    Entrega = apps.get_model('core', 'EntregaDigitalEstudio')
    Entrega.objects.filter(activa=True).update(vence_el=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0034_entregadigitalestudio'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='entregadigitalestudio',
            name='vence_el',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='entregadigitalestudio',
            name='destinatario',
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name='entregadigitalestudio',
            name='telefono_destino',
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AddField(
            model_name='entregadigitalestudio',
            name='revocada_el',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='entregadigitalestudio',
            name='revocada_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='entregas_digitales_estudios_revocadas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            convertir_enlaces_activos_en_permanentes,
            migrations.RunPython.noop,
        ),
    ]
