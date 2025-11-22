from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('statsapp', '0006_accountclient_phone'),
    ]

    operations = [
        migrations.CreateModel(
            name='SalesManualEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('anulado', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('fc_inicial', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('pagos', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('debitos', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('gastos', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('vales', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('fc_final', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('total', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sales_manual_entries', to='statsapp.uploadbatch')),
            ],
            options={
                'ordering': ['date'],
            },
        ),
        migrations.AddIndex(
            model_name='salesmanualentry',
            index=models.Index(fields=['batch', 'date'], name='statsapp_sa_batch__2f61cb_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='salesmanualentry',
            unique_together={('batch', 'date')},
        ),
    ]
