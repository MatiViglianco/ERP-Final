from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from statsapp.models import AccountClient, AccountClientAlias, AccountTransaction, ValeImportBatch


User = get_user_model()


class ValesDuplicateGuardTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='monica',
            password='carni2026',
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_authenticate(self.user)
        self.clients = [
            AccountClient.objects.create(external_id=f'C-{idx}', first_name=first, last_name=last)
            for idx, (first, last) in enumerate([
                ('Natalia', 'Viglianco'),
                ('Naldi', 'del Canto'),
                ('Cesar', 'Ferrero'),
                ('Valeria', 'Gonzalez'),
                ('Ignacio', 'Tillous'),
            ])
        ]
        self.today = timezone.localdate().isoformat()

    def _vale(self, amount, client_idx=None, raw='Cliente'):
        return {
            'importe': amount,
            'cliente_id': str(self.clients[client_idx].id) if client_idx is not None else None,
            'cliente_raw': raw,
            'detalle': '',
            'confianza': 0.95,
        }

    def _sheet(self):
        return [
            self._vale(7985, 2, 'Ferrero'),
            self._vale(4313, 0, 'Naty'),
            self._vale(12500, 3, 'Vale G'),
            self._vale(3200, 4, 'Tillous'),
            self._vale(61838, None, 'Figueroa'),
        ]

    def _post(self, vales, fecha=None, filenames=None, **extra):
        payload = {
            'fecha': fecha or self.today,
            'source_filenames': filenames or ['1000251244-fix.jpg'],
            'vales': vales,
            **extra,
        }
        return self.client.post('/api/vales/cargar/', payload, format='json')

    def test_same_sheet_twice_is_rejected_until_forced(self):
        first = self._post(self._sheet())
        second = self._post(self._sheet())

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.data['duplicado']['lote_id'], first.data['lote_id'])
        self.assertTrue(second.data['duplicado']['identico'])
        self.assertEqual(second.data['duplicado']['coincidencias'], 5)
        self.assertEqual(ValeImportBatch.objects.count(), 1)
        self.assertEqual(AccountTransaction.objects.count(), 4)

        forced = self._post(self._sheet(), forzar_duplicado=True)

        self.assertEqual(forced.status_code, 201)
        self.assertEqual(ValeImportBatch.objects.count(), 2)

    def test_ocr_reread_with_small_differences_is_still_detected(self):
        self._post(self._sheet())
        reread = self._sheet()
        reread[1] = self._vale(4313, 1, 'Naty')  # otro cliente elegido
        reread[3] = self._vale(3290, 4, 'Tillous')  # un importe mal leido

        response = self._post(reread, filenames=['otra-foto-fix.jpg'])

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.data['duplicado']['identico'])
        self.assertEqual(response.data['duplicado']['coincidencias'], 4)

    def test_second_sheet_of_the_same_day_is_accepted(self):
        self._post(self._sheet())
        afternoon = [
            self._vale(9900, 0, 'Naty'),
            self._vale(26500, 2, 'Ferrero'),
            self._vale(4529, 1, 'Naldi'),
            self._vale(7985, 3, 'Vale G'),
        ]

        response = self._post(afternoon, filenames=['1000251245-fix.jpg'])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ValeImportBatch.objects.count(), 2)

    def test_small_batches_only_match_when_identical(self):
        self._post([self._vale(5000, 0, 'Naty'), self._vale(3000, 2, 'Ferrero')])

        response = self._post(
            [self._vale(5000, 0, 'Naty'), self._vale(3100, 2, 'Ferrero')],
            filenames=['otra-fix.jpg'],
        )

        self.assertEqual(response.status_code, 201)

    def test_same_photo_loaded_with_another_date_is_detected(self):
        self._post(self._sheet())
        other_date = (timezone.localdate() - timedelta(days=1)).isoformat()

        response = self._post(self._sheet(), fecha=other_date)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['duplicado']['fecha'], self.today)

    def test_generic_camera_filename_does_not_link_other_dates(self):
        self._post(self._sheet(), filenames=['image-fix.jpg'])
        other_date = (timezone.localdate() - timedelta(days=1)).isoformat()

        response = self._post(self._sheet(), fecha=other_date, filenames=['image-fix.jpg'])

        self.assertEqual(response.status_code, 201)

    def test_alias_conflict_is_reported_but_batch_is_loaded(self):
        AccountClientAlias.objects.create(
            client=self.clients[0],
            alias='Naty',
            normalized_alias='naty',
        )

        wrong = self._post([self._vale(4529, 1, 'Naty')])
        right = self._post([self._vale(4313, 0, 'Naty')], filenames=['otra-fix.jpg'])

        self.assertEqual(wrong.status_code, 201)
        self.assertTrue(any(
            '"Naty"' in warning and 'Viglianco, Natalia' in warning and 'del Canto, Naldi' in warning
            for warning in wrong.data['warnings']
        ))
        self.assertEqual(right.status_code, 201)
        self.assertFalse(any('alias' in warning for warning in right.data['warnings']))
