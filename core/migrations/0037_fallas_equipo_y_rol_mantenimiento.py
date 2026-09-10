import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0036_merge_20260910_1119'),
    ]

    operations = [
        migrations.AlterField(
            model_name='membresiainstitucion',
            name='rol',
            field=models.CharField(choices=[('ADMIN', 'Administrador'), ('RECEPCION', 'Recepción'), ('MEDICO', 'Médico'), ('RADIOLOGIA', 'Radiología'), ('TECNICO', 'Técnico'), ('ENFERMERIA', 'Enfermería'), ('MANTENIMIENTO', 'Ingeniería y mantenimiento'), ('OTRO', 'Otro')], default='OTRO', max_length=20),
        ),
        migrations.CreateModel(
            name='ReporteFallaEquipo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=180)),
                ('descripcion', models.TextField()),
                ('prioridad', models.CharField(choices=[('BAJA', 'Baja'), ('MEDIA', 'Media'), ('ALTA', 'Alta'), ('CRITICA', 'Crítica')], default='MEDIA', max_length=10)),
                ('estado', models.CharField(choices=[('REPORTADA', 'Reportada'), ('RECIBIDA', 'Recibida'), ('EN_REVISION', 'En revisión'), ('FUERA_SERVICIO', 'Fuera de servicio'), ('RESUELTA', 'Resuelta'), ('CERRADA', 'Cerrada')], default='REPORTADA', max_length=20)),
                ('reportada_el', models.DateTimeField(auto_now_add=True)),
                ('actualizada_el', models.DateTimeField(auto_now=True)),
                ('cerrada_el', models.DateTimeField(blank=True, null=True)),
                ('asignada_a', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fallas_asignadas', to=settings.AUTH_USER_MODEL)),
                ('equipo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fallas', to='core.equiporadiologico')),
                ('institucion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fallas_equipos', to='core.institucion')),
                ('reportada_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fallas_reportadas', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-reportada_el']},
        ),
        migrations.CreateModel(
            name='SeguimientoFallaEquipo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado', models.CharField(choices=[('REPORTADA', 'Reportada'), ('RECIBIDA', 'Recibida'), ('EN_REVISION', 'En revisión'), ('FUERA_SERVICIO', 'Fuera de servicio'), ('RESUELTA', 'Resuelta'), ('CERRADA', 'Cerrada')], max_length=20)),
                ('nota', models.TextField()),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('falla', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='seguimientos', to='core.reportefallaequipo')),
                ('registrado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='seguimientos_fallas', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-creado_el']},
        ),
    ]
