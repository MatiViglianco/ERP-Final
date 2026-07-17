from django.db import migrations


PRIMARY_BRANCH_NAME = 'Sucursal Primaria'
PRIMARY_BRANCH_SLUG = 'sucursal-primaria'


def seed_primary_branch(apps, schema_editor):
    Branch = apps.get_model('statsapp', 'Branch')
    branch = Branch.objects.filter(slug=PRIMARY_BRANCH_SLUG).first()
    if branch is None:
        branch = Branch.objects.filter(name=PRIMARY_BRANCH_NAME).first()
    if branch is None:
        branch = Branch.objects.create(
            name=PRIMARY_BRANCH_NAME,
            slug=PRIMARY_BRANCH_SLUG,
            active=True,
        )
    elif not branch.active:
        branch.active = True
        branch.save(update_fields=['active', 'updated_at'])

    for model_name in (
        'UploadBatch',
        'AccountTransaction',
        'ExpenseEntry',
        'Payment',
        'Invoice',
        'GetnetTerminal',
    ):
        model = apps.get_model('statsapp', model_name)
        model.objects.filter(branch__isnull=True).update(branch_id=branch.id)


class Migration(migrations.Migration):

    dependencies = [
        ('statsapp', '0017_invoice_branch_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_primary_branch, migrations.RunPython.noop),
    ]
