import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0034_entregadigitalestudio'),
    ]

    operations = [
        migrations.AddField(
            model_name='paciente',
            name='creado_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pacientes_registrados', to=settings.AUTH_USER_MODEL, verbose_name='Registrado por'),
        ),
        migrations.AddField(
            model_name='paciente',
            name='origen_registro',
            field=models.CharField(choices=[('RECEPCION', 'Recepción'), ('RADIOLOGIA', 'Radiología'), ('ADMIN', 'Administración')], default='RECEPCION', max_length=20, verbose_name='Área de registro'),
        ),
        migrations.AddField(
            model_name='equiporadiologico',
            name='institucion',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='equipos_radiologicos', to='core.institucion'),
        ),
        migrations.AddField(
            model_name='bitacoraradiologica',
            name='medio_entrega',
            field=models.CharField(choices=[('PENDIENTE', 'Pendiente de entrega'), ('IMPRESO', 'Impreso'), ('DIGITAL', 'Digital'), ('AMBOS', 'Impreso y digital')], default='PENDIENTE', max_length=15),
        ),
        migrations.AddField(
            model_name='bitacoraradiologica',
            name='fecha_entrega',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='bitacoraradiologica',
            name='entrega_registrada_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entregas_radiologicas_registradas', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='MantenimientoEquipoRadiologico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('PREVENTIVO', 'Preventivo'), ('CORRECTIVO', 'Correctivo'), ('CALIBRACION', 'Calibración / control de calidad'), ('OTRO', 'Otro')], max_length=20)),
                ('fecha_servicio', models.DateField(verbose_name='Fecha del servicio')),
                ('proveedor_ingeniero', models.CharField(max_length=180, verbose_name='Proveedor o ingeniero')),
                ('informe_servicio', models.TextField(verbose_name='Informe del servicio')),
                ('proximo_mantenimiento', models.DateField(blank=True, null=True)),
                ('documento', models.FileField(blank=True, null=True, upload_to='equipos/mantenimientos/', verbose_name='Informe adjunto')),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('equipo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='mantenimientos', to='core.equiporadiologico')),
                ('registrado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mantenimientos_radiologicos_registrados', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-fecha_servicio', '-creado_el']},
        ),
        migrations.CreateModel(
            name='EntregaResultadoEstudio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('medio', models.CharField(choices=[('IMPRESO', 'Impreso'), ('DIGITAL', 'Digital'), ('AMBOS', 'Impreso y digital')], max_length=15)),
                ('entregado_a', models.CharField(blank=True, max_length=180)),
                ('observaciones', models.TextField(blank=True)),
                ('fecha_entrega', models.DateTimeField(auto_now_add=True)),
                ('estudio', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='entregas_resultado', to='core.estudio')),
                ('registrado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entregas_resultados_registradas', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-fecha_entrega']},
        ),
    ]
