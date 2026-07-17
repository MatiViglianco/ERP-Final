from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from statsapp.models import (
    AccountClient,
    AccountTransaction,
    BankTransaction,
    BankUploadBatch,
    Branch,
    Employee,
    EmployeeMovement,
    ExpenseCategory,
    ExpenseEntry,
    ExpenseSubcategory,
    ExternalEvent,
    GetnetTerminal,
    Invoice,
    Payment,
    Record,
    UploadBatch,
)
from statsapp.salary_services import create_employee


class Command(BaseCommand):
    help = 'Carga datos deterministas para el E2E de facturacion.'

    def handle(self, *args, **options):
        ExternalEvent.objects.filter(provider='getnet').delete()
        Payment.objects.filter(client__external_id='E2E-CLIENTE-FACT').delete()
        Payment.objects.filter(external_id='E2E-GETNET-CSV').delete()
        GetnetTerminal.objects.filter(code='AR0E2E01').delete()
        Invoice.objects.filter(client__external_id='E2E-CLIENTE-FACT').delete()
        AccountTransaction.objects.filter(external_id='E2E-TX-FACT-1').delete()
        EmployeeMovement.objects.all().delete()
        Employee.objects.filter(name__in=['Diego E2E', 'JUAN CATEGORIA E2E', 'Juan Interno E2E']).delete()
        ExpenseEntry.objects.filter(external_id='E2E-SUELDO-EFECTIVO').delete()
        BankUploadBatch.objects.filter(original_filename='e2e-sueldos.csv').delete()
        AccountTransaction.objects.filter(external_id__startswith='E2E-SUELDO-CC').delete()
        Branch.objects.filter(slug__in=['e2e-central', 'e2e-norte']).delete()
        UploadBatch.objects.filter(original_filename__in=['e2e-central-kretz.csv', 'e2e-norte-kretz.csv']).delete()

        user_model = get_user_model()
        user, _ = user_model.objects.update_or_create(
            username='e2eadmin',
            defaults={
                'is_staff': True,
                'is_superuser': True,
                'first_name': 'E2E',
                'last_name': 'Admin',
            },
        )
        user.set_password('e2eadmin123')
        user.save()

        branch_central = Branch.objects.create(name='E2E Central', slug='e2e-central')
        branch_norte = Branch.objects.create(name='E2E Norte', slug='e2e-norte')

        central_batch = UploadBatch.objects.create(
            branch=branch_central,
            original_filename='e2e-central-kretz.csv',
            single_date=date(2026, 7, 10),
            is_single_day=True,
        )
        north_batch = UploadBatch.objects.create(
            branch=branch_norte,
            original_filename='e2e-norte-kretz.csv',
            single_date=date(2026, 7, 10),
            is_single_day=True,
        )
        Record.objects.create(
            batch=central_batch,
            dsc_seccion='CARNES',
            nom_plu='ASADO CENTRAL',
            imp=1000,
            peso=2,
        )
        Record.objects.create(
            batch=north_batch,
            dsc_seccion='CARNES',
            nom_plu='ASADO NORTE',
            imp=3000,
            peso=6,
        )

        client, _ = AccountClient.objects.update_or_create(
            external_id='E2E-CLIENTE-FACT',
            defaults={
                'first_name': 'Cliente',
                'last_name': 'Facturacion',
                'total_debt': Decimal('3210.00'),
                'status': AccountClient.Status.ACTIVE,
            },
        )
        AccountTransaction.objects.update_or_create(
            external_id='E2E-TX-FACT-1',
            defaults={
                'client': client,
                'branch': branch_central,
                'description': 'Venta E2E cuenta corriente',
                'date': date(2026, 7, 10),
                'original_amount': Decimal('3210.00'),
                'paid_amount': Decimal('0'),
                'status': AccountTransaction.Status.ACTIVE,
                'payments': [],
                'meta': {'e2e': True},
            },
        )
        employee_client, _ = AccountClient.objects.update_or_create(
            external_id='E2E-EMPLEADO-DIEGO',
            defaults={
                'first_name': 'Diego',
                'last_name': 'E2E',
                'total_debt': Decimal('9000.00'),
                'status': AccountClient.Status.ACTIVE,
            },
        )
        create_employee('Diego E2E', aliases=['DIEGO E2E', 'DIEGO'], account_client=employee_client)
        salary_category, _ = ExpenseCategory.objects.get_or_create(name='SUELDOS')
        ExpenseSubcategory.objects.get_or_create(category=salary_category, name='JUAN CATEGORIA E2E')
        salary_batch = BankUploadBatch.objects.create(
            bank='santander',
            original_filename='e2e-sueldos.csv',
            fecha_desde=date(2026, 7, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        BankTransaction.objects.create(
            batch=salary_batch,
            date=date(2026, 7, 8),
            concept='TRANSFERENCIA DIEGO E2E',
            description='Pago sueldo',
            amount=-45000,
        )
        ExpenseEntry.objects.create(
            external_id='E2E-SUELDO-EFECTIVO',
            branch=branch_central,
            date=date(2026, 7, 9),
            amount=Decimal('15000'),
            method=ExpenseEntry.Method.CASH,
            category='SUELDOS',
            subcategory='DIEGO',
            description='Efectivo empleado',
        )
        AccountTransaction.objects.create(
            client=employee_client,
            branch=branch_norte,
            external_id='E2E-SUELDO-CC',
            description='Retiro cuenta corriente empleado',
            date=date(2026, 7, 10),
            original_amount=Decimal('9000'),
            paid_amount=Decimal('0'),
            status=AccountTransaction.Status.ACTIVE,
            payments=[],
            meta={'e2e': True},
        )
        for index in range(1, 9):
            AccountTransaction.objects.create(
                client=employee_client,
                branch=branch_norte,
                external_id=f'E2E-SUELDO-CC-PAGE-{index}',
                description=f'Movimiento paginado {index}',
                date=date(2026, 7, index),
                original_amount=Decimal('100'),
                paid_amount=Decimal('0'),
                status=AccountTransaction.Status.ACTIVE,
                payments=[],
                meta={'e2e': True},
            )
        self.stdout.write(self.style.SUCCESS('Datos E2E de facturacion cargados'))
