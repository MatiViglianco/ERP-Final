from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from statsapp.models import AccountClient, AccountTransaction
from statsapp.views import (
    _normalize_account_tx_status,
    _parse_decimal,
    _recalc_account_totals,
    account_client_pay,
    account_client_view,
    account_clients_stats,
    account_transaction_delete,
)


class AccountCalculationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='admin',
            password='admin',
            is_staff=True,
        )

    def test_recalc_ignores_paid_overdue_transactions_for_client_status(self):
        client = AccountClient.objects.create(external_id='client-1', first_name='Test', last_name='Client')
        AccountTransaction.objects.create(
            client=client,
            external_id='paid-overdue',
            original_amount=Decimal('100'),
            paid_amount=Decimal('150'),
            status=AccountTransaction.Status.OVERDUE,
        )
        AccountTransaction.objects.create(
            client=client,
            external_id='pending-active',
            original_amount=Decimal('80'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )

        _recalc_account_totals([client.id])

        client.refresh_from_db()
        self.assertEqual(client.total_debt, Decimal('80.00'))
        self.assertEqual(client.status, AccountClient.Status.ACTIVE)

    def test_detail_totals_sum_clamped_remaining_per_transaction(self):
        client = AccountClient.objects.create(external_id='client-2', first_name='Test', last_name='Client')
        AccountTransaction.objects.create(
            client=client,
            external_id='overpaid',
            original_amount=Decimal('100'),
            paid_amount=Decimal('150'),
            status=AccountTransaction.Status.PAID,
        )
        AccountTransaction.objects.create(
            client=client,
            external_id='pending',
            original_amount=Decimal('80'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )
        request = APIRequestFactory().get(f'/api/accounts/clients/{client.id}/')
        force_authenticate(request, user=self.user)

        response = account_client_view(request, pk=client.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['totals']['original'], 180.0)
        self.assertEqual(response.data['totals']['paid'], 150.0)
        self.assertEqual(response.data['totals']['remaining'], 80.0)

    def test_import_value_normalization(self):
        self.assertEqual(_parse_decimal('$ 1.234,50'), Decimal('1234.5'))
        self.assertEqual(
            _normalize_account_tx_status('overdue', original_amount=Decimal('10'), paid_amount=Decimal('0')),
            AccountTransaction.Status.OVERDUE,
        )
        self.assertEqual(
            _normalize_account_tx_status('active', original_amount=Decimal('10'), paid_amount=Decimal('5')),
            AccountTransaction.Status.PARTIAL,
        )
        self.assertEqual(
            _normalize_account_tx_status('vencido', original_amount=Decimal('10'), paid_amount=Decimal('10')),
            AccountTransaction.Status.PAID,
        )

    def test_stats_use_transaction_date_not_created_at_month(self):
        client = AccountClient.objects.create(external_id='client-3', first_name='Test', last_name='Client')
        # Movimiento con fecha real de vale el 31/5, pero cargado/importado el 2/6.
        # El reporte debe agruparlo por la fecha del vale (mayo), no por la fecha de carga.
        AccountTransaction.objects.create(
            client=client,
            external_id='loaded-in-june-dated-may',
            date=date(2026, 5, 31),
            created_at=timezone.make_aware(datetime(2026, 6, 2, 22, 50, 39)),
            original_amount=Decimal('100'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )
        factory = APIRequestFactory()

        may_request = factory.get('/api/accounts/clients/stats/?year=2026&month=5')
        force_authenticate(may_request, user=self.user)
        may_response = account_clients_stats(may_request)

        june_request = factory.get('/api/accounts/clients/stats/?year=2026&month=6')
        force_authenticate(june_request, user=self.user)
        june_response = account_clients_stats(june_request)

        self.assertEqual(may_response.status_code, 200)
        self.assertEqual(june_response.status_code, 200)
        # Junio queda vacío: el movimiento pertenece a mayo por su fecha de vale.
        self.assertEqual(june_response.data['results'], [])
        self.assertEqual(may_response.data['year_totals']['original'], 100.0)
        self.assertEqual(may_response.data['results'][0]['month'], '2026-05')
        self.assertEqual(may_response.data['results'][0]['days'][0]['date'], '2026-05-31')

    def test_payment_response_includes_changed_transactions_and_totals(self):
        client = AccountClient.objects.create(external_id='client-4', first_name='Test', last_name='Client')
        AccountTransaction.objects.create(
            client=client,
            external_id='pay-me',
            original_amount=Decimal('100'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )
        AccountTransaction.objects.create(
            client=client,
            external_id='keep-pending',
            original_amount=Decimal('50'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )
        _recalc_account_totals([client.id])
        request = APIRequestFactory().post(
            f'/api/accounts/clients/{client.id}/pay/',
            {'mode': 'selected', 'transaction_ids': ['pay-me']},
            format='json',
        )
        force_authenticate(request, user=self.user)

        response = account_client_pay(request, pk=client.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['client']['total_debt'], 50.0)
        self.assertEqual(response.data['totals']['remaining'], 50.0)
        self.assertEqual(len(response.data['transactions']), 1)
        self.assertEqual(response.data['transactions'][0]['id'], 'pay-me')
        self.assertEqual(response.data['transactions'][0]['remaining'], 0.0)
        self.assertEqual(response.data['transactions'][0]['status'], AccountTransaction.Status.PAID)

    def test_delete_transaction_response_includes_removed_id_client_and_totals(self):
        client = AccountClient.objects.create(external_id='client-5', first_name='Test', last_name='Client')
        AccountTransaction.objects.create(
            client=client,
            external_id='delete-me',
            original_amount=Decimal('100'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )
        AccountTransaction.objects.create(
            client=client,
            external_id='keep-me',
            original_amount=Decimal('25'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )
        _recalc_account_totals([client.id])
        request = APIRequestFactory().delete('/api/accounts/transactions/delete-me/')
        force_authenticate(request, user=self.user)

        response = account_transaction_delete(request, external_id='delete-me')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['deleted_transaction_id'], 'delete-me')
        self.assertEqual(response.data['client']['total_debt'], 25.0)
        self.assertEqual(response.data['totals']['original'], 25.0)
        self.assertEqual(response.data['totals']['remaining'], 25.0)
