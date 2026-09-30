from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from statsapp.models import BankTransaction, BankUploadBatch


SANTANDER_HEADER = 'Fecha;Sucursal;Cod;Ref;Descripcion;Concepto;Importe;Saldo\n'


def santander_csv(name, rows):
    lines = [SANTANDER_HEADER]
    for day, description, concept, amount in rows:
        lines.append(f'{day};001;0;0;{description};{concept};{amount};0\n')
    return SimpleUploadedFile(name, ''.join(lines).encode('latin-1'), content_type='text/csv')


class BankUploadTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username='admin',
            password='admin123',
            is_staff=True,
            is_superuser=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(user)

    def test_santander_month_split_in_overlapping_files_is_merged_without_duplicates(self):
        first_half = santander_csv('santander-1.csv', [
            ('01/08/2026', 'Pago proveedor', 'Transferencia', '-1.000,00'),
            ('10/08/2026', 'Venta', 'Credito', '5.000,00'),
            ('15/08/2026', 'Comision', 'Comision', '-50,00'),
            ('15/08/2026', 'Comision', 'Comision', '-50,00'),
        ])
        second_half = santander_csv('santander-2.csv', [
            ('15/08/2026', 'Comision', 'Comision', '-50,00'),
            ('15/08/2026', 'Comision', 'Comision', '-50,00'),
            ('20/08/2026', 'Sueldo', 'Transferencia', '-2.000,00'),
            ('31/08/2026', 'Venta', 'Credito', '7.000,00'),
        ])

        response = self.api.post(
            '/api/bank/upload/',
            {'bank': 'santander', 'file': [first_half, second_half]},
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        summary = response.data['summary']
        self.assertEqual(summary['archivos'], 2)
        self.assertEqual(summary['movimientos'], 6)
        self.assertEqual(summary['solapados_entre_archivos'], 2)
        self.assertEqual(summary['desde'], '2026-08-01')
        self.assertEqual(summary['hasta'], '2026-08-31')
        self.assertEqual(BankTransaction.objects.filter(batch__bank='santander').count(), 6)
        self.assertEqual(
            BankTransaction.objects.filter(date=date(2026, 8, 15), amount=-50.0).count(),
            2,
        )
        batch = BankUploadBatch.objects.get(pk=response.data['batch_id'])
        self.assertEqual(batch.original_filename, 'santander-1.csv, santander-2.csv')

    def test_santander_files_uploaded_separately_only_add_missing_movements(self):
        first_half = santander_csv('santander-1.csv', [
            ('01/08/2026', 'Pago proveedor', 'Transferencia', '-1.000,00'),
            ('15/08/2026', 'Comision', 'Comision', '-50,00'),
        ])
        second_half = santander_csv('santander-2.csv', [
            ('15/08/2026', 'Comision', 'Comision', '-50,00'),
            ('15/08/2026', 'Comision', 'Comision', '-50,00'),
            ('31/08/2026', 'Venta', 'Credito', '7.000,00'),
        ])

        first = self.api.post('/api/bank/upload/', {'bank': 'santander', 'file': first_half}, format='multipart')
        second = self.api.post('/api/bank/upload/', {'bank': 'santander', 'file': second_half}, format='multipart')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['summary']['movimientos'], 2)
        self.assertEqual(second.data['summary']['duplicados'], 1)
        self.assertEqual(BankTransaction.objects.filter(batch__bank='santander').count(), 4)

    def test_invalid_file_among_several_reports_its_name(self):
        valid = santander_csv('santander-1.csv', [
            ('01/08/2026', 'Pago proveedor', 'Transferencia', '-1.000,00'),
        ])
        empty = SimpleUploadedFile('vacio.csv', b'nada;que;ver;aca;x\n', content_type='text/csv')

        response = self.api.post(
            '/api/bank/upload/',
            {'bank': 'santander', 'file': [valid, empty]},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('vacio.csv', response.data['detail'])
        self.assertFalse(BankTransaction.objects.exists())
