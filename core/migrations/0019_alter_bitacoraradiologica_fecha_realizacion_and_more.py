from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_consulta_antecedentes_consulta_diagnostico_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IndicacionMedica',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'indicaciones',
                    models.TextField(
                        verbose_name='Indicaciones médicas',
                    ),
                ),
                (
                    'creada_el',
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    'actualizada_el',
                    models.DateTimeField(
                        auto_now=True,
                    ),
                ),
                (
                    'consulta',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='indicacion_medica',
                        to='core.consulta',
                    ),
                ),
                (
                    'medico',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='indicaciones_medicas_emitidas',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),

        migrations.CreateModel(
            name='RecetaMedica',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'observaciones',
                    models.TextField(
                        blank=True,
                        null=True,
                        verbose_name='Observaciones de la receta',
                    ),
                ),
                (
                    'creada_el',
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    'actualizada_el',
                    models.DateTimeField(
                        auto_now=True,
                    ),
                ),
                (
                    'consulta',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='receta_medica',
                        to='core.consulta',
                    ),
                ),
                (
                    'medico',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='recetas_medicas_emitidas',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),

        migrations.CreateModel(
            name='MedicamentoReceta',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'medicamento',
                    models.CharField(
                        max_length=200,
                    ),
                ),
                (
                    'presentacion',
                    models.CharField(
                        blank=True,
                        max_length=150,
                        null=True,
                        verbose_name='Presentación',
                    ),
                ),
                (
                    'dosis',
                    models.CharField(
                        blank=True,
                        max_length=150,
                        null=True,
                    ),
                ),
                (
                    'via',
                    models.CharField(
                        blank=True,
                        choices=[
                            ('ORAL', 'Oral'),
                            ('SUBLINGUAL', 'Sublingual'),
                            ('TOPICA', 'Tópica'),
                            ('INHALADA', 'Inhalada'),
                            ('OFTALMICA', 'Oftálmica'),
                            ('OTICA', 'Ótica'),
                            ('NASAL', 'Nasal'),
                            ('RECTAL', 'Rectal'),
                            ('VAGINAL', 'Vaginal'),
                            ('INTRAMUSCULAR', 'Intramuscular'),
                            ('INTRAVENOSA', 'Intravenosa'),
                            ('SUBCUTANEA', 'Subcutánea'),
                            ('OTRA', 'Otra'),
                        ],
                        max_length=30,
                        null=True,
                        verbose_name='Vía de administración',
                    ),
                ),
                (
                    'frecuencia',
                    models.CharField(
                        blank=True,
                        max_length=150,
                        null=True,
                    ),
                ),
                (
                    'duracion',
                    models.CharField(
                        blank=True,
                        max_length=150,
                        null=True,
                        verbose_name='Duración',
                    ),
                ),
                (
                    'indicaciones',
                    models.TextField(
                        blank=True,
                        null=True,
                        verbose_name='Indicaciones del medicamento',
                    ),
                ),
                (
                    'orden',
                    models.PositiveIntegerField(
                        default=1,
                    ),
                ),
                (
                    'receta',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='medicamentos',
                        to='core.recetamedica',
                    ),
                ),
            ],
            options={
                'ordering': ['orden', 'id'],
            },
        ),

        migrations.CreateModel(
            name='SolicitudEstudio',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'tipo',
                    models.CharField(
                        choices=[
                            ('LABORATORIO', 'Laboratorio clínico'),
                            ('IMAGEN', 'Imagenología'),
                            ('PATOLOGIA', 'Patología'),
                            ('CARDIOLOGIA', 'Cardiología'),
                            ('OTRO', 'Otro estudio o procedimiento'),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    'prioridad',
                    models.CharField(
                        choices=[
                            ('RUTINA', 'Rutina'),
                            ('PREFERENTE', 'Preferente'),
                            ('URGENTE', 'Urgente'),
                        ],
                        default='RUTINA',
                        max_length=20,
                    ),
                ),
                (
                    'motivo_clinico',
                    models.TextField(
                        blank=True,
                        null=True,
                        verbose_name='Motivo clínico / diagnóstico presuntivo',
                    ),
                ),
                (
                    'observaciones',
                    models.TextField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    'creada_el',
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    'actualizada_el',
                    models.DateTimeField(
                        auto_now=True,
                    ),
                ),
                (
                    'consulta',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='solicitudes_estudio',
                        to='core.consulta',
                    ),
                ),
                (
                    'medico',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='solicitudes_estudio_emitidas',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['-creada_el'],
            },
        ),

        migrations.CreateModel(
            name='EstudioSolicitado',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'nombre',
                    models.CharField(
                        max_length=250,
                        verbose_name='Estudio solicitado',
                    ),
                ),
                (
                    'region_o_detalle',
                    models.CharField(
                        blank=True,
                        max_length=250,
                        null=True,
                        verbose_name='Región, muestra o detalle',
                    ),
                ),
                (
                    'indicaciones',
                    models.TextField(
                        blank=True,
                        null=True,
                        verbose_name='Indicaciones específicas',
                    ),
                ),
                (
                    'orden',
                    models.PositiveIntegerField(
                        default=1,
                    ),
                ),
                (
                    'solicitud',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='estudios_solicitados',
                        to='core.solicitudestudio',
                    ),
                ),
            ],
            options={
                'ordering': ['orden', 'id'],
            },
        ),
    ]