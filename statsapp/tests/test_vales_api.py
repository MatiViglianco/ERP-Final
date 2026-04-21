import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from statsapp.models import AccountClient, AccountTransaction, ValeImportBatch


User = get_user_model()


class ValesApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='monica',
            password='carni2026',
            first_name='Monica',
            last_name='Carnicera',
            is_staff=True,
            is_superuser=True,
        )
        self.operator = User.objects.create_user(
            username='dario',
            password='vales123',
            first_name='Dario',
            last_name='Operador',
            is_staff=True,
            is_superuser=False,
        )
        self.valeria = AccountClient.objects.create(
            external_id='C-0089',
            first_name='Valeria',
            last_name='Gomez',
            phone='+543584000001',
        )
        self.silvina = AccountClient.objects.create(
            external_id='C-0012',
            first_name='Silvina',
            last_name='Farias',
            phone='+543584000002',
        )

    def authenticate(self):
        response = self.client.post('/api/auth/login/', {
            'user': 'monica',
            'pass': 'carni2026',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return response

    def test_login_accepts_user_and_pass_aliases(self):
        response = self.authenticate()
        self.assertIn('token', response.data)
        self.assertEqual(response.data['user']['rol'], 'admin')
        self.assertEqual(response.data['user']['iniciales'], 'MC')

    def test_login_returns_operator_role_for_non_superuser_staff(self):
        response = self.client.post('/api/auth/login/', {
            'user': 'dario',
            'pass': 'vales123',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user']['rol'], 'operador')
        self.assertEqual(response.data['user']['iniciales'], 'DO')

    def test_client_suggestions_match_valery_with_valeria(self):
        self.authenticate()
        response = self.client.get('/api/clientes/sugerencias/?alias=Valery&limit=5')
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        best = response.data[0]
        self.assertEqual(best['cliente']['codigo'], 'C-0089')
        self.assertGreater(best['similitud'], 0.7)

    def test_operator_can_create_client_from_vales_flow(self):
        response = self.client.post('/api/auth/login/', {
            'user': 'dario',
            'pass': 'vales123',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

        create_response = self.client.post('/api/clientes/', {
            'nombre': 'Mirela Sosa',
        }, format='json')
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data['nombre'], 'Mirela Sosa')
        self.assertTrue(str(create_response.data['codigo']).startswith('MANUAL-'))

    def test_vales_batch_creates_transactions_and_pending_items(self):
        self.authenticate()
        payload = {
            'fecha': '2026-04-07',
            'source_filenames': ['vale-ejemplo.jpeg'],
            'vales': [
                {
                    'importe': 54731,
                    'cliente_id': str(self.silvina.id),
                    'cliente_raw': 'Silvi Farias',
                    'detalle': '',
                    'confianza': 0.94,
                },
                {
                    'importe': 7560,
                    'cliente_id': None,
                    'cliente_raw': 'Desconocido',
                    'detalle': '',
                    'confianza': 0.41,
                },
            ],
        }
        response = self.client.post('/api/vales/cargar/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ValeImportBatch.objects.count(), 1)
        batch = ValeImportBatch.objects.first()
        self.assertEqual(batch.items.count(), 2)
        self.assertEqual(batch.items.filter(pending_review=True).count(), 1)
        self.assertEqual(AccountTransaction.objects.filter(client=self.silvina).count(), 1)

    @mock.patch.dict(os.environ, {'OCR_PROVIDER': 'mock'}, clear=False)
    def test_ocr_process_returns_mock_payload(self):
        self.authenticate()
        upload = SimpleUploadedFile('vale-ejemplo.jpeg', b'fake-image-bytes', content_type='image/jpeg')
        response = self.client.post('/api/ocr/procesar/', {'fotos': [upload]}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['fecha_detectada'], '2026-04-07')
        self.assertGreaterEqual(len(response.data['vales']), 1)

    @mock.patch.dict(os.environ, {
        'OCR_PROVIDER': 'gemini',
        'GEMINI_API_KEY': 'test-key',
        'GEMINI_OCR_MODEL': 'gemini-2.5-flash',
    }, clear=False)
    @mock.patch('statsapp.vales_services._http_json')
    def test_ocr_process_supports_gemini_provider(self, http_json_mock):
        http_json_mock.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': '{"fecha_detectada":"2026-04-20","vales":[{"importe":12345,"cliente_raw":"Valery","detalle":"","confianza":0.91}]}'
                    }]
                }
            }]
        }
        self.authenticate()
        upload = SimpleUploadedFile('vale-ejemplo.jpeg', b'fake-image-bytes', content_type='image/jpeg')
        response = self.client.post('/api/ocr/procesar/', {'fotos': [upload]}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['fecha_detectada'], '2026-04-20')
        self.assertEqual(len(response.data['vales']), 1)
        self.assertEqual(response.data['vales'][0]['importe'], 12345.0)
