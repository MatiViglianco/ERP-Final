from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError
from django.db.models.query import QuerySet
from django.test import TestCase
from rest_framework.test import APIClient

from statsapp.models import (
    AccountClient,
    AccountTransaction,
    BankTransaction,
    BankUploadBatch,
    Employee,
    EmployeeAlias,
    EmployeeMovement,
    EmployeeRemuneration,
    ExpenseCategory,
    ExpenseEntry,
    ExpenseSubcategory,
)
from statsapp.salary_services import (
    aguinaldo_estimate,
    create_employee,
    salaries_monthly_summary,
    salaries_summary,
    save_aguinaldo_remunerations,
    sync_employee_movements,
)


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

    def test_summary_syncs_salary_subcategories_and_detects_all_sources(self):
        salary_category = ExpenseCategory.objects.create(name='SUELDOS')
        ExpenseSubcategory.objects.create(category=salary_category, name='ROCIO')
        batch = BankUploadBatch.objects.create(
            bank='bancon',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 12),
            concept='TRANSFERENCIA HOMEBANKING',
            description='PENDIENTE ROCIO',
            amount=-42000,
        )
        ExpenseEntry.objects.create(
            date=date(2026, 7, 13),
            amount=Decimal('10000'),
            method=ExpenseEntry.Method.CASH,
            category='SUELDOS',
            subcategory='ROCIO',
        )
        employee_client = AccountClient.objects.create(
            external_id='EMP-ROCIO-AUTO',
            first_name='Rocio',
            last_name='Pendiente',
        )
        AccountTransaction.objects.create(
            client=employee_client,
            external_id='cc-pendiente-1',
            description='Consumo empleado sin vincular',
            date=date(2026, 7, 14),
            original_amount=Decimal('7000'),
        )

        first = salaries_summary(date(2026, 7, 1), date(2026, 7, 31), sync=True)
        second = salaries_summary(date(2026, 7, 1), date(2026, 7, 31), sync=True)

        self.assertEqual(first['employee_sync'], {'configured': 1, 'created': 1})
        self.assertEqual(second['employee_sync'], {'configured': 1, 'created': 0})
        self.assertEqual(second['sources']['bank_transactions'], 1)
        self.assertEqual(second['sources']['salary_cash_expenses'], 1)
        self.assertEqual(second['sources']['account_current_transactions'], 1)
        self.assertEqual(second['sources']['latest_bank_dates']['bancon'], '2026-07-12')
        self.assertEqual(second['totals']['bank_transfer'], 42000.0)
        self.assertEqual(second['totals']['cash_expense'], 10000.0)
        self.assertEqual(second['totals']['account_current'], 7000.0)
        self.assertEqual(second['totals']['total'], 59000.0)
        self.assertEqual(Employee.objects.filter(name='ROCIO').count(), 1)
        self.assertTrue(EmployeeAlias.objects.filter(employee__name='ROCIO', normalized_alias='rocio').exists())
        self.assertEqual(EmployeeMovement.objects.filter(employee__name='ROCIO').count(), 3)

    def test_employees_endpoint_syncs_salary_subcategories(self):
        salary_category = ExpenseCategory.objects.create(name='SUELDOS')
        ExpenseSubcategory.objects.create(category=salary_category, name='ZAIRA')

        response = self.api.get('/api/salaries/employees/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('ZAIRA', [employee['name'] for employee in response.data])

    def test_monthly_summary_groups_employee_sources_without_duplicates(self):
        batch = BankUploadBatch.objects.create(
            bank='santander',
            fecha_desde=date(2026, 6, 1),
            fecha_hasta=date(2026, 6, 30),
        )
        BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 6, 10),
            concept='TRANSFERENCIA DIEGO EMP',
            amount=-40000,
        )
        ExpenseEntry.objects.create(
            date=date(2026, 7, 6),
            amount=Decimal('15000'),
            method=ExpenseEntry.Method.CASH,
            category='SUELDOS',
            subcategory='DIEGO',
        )

        first = salaries_monthly_summary(2026, sync=True)
        second = salaries_monthly_summary(2026, sync=True)

        diego = next(row for row in second['employees'] if row['employee_name'] == 'Diego Empleado')
        self.assertEqual(first['sync']['created'], 2)
        self.assertEqual(second['sync']['created'], 0)
        self.assertEqual(diego['total'], 55000.0)
        self.assertEqual(diego['months'][5]['bank_transfer'], 40000.0)
        self.assertEqual(diego['months'][6]['cash_expense'], 15000.0)
        self.assertEqual(len(diego['months']), 12)

    def test_monthly_summary_endpoint_validates_year(self):
        invalid = self.api.get('/api/salaries/monthly/?year=invalid')
        valid = self.api.get('/api/salaries/monthly/?year=2026&sync=0')

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.data['detail'], 'Anio invalido')
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.data['year'], 2026)

    def test_aguinaldo_uses_detected_amounts_until_remunerations_are_confirmed(self):
        EmployeeMovement.objects.create(
            employee=self.employee,
            source=EmployeeMovement.Source.BANK_TRANSFER,
            date=date(2026, 3, 10),
            amount=Decimal('100000'),
        )
        EmployeeMovement.objects.create(
            employee=self.employee,
            source=EmployeeMovement.Source.CASH_EXPENSE,
            date=date(2026, 4, 10),
            amount=Decimal('150000'),
        )

        suggested = aguinaldo_estimate(self.employee, 2026, 1)
        confirmed = save_aguinaldo_remunerations(
            self.employee,
            2026,
            1,
            [{'month': 4, 'amount': '120000'}],
            user=self.user,
        )

        self.assertEqual(suggested['best_month'], 4)
        self.assertEqual(suggested['sac_amount'], 75000.0)
        self.assertFalse(suggested['complete'])
        self.assertEqual(confirmed['best_month'], 4)
        self.assertEqual(confirmed['best_remuneration'], 120000.0)
        self.assertEqual(confirmed['sac_amount'], 60000.0)
        april = next(item for item in confirmed['months'] if item['month'] == 4)
        self.assertTrue(april['confirmed'])
        self.assertEqual(april['confirmed_by'], 'admin')

    def test_aguinaldo_endpoint_saves_values_and_prorates_by_employment_dates(self):
        self.employee.hire_date = date(2026, 3, 1)
        self.employee.save(update_fields=['hire_date'])
        response = self.api.put(
            f'/api/salaries/aguinaldo/?employee_id={self.employee.id}&year=2026&semester=1',
            {
                'remunerations': [
                    {'month': 3, 'amount': '100000'},
                    {'month': 4, 'amount': '120000'},
                    {'month': 5, 'amount': '110000'},
                    {'month': 6, 'amount': '130000'},
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['best_month_label'], 'Junio')
        self.assertEqual(response.data['best_remuneration'], 130000.0)
        self.assertEqual(response.data['worked_days'], 122)
        self.assertEqual(response.data['semester_days'], 181)
        self.assertEqual(response.data['sac_amount'], 43812.15)
        self.assertEqual(response.data['confirmed_months'], 4)
        self.assertEqual(response.data['required_months'], 4)
        self.assertTrue(response.data['complete'])
        self.assertTrue(response.data['employment_period_confirmed'])
        self.assertEqual(EmployeeRemuneration.objects.filter(employee=self.employee, year=2026).count(), 4)

        fetched = self.api.get(f'/api/salaries/aguinaldo/?employee_id={self.employee.id}&year=2026&semester=1')
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.data['sac_amount'], 43812.15)

    def test_aguinaldo_rejects_negative_or_repeated_months(self):
        endpoint = f'/api/salaries/aguinaldo/?employee_id={self.employee.id}&year=2026&semester=1'
        negative = self.api.put(endpoint, {'remunerations': [{'month': 1, 'amount': '-1'}]}, format='json')
        repeated = self.api.put(endpoint, {
            'remunerations': [{'month': 1, 'amount': '100'}, {'month': 1, 'amount': '200'}],
        }, format='json')

        self.assertEqual(negative.status_code, 400)
        self.assertEqual(negative.data['detail'], 'Importe de remuneracion fuera de rango')
        self.assertEqual(repeated.status_code, 400)
        self.assertEqual(repeated.data['detail'], 'Mes invalido o repetido')

    def test_summary_keeps_unmatched_diagnostics_for_api_compatibility(self):
        batch = BankUploadBatch.objects.create(
            bank='bancon',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 12),
            concept='TRANSFERENCIA HOMEBANKING',
            description='PERSONA SIN CONFIGURAR',
            amount=-42000,
        )

        result = salaries_summary(date(2026, 7, 1), date(2026, 7, 31), sync=True)

        self.assertEqual(result['unmatched']['count'], 1)
        self.assertEqual(result['unmatched']['items'][0]['source'], 'bank_transfer')

    def test_assign_pending_bank_transfer_endpoint_remains_available(self):
        batch = BankUploadBatch.objects.create(
            bank='santander',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        bank_tx = BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 15),
            concept='TRANSFERENCIA A TERCEROS',
            description='PEREZ JUAN',
            amount=-55000,
        )

        response = self.api.post('/api/salaries/movements/assign/', {
            'employee_id': str(self.employee.id),
            'source': 'bank_transfer',
            'source_id': str(bank_tx.id),
            'alias': 'PEREZ JUAN',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'manual')
        self.assertTrue(EmployeeAlias.objects.filter(employee=self.employee, normalized_alias='perez juan').exists())
        self.assertTrue(EmployeeMovement.objects.filter(bank_transaction=bank_tx, employee=self.employee).exists())

    def test_assign_account_current_links_client_for_future_movements(self):
        employee_without_account = create_employee('Rocio Empleado', aliases=['ROCIO'])
        client = AccountClient.objects.create(
            external_id='EMP-ROCIO-CC',
            first_name='Rocio',
            last_name='Cuenta',
        )
        account_tx = AccountTransaction.objects.create(
            client=client,
            external_id='cc-rocio-1',
            description='Retiro mercaderia',
            date=date(2026, 7, 16),
            original_amount=Decimal('8000'),
        )

        response = self.api.post('/api/salaries/movements/assign/', {
            'employee_id': str(employee_without_account.id),
            'source': 'account_current',
            'source_id': account_tx.external_id,
        }, format='json')

        self.assertEqual(response.status_code, 201)
        employee_without_account.refresh_from_db()
        self.assertEqual(employee_without_account.account_client_id, client.id)
        self.assertEqual(response.data['amount'], 8000.0)

    def test_assign_rejects_invalid_employee_id(self):
        response = self.api.post('/api/salaries/movements/assign/', {
            'employee_id': 'not-a-uuid',
            'source': 'bank_transfer',
            'source_id': '1',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'Empleado invalido')

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

    def test_bank_transfer_matches_employee_by_exact_dni(self):
        employee = create_employee(
            'Rocio Documento',
            aliases=['ROCIO DOCUMENTO'],
            document_type='dni',
            document_number='19.440.880',
        )
        batch = BankUploadBatch.objects.create(
            bank='santander',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        matching = BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 18),
            concept='TRANSFERENCIA A TERCEROS',
            description='19.440.880',
            amount=-65000,
        )
        not_matching = BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 19),
            concept='TRANSFERENCIA A TERCEROS',
            description='1194408809',
            amount=-1000,
        )

        sync_employee_movements(date(2026, 7, 1), date(2026, 7, 31))

        movement = EmployeeMovement.objects.get(bank_transaction=matching)
        self.assertEqual(movement.employee, employee)
        self.assertEqual(movement.matched_alias, 'DNI 19440880')
        self.assertFalse(EmployeeMovement.objects.filter(bank_transaction=not_matching).exists())

    def test_santander_transfer_matches_dni_employee_by_equivalent_cuil(self):
        employee = create_employee(
            'Rocio DNI CUIL',
            document_type='dni',
            document_number='12.345.678',
        )
        batch = BankUploadBatch.objects.create(
            bank='santander',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        transaction = BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 18),
            concept='TRANSFERENCIA A TERCEROS',
            description='CUIL 20-12345678-6',
            amount=-65000,
        )

        sync_employee_movements(date(2026, 7, 1), date(2026, 7, 31))

        movement = EmployeeMovement.objects.get(bank_transaction=transaction)
        self.assertEqual(movement.employee, employee)
        self.assertEqual(movement.matched_alias, 'DNI 12345678')

    def test_bancon_import_preserves_dni_and_matches_employee_with_cuil(self):
        employee = create_employee(
            'Rocio Bancor Documento',
            document_type='cuil_cuit',
            document_number='20-12345678-6',
        )
        content = (
            'Fecha;Concepto;Descripcion;Importe\n'
            '18/07/2026;TRANSFERENCIA A TERCEROS;DNI 12345678;-65000\n'
        )
        upload = SimpleUploadedFile('bancor.csv', content.encode('latin-1'), content_type='text/csv')

        response = self.api.post('/api/bank/upload/', {'bank': 'bancon', 'file': upload}, format='multipart')
        self.assertEqual(response.status_code, 200)
        transaction = BankTransaction.objects.get(batch__bank='bancon', date=date(2026, 7, 18))
        self.assertEqual(transaction.description, 'DNI')
        self.assertIn('DNI 12345678', transaction.raw_details)

        sync_employee_movements(date(2026, 7, 1), date(2026, 7, 31))

        movement = EmployeeMovement.objects.get(bank_transaction=transaction)
        self.assertEqual(movement.employee, employee)
        self.assertEqual(movement.matched_alias, 'CUIL/CUIT 20123456786')

    def test_document_matching_does_not_guess_when_legacy_identities_are_duplicated(self):
        Employee.objects.create(
            name='Empleado DNI legado',
            document_type=Employee.DocumentType.DNI,
            document_number='12345678',
        )
        Employee.objects.create(
            name='Empleado CUIL legado',
            document_type=Employee.DocumentType.CUIL_CUIT,
            document_number='20123456786',
        )
        batch = BankUploadBatch.objects.create(
            bank='santander',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        transaction = BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 18),
            concept='TRANSFERENCIA A TERCEROS',
            description='DNI 12345678',
            amount=-65000,
        )

        sync_employee_movements(date(2026, 7, 1), date(2026, 7, 31))

        self.assertFalse(EmployeeMovement.objects.filter(bank_transaction=transaction).exists())

    def test_reimport_enriches_legacy_bank_row_without_duplicating_it(self):
        batch = BankUploadBatch.objects.create(
            bank='bancon',
            fecha_desde=date(2026, 7, 18),
            fecha_hasta=date(2026, 7, 18),
        )
        legacy = BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 18),
            concept='TRANSFERENCIA A TERCEROS',
            description='DNI',
            amount=-65000,
        )
        content = (
            'Fecha;Concepto;Descripcion;Importe\n'
            '18/07/2026;TRANSFERENCIA A TERCEROS;DNI 12345678;-65000\n'
        )
        upload = SimpleUploadedFile('bancor.csv', content.encode('latin-1'), content_type='text/csv')

        response = self.api.post('/api/bank/upload/', {'bank': 'bancon', 'file': upload}, format='multipart')

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['batch_id'])
        self.assertEqual(response.data['summary']['duplicados'], 1)
        self.assertEqual(response.data['summary']['detalles_actualizados'], 1)
        self.assertEqual(BankTransaction.objects.filter(batch__bank='bancon').count(), 1)
        legacy.refresh_from_db()
        self.assertIn('DNI 12345678', legacy.raw_details)

    def test_employee_endpoint_normalizes_and_validates_documents(self):
        valid = self.api.post('/api/salaries/employees/', {
            'name': 'Rocio Cuil',
            'document_type': 'cuil_cuit',
            'document_number': '20-12345678-6',
        }, format='json')
        invalid = self.api.post('/api/salaries/employees/', {
            'name': 'Documento Invalido',
            'document_type': 'cuil_cuit',
            'document_number': '20-12345678-0',
        }, format='json')
        duplicate = self.api.post('/api/salaries/employees/', {
            'name': 'Documento Repetido',
            'document_type': 'cuil_cuit',
            'document_number': '20123456786',
        }, format='json')
        equivalent = self.api.post('/api/salaries/employees/', {
            'name': 'DNI Equivalente',
            'document_type': 'dni',
            'document_number': '12345678',
        }, format='json')

        self.assertEqual(valid.status_code, 201)
        self.assertEqual(valid.data['document_number'], '20123456786')
        self.assertEqual(valid.data['document_type_label'], 'CUIL/CUIT')
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.data['detail'], 'El CUIL/CUIT no es valido')
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn('Rocio Cuil', duplicate.data['detail'])
        self.assertEqual(equivalent.status_code, 400)
        self.assertIn('Rocio Cuil', equivalent.data['detail'])

    def test_employee_deactivation_preserves_history_and_stops_future_matching(self):
        batch = BankUploadBatch.objects.create(
            bank='santander',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        previous_tx = BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 5),
            concept='TRANSFERENCIA DIEGO EMP',
            amount=-50000,
        )
        sync_employee_movements(date(2026, 7, 1), date(2026, 7, 10))

        response = self.api.patch(f'/api/salaries/employees/{self.employee.id}/', {
            'active': False,
            'termination_reason': 'resignation',
            'termination_date': '2026-07-11',
        }, format='json')
        future_tx = BankTransaction.objects.create(
            batch=batch,
            date=date(2026, 7, 12),
            concept='TRANSFERENCIA DIEGO EMP',
            amount=-60000,
        )
        sync_employee_movements(date(2026, 7, 11), date(2026, 7, 31))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['active'])
        self.assertEqual(response.data['termination_reason_label'], 'Renuncia')
        self.assertEqual(response.data['termination_date'], '2026-07-11')
        self.assertTrue(EmployeeMovement.objects.filter(bank_transaction=previous_tx, employee=self.employee).exists())
        self.assertFalse(EmployeeMovement.objects.filter(bank_transaction=future_tx).exists())

        summary = salaries_summary(date(2026, 7, 1), date(2026, 7, 31), sync=False)
        monthly = salaries_monthly_summary(2026, sync=False)
        self.assertNotIn(str(self.employee.id), [row['employee_id'] for row in summary['employees']])
        self.assertNotIn(str(self.employee.id), [row['employee_id'] for row in monthly['employees']])
        self.assertEqual(summary['totals']['total'], 0.0)
        self.assertEqual(summary['movements'], [])

    def test_employee_reactivation_clears_termination_data(self):
        self.employee.active = False
        self.employee.termination_reason = Employee.TerminationReason.DISMISSAL
        self.employee.termination_date = date(2026, 7, 10)
        self.employee.save(update_fields=['active', 'termination_reason', 'termination_date'])

        response = self.api.patch(f'/api/salaries/employees/{self.employee.id}/', {
            'active': True,
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['active'])
        self.assertEqual(response.data['termination_reason'], '')
        self.assertIsNone(response.data['termination_date'])

    def test_employee_deactivation_requires_reason_and_non_future_date(self):
        missing_reason = self.api.patch(f'/api/salaries/employees/{self.employee.id}/', {
            'active': False,
            'termination_date': '2026-07-11',
        }, format='json')
        future_date = self.api.patch(f'/api/salaries/employees/{self.employee.id}/', {
            'active': False,
            'termination_reason': 'dismissal',
            'termination_date': '2100-01-01',
        }, format='json')

        self.assertEqual(missing_reason.status_code, 400)
        self.assertEqual(missing_reason.data['detail'], 'Motivo de baja requerido')
        self.assertEqual(future_date.status_code, 400)
        self.assertEqual(future_date.data['detail'], 'La fecha de baja no puede ser futura')
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.active)

    def test_employee_hire_date_is_validated_against_future_and_termination(self):
        future_hire = self.api.patch(f'/api/salaries/employees/{self.employee.id}/', {
            'hire_date': '2100-01-01',
        }, format='json')
        valid_hire = self.api.patch(f'/api/salaries/employees/{self.employee.id}/', {
            'hire_date': '2026-01-01',
        }, format='json')
        invalid_termination = self.api.patch(f'/api/salaries/employees/{self.employee.id}/', {
            'active': False,
            'termination_reason': 'resignation',
            'termination_date': '2025-12-31',
        }, format='json')

        self.assertEqual(future_hire.status_code, 400)
        self.assertEqual(future_hire.data['detail'], 'La fecha de ingreso no puede ser futura')
        self.assertEqual(valid_hire.status_code, 200)
        self.assertEqual(valid_hire.data['hire_date'], '2026-01-01')
        self.assertEqual(invalid_termination.status_code, 400)
        self.assertEqual(invalid_termination.data['detail'], 'La fecha de baja no puede ser anterior al ingreso')

    def test_employee_account_client_cannot_be_linked_twice(self):
        other_employee = create_employee('Otro Empleado', aliases=['OTRO'])

        response = self.api.patch(f'/api/salaries/employees/{other_employee.id}/', {
            'account_client_id': str(self.employee_client.id),
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Diego Empleado', response.data['detail'])
