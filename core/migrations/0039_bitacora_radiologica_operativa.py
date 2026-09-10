import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0038_equipo_estado_operativo'),
    ]

    operations = [
        migrations.AlterField(model_name='bitacoraradiologica', name='modalidad', field=models.CharField(choices=[('RX', 'Radiografía'), ('TAC', 'Tomografía'), ('FLUORO', 'Fluoroscopia'), ('MASTO', 'Mastografía'), ('USG', 'Ultrasonido'), ('RM', 'Resonancia magnética'), ('DXA', 'Densitometría'), ('OTRA', 'Otra')], max_length=20)),
        migrations.AddField(model_name='bitacoraradiologica', name='numero_imagenes_impresas', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='bitacoraradiologica', name='numero_repeticiones', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='bitacoraradiologica', name='motivo_repeticion', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='bitacoraradiologica', name='contraste_nombre', field=models.CharField(blank=True, max_length=150, null=True)),
        migrations.AddField(model_name='bitacoraradiologica', name='contraste_lote', field=models.CharField(blank=True, max_length=100, null=True)),
        migrations.AddField(model_name='bitacoraradiologica', name='contraste_volumen_ml', field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
        migrations.AddField(model_name='bitacoraradiologica', name='contraste_via', field=models.CharField(blank=True, max_length=80, null=True)),
        migrations.AddField(model_name='bitacoraradiologica', name='reaccion_contraste', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='bitacoraradiologica', name='verificacion_embarazo', field=models.CharField(choices=[('NO_APLICA', 'No aplica'), ('DESCARTADO', 'Descartado'), ('POSIBLE', 'Posible embarazo')], default='NO_APLICA', max_length=20)),
        migrations.AddField(model_name='bitacoraradiologica', name='proteccion_radiologica', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='bitacoraradiologica', name='incidencias', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='bitacoraradiologica', name='actualizado_el', field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now), preserve_default=False),
        migrations.AddField(model_name='bitacoraradiologica', name='actualizado_por', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bitacoras_radiologicas_actualizadas', to=settings.AUTH_USER_MODEL)),
    ]
