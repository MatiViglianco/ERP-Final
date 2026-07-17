from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.db.models.query import QuerySet
from django.test import TestCase
from rest_framework.test import APIClient

from statsapp.models import (
    AccountClient,
    AccountTransaction,
    BankTransaction,
    BankUploadBatch,
    EmployeeMovement,
    ExpenseEntry,
)
from statsapp.salary_services import create_employee, salaries_summary, sync_employee_movements


class SalaryFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='admin',
            password='admin123',
            is_staff=True,
            is_superuser=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.employee_client = AccountClient.objects.create(
            external_id='EMP-DIEGO',
            first_name='Diego',
            last_name='Empleado',
        )
        self.employee = create_employee(
            'Diego Empleado',
            aliases=['DIEGO', 'DIEGO EMP'],
            account_client=self.employee_client,
        )

    def test_salaries_summary_collects_transfer_cash_and_account_current(self):
        batch = BankUploadBatch.objects.create(
            bank='santander',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 5),
            concept='TRANSFERENCIA DIEGO EMP',
            description='Pago empleado',
            amount=-100000,
        )
        ExpenseEntry.objects.create(
            date=date(2026, 7, 6),
            amount=Decimal('25000'),
            method=ExpenseEntry.Method.CASH,
            category='SUELDOS',
            subcategory='DIEGO',
            description='Efectivo entregado',
        )
        AccountTransaction.objects.create(
            client=self.employee_client,
            external_id='cc-diego-1',
            description='Retiro mercaderia',
            date=date(2026, 7, 7),
            original_amount=Decimal('12000'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
        )

        first = salaries_summary(date(2026, 7, 1), date(2026, 7, 31), sync=True)
        second = salaries_summary(date(2026, 7, 1), date(2026, 7, 31), sync=True)

        self.assertEqual(EmployeeMovement.objects.count(), 3)
        self.assertEqual(first['totals']['bank_transfer'], 100000.0)
        self.assertEqual(first['totals']['cash_expense'], 25000.0)
        self.assertEqual(first['totals']['account_current'], 12000.0)
        self.assertEqual(first['totals']['total'], 137000.0)
        self.assertEqual(second['sync']['created'], 0)
        self.assertEqual(len(second['movements']), 3)

    def test_salaries_dashboard_endpoint_returns_employee_rows(self):
        ExpenseEntry.objects.create(
            date=date(2026, 7, 10),
            amount=Decimal('35000'),
            method=ExpenseEntry.Method.CASH,
            category='SUELDOS',
            subcategory='DIEGO',
            description='Adelanto',
        )

        response = self.api.get('/api/salaries/summary/?year=2026&month=7')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['totals']['cash_expense'], 35000.0)
        self.assertEqual(response.data['employees'][0]['employee_name'], 'Diego Empleado')

    def test_salary_sync_rolls_back_partial_results_on_database_error(self):
        batch = BankUploadBatch.objects.create(
            bank='santander',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 5),
            concept='TRANSFERENCIA DIEGO EMP',
            amount=-100000,
        )
        ExpenseEntry.objects.create(
            date=date(2026, 7, 6),
            amount=Decimal('25000'),
            method=ExpenseEntry.Method.CASH,
            category='SUELDOS',
            subcategory='DIEGO',
        )

        original_update_or_create = QuerySet.update_or_create
        call_count = 0

        def fail_second_update(queryset, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise OperationalError('database is locked')
            return original_update_or_create(queryset, *args, **kwargs)

        with patch.object(QuerySet, 'update_or_create', new=fail_second_update):
            with self.assertRaises(OperationalError):
                sync_employee_movements(date(2026, 7, 1), date(2026, 7, 31))

        self.assertEqual(EmployeeMovement.objects.count(), 0)

    @patch('statsapp.salary_services.sleep')
    @patch('statsapp.salary_services.sync_employee_movements')
    def test_salary_summary_retries_transient_database_error(self, sync_mock, sleep_mock):
        sync_mock.side_effect = [
            OperationalError('database is locked'),
            {'created': 0, 'updated': 0},
        ]

        result = salaries_summary(date(2026, 7, 1), date(2026, 7, 31), sync=True)

        self.assertEqual(sync_mock.call_count, 2)
        sleep_mock.assert_called_once_with(0.05)
        self.assertEqual(result['sync'], {'created': 0, 'updated': 0})

    def test_create_employee_endpoint_adds_aliases(self):
        client = AccountClient.objects.create(
            external_id='EMP-ROCIO',
            first_name='Rocio',
            last_name='Empleado',
        )

        response = self.api.post('/api/salaries/employees/', {
            'name': 'Rocio Empleado',
            'aliases': ['ROCIO', 'ROCI'],
            'account_client_id': str(client.id),
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertIn('ROCIO', response.data['aliases'])
        self.assertEqual(response.data['account_client_name'], 'Empleado, Rocio')
