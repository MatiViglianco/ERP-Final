from decimal import Decimal

from django.db import migrations


def recalculate_account_client_totals(apps, schema_editor):
    AccountClient = apps.get_model('statsapp', 'AccountClient')
    AccountTransaction = apps.get_model('statsapp', 'AccountTransaction')

    for client in AccountClient.objects.all().iterator(chunk_size=1000):
        total_debt = Decimal('0')
        has_overdue = False
        has_partial = False

        transactions = AccountTransaction.objects.filter(client_id=client.id).only(
            'original_amount',
            'paid_amount',
            'status',
        )
        for tx in transactions.iterator(chunk_size=1000):
            original = tx.original_amount or Decimal('0')
            paid = tx.paid_amount or Decimal('0')
            remaining = original - paid
            if remaining <= Decimal('0'):
                continue
            total_debt += remaining
            if tx.status == 'vencido':
                has_overdue = True
            elif tx.status == 'parcial':
                has_partial = True

        if total_debt <= Decimal('0'):
            status = 'paid'
        elif has_overdue:
            status = 'overdue'
        elif has_partial:
            status = 'partial'
        else:
            status = 'active'

        AccountClient.objects.filter(id=client.id).update(total_debt=total_debt, status=status)


class Migration(migrations.Migration):

    dependencies = [
        ('statsapp', '0010_expenses'),
    ]

    operations = [
        migrations.RunPython(recalculate_account_client_totals, migrations.RunPython.noop),
    ]
