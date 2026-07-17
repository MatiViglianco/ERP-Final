from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ProductionUpgradeMigrationTests(TransactionTestCase):
    migrate_from = ('statsapp', '0012_recalculate_account_client_totals')
    migrate_to = ('statsapp', '0018_seed_primary_branch')

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps

        UploadBatch = old_apps.get_model('statsapp', 'UploadBatch')
        Record = old_apps.get_model('statsapp', 'Record')
        AccountClient = old_apps.get_model('statsapp', 'AccountClient')
        AccountTransaction = old_apps.get_model('statsapp', 'AccountTransaction')
        ExpenseEntry = old_apps.get_model('statsapp', 'ExpenseEntry')
        BankUploadBatch = old_apps.get_model('statsapp', 'BankUploadBatch')
        BankTransaction = old_apps.get_model('statsapp', 'BankTransaction')

        batch = UploadBatch.objects.create(
            original_filename='kretz-produccion.csv',
            single_date=date(2026, 5, 31),
            is_single_day=True,
            note='Carga historica',
        )
        Record.objects.create(
            batch=batch,
            cod_seccion='1',
            dsc_seccion='CARNES',
            cod_familia='10',
            dsc_familia='VACUNO',
            nro_plu='100',
            nom_plu='COSTILLA',
            uni='kg',
            peso=Decimal('2.50'),
            imp=Decimal('50000'),
        )
        client = AccountClient.objects.create(
            external_id='prod-client-1',
            first_name='Cliente',
            last_name='Historico',
            total_debt=Decimal('120000'),
            phone='',
        )
        transaction = AccountTransaction.objects.create(
            client=client,
            external_id='prod-account-tx-1',
            description='Compra cuenta corriente',
            date=date(2026, 5, 31),
            original_amount=Decimal('120000'),
            paid_amount=Decimal('20000'),
        )
        expense = ExpenseEntry.objects.create(
            external_id='prod-expense-1',
            date=date(2026, 5, 31),
            amount=Decimal('30000'),
            method='cash',
            category='SUELDOS',
            subcategory='ADELANTO',
            description='Adelanto historico',
        )
        bank_batch = BankUploadBatch.objects.create(
            bank='santander',
            original_filename='santander-produccion.csv',
        )
        bank_transaction = BankTransaction.objects.create(
            batch=bank_batch,
            date=date(2026, 5, 31),
            concept='Credito transf online banking emp - De Getnet Argentina SAU',
            description='Liquidacion Getnet',
            amount=95000,
        )

        self.ids = {
            'batch': batch.pk,
            'client': client.pk,
            'transaction': transaction.pk,
            'expense': expense.pk,
            'bank_transaction': bank_transaction.pk,
        }

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        super().tearDown()

    def test_upgrade_preserves_production_data_and_scopes_historical_records(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_to])
        apps = self.executor.loader.project_state([self.migrate_to]).apps

        Branch = apps.get_model('statsapp', 'Branch')
        UploadBatch = apps.get_model('statsapp', 'UploadBatch')
        Record = apps.get_model('statsapp', 'Record')
        AccountClient = apps.get_model('statsapp', 'AccountClient')
        AccountTransaction = apps.get_model('statsapp', 'AccountTransaction')
        ExpenseEntry = apps.get_model('statsapp', 'ExpenseEntry')
        BankTransaction = apps.get_model('statsapp', 'BankTransaction')
        Invoice = apps.get_model('statsapp', 'Invoice')
        Payment = apps.get_model('statsapp', 'Payment')

        primary = Branch.objects.get(slug='sucursal-primaria')
        batch = UploadBatch.objects.get(pk=self.ids['batch'])
        transaction = AccountTransaction.objects.get(pk=self.ids['transaction'])
        expense = ExpenseEntry.objects.get(pk=self.ids['expense'])
        client = AccountClient.objects.get(pk=self.ids['client'])
        bank_transaction = BankTransaction.objects.get(pk=self.ids['bank_transaction'])

        self.assertEqual(batch.branch_id, primary.id)
        self.assertEqual(transaction.branch_id, primary.id)
        self.assertEqual(expense.branch_id, primary.id)
        self.assertEqual(Record.objects.get(batch_id=batch.id).imp, 50000)
        self.assertEqual(client.total_debt, Decimal('120000.00'))
        self.assertEqual(transaction.original_amount, Decimal('120000.00'))
        self.assertEqual(transaction.paid_amount, Decimal('20000.00'))
        self.assertEqual(expense.amount, Decimal('30000.00'))
        self.assertEqual(bank_transaction.amount, 95000)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
