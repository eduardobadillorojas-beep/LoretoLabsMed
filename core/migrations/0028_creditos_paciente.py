from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import core.models
import uuid

class Migration(migrations.Migration):
    dependencies = [('core', '0027_cancelacion_reembolso_cobro')]
    operations = [
        migrations.CreateModel(name='CreditoPaciente', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('folio', models.CharField(default=core.models.generar_folio_credito, editable=False, max_length=30, unique=True)),
            ('total', models.DecimalField(decimal_places=2, max_digits=12)), ('saldo', models.DecimalField(decimal_places=2, max_digits=12)),
            ('numero_cuotas', models.PositiveIntegerField(default=1)), ('fecha_vencimiento', models.DateField()),
            ('estado', models.CharField(choices=[('VIGENTE','Vigente'),('LIQUIDADO','Liquidado'),('VENCIDO','Vencido'),('CANCELADO','Cancelado')], default='VIGENTE', max_length=20)),
            ('notas', models.CharField(blank=True, max_length=300, null=True)), ('creado_el', models.DateTimeField(auto_now_add=True)), ('actualizado_el', models.DateTimeField(auto_now=True)),
            ('autorizado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='creditos_autorizados', to=settings.AUTH_USER_MODEL)),
            ('creado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='creditos_registrados', to=settings.AUTH_USER_MODEL)),
            ('institucion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='creditos', to='core.institucion')),
            ('paciente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='creditos', to='core.paciente')),
        ], options={'ordering':['-creado_el']}),
        migrations.CreateModel(name='AbonoCredito', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('folio', models.CharField(default=core.models.generar_folio_abono, editable=False, max_length=30, unique=True)), ('token_publico', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ('monto', models.DecimalField(decimal_places=2, max_digits=12)), ('forma_pago', models.CharField(choices=[('EFECTIVO','Efectivo'),('TARJETA','Tarjeta'),('TRANSFERENCIA','Transferencia'),('OTRO','Otro')], default='EFECTIVO', max_length=20)), ('referencia', models.CharField(blank=True, max_length=100, null=True)), ('monto_recibido', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)), ('cambio', models.DecimalField(decimal_places=2, default=0, max_digits=12)), ('creado_el', models.DateTimeField(auto_now_add=True)),
            ('credito', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='abonos', to='core.creditopaciente')), ('registrado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='abonos_credito_registrados', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering':['creado_el','pk']}),
        migrations.CreateModel(name='PagoAbonoCredito', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('forma_pago', models.CharField(choices=[('EFECTIVO','Efectivo'),('TARJETA','Tarjeta'),('TRANSFERENCIA','Transferencia'),('OTRO','Otro')], max_length=20)), ('monto', models.DecimalField(decimal_places=2, max_digits=12)), ('referencia', models.CharField(blank=True, max_length=100, null=True)), ('abono', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pagos', to='core.abonocredito')),
        ], options={'ordering':['pk']}),
        migrations.AddField(model_name='cargopaciente', name='credito', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cargos', to='core.creditopaciente')),
        migrations.AlterField(model_name='cargopaciente', name='estado', field=models.CharField(choices=[('PENDIENTE','Pendiente'),('CREDITO','A crédito'),('PAGADO','Pagado'),('CANCELADO','Cancelado')], default='PENDIENTE', max_length=20)),
        migrations.AddIndex(model_name='creditopaciente', index=models.Index(fields=['institucion','paciente','estado'], name='credito_inst_pac_estado_idx')),
    ]
