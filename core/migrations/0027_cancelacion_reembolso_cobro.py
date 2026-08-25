import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_pagocobro_pagos_mixtos'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cobro',
            name='cancelado_el',
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='cobro',
            name='cancelado_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cobros_cancelados',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='cobro',
            name='destino_cargos_cancelacion',
            field=models.CharField(
                blank=True,
                choices=[
                    ('CANCELAR', 'Cancelar también los servicios'),
                    ('REABRIR', 'Dejar los servicios pendientes para volver a cobrar'),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='cobro',
            name='forma_reembolso',
            field=models.CharField(
                blank=True,
                choices=[
                    ('EFECTIVO', 'Efectivo'),
                    ('TARJETA', 'Tarjeta'),
                    ('TRANSFERENCIA', 'Transferencia'),
                    ('OTRO', 'Otro'),
                    ('MIXTO', 'Pago mixto'),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='cobro',
            name='monto_reembolsado',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name='cobro',
            name='motivo_cancelacion',
            field=models.CharField(
                blank=True,
                max_length=300,
                null=True,
            ),
        ),
    ]
