from django.db import migrations, models
import django.db.models.deletion


def backfill_employee_branches(apps, schema_editor):
    Branch = apps.get_model('statsapp', 'Branch')
    Employee = apps.get_model('statsapp', 'Employee')
    EmployeeMovement = apps.get_model('statsapp', 'EmployeeMovement')

    primary = Branch.objects.filter(slug='sucursal-primaria').first()
    if not primary:
        primary = Branch.objects.filter(active=True).order_by('id').first()
    if not primary:
        primary = Branch.objects.create(
            name='Sucursal Primaria',
            slug='sucursal-primaria',
            active=True,
        )

    Employee.objects.filter(branch__isnull=True).update(branch=primary)
    for movement in EmployeeMovement.objects.filter(branch__isnull=True).select_related('employee'):
        movement.branch_id = movement.employee.branch_id or primary.id
        movement.save(update_fields=['branch'])


class Migration(migrations.Migration):

    dependencies = [
        ('statsapp', '0022_employee_account_discount_percent_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='branch',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='employees',
                to='statsapp.branch',
            ),
        ),
        migrations.AddField(
            model_name='employeemovement',
            name='branch',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='employee_movements',
                to='statsapp.branch',
            ),
        ),
        migrations.RunPython(backfill_employee_branches, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['branch', 'active', 'name'], name='statsapp_em_branch__f890a4_idx'),
        ),
        migrations.AddIndex(
            model_name='employeemovement',
            index=models.Index(fields=['branch', '-date'], name='statsapp_em_branch__b8f387_idx'),
        ),
    ]
