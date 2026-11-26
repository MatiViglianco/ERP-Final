from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from statsapp import arca_services
from statsapp.arca_client import ArcaConnectionError
from statsapp.arca_retry import retry_pending_invoices, retryable_invoices, verify_invoices_with_arca
from statsapp.arca_services import authorize_invoice_wsfe
from statsapp.models import ArcaAccessTicket, Invoice, InvoiceLine, Payment

from .test_arca_wsfe import (
    CUIT,
    WSFE_SETTINGS,
    FakeTransport,
    _soap,
    cae_response,
    consult_response,
    last_authorized_response,
)


def dummy_response(app='OK', db='OK', auth='OK'):
    return _soap(
        '<FEDummyResponse xmlns="http://ar.gov.afip.dif.FEV1/"><FEDummyResult>'
        f'<AppServer>{app}</AppServer><DbServer>{db}</DbServer><AuthServer>{auth}</AuthServer>'
        '</FEDummyResult></FEDummyResponse>'
    )


def not_found_response():
    return _soap(
        '<FECompConsultarResponse xmlns="http://ar.gov.afip.dif.FEV1/"><FECompConsultarResult>'
        '<Errors><Err><Code>602</Code><Msg>No existen datos</Msg></Err></Errors>'
        '</FECompConsultarResult></FECompConsultarResponse>'
    )


RESET = ArcaConnectionError("No se pudo conectar con ARCA: ('Connection aborted.', ConnectionResetError(104))")


class ArcaRetryBase(TestCase):
    def setUp(self):
        ArcaAccessTicket.objects.create(
            environment='homologacion', service='wsfe', cuit=CUIT, token='TOKEN', sign='SIGN',
            generated_at=timezone.now(), expires_at=timezone.now() + timedelta(hours=10),
        )
        self.addCleanup(arca_services.set_transport_factory, None)

    def use(self, transport):
        arca_services.set_transport_factory(lambda: transport)
        return transport

    def make_invoice(self, key='inv-1', total='24363.00', **extra):
        fields = {
            'source': Invoice.Source.MANUAL,
            'point_of_sale': 4,
            'voucher_type': 6,
            'total_amount': Decimal(total),
            'net_amount': Decimal(total),
            'idempotency_key': key,
            'meta': {'vat_rate': '10.5'},
        }
        fields.update(extra)
        return Invoice.objects.create(**fields)


