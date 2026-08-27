from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0030_movimientos_caja'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EstudioDicom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('study_instance_uid', models.CharField(max_length=128)),
                ('accession_number', models.CharField(blank=True, max_length=64)),
                ('patient_id_dicom', models.CharField(blank=True, max_length=128)),
                ('patient_name_dicom', models.CharField(blank=True, max_length=250)),
                ('descripcion', models.CharField(blank=True, max_length=250)),
                ('fecha_estudio', models.DateField(blank=True, null=True)),
                ('hora_estudio', models.TimeField(blank=True, null=True)),
                ('medico_referente', models.CharField(blank=True, max_length=250)),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('estudio', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='registro_dicom', to='core.estudio')),
                ('institucion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='estudios_dicom', to='core.institucion')),
            ],
            options={'ordering': ['-creado_el']},
        ),
        migrations.CreateModel(
            name='SerieDicom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('series_instance_uid', models.CharField(max_length=128)),
                ('modalidad', models.CharField(blank=True, max_length=20)),
                ('numero_serie', models.IntegerField(blank=True, null=True)),
                ('descripcion', models.CharField(blank=True, max_length=250)),
                ('protocolo', models.CharField(blank=True, max_length=250)),
                ('region_anatomica', models.CharField(blank=True, max_length=100)),
                ('fabricante', models.CharField(blank=True, max_length=150)),
                ('estacion', models.CharField(blank=True, max_length=150)),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('estudio_dicom', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='series', to='core.estudiodicom')),
                ('institucion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='series_dicom', to='core.institucion')),
            ],
            options={'ordering': ['numero_serie', 'id']},
        ),
        migrations.CreateModel(
            name='InstanciaDicom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sop_instance_uid', models.CharField(max_length=128)),
                ('sop_class_uid', models.CharField(blank=True, max_length=128)),
                ('transfer_syntax_uid', models.CharField(blank=True, max_length=128)),
                ('numero_instancia', models.IntegerField(blank=True, null=True)),
                ('filas', models.PositiveIntegerField(blank=True, null=True)),
                ('columnas', models.PositiveIntegerField(blank=True, null=True)),
                ('numero_frames', models.PositiveIntegerField(default=1)),
                ('bits_asignados', models.PositiveIntegerField(blank=True, null=True)),
                ('interpretacion_fotometrica', models.CharField(blank=True, max_length=64)),
                ('hash_sha256', models.CharField(max_length=64)),
                ('tamano_bytes', models.PositiveBigIntegerField(default=0)),
                ('metadatos', models.JSONField(blank=True, default=dict)),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('archivo_estudio', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='instancia_dicom', to='core.archivoestudio')),
                ('institucion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='instancias_dicom', to='core.institucion')),
                ('serie', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='instancias', to='core.seriedicom')),
            ],
            options={'ordering': ['numero_instancia', 'id']},
        ),
        migrations.AddConstraint(model_name='estudiodicom', constraint=models.UniqueConstraint(fields=('institucion', 'study_instance_uid'), name='dicom_study_uid_por_institucion')),
        migrations.AddIndex(model_name='estudiodicom', index=models.Index(fields=['institucion', 'study_instance_uid'], name='dicom_study_inst_uid_idx')),
        migrations.AddConstraint(model_name='seriedicom', constraint=models.UniqueConstraint(fields=('institucion', 'series_instance_uid'), name='dicom_series_uid_por_institucion')),
        migrations.AddIndex(model_name='seriedicom', index=models.Index(fields=['estudio_dicom', 'numero_serie'], name='dicom_series_study_num_idx')),
        migrations.AddConstraint(model_name='instanciadicom', constraint=models.UniqueConstraint(fields=('institucion', 'sop_instance_uid'), name='dicom_sop_uid_por_institucion')),
        migrations.AddConstraint(model_name='instanciadicom', constraint=models.UniqueConstraint(fields=('institucion', 'hash_sha256'), name='dicom_hash_por_institucion')),
        migrations.AddIndex(model_name='instanciadicom', index=models.Index(fields=['serie', 'numero_instancia'], name='dicom_instance_series_num_idx')),
    ]
