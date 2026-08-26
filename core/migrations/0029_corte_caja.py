from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import core.models


class Migration(migrations.Migration):
    dependencies = [('core', '0028_creditos_paciente')]
    operations = [
        migrations.CreateModel(
            name='CorteCaja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('folio', models.CharField(default=core.models.generar_folio_corte_caja, editable=False, max_length=30, unique=True)),
                ('estado', models.CharField(choices=[('ABIERTA', 'Abierta'), ('CERRADA', 'Cerrada')], default='ABIERTA', max_length=10)),
                ('fondo_inicial', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('abierto_el', models.DateTimeField(auto_now_add=True)),
                ('cerrado_el', models.DateTimeField(blank=True, null=True)),
                ('total_cobros', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_abonos', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_reembolsos', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_neto', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_efectivo', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_tarjeta', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_transferencia', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_otro', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('reembolso_efectivo', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('efectivo_esperado', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('efectivo_contado', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('efectivo_entregado', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('efectivo_dejado', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('diferencia', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('numero_cobros', models.PositiveIntegerField(default=0)),
                ('numero_abonos', models.PositiveIntegerField(default=0)),
                ('numero_reembolsos', models.PositiveIntegerField(default=0)),
                ('observaciones_apertura', models.CharField(blank=True, max_length=300, null=True)),
                ('observaciones_cierre', models.CharField(blank=True, max_length=500, null=True)),
                ('confirmacion_primera', models.BooleanField(default=False)),
                ('confirmacion_segunda', models.BooleanField(default=False)),
                ('institucion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cortes_caja', to='core.institucion')),
                ('responsable', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cortes_caja', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-abierto_el']},
        ),
        migrations.AddConstraint(model_name='cortecaja', constraint=models.UniqueConstraint(condition=models.Q(estado='ABIERTA'), fields=('institucion', 'responsable'), name='una_caja_abierta_por_responsable')),
        migrations.AddIndex(model_name='cortecaja', index=models.Index(fields=['institucion', 'estado', 'abierto_el'], name='corte_inst_estado_fecha_idx')),
    ]
