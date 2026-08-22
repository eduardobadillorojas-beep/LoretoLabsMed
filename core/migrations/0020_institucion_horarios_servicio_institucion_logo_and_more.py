from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_alter_bitacoraradiologica_fecha_realizacion_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='institucion',
            name='horarios_servicio',
            field=models.TextField(blank=True, null=True, verbose_name='Horarios de servicio'),
        ),
        migrations.AddField(
            model_name='institucion',
            name='logo',
            field=models.ImageField(blank=True, null=True, upload_to='instituciones/logos/', verbose_name='Logo institucional'),
        ),
        migrations.AddField(
            model_name='institucion',
            name='pie_documentos',
            field=models.TextField(blank=True, null=True, verbose_name='Pie de documentos'),
        ),
        migrations.AddField(
            model_name='institucion',
            name='telefono_secundario',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Teléfono secundario'),
        ),
        migrations.CreateModel(
            name='PerfilMedico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('especialidad', models.CharField(blank=True, max_length=150, null=True, verbose_name='Especialidad')),
                ('cedula_profesional', models.CharField(blank=True, max_length=50, null=True, verbose_name='Cédula profesional')),
                ('telefono_profesional', models.CharField(blank=True, max_length=20, null=True, verbose_name='Teléfono profesional')),
                ('firma', models.ImageField(blank=True, null=True, upload_to='medicos/firmas/', verbose_name='Firma digitalizada')),
                ('activo', models.BooleanField(default=True)),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('actualizado_el', models.DateTimeField(auto_now=True)),
                ('institucion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='perfiles_medicos', to='core.institucion')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='perfiles_medicos', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='perfilmedico',
            constraint=models.UniqueConstraint(fields=('institucion', 'usuario'), name='unique_perfil_medico_por_institucion'),
        ),
    ]