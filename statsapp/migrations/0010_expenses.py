from django.db import migrations, models
import django.db.models.deletion
import uuid
import decimal


class Migration(migrations.Migration):

    dependencies = [
        ('statsapp', '0009_useractivity'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExpenseCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ExpenseEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('external_id', models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ('date', models.DateField()),
                ('amount', models.DecimalField(decimal_places=2, default=decimal.Decimal('0'), max_digits=14)),
                ('method', models.CharField(choices=[('EFECTIVO', 'Efectivo'), ('TRANSFERENCIA', 'Transferencia'), ('CHEQUE', 'Cheque')], default='EFECTIVO', max_length=32)),
                ('category', models.CharField(blank=True, max_length=100)),
                ('subcategory', models.CharField(blank=True, max_length=100)),
                ('description', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ExpenseSubcategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subcategories', to='statsapp.expensecategory')),
            ],
            options={
                'ordering': ['name'],
                'unique_together': {('category', 'name')},
            },
        ),
        migrations.CreateModel(
            name='BankExpenseAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(max_length=128, unique=True)),
                ('category', models.CharField(blank=True, max_length=100)),
                ('subcategory', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='expensesubcategory',
            index=models.Index(fields=['category', 'name'], name='expense_subcat_cat_name_idx'),
        ),
        migrations.AddIndex(
            model_name='expenseentry',
            index=models.Index(fields=['date'], name='expenseentry_date_idx'),
        ),
        migrations.AddIndex(
            model_name='expenseentry',
            index=models.Index(fields=['category'], name='expenseentry_category_idx'),
        ),
        migrations.AddIndex(
            model_name='expenseentry',
            index=models.Index(fields=['subcategory'], name='expenseentry_subcategory_idx'),
        ),
        migrations.AddIndex(
            model_name='bankexpenseassignment',
            index=models.Index(fields=['external_id'], name='bankexpense_external_id_idx'),
        ),
    ]