@override_settings(**WSFE_SETTINGS)
class AutoRetryTests(ArcaRetryBase):
    def test_connection_failure_before_cae_marks_invoice_for_retry(self):
        invoice = self.make_invoice()
        self.use(FakeTransport({'FECompUltimoAutorizado': [RESET]}))

        with self.assertRaises(ArcaConnectionError):
            authorize_invoice_wsfe(invoice)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ERROR)
        self.assertTrue(invoice.meta['arca_retry'])
        self.assertIn('No se pudo conectar con ARCA', invoice.error_message)
        self.assertEqual(list(retryable_invoices()), [invoice])

    def test_retry_waits_while_arca_is_down(self):
        invoice = self.make_invoice(status=Invoice.Status.ERROR, meta={'vat_rate': '10.5', 'arca_retry': True})
        transport = self.use(FakeTransport({'FEDummy': [RESET]}))

        summary = retry_pending_invoices()

        self.assertFalse(summary['arca_up'])
        self.assertEqual(summary['still_pending'], 1)
        self.assertEqual(transport.count('FECAESolicitar'), 0)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ERROR)

    def test_retry_skips_when_arca_reports_a_server_down(self):
        self.make_invoice(status=Invoice.Status.ERROR, meta={'vat_rate': '10.5', 'arca_retry': True})
        self.use(FakeTransport({'FEDummy': [dummy_response(db='ERROR')]}))

        summary = retry_pending_invoices()

        self.assertFalse(summary['arca_up'])
        self.assertIn('db_server', summary['detail'])

    def test_retry_authorizes_pending_invoices_when_arca_is_back(self):
        first = self.make_invoice('a', status=Invoice.Status.ERROR, meta={'vat_rate': '10.5', 'arca_retry': True})
        # Factura de antes de este cambio: solo tiene el mensaje de error de conexion.
        legacy = self.make_invoice(
            'b', total='1000.00', status=Invoice.Status.ERROR,
            error_message="No se pudo conectar con ARCA: ('Connection aborted.', ConnectionResetError(104))",
        )
        transport = self.use(FakeTransport({
            'FEDummy': [dummy_response()],
            'FECompUltimoAutorizado': [last_authorized_response(7), last_authorized_response(8)],
            'FECAESolicitar': [cae_response('A', cae='76000000000008'), cae_response('A', cae='76000000000009')],
        }))

        summary = retry_pending_invoices()

        self.assertEqual(summary['authorized'], 2)
        first.refresh_from_db()
        legacy.refresh_from_db()
        self.assertEqual((first.status, first.voucher_number), (Invoice.Status.AUTHORIZED, 8))
        self.assertEqual((legacy.status, legacy.voucher_number), (Invoice.Status.AUTHORIZED, 9))
        self.assertNotIn('arca_retry', first.meta)
        self.assertIn('auto_retried_at', first.meta)
        self.assertEqual(transport.count('FECAESolicitar'), 2)
        self.assertFalse(retryable_invoices().exists())

    def test_rejected_invoices_are_never_retried(self):
        self.make_invoice(status=Invoice.Status.REJECTED, error_message='10013: dato invalido')
        self.make_invoice('c', status=Invoice.Status.ERROR, error_message='Faltan ARCA_CERT_PATH')
        transport = self.use(FakeTransport({}))

        summary = retry_pending_invoices()

        self.assertEqual(summary['candidates'], 0)
        self.assertEqual(transport.calls, [])

    def test_retry_stops_if_arca_drops_again(self):
        self.make_invoice('a', status=Invoice.Status.ERROR, meta={'vat_rate': '10.5', 'arca_retry': True})
        second = self.make_invoice('b', status=Invoice.Status.ERROR, meta={'vat_rate': '10.5', 'arca_retry': True})
        self.use(FakeTransport({
            'FEDummy': [dummy_response()],
            'FECompUltimoAutorizado': [RESET],
        }))

        summary = retry_pending_invoices()

        self.assertEqual(summary['still_pending'], 2)
        second.refresh_from_db()
        self.assertTrue(second.meta['arca_retry'])

    def test_uncertain_attempt_from_another_day_is_recovered_not_reissued(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        invoice = self.make_invoice(
            status=Invoice.Status.ERROR,
            issue_date=yesterday,
            meta={'vat_rate': '10.5', 'arca_retry': True, 'arca_pending_number': 31},
            error_message='No se pudo conectar con ARCA: timeout',
        )
        transport = self.use(FakeTransport({
            'FEDummy': [dummy_response()],
            'FECompConsultar': [consult_response(31, '24363.00', yesterday)],
        }))

        retry_pending_invoices()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.AUTHORIZED)
        self.assertEqual(invoice.voucher_number, 31)
        self.assertEqual(invoice.issue_date, yesterday)
        self.assertEqual(transport.count('FECAESolicitar'), 0)

    def test_pending_date_is_stored_with_the_pending_number(self):
        invoice = self.make_invoice()
        self.use(FakeTransport({
            'FECompUltimoAutorizado': [last_authorized_response(3)],
            'FECAESolicitar': [RESET],
        }))
        with self.assertRaises(ArcaConnectionError):
            authorize_invoice_wsfe(invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.meta['arca_pending_number'], 4)
        self.assertEqual(invoice.meta['arca_pending_date'], timezone.localdate().isoformat())
        self.assertTrue(invoice.meta['arca_retry'])

    def test_retried_credit_note_cancels_the_original_invoice(self):
        original = self.make_invoice(
            'orig', status=Invoice.Status.AUTHORIZED, voucher_number=42, cae='76000000000001',
            issue_date=timezone.localdate() - timedelta(days=1),
        )
        payment = Payment.objects.create(
            source=Payment.Source.GETNET, status=Payment.Status.APPROVED, date=original.issue_date,
            amount=original.total_amount, external_id='cup-1', idempotency_key='getnet:cup-1', invoice=original,
        )
        credit_note = self.make_invoice(
            'nc', voucher_type=8, cancels=original, status=Invoice.Status.ERROR,
            meta={'vat_rate': '10.5', 'arca_retry': True, 'reason': 'Error de carga'},
        )
        InvoiceLine.objects.create(invoice=credit_note, description='Anulacion', unit_price=original.total_amount,
                                   total=original.total_amount)
        self.use(FakeTransport({
            'FEDummy': [dummy_response()],
            'FECompUltimoAutorizado': [last_authorized_response(0)],
            'FECAESolicitar': [cae_response('A')],
        }))

        retry_pending_invoices()

        credit_note.refresh_from_db()
        original.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(credit_note.status, Invoice.Status.AUTHORIZED)
        self.assertEqual(original.status, Invoice.Status.CANCELLED)
        self.assertEqual(original.meta['cancel_reason'], 'Error de carga')
        self.assertIsNone(payment.invoice)

    @override_settings(ARCA_AUTO_RETRY_MAX_AGE_DAYS=3)
    def test_old_failures_are_left_for_manual_review(self):
        invoice = self.make_invoice(status=Invoice.Status.ERROR, meta={'arca_retry': True})
        Invoice.objects.filter(pk=invoice.pk).update(created_at=timezone.now() - timedelta(days=5))
        self.assertFalse(retryable_invoices().exists())

    def test_status_reports_pending_retry(self):
        self.make_invoice(status=Invoice.Status.ERROR, meta={'arca_retry': True})
        self.use(FakeTransport({'FEDummy': [RESET]}))
        user = get_user_model().objects.create_user(username='admin', password='x', is_staff=True)
        api = APIClient()
        api.force_authenticate(user)

        data = api.get('/api/billing/arca/status/').json()

        self.assertFalse(data['ready'])
        self.assertEqual(data['pending_retry'], {'count': 1, 'total': 24363.0})


