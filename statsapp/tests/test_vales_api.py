import os
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase

from statsapp.models import AccountClient, AccountClientAlias, AccountTransaction, ValeImportBatch, ValeImportItem
from statsapp.vales_services import create_vale_batch


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
        self.noisy = AccountClient.objects.create(
            external_id='C-0999',
            first_name='Dolo?',
            last_name='V',
            phone='',
        )
        self.vila = AccountClient.objects.create(
            external_id='C-0998',
            first_name='Miguel',
            last_name='Vila',
            phone='',
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

    def test_logout_without_refresh_cookie_is_idempotent(self):
        response = self.client.post('/api/auth/logout/', {}, format='json')
        self.assertEqual(response.status_code, 204)

    def test_client_suggestions_match_valery_with_valeria(self):
        self.authenticate()
        response = self.client.get('/api/clientes/sugerencias/?alias=Valery&limit=5')
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        best = response.data[0]
        self.assertEqual(best['cliente']['codigo'], 'C-0089')
        self.assertGreater(best['similitud'], 0.7)
        self.assertNotEqual(best['cliente']['codigo'], 'C-0999')
        self.assertNotEqual(best['cliente']['codigo'], 'C-0998')

    def test_client_suggestions_leverage_confirmed_alias_feedback(self):
        self.authenticate()
        feedback_target = AccountClient.objects.create(
            external_id='C-0200',
            first_name='Marta',
            last_name='Gimenez',
            phone='',
        )
        competitor = AccountClient.objects.create(
            external_id='C-0201',
            first_name='Matias',
            last_name='Albano',
            phone='',
        )
        AccountClientAlias.objects.create(
            client=feedback_target,
            alias='Abano Marta',
            auto_detected=True,
            uses=6,
        )

        response = self.client.get('/api/clientes/sugerencias/?alias=Avano Marta&limit=5')
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        best = response.data[0]
        self.assertEqual(best['cliente']['codigo'], 'C-0200')
        self.assertEqual(best['motivo'], 'aprendido')
        self.assertNotEqual(best['cliente']['codigo'], competitor.external_id)

    def test_client_suggestions_match_ocr_partial_names(self):
        self.authenticate()
        matias = AccountClient.objects.create(
            external_id='C-0300',
            first_name='Matias',
            last_name='Viglianco',
            phone='',
        )
        maxi = AccountClient.objects.create(
            external_id='C-0301',
            first_name='Maximiliano',
            last_name='Campo',
            phone='',
        )

        matias_response = self.client.get('/api/clientes/sugerencias/?alias=Matias%20Vigli&limit=5')
        self.assertEqual(matias_response.status_code, 200)
        self.assertEqual(matias_response.data[0]['cliente']['id'], str(matias.id))
        self.assertGreater(matias_response.data[0]['similitud'], 0.84)

        maxi_response = self.client.get('/api/clientes/sugerencias/?alias=Maxi%20Camp&limit=5')
        self.assertEqual(maxi_response.status_code, 200)
        self.assertEqual(maxi_response.data[0]['cliente']['id'], str(maxi.id))
        self.assertGreater(maxi_response.data[0]['similitud'], 0.84)

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
        self.assertEqual(response.data['cuenta_corriente_importados'], 1)
        self.assertEqual(response.data['pendientes'], 1)
        self.assertEqual(response.data['cuenta_corriente_total'], 54731.0)

        detail_response = self.client.get(f'/api/vales/lotes/{batch.lote_id}/')
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data['cuenta_corriente_count'], 1)
        self.assertEqual(detail_response.data['cuenta_corriente_total'], 54731.0)
        self.assertTrue(detail_response.data['vales'][0]['en_cuenta_corriente'])
        self.assertFalse(detail_response.data['vales'][1]['en_cuenta_corriente'])

    def test_pending_vale_item_can_be_resolved_from_history(self):
        self.authenticate()
        payload = {
            'fecha': '2026-04-07',
            'source_filenames': ['vale-pendiente.jpeg'],
            'vales': [
                {
                    'importe': 7560,
                    'cliente_id': None,
                    'cliente_raw': 'Jorge Soucedo',
                    'detalle': 'Vale pendiente',
                    'confianza': 0.41,
                },
            ],
        }
        create_response = self.client.post('/api/vales/cargar/', payload, format='json')
        self.assertEqual(create_response.status_code, 201)

        item = ValeImportItem.objects.get()
        self.assertTrue(item.pending_review)
        self.assertIsNone(item.transaction_id)

        resolve_response = self.client.post(
            f'/api/vales/items/{item.id}/resolver/',
            {
                'cliente_id': str(self.valeria.id),
            },
            format='json',
        )
        self.assertEqual(resolve_response.status_code, 200)

        item.refresh_from_db()
        self.assertFalse(item.pending_review)
        self.assertEqual(item.client_id, self.valeria.id)
        self.assertIsNotNone(item.transaction_id)
        self.assertEqual(resolve_response.data['pendientes_count'], 0)
        self.assertEqual(AccountTransaction.objects.filter(client=self.valeria).count(), 1)
        self.assertTrue(
            AccountClientAlias.objects.filter(client=self.valeria, alias='Jorge Soucedo').exists()
        )

    def test_vale_lote_date_patch_updates_items_and_transactions(self):
        self.authenticate()
        current_year = timezone.localdate().year
        batch, _warnings = create_vale_batch(
            user=self.user,
            batch_date=date(2024, 4, 1),
            source_filenames=['fecha-mal.jpeg'],
            vales_payload=[{
                'importe': 1234,
                'cliente_id': str(self.silvina.id),
                'cliente_raw': 'Silvi Farias',
                'detalle': '',
                'confianza': 1,
            }],
        )
        item = batch.items.select_related('transaction').get()
        self.assertEqual(item.date, date(current_year, 4, 1))
        self.assertEqual(item.transaction.date, date(current_year, 4, 1))

        response = self.client.patch(
            f'/api/vales/lotes/{batch.lote_id}/',
            {'fecha': '2024-04-02'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        batch.refresh_from_db()
        item.refresh_from_db()
        item.transaction.refresh_from_db()
        self.assertEqual(batch.date, date(current_year, 4, 2))
        self.assertEqual(item.date, date(current_year, 4, 2))
        self.assertEqual(item.transaction.date, date(current_year, 4, 2))
        self.assertEqual(response.data['fecha'], f'{current_year}-04-02')

    def test_vale_lote_delete_removes_items_transactions_and_recalculates_client(self):
        self.authenticate()
        batch, _warnings = create_vale_batch(
            user=self.user,
            batch_date=date(2026, 4, 1),
            source_filenames=['lote-mal.jpeg'],
            vales_payload=[{
                'importe': 4321,
                'cliente_id': str(self.silvina.id),
                'cliente_raw': 'Silvi Farias',
                'detalle': '',
                'confianza': 1,
            }],
        )
        self.silvina.refresh_from_db()
        self.assertGreater(float(self.silvina.total_debt), 0)
        self.assertEqual(ValeImportItem.objects.filter(batch=batch).count(), 1)
        self.assertEqual(AccountTransaction.objects.filter(meta__lote_id=batch.lote_id).count(), 1)

        response = self.client.delete(f'/api/vales/lotes/{batch.lote_id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['items_deleted'], 1)
        self.assertEqual(response.data['transactions_deleted'], 1)
        self.assertFalse(ValeImportBatch.objects.filter(lote_id=batch.lote_id).exists())
        self.assertEqual(ValeImportItem.objects.filter(batch_id=batch.id).count(), 0)
        self.assertEqual(AccountTransaction.objects.filter(meta__lote_id=batch.lote_id).count(), 0)
        self.silvina.refresh_from_db()
        self.assertEqual(float(self.silvina.total_debt), 0)

    def test_vale_lote_post_delete_fallback_removes_batch(self):
        self.authenticate()
        batch, _warnings = create_vale_batch(
            user=self.user,
            batch_date=date(2026, 4, 1),
            source_filenames=['lote-mal-post.jpeg'],
            vales_payload=[{
                'importe': 1234,
                'cliente_id': str(self.silvina.id),
                'cliente_raw': 'Silvi Farias',
                'detalle': '',
                'confianza': 1,
            }],
        )

        response = self.client.post(
            f'/api/vales/lotes/{batch.lote_id}/',
            {'action': 'delete'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ValeImportBatch.objects.filter(lote_id=batch.lote_id).exists())
        self.assertEqual(AccountTransaction.objects.filter(meta__lote_id=batch.lote_id).count(), 0)

    def test_vales_lotes_caps_pagination_at_twenty_items(self):
        self.authenticate()
        for idx in range(25):
            create_vale_batch(
                user=self.user,
                batch_date=date(2026, 4, 1),
                source_filenames=[f'archivo-{idx}.jpeg'],
                vales_payload=[{
                    'importe': 1000 + idx,
                    'cliente_id': str(self.silvina.id),
                    'cliente_raw': f'Cliente {idx}',
                    'detalle': '',
                    'confianza': 1,
                }],
            )

        response = self.client.get('/api/vales/lotes/?page=1&page_size=50')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 25)
        self.assertEqual(response.data['page_size'], 20)
        self.assertEqual(response.data['total_pages'], 2)
        self.assertEqual(len(response.data['results']), 20)

    def test_vales_lotes_supports_search_status_and_date_filters(self):
        self.authenticate()
        create_vale_batch(
            user=self.user,
            batch_date=date(2026, 4, 1),
            source_filenames=['pendiente-buscado.jpeg'],
            vales_payload=[{
                'importe': 2000,
                'cliente_id': None,
                'cliente_raw': 'Cliente Buscado',
                'detalle': '',
                'confianza': 0.5,
            }],
        )
        create_vale_batch(
            user=self.user,
            batch_date=date(2026, 4, 5),
            source_filenames=['importado.jpeg'],
            vales_payload=[{
                'importe': 3000,
                'cliente_id': str(self.silvina.id),
                'cliente_raw': 'Silvi Farias',
                'detalle': '',
                'confianza': 1,
            }],
        )

        search_response = self.client.get('/api/vales/lotes/?q=Buscado')
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.data['count'], 1)
        self.assertEqual(search_response.data['results'][0]['pendientes_count'], 1)

        pending_response = self.client.get('/api/vales/lotes/?estado=pendientes')
        self.assertEqual(pending_response.status_code, 200)
        self.assertEqual(pending_response.data['count'], 1)

        imported_response = self.client.get('/api/vales/lotes/?estado=importado')
        self.assertEqual(imported_response.status_code, 200)
        self.assertEqual(imported_response.data['count'], 1)
        self.assertEqual(imported_response.data['results'][0]['fecha'], '2026-04-05')

        date_response = self.client.get('/api/vales/lotes/?fecha_desde=2026-04-02')
        self.assertEqual(date_response.status_code, 200)
        self.assertEqual(date_response.data['count'], 1)
        self.assertEqual(date_response.data['results'][0]['fecha'], '2026-04-05')

    @mock.patch.dict(os.environ, {'OCR_PROVIDER': 'mock'}, clear=False)
    def test_ocr_process_returns_mock_payload(self):
        self.authenticate()
        upload = SimpleUploadedFile('vale-ejemplo.jpeg', b'fake-image-bytes', content_type='image/jpeg')
        response = self.client.post('/api/ocr/procesar/', {'fotos': [upload]}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['fecha_detectada'], '2026-04-07')
        self.assertGreaterEqual(len(response.data['vales']), 1)
        self.assertEqual(response.data['vales'][0]['source_index'], 0)
        self.assertEqual(response.data['vales'][0]['source_filename'], 'vale-ejemplo.jpeg')

    @mock.patch('statsapp.vales_views.process_ocr_uploads')
    def test_ocr_process_autolinks_partial_real_client_names(self, process_ocr_mock):
        matias = AccountClient.objects.create(
            external_id='C-0302',
            first_name='Matias',
            last_name='Viglianco',
            phone='',
        )
        process_ocr_mock.return_value = {
            'fecha_detectada': '2026-04-01',
            'vales': [{
                'importe': 3900,
                'cliente_raw': 'Matias Vigli',
                'detalle': '',
                'confianza': 0.91,
                'source_index': 0,
            }],
        }
        self.authenticate()
        upload = SimpleUploadedFile('vale-real.jpeg', b'fake-image-bytes', content_type='image/jpeg')
        response = self.client.post('/api/ocr/procesar/', {'fotos': [upload]}, format='multipart')
        self.assertEqual(response.status_code, 200)
        vale = response.data['vales'][0]
        self.assertEqual(vale['cliente_id'], str(matias.id))
        self.assertEqual(vale['cliente_nombre'], 'Viglianco, Matias')
        self.assertGreater(vale['cliente_match']['similitud'], 0.84)
        self.assertGreaterEqual(len(vale['sugerencias']), 1)

    @mock.patch('statsapp.vales_views.process_ocr_uploads')
    def test_ocr_process_does_not_autolink_generic_vale_text(self, process_ocr_mock):
        process_ocr_mock.return_value = {
            'fecha_detectada': '2026-04-01',
            'vales': [{
                'importe': 3600,
                'cliente_raw': 'Vale mp.',
                'detalle': '',
                'confianza': 0.72,
                'source_index': 0,
            }],
        }
        self.authenticate()
        upload = SimpleUploadedFile('vale-ruido.jpeg', b'fake-image-bytes', content_type='image/jpeg')
        response = self.client.post('/api/ocr/procesar/', {'fotos': [upload]}, format='multipart')
        self.assertEqual(response.status_code, 200)
        vale = response.data['vales'][0]
        self.assertIsNone(vale['cliente_id'])
        self.assertEqual(vale['sugerencias'], [])

    @mock.patch.dict(os.environ, {
        'OCR_PROVIDER': 'gemini',
        'GEMINI_API_KEY': 'test-key',
        'GEMINI_OCR_MODEL': 'gemini-3-flash-preview',
    }, clear=False)
    @mock.patch('statsapp.vales_services._http_json')
    def test_ocr_process_sums_multiple_amounts_in_same_row(self, http_json_mock):
        http_json_mock.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': '{"fecha_detectada":"2026-04-01","vales":[{"importe":"4388 + 9182","cliente_raw":"Cesar Ferrero","detalle":"","source_index":0,"confianza":0.9}]}'
                    }]
                }
            }]
        }
        self.authenticate()
        upload = SimpleUploadedFile('vale-suma.jpeg', b'fake-image-bytes', content_type='image/jpeg')
        response = self.client.post('/api/ocr/procesar/', {'fotos': [upload]}, format='multipart')
        self.assertEqual(response.status_code, 200)
        vale = response.data['vales'][0]
        self.assertEqual(vale['importe'], 13570.0)
        self.assertEqual(vale['detalle'], '4388 + 9182')

    @mock.patch.dict(os.environ, {
        'OCR_PROVIDER': 'gemini',
        'GEMINI_API_KEY': 'test-key',
        'GEMINI_OCR_MODEL': 'gemini-3-flash-preview',
    }, clear=False)
    @mock.patch('statsapp.vales_services._http_json')
    def test_ocr_process_sums_importes_array_in_same_row(self, http_json_mock):
        http_json_mock.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': '{"fecha_detectada":"2026-04-01","vales":[{"importe":13570,"importes":[4388,9182],"cliente_raw":"Cesar Ferrero","detalle":"mismo renglon","source_index":0,"confianza":0.9}]}'
                    }]
                }
            }]
        }
        self.authenticate()
        upload = SimpleUploadedFile('vale-array.jpeg', b'fake-image-bytes', content_type='image/jpeg')
        response = self.client.post('/api/ocr/procesar/', {'fotos': [upload]}, format='multipart')
        self.assertEqual(response.status_code, 200)
        vale = response.data['vales'][0]
        self.assertEqual(vale['importe'], 13570.0)
        self.assertEqual(vale['detalle'], '4388 + 9182 - mismo renglon')

    @mock.patch.dict(os.environ, {
        'OCR_PROVIDER': 'gemini',
        'GEMINI_API_KEY': 'test-key',
        'GEMINI_OCR_MODEL': 'gemini-3-flash-preview',
    }, clear=False)
    @mock.patch('statsapp.vales_services._http_json')
    def test_ocr_process_supports_gemini_provider(self, http_json_mock):
        current_year = timezone.localdate().year
        http_json_mock.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': '{"fecha_detectada":"2024-04-20","vales":[{"importe":12345,"cliente_raw":"Valery","detalle":"","source_index":0,"confianza":0.91,"bbox":{"x":0.12,"y":0.44,"w":0.7,"h":0.04}}]}'
                    }]
                }
            }]
        }
        self.authenticate()
        upload = SimpleUploadedFile('vale-ejemplo.jpeg', b'fake-image-bytes', content_type='image/jpeg')
        response = self.client.post('/api/ocr/procesar/', {'fotos': [upload]}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['fecha_detectada'], f'{current_year}-04-20')
        self.assertEqual(len(response.data['vales']), 1)
        self.assertEqual(response.data['vales'][0]['importe'], 12345.0)
        self.assertEqual(response.data['vales'][0]['source_index'], 0)
        self.assertEqual(response.data['vales'][0]['bbox'], {'x': 0.12, 'y': 0.44, 'w': 0.7, 'h': 0.04})

    @mock.patch.dict(os.environ, {
        'OCR_PROVIDER': 'gemini',
        'GEMINI_API_KEY': 'test-key',
        'GEMINI_OCR_MODEL': 'gemini-3-flash-preview',
    }, clear=False)
    @mock.patch('statsapp.vales_services._http_json')
    def test_ocr_process_normalizes_bbox_percentages(self, http_json_mock):
        http_json_mock.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': '{"fecha_detectada":"2026-04-01","vales":[{"importe":25000,"cliente_raw":"Euge","detalle":"","source_index":0,"confianza":0.9,"bbox":{"x":10,"y":52,"w":72,"h":5}}]}'
                    }]
                }
            }]
        }
        self.authenticate()
        upload = SimpleUploadedFile('vale-bbox.jpeg', b'fake-image-bytes', content_type='image/jpeg')
        response = self.client.post('/api/ocr/procesar/', {'fotos': [upload]}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['vales'][0]['bbox'], {'x': 0.1, 'y': 0.52, 'w': 0.72, 'h': 0.05})
