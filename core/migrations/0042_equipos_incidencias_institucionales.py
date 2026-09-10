from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0041_control_calidad_equipos')]

    operations = [
        migrations.AddField(
            model_name='equiporadiologico', name='area',
            field=models.CharField(choices=[('RADIOLOGIA', 'Radiología e imagen'), ('CONSULTA', 'Consulta externa'), ('URGENCIAS', 'Urgencias'), ('QUIROFANO', 'Quirófano'), ('HOSPITALIZACION', 'Hospitalización'), ('ENFERMERIA', 'Enfermería'), ('LABORATORIO', 'Laboratorio'), ('FARMACIA', 'Farmacia'), ('RECEPCION', 'Recepción y admisión'), ('ADMINISTRACION', 'Administración y caja'), ('SISTEMAS', 'Sistemas y comunicaciones'), ('LIMPIEZA', 'Intendencia y limpieza'), ('SEGURIDAD', 'Vigilancia y seguridad'), ('MANTENIMIENTO', 'Ingeniería y mantenimiento'), ('GENERAL', 'Servicios generales'), ('OTRA', 'Otra área')], db_index=True, default='RADIOLOGIA', max_length=25),
        ),
        migrations.AlterField(
            model_name='equiporadiologico', name='tipo',
            field=models.CharField(choices=[('RX', 'Radiografía'), ('TAC', 'Tomografía'), ('FLUORO', 'Fluoroscopia'), ('MASTO', 'Mastografía'), ('PORTATIL', 'Rayos X portátil'), ('MEDICO', 'Equipo médico general'), ('MONITOREO', 'Monitoreo de pacientes'), ('QUIRURGICO', 'Equipo quirúrgico'), ('LABORATORIO', 'Equipo de laboratorio'), ('COMPUTO', 'Cómputo y red'), ('IMPRESION', 'Impresión'), ('COMUNICACION', 'Comunicación'), ('LIMPIEZA', 'Limpieza'), ('SEGURIDAD', 'Seguridad'), ('MOBILIARIO', 'Mobiliario'), ('OTRO', 'Otro')], max_length=20),
        ),
        migrations.AddField(model_name='reportefallaequipo', name='area_reportada', field=models.CharField(choices=[('RADIOLOGIA', 'Radiología e imagen'), ('CONSULTA', 'Consulta externa'), ('URGENCIAS', 'Urgencias'), ('QUIROFANO', 'Quirófano'), ('HOSPITALIZACION', 'Hospitalización'), ('ENFERMERIA', 'Enfermería'), ('LABORATORIO', 'Laboratorio'), ('FARMACIA', 'Farmacia'), ('RECEPCION', 'Recepción y admisión'), ('ADMINISTRACION', 'Administración y caja'), ('SISTEMAS', 'Sistemas y comunicaciones'), ('LIMPIEZA', 'Intendencia y limpieza'), ('SEGURIDAD', 'Vigilancia y seguridad'), ('MANTENIMIENTO', 'Ingeniería y mantenimiento'), ('GENERAL', 'Servicios generales'), ('OTRA', 'Otra área')], db_index=True, default='RADIOLOGIA', max_length=25)),
        migrations.AddField(model_name='reportefallaequipo', name='ubicacion_reportada', field=models.CharField(blank=True, max_length=180)),
        migrations.AddField(model_name='reportefallaequipo', name='evidencia', field=models.FileField(blank=True, null=True, upload_to='equipos/incidencias/%Y/%m/')),
    ]
