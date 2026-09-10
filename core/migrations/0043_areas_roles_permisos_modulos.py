from django.db import migrations, models
import django.db.models.deletion


AREAS = [
    ('administracion', 'Administración', 10), ('recepcion', 'Recepción y admisión', 20),
    ('consulta', 'Consulta médica', 30), ('enfermeria', 'Enfermería', 40),
    ('radiologia', 'Radiología e imagen', 50), ('laboratorio', 'Laboratorio', 60),
    ('farmacia', 'Farmacia', 70), ('finanzas', 'Caja y finanzas', 80),
    ('mantenimiento', 'Ingeniería y mantenimiento', 90), ('sistemas', 'Sistemas', 100),
    ('limpieza', 'Intendencia y limpieza', 110), ('seguridad', 'Vigilancia y seguridad', 120),
    ('general', 'Servicios generales', 130),
]

MODULOS = [
    ('configuracion', 'Configuración institucional', '⚙', 'panel_config', True, 10),
    ('recepcion', 'Recepción y agenda', '📅', 'panel_recepcion', True, 20),
    ('caja', 'Caja y cobros', '💳', 'caja_recepcion', True, 30),
    ('medicos', 'Atención médica', '🩺', 'panel_medico', True, 40),
    ('enfermeria', 'Enfermería', '💉', '', False, 50),
    ('radiologia', 'Radiología e imagen', '☢', 'panel_radiologo', True, 60),
    ('dicom', 'Visor y archivo DICOM', '🖥', 'panel_radiologo', True, 70),
    ('reportes', 'Reportes radiológicos', '📄', 'panel_radiologo', True, 80),
    ('entrega_digital', 'Entrega digital', '🔗', 'panel_radiologo', True, 90),
    ('bitacora_radiologica', 'Bitácora radiológica', '▤', 'bitacora_radiologica_panel', True, 100),
    ('repeticiones', 'Análisis de repeticiones', '↻', 'analisis_repeticiones_radiologia', True, 110),
    ('equipos', 'Equipos e incidencias', '⚠', 'equipos_incidencias_institucionales', True, 120),
    ('mantenimiento', 'Mantenimiento de equipos', '🔧', 'mantenimiento_equipos_radiologia', True, 130),
    ('calidad', 'Control de calidad', '✓', 'control_calidad_equipos_radiologia', True, 140),
    ('limpieza', 'Limpieza e intendencia', '🧹', '', False, 150),
    ('seguridad', 'Vigilancia y seguridad', '🛡', '', False, 160),
    ('medico_independiente', 'Consultorio médico independiente', '👨‍⚕️', '', False, 170),
    ('paciente_independiente', 'Expediente personal del paciente', '👤', '', False, 180),
]

ROL_AREA = {'ADMIN':'administracion','RECEPCION':'recepcion','MEDICO':'consulta','RADIOLOGIA':'radiologia','TECNICO':'radiologia','ENFERMERIA':'enfermeria','MANTENIMIENTO':'mantenimiento','LIMPIEZA':'limpieza','SEGURIDAD':'seguridad','LABORATORIO':'laboratorio','FARMACIA':'farmacia','FINANZAS':'finanzas','SISTEMAS':'sistemas','OTRO':'general'}
ROL_MODULOS = {
    'ADMIN': [m[0] for m in MODULOS if m[4]],
    'RECEPCION': ['recepcion','caja','equipos'],
    'MEDICO': ['medicos','reportes','dicom','equipos'],
    'RADIOLOGIA': ['radiologia','dicom','reportes','entrega_digital','bitacora_radiologica','repeticiones','equipos','calidad'],
    'TECNICO': ['radiologia','dicom','entrega_digital','bitacora_radiologica','repeticiones','equipos','calidad'],
    'ENFERMERIA': ['equipos'], 'MANTENIMIENTO': ['equipos','mantenimiento','calidad'],
    'LIMPIEZA': ['equipos'], 'SEGURIDAD': ['equipos'], 'LABORATORIO': ['equipos'],
    'FARMACIA': ['equipos'], 'FINANZAS': ['caja','equipos'], 'SISTEMAS': ['equipos'], 'OTRO': ['equipos'],
}


