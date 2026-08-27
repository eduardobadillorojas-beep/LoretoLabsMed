from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('core', '0029_corte_caja')]
    operations = [
        migrations.AddField(model_name='cortecaja', name='numero_movimientos', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='cortecaja', name='total_entradas_efectivo', field=models.DecimalField(decimal_places=2, default=0, max_digits=12)),
        migrations.AddField(model_name='cortecaja', name='total_retiros_efectivo', field=models.DecimalField(decimal_places=2, default=0, max_digits=12)),
        migrations.CreateModel(name='MovimientoCaja', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('tipo', models.CharField(choices=[('ENTRADA', 'Entrada extraordinaria'), ('RETIRO', 'Retiro de efectivo')], max_length=10)),
            ('monto', models.DecimalField(decimal_places=2, max_digits=12)),
            ('motivo', models.CharField(max_length=300)),
            ('creado_el', models.DateTimeField(auto_now_add=True)),
            ('corte', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='movimientos', to='core.cortecaja')),
            ('registrado_por', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='movimientos_caja_registrados', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ['creado_el', 'pk']}),
        migrations.AddIndex(model_name='movimientocaja', index=models.Index(fields=['corte', 'tipo', 'creado_el'], name='mov_caja_corte_tipo_idx')),
    ]
