import core.models
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_cargar_catalogo_servicios'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='institucion',
            name='rfc',
            field=models.CharField(
                blank=True,
                max_length=13,
                null=True,
                verbose_name='RFC',
            ),
        ),
        migrations.CreateModel(
            name='Cobro',
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
                    'folio',
                    models.CharField(
                        default=core.models.generar_folio_cobro,
                        editable=False,
                        max_length=30,
                        unique=True,
                    ),
                ),
                (
                    'token_publico',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                (
                    'forma_pago',
                    models.CharField(
                        choices=[
                            ('EFECTIVO', 'Efectivo'),
                            ('TARJETA', 'Tarjeta'),
                            ('TRANSFERENCIA', 'Transferencia'),
                            ('OTRO', 'Otro'),
                        ],
                        default='EFECTIVO',
                        max_length=20,
                    ),
                ),
                (
                    'total',
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=12,
                    ),
                ),
                (
                    'monto_recibido',
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                    ),
                ),
                (
                    'cambio',
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=12,
                    ),
                ),
                (
                    'telefono_envio',
                    models.CharField(
                        blank=True,
                        max_length=20,
                        null=True,
                    ),
                ),
                (
                    'estado',
                    models.CharField(
                        choices=[
                            ('PAGADO', 'Pagado'),
                            ('CANCELADO', 'Cancelado'),
                        ],
                        default='PAGADO',
                        max_length=20,
                    ),
                ),
                (
                    'creado_el',
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    'creado_por',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='cobros_registrados',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'institucion',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='cobros',
                        to='core.institucion',
                    ),
                ),
                (
                    'paciente',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='cobros',
                        to='core.paciente',
                    ),
                ),
            ],
            options={
                'ordering': ['-creado_el'],
                'indexes': [
                    models.Index(
                        fields=['institucion', 'paciente', 'creado_el'],
                        name='core_cobro_institu_9a48b6_idx',
                    ),
                    models.Index(
                        fields=['folio'],
                        name='core_cobro_folio_86e6df_idx',
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name='cargopaciente',
            name='cobro',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cargos',
                to='core.cobro',
            ),
        ),
    ]
