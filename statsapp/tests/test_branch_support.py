from datetime import date
from decimal import Decimal
from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from statsapp.models import (
    AccountClient,
    AccountTransaction,
    Branch,
    ExpenseEntry,
    GetnetTerminal,
    Invoice,
    Payment,
    Record,
    UploadBatch,
)


class PrimaryBranchBackfillTests(TestCase):
    def test_assigns_existing_unscoped_data_to_primary_branch(self):
        client = AccountClient.objects.create(
            external_id='historical-client',
            first_name='Cliente',
            last_name='Historico',
        )
        batch = UploadBatch.objects.create(single_date=date(2026, 5, 31), is_single_day=True)
        transaction = AccountTransaction.objects.create(
            client=client,
            external_id='historical-tx',
            date=date(2026, 5, 31),
            original_amount=Decimal('1000'),
        )
        expense = ExpenseEntry.objects.create(
            date=date(2026, 5, 31),
            amount=Decimal('500'),
            method=ExpenseEntry.Method.CASH,
            category='SUELDOS',
        )
        payment = Payment.objects.create(
            source=Payment.Source.GETNET,
            amount=Decimal('250'),
            idempotency_key='historical-payment',
        )
        invoice = Invoice.objects.create(idempotency_key='historical-invoice')
        terminal = GetnetTerminal.objects.create(code='HISTORICAL-TERMINAL')

        migration = import_module('statsapp.migrations.0018_seed_primary_branch')
        migration.seed_primary_branch(django_apps, None)

        branch = Branch.objects.get(slug='sucursal-primaria')
        for instance in (batch, transaction, expense, payment, invoice, terminal):
            instance.refresh_from_db()
            self.assertEqual(instance.branch_id, branch.id)



class BranchSupportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='admin',
            password='admin123',
            is_staff=True,
            is_superuser=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.branch_a = Branch.objects.create(name='Casa Central', slug='casa-central')
        self.branch_b = Branch.objects.create(name='Sucursal Norte', slug='sucursal-norte')

    def test_kretz_stats_are_filtered_by_branch(self):
        batch_a = UploadBatch.objects.create(
            branch=self.branch_a,
            single_date=date(2026, 7, 10),
            is_single_day=True,
        )
        batch_b = UploadBatch.objects.create(
            branch=self.branch_b,
            single_date=date(2026, 7, 10),
            is_single_day=True,
        )
        Record.objects.create(batch=batch_a, dsc_seccion='CARNES', nom_plu='ASADO', imp=1000, peso=2, units=0)
        Record.objects.create(batch=batch_b, dsc_seccion='CARNES', nom_plu='ASADO', imp=3000, peso=6, units=0)

        response = self.api.get(f'/api/stats/?branch_id={self.branch_a.id}&fecha_desde=2026-07-10&fecha_hasta=2026-07-10')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['totals']['imp'], 1000.0)
        self.assertEqual(response.data['totals']['peso'], 2.0)

    def test_expenses_are_filtered_and_created_by_branch(self):
        ExpenseEntry.objects.create(
            branch=self.branch_a,
            date=date(2026, 7, 10),
            amount=Decimal('1000'),
            method=ExpenseEntry.Method.CASH,
            category='SUELDOS',
            subcategory='ADELANTO',
        )
        ExpenseEntry.objects.create(
            branch=self.branch_b,
            date=date(2026, 7, 10),
            amount=Decimal('5000'),
            method=ExpenseEntry.Method.CASH,
            category='SUELDOS',
            subcategory='ADELANTO',
        )

        list_response = self.api.get(f'/api/expenses/?branch_id={self.branch_a.id}')
        create_response = self.api.post('/api/expenses/', {
            'branch_id': str(self.branch_a.id),
            'date': '2026-07-11',
            'amount': '2500',
            'method': ExpenseEntry.Method.CASH,
            'category': 'COMIDA',
            'subcategory': 'LOCAL',
        }, format='json')

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]['amount'], 1000.0)
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data['branch']['id'], self.branch_a.id)

    def test_account_current_detail_and_payments_are_filtered_by_branch(self):
        client = AccountClient.objects.create(
            external_id='client-branch',
            first_name='Cliente',
            last_name='Compartido',
        )
        AccountTransaction.objects.create(
            client=client,
            branch=self.branch_a,
            external_id='tx-a',
            date=date(2026, 7, 10),
            original_amount=Decimal('1000'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )
        AccountTransaction.objects.create(
            client=client,
            branch=self.branch_b,
            external_id='tx-b',
            date=date(2026, 7, 10),
            original_amount=Decimal('9000'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )

        detail = self.api.get(f'/api/accounts/clients/{client.id}/?branch_id={self.branch_a.id}')
        pay = self.api.post(f'/api/accounts/clients/{client.id}/pay/', {
            'branch_id': str(self.branch_a.id),
            'mode': 'full',
        }, format='json')

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['totals']['remaining'], 1000.0)
        self.assertEqual([tx['id'] for tx in detail.data['transactions']], ['tx-a'])
        self.assertEqual(pay.status_code, 200)
        self.assertEqual(pay.data['totals']['remaining'], 0.0)

        tx_b = AccountTransaction.objects.get(external_id='tx-b')
        self.assertEqual(tx_b.paid_amount, Decimal('0.00'))
