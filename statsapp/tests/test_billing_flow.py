import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from statsapp.fiscal_services import account_invoice_preview, process_getnet_webhook
from statsapp.models import (
    AccountClient,
    AccountTransaction,
    BankTransaction,
    BankUploadBatch,
    Branch,
    GetnetTerminal,
    Invoice,
    Payment,
)


class BillingFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='admin',
            password='admin123',
            is_staff=True,
            is_superuser=True,
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)
        self.account = AccountClient.objects.create(
            external_id='C-100',
            first_name='Ana',
            last_name='Perez',
            total_debt=Decimal('1500'),
        )
        self.tx = AccountTransaction.objects.create(
            client=self.account,
            external_id='tx-1',
            description='Venta cuenta corriente',
            date=date(2026, 7, 10),
            original_amount=Decimal('1500'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )

    def getnet_csv_file(self, *, transaction_id='getnet-tx-1', terminal='AR002R9R', status='Liquidado', amount='24363'):
        content = (
            'Nro de Establecimiento,Nombre Establecimiento,Fecha de Operación,Tipo de Transacción,'
            'Canal,Modo de Canal,Código del POS,Estado,Cód. de Transacción,Moneda,'
            'Monto Bruto Transacción,Monto Neto Transacción,Nro de Cupón,Cód. Aut.\n'
            f'0000109768,LA CARNICERIA,14/07/2026 09:14:49,Venta,pos,chip,{terminal},'
            f'{status},{transaction_id},ARS,{amount},"24068,21",16362,175503\n'
        )
        return SimpleUploadedFile('getnet.csv', content.encode('utf-8'), content_type='text/csv')

    def test_getnet_csv_import_is_idempotent_and_maps_terminal_to_branch(self):
        branch, _ = Branch.objects.get_or_create(
            slug='sucursal-primaria',
            defaults={'name': 'Sucursal Primaria'},
        )

        first = self.client_api.post(
            '/api/billing/getnet/import/',
            {'file': self.getnet_csv_file(), 'branch_id': str(branch.id)},
            format='multipart',
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['created'], 1)
        payment = Payment.objects.get(external_id='getnet-tx-1')
        self.assertEqual(payment.status, Payment.Status.RECONCILED)
        self.assertEqual(payment.provider_status, 'Liquidado')
        self.assertEqual(payment.amount, Decimal('24363.00'))
        self.assertEqual(payment.branch, branch)
        self.assertEqual(payment.terminal.code, 'AR002R9R')

        second = self.client_api.post(
            '/api/billing/getnet/import/',
            {
                'file': self.getnet_csv_file(status='Pendiente', amount='25000'),
                'branch_id': str(branch.id),
            },
            format='multipart',
        )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['created'], 0)
        self.assertEqual(second.data['updated'], 1)
        self.assertEqual(Payment.objects.filter(external_id='getnet-tx-1').count(), 1)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.provider_status, 'Pendiente')
        self.assertEqual(payment.amount, Decimal('25000.00'))

    def test_unknown_getnet_terminal_can_be_assigned_after_import(self):
        response = self.client_api.post(
            '/api/billing/getnet/import/',
            {'file': self.getnet_csv_file(terminal='AR009XYZ')},
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['unassigned_terminals'][0]['code'], 'AR009XYZ')
        terminal = GetnetTerminal.objects.get(code='AR009XYZ')
        self.assertIsNone(terminal.branch_id)

        branch = Branch.objects.create(name='Sucursal Secundaria', slug='sucursal-secundaria')
        assigned = self.client_api.patch(
            f'/api/billing/getnet/terminals/{terminal.id}/',
            {'branch_id': branch.id},
            format='json',
        )

        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(assigned.data['branch']['name'], 'Sucursal Secundaria')
        self.assertEqual(Payment.objects.get(external_id='getnet-tx-1').branch, branch)

    def test_billing_summary_filters_getnet_collection_by_terminal(self):
        branch, _ = Branch.objects.get_or_create(
            slug='sucursal-primaria',
            defaults={'name': 'Sucursal Primaria'},
        )
        terminal_one = GetnetTerminal.objects.create(code='AR002R9R', branch=branch)
        terminal_two = GetnetTerminal.objects.create(code='AR009XYZ')
        Payment.objects.create(
            source=Payment.Source.GETNET,
            status=Payment.Status.RECONCILED,
            date=date(2026, 7, 10),
            amount=Decimal('1000'),
            idempotency_key='getnet:terminal-one',
            terminal=terminal_one,
            branch=branch,
        )
        Payment.objects.create(
            source=Payment.Source.GETNET,
            status=Payment.Status.RECONCILED,
            date=date(2026, 7, 10),
            amount=Decimal('2000'),
            idempotency_key='getnet:terminal-two',
            terminal=terminal_two,
        )

        response = self.client_api.get(
            f'/api/billing/summary/?year=2026&month=7&terminal_id={terminal_one.id}'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['collections']['getnet'], 1000.0)

    def test_billing_summary_does_not_count_getnet_bank_settlements_twice(self):
        Payment.objects.create(
            source=Payment.Source.GETNET,
            status=Payment.Status.RECONCILED,
            date=date(2026, 7, 10),
            amount=Decimal('1000'),
            idempotency_key='getnet:gross-sale',
        )
        batch = BankUploadBatch.objects.create(bank='santander')
        BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 11),
            concept='Credito transf online banking emp - De Getnet Argentina SAU',
            amount=950,
        )
        BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 11),
            concept='Transferencia recibida - Cliente mostrador',
            amount=200,
        )

        response = self.client_api.get('/api/billing/summary/?year=2026&month=7')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['collections']['getnet'], 1000.0)
        self.assertEqual(response.data['collections']['santander'], 200.0)
        self.assertEqual(response.data['getnet']['bank_settled_total'], 950.0)
        self.assertEqual(response.data['getnet']['bank_settled_by_bank']['santander'], 950.0)

    @override_settings(ARCA_PROVIDER='mock', ARCA_DEFAULT_POINT_OF_SALE=5, ARCA_DEFAULT_VOUCHER_TYPE=11)
    def test_create_authorized_invoice_from_account_debt(self):
        response = self.client_api.post(
            f'/api/billing/accounts/{self.account.id}/invoices/',
            {'transaction_ids': ['tx-1'], 'authorize': True},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], Invoice.Status.AUTHORIZED)
        self.assertEqual(response.data['total_amount'], 1500.0)
        self.assertTrue(response.data['cae'].startswith('MOCK'))
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertTrue(AccountTransaction.objects.get(external_id='tx-1').invoice_link)

        duplicate = self.client_api.post(
            f'/api/billing/accounts/{self.account.id}/invoices/',
            {'transaction_ids': ['tx-1'], 'authorize': True},
            format='json',
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn('ya facturados', duplicate.data['detail'])

    def test_account_preview_excludes_already_invoiced_transactions(self):
        first = self.client_api.post(
            f'/api/billing/accounts/{self.account.id}/invoices/',
            {'transaction_ids': ['tx-1'], 'authorize': False},
            format='json',
        )
        self.assertEqual(first.status_code, 201)

        preview = account_invoice_preview(self.account)

        self.assertEqual(preview['total_pending_to_invoice'], 0.0)
        self.assertEqual(preview['transactions'], [])

    @override_settings(ARCA_PROVIDER='mock', ARCA_DEFAULT_POINT_OF_SALE=5, ARCA_DEFAULT_VOUCHER_TYPE=11)
    def test_account_invoice_is_scoped_to_one_branch(self):
        central = Branch.objects.create(name='Casa Central', slug='casa-central')
        north = Branch.objects.create(name='Sucursal Norte', slug='sucursal-norte')
        self.tx.branch = central
        self.tx.save(update_fields=['branch'])
        other_tx = AccountTransaction.objects.create(
            client=self.account,
            branch=north,
            external_id='tx-north',
            description='Venta sucursal norte',
            date=date(2026, 7, 11),
            original_amount=Decimal('2500'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )

        preview = self.client_api.get(
            f'/api/billing/accounts/{self.account.id}/preview/?branch_id={central.id}'
        )
        mixed = self.client_api.post(
            f'/api/billing/accounts/{self.account.id}/invoices/',
            {'transaction_ids': ['tx-1', 'tx-north'], 'authorize': True},
            format='json',
        )
        created = self.client_api.post(
            f'/api/billing/accounts/{self.account.id}/invoices/',
            {'transaction_ids': ['tx-1'], 'branch_id': central.id, 'authorize': True},
            format='json',
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data['branch']['name'], 'Casa Central')
        self.assertEqual([item['id'] for item in preview.data['transactions']], ['tx-1'])
        self.assertEqual(mixed.status_code, 400)
        self.assertIn('distintas sucursales', mixed.data['detail'])
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data['branch']['name'], 'Casa Central')
        self.assertEqual(Invoice.objects.get(pk=created.data['id']).branch, central)
        self.assertFalse(hasattr(other_tx, 'invoice_link'))

    @override_settings(ARCA_PROVIDER='mock')
    def test_getnet_webhook_is_idempotent_and_matches_invoice(self):
        invoice = Invoice.objects.create(
            client=self.account,
            source=Invoice.Source.GETNET,
            status=Invoice.Status.DRAFT,
            external_reference='order-123',
            idempotency_key='order-123',
            total_amount=Decimal('2000'),
            net_amount=Decimal('2000'),
        )
        payload = {
            'id': 'evt-1',
            'payment_id': 'pay-1',
            'order_id': 'order-123',
            'status': 'APPROVED',
            'amount': '2000.00',
        }
        body = json.dumps(payload).encode('utf-8')

        first = process_getnet_webhook(body)
        second = process_getnet_webhook(body)

        invoice.refresh_from_db()
        self.assertFalse(first['duplicate'])
        self.assertTrue(second['duplicate'])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Payment.objects.get().status, Payment.Status.APPROVED)
        self.assertEqual(invoice.status, Invoice.Status.AUTHORIZED)

    def test_unmatched_getnet_payment_needs_review(self):
        payload = {
            'id': 'evt-unmatched',
            'payment_id': 'pay-unmatched',
            'order_id': 'unknown-order',
            'status': 'APPROVED',
            'amount': '500.00',
        }

        result = process_getnet_webhook(json.dumps(payload).encode('utf-8'))

        self.assertFalse(result['duplicate'])
        payment = Payment.objects.get()
        self.assertEqual(payment.status, Payment.Status.NEEDS_REVIEW)
        self.assertIsNone(payment.invoice_id)

    def test_billing_summary_includes_bank_income_and_getnet_payments(self):
        batch = BankUploadBatch.objects.create(
            bank='santander',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 10),
            concept='TRANSFERENCIA',
            amount=1000,
        )
        Payment.objects.create(
            source=Payment.Source.GETNET,
            status=Payment.Status.APPROVED,
            date=date(2026, 7, 10),
            amount=Decimal('750'),
            idempotency_key='getnet-test',
        )
        Payment.objects.create(
            source=Payment.Source.GETNET,
            status=Payment.Status.REJECTED,
            date=date(2026, 7, 10),
            amount=Decimal('999'),
            idempotency_key='getnet-rejected-test',
        )

        response = self.client_api.get('/api/billing/summary/?year=2026&month=7')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['collections']['santander'], 1000.0)
        self.assertEqual(response.data['collections']['getnet'], 750.0)
