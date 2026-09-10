import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0040_parametros_dicom_automaticos_bitacora'),
    ]

    operations = [
        migrations.CreateModel(
            name='PruebaControlCalidadEquipo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=180)),
                ('descripcion', models.TextField(blank=True)),
                ('periodicidad', models.CharField(choices=[('DIARIA', 'Diaria'), ('SEMANAL', 'Semanal'), ('MENSUAL', 'Mensual'), ('TRIMESTRAL', 'Trimestral'), ('SEMESTRAL', 'Semestral'), ('ANUAL', 'Anual')], max_length=12)),
                ('tolerancia', models.CharField(help_text='Criterio definido por el programa de garantía de calidad, fabricante o responsable.', max_length=250)),
                ('unidad', models.CharField(blank=True, max_length=40)),
                ('proxima_fecha', models.DateField()),
                ('activa', models.BooleanField(default=True)),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('actualizado_el', models.DateTimeField(auto_now=True)),
                ('creado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pruebas_control_calidad_creadas', to=settings.AUTH_USER_MODEL)),
                ('equipo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pruebas_control_calidad', to='core.equiporadiologico')),
                ('institucion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pruebas_control_calidad', to='core.institucion')),
            ],
            options={'ordering': ['proxima_fecha', 'equipo__nombre', 'nombre']},
        ),
        migrations.CreateModel(
            name='RegistroControlCalidadEquipo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('realizado_el', models.DateTimeField(default=django.utils.timezone.now)),
                ('valor_obtenido', models.CharField(blank=True, max_length=180)),
                ('unidad_aplicada', models.CharField(blank=True, max_length=40)),
                ('tolerancia_aplicada', models.CharField(max_length=250)),
                ('resultado', models.CharField(choices=[('APROBADO', 'Aprobado'), ('OBSERVACIONES', 'Aprobado con observaciones'), ('FUERA_TOLERANCIA', 'Fuera de tolerancia')], max_length=22)),
                ('observaciones', models.TextField(blank=True)),
                ('evidencia', models.FileField(blank=True, null=True, upload_to='equipos/control_calidad/%Y/%m/')),
                ('proxima_fecha_calculada', models.DateField()),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('falla_generada', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='control_calidad_origen', to='core.reportefallaequipo')),
                ('prueba', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='registros', to='core.pruebacontrolcalidadequipo')),
                ('realizado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='controles_calidad_realizados', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-realizado_el', '-id']},
        ),
        migrations.AddConstraint(
            model_name='pruebacontrolcalidadequipo',
            constraint=models.UniqueConstraint(fields=('institucion', 'equipo', 'nombre'), name='control_calidad_prueba_unica_equipo'),
        ),
        migrations.AddIndex(
            model_name='pruebacontrolcalidadequipo',
            index=models.Index(fields=['institucion', 'proxima_fecha'], name='cc_prueba_inst_fecha_idx'),
        ),
        migrations.AddIndex(
            model_name='registrocontrolcalidadequipo',
            index=models.Index(fields=['resultado', 'realizado_el'], name='cc_reg_result_fecha_idx'),
        ),
    ]