def cargar_catalogos(apps, schema_editor):
    Institucion = apps.get_model('core', 'Institucion')
    Area = apps.get_model('core', 'AreaInstitucional')
    Modulo = apps.get_model('core', 'ModuloSistema')
    Membresia = apps.get_model('core', 'MembresiaInstitucion')
    Acceso = apps.get_model('core', 'AccesoModuloMembresia')
    modulos = {}
    for codigo, nombre, icono, ruta, disponible, orden in MODULOS:
        modulos[codigo], _ = Modulo.objects.update_or_create(codigo=codigo, defaults={'nombre':nombre,'icono':icono,'ruta':ruta,'disponible':disponible,'orden':orden})
    for institucion in Institucion.objects.all():
        areas = {}
        for clave, nombre, orden in AREAS:
            areas[clave], _ = Area.objects.get_or_create(institucion=institucion, clave=clave, defaults={'nombre':nombre,'orden':orden})
        for membresia in Membresia.objects.filter(institucion=institucion):
            membresia.area = areas.get(ROL_AREA.get(membresia.rol, 'general'))
            membresia.save(update_fields=['area'])
            for codigo in ROL_MODULOS.get(membresia.rol, ['equipos']):
                Acceso.objects.get_or_create(membresia=membresia, modulo=modulos[codigo], defaults={'puede_ver':True,'puede_registrar':membresia.rol!='MEDICO','puede_editar':membresia.rol in ['ADMIN','MANTENIMIENTO'],'puede_administrar':membresia.rol=='ADMIN'})


class Migration(migrations.Migration):
    dependencies = [('core', '0042_equipos_incidencias_institucionales')]
    operations = [
        migrations.CreateModel(name='AreaInstitucional', fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('clave', models.SlugField(max_length=50)), ('nombre', models.CharField(max_length=120)), ('descripcion', models.CharField(blank=True, max_length=250)), ('activa', models.BooleanField(default=True)), ('orden', models.PositiveSmallIntegerField(default=100)), ('institucion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='areas_institucionales', to='core.institucion'))], options={'ordering':['orden','nombre']},),
        migrations.CreateModel(name='ModuloSistema', fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('codigo', models.SlugField(max_length=50, unique=True)), ('nombre', models.CharField(max_length=120)), ('descripcion', models.CharField(blank=True, max_length=300)), ('icono', models.CharField(blank=True, max_length=10)), ('ruta', models.CharField(blank=True, max_length=100)), ('disponible', models.BooleanField(default=True)), ('orden', models.PositiveSmallIntegerField(default=100))], options={'ordering':['orden','nombre']},),
        migrations.AddField(model_name='membresiainstitucion', name='area', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='membresias', to='core.areainstitucional')),
        migrations.AddField(model_name='membresiainstitucion', name='puesto', field=models.CharField(blank=True, max_length=120)),
        migrations.AlterField(model_name='membresiainstitucion', name='rol', field=models.CharField(choices=[('ADMIN','Administrador'),('RECEPCION','Recepción'),('MEDICO','Médico'),('RADIOLOGIA','Radiología'),('TECNICO','Técnico'),('ENFERMERIA','Enfermería'),('MANTENIMIENTO','Ingeniería y mantenimiento'),('LIMPIEZA','Intendencia y limpieza'),('SEGURIDAD','Vigilancia y seguridad'),('LABORATORIO','Laboratorio'),('FARMACIA','Farmacia'),('FINANZAS','Caja y finanzas'),('SISTEMAS','Sistemas'),('OTRO','Otro')], default='OTRO', max_length=20)),
        migrations.CreateModel(name='AccesoModuloMembresia', fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('puede_ver', models.BooleanField(default=True)), ('puede_registrar', models.BooleanField(default=False)), ('puede_editar', models.BooleanField(default=False)), ('puede_administrar', models.BooleanField(default=False)), ('asignado_el', models.DateTimeField(auto_now_add=True)), ('membresia', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='accesos_modulos', to='core.membresiainstitucion')), ('modulo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='accesos_membresias', to='core.modulosistema'))], options={'ordering':['modulo__orden','modulo__nombre']},),
        migrations.AddConstraint(model_name='areainstitucional', constraint=models.UniqueConstraint(fields=('institucion','clave'), name='area_clave_unica_institucion')),
        migrations.AddConstraint(model_name='accesomodulomembresia', constraint=models.UniqueConstraint(fields=('membresia','modulo'), name='acceso_modulo_unico_membresia')),
        migrations.RunPython(cargar_catalogos, migrations.RunPython.noop),
    ]
