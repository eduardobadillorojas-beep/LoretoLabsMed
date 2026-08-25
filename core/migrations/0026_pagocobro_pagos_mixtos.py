import django.db.models.deletion
from django.db import migrations, models


def crear_detalles_de_cobros_existentes(apps, schema_editor):
    Cobro = apps.get_model('core', 'Cobro')
    PagoCobro = apps.get_model('core', 'PagoCobro')

    pagos = []

    for cobro in Cobro.objects.filter(estado='PAGADO').iterator():
        if cobro.total and cobro.total > 0:
            pagos.append(
                PagoCobro(
                    cobro_id=cobro.pk,
                    forma_pago=cobro.forma_pago,
                    monto=cobro.total,
                )
            )

    PagoCobro.objects.bulk_create(
        pagos,
        batch_size=500,
        ignore_conflicts=True,
    )


def eliminar_detalles_migrados(apps, schema_editor):
    PagoCobro = apps.get_model('core', 'PagoCobro')
    PagoCobro.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0025_rename_core_cobro_institu_9a48b6_idx_core_cobro_institu_48f8cb_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cobro',
            name='forma_pago',
            field=models.CharField(
                choices=[
                    ('EFECTIVO', 'Efectivo'),
                    ('TARJETA', 'Tarjeta'),
                    ('TRANSFERENCIA', 'Transferencia'),
                    ('OTRO', 'Otro'),
                    ('MIXTO', 'Pago mixto'),
                ],
                default='EFECTIVO',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='PagoCobro',
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
                    'forma_pago',
                    models.CharField(
                        choices=[
                            ('EFECTIVO', 'Efectivo'),
                            ('TARJETA', 'Tarjeta'),
                            ('TRANSFERENCIA', 'Transferencia'),
                            ('OTRO', 'Otro'),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    'monto',
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                    ),
                ),
                (
                    'referencia',
                    models.CharField(
                        blank=True,
                        max_length=100,
                        null=True,
                    ),
                ),
                (
                    'creado_el',
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    'cobro',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='pagos',
                        to='core.cobro',
                    ),
                ),
            ],
            options={
                'ordering': ['pk'],
                'indexes': [
                    models.Index(
                        fields=['forma_pago', 'creado_el'],
                        name='pago_forma_fecha_idx',
                    ),
                ],
                'constraints': [
                    models.CheckConstraint(
                        condition=models.Q(monto__gt=0),
                        name='pago_cobro_monto_positivo',
                    ),
                ],
            },
        ),
        migrations.RunPython(
            crear_detalles_de_cobros_existentes,
            eliminar_detalles_migrados,
        ),
    ]