@override_settings(**WSFE_SETTINGS)
class VerifyWithArcaTests(ArcaRetryBase):
    def test_reports_matches_differences_missing_and_unknown_vouchers(self):
        day = date(2026, 11, 10)
        self.make_invoice('ok', status=Invoice.Status.AUTHORIZED, voucher_number=10, cae='CAE10', issue_date=day)
        self.make_invoice('diff', total='500.00', status=Invoice.Status.AUTHORIZED, voucher_number=11,
                          cae='CAE11', issue_date=day)
        self.make_invoice('gone', total='700.00', status=Invoice.Status.AUTHORIZED, voucher_number=13,
                          cae='CAE13', issue_date=day)
        transport = self.use(FakeTransport({
            'FECompConsultar': [
                consult_response(10, '24363.00', day, cae='CAE10'),
                consult_response(11, '550.00', day, cae='CAE11'),
                not_found_response(),
                # Numero 12: el ERP no lo tiene pero ARCA si.
                consult_response(12, '999.00', day, cae='CAE12'),
            ],
        }))

        report = verify_invoices_with_arca(date(2026, 11, 1), date(2026, 11, 30))

        self.assertEqual(report['checked'], 3)
        self.assertEqual(report['counts'], {'ok': 1, 'mismatch': 1, 'missing': 1, 'simulated': 0})
        self.assertFalse(report['all_ok'])
        self.assertEqual(report['totals']['erp_active_invoices'], 25563.0)
        self.assertEqual(report['totals']['arca_active_invoices'], 24913.0)
        problems = {entry['voucher']: entry for entry in report['problems']}
        self.assertIn('Importe distinto', problems['FB 00004-00000011']['problems'][0])
        self.assertEqual(problems['FB 00004-00000013']['result'], 'missing')
        self.assertEqual(report['not_in_erp']['vouchers'][0]['voucher'], 'FB 00004-00000012')
        self.assertEqual(transport.count('FECompConsultar'), 4)

    def test_all_ok_and_simulated_vouchers_are_flagged(self):
        day = date(2026, 11, 10)
        self.make_invoice('ok', status=Invoice.Status.AUTHORIZED, voucher_number=1, cae='CAE1', issue_date=day)
        self.make_invoice('mock', status=Invoice.Status.AUTHORIZED, voucher_number=2, cae='MOCK2026', issue_date=day,
                          provider_result={'provider': 'mock'})
        self.use(FakeTransport({'FECompConsultar': [consult_response(1, '24363.00', day, cae='CAE1')]}))

        report = verify_invoices_with_arca(date(2026, 11, 1), date(2026, 11, 30))

        self.assertEqual(report['counts']['ok'], 1)
        self.assertEqual(report['counts']['simulated'], 1)
        self.assertFalse(report['all_ok'])

    def test_api_returns_503_when_arca_is_down(self):
        self.make_invoice(status=Invoice.Status.AUTHORIZED, voucher_number=1, cae='CAE1',
                          issue_date=date(2026, 11, 10))
        self.use(FakeTransport({'FECompConsultar': [RESET]}))
        user = get_user_model().objects.create_user(username='admin', password='x', is_staff=True)
        api = APIClient()
        api.force_authenticate(user)

        response = api.get('/api/billing/arca/verify/?year=2026&month=11')

        self.assertEqual(response.status_code, 503)
        self.assertIn('No se pudo conectar con ARCA', response.json()['detail'])
