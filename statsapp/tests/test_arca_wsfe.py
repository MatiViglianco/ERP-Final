import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from statsapp import arca_services
from statsapp.arca_client import ArcaServiceError
from statsapp.arca_services import authorize_invoice_wsfe, get_access_ticket, split_vat_included
from statsapp.models import ArcaAccessTicket, GetnetTerminal, Invoice, Payment

CUIT = '20111111112'


def _soap(inner):
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        f'{inner}'
        '</soap:Body></soap:Envelope>'
    ).encode('utf-8')


def last_authorized_response(number):
    return _soap(
        '<FECompUltimoAutorizadoResponse xmlns="http://ar.gov.afip.dif.FEV1/">'
        f'<FECompUltimoAutorizadoResult><PtoVta>4</PtoVta><CbteTipo>6</CbteTipo><CbteNro>{number}</CbteNro>'
        '</FECompUltimoAutorizadoResult></FECompUltimoAutorizadoResponse>'
    )


def cae_response(result='A', cae='76123456789012', errors=None, observations=None):
    errors_xml = ''
    if errors:
        errors_xml = '<Errors>' + ''.join(
            f'<Err><Code>{code}</Code><Msg>{msg}</Msg></Err>' for code, msg in errors
        ) + '</Errors>'
    obs_xml = ''
    if observations:
        obs_xml = '<Observaciones>' + ''.join(
            f'<Obs><Code>{code}</Code><Msg>{msg}</Msg></Obs>' for code, msg in observations
        ) + '</Observaciones>'
    cae_xml = f'<CAE>{cae}</CAE><CAEFchVto>20261201</CAEFchVto>' if result == 'A' else '<CAE></CAE><CAEFchVto></CAEFchVto>'
    return _soap(
        '<FECAESolicitarResponse xmlns="http://ar.gov.afip.dif.FEV1/"><FECAESolicitarResult>'
        f'<FeCabResp><Cuit>{CUIT}</Cuit><PtoVta>4</PtoVta><CbteTipo>6</CbteTipo><Resultado>{result}</Resultado></FeCabResp>'
        '<FeDetResp><FECAEDetResponse>'
        f'<Concepto>1</Concepto><DocTipo>99</DocTipo><DocNro>0</DocNro><Resultado>{result}</Resultado>'
        f'{obs_xml}{cae_xml}'
        '</FECAEDetResponse></FeDetResp>'
        f'{errors_xml}'
        '</FECAESolicitarResult></FECAESolicitarResponse>'
    )


def consult_response(number, total, issue_date, cae='76999999999999'):
    return _soap(
        '<FECompConsultarResponse xmlns="http://ar.gov.afip.dif.FEV1/"><FECompConsultarResult><ResultGet>'
        f'<Concepto>1</Concepto><DocTipo>99</DocTipo><DocNro>0</DocNro><CbteDesde>{number}</CbteDesde>'
        f'<CbteHasta>{number}</CbteHasta><CbteFch>{issue_date.strftime("%Y%m%d")}</CbteFch>'
        f'<ImpTotal>{total}</ImpTotal><Resultado>A</Resultado><CodAutorizacion>{cae}</CodAutorizacion>'
        '<FchVto>20261205</FchVto>'
        '</ResultGet></FECompConsultarResult></FECompConsultarResponse>'
    )


def login_response(expires):
    ticket = (
        '<?xml version="1.0" encoding="UTF-8"?><loginTicketResponse version="1.0"><header>'
        '<source>CN=wsaahomo</source><destination>SERIALNUMBER=CUIT 20111111112</destination>'
        '<uniqueId>1</uniqueId><generationTime>2026-11-21T10:00:00.000-03:00</generationTime>'
        f'<expirationTime>{expires}</expirationTime></header>'
        '<credentials><token>TOKEN-ABC</token><sign>SIGN-XYZ</sign></credentials></loginTicketResponse>'
    )
    escaped = ticket.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return _soap(
        '<loginCmsResponse xmlns="http://wsaa.view.sua.dvadac.desein.afip.gov">'
        f'<loginCmsReturn>{escaped}</loginCmsReturn></loginCmsResponse>'
    )


class FakeTransport:
    """Responde segun el metodo SOAP; cada metodo tiene una cola de respuestas."""

    def __init__(self, responses):
        self.responses = {method: list(items) for method, items in responses.items()}
        self.calls = []

    def post(self, url, body, soap_action):
        method = soap_action.rsplit('/', 1)[-1] or 'loginCms'
        self.calls.append((method, body))
        queue = self.responses.get(method)
        if not queue:
            raise AssertionError(f'Llamada inesperada a {method}')
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def count(self, method):
        return sum(1 for name, _ in self.calls if name == method)

    def body(self, method, index=0):
        return [body for name, body in self.calls if name == method][index]


def _self_signed_credentials(directory):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, 'erptest'),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, f'CUIT {CUIT}'),
    ])
    now = timezone.now()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    cert_path = Path(directory) / 'test.crt'
    key_path = Path(directory) / 'test.key'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    return str(cert_path), str(key_path)


WSFE_SETTINGS = {
    'ARCA_PROVIDER': 'wsfe',
    'ARCA_ENVIRONMENT': 'homologacion',
    'ARCA_CUIT': CUIT,
    'ARCA_DEFAULT_POINT_OF_SALE': 4,
    'ARCA_GETNET_VOUCHER_TYPE': 6,
    'ARCA_DEFAULT_VAT_RATE': '10.5',
}


class VatSplitTests(TestCase):
    def test_net_plus_vat_always_matches_total(self):
        for total in ['24363', '1000', '99.99', '15750.50', '0.10', '123456.78']:
            for rate in ['10.5', '21']:
                net, vat = split_vat_included(Decimal(total), rate)
                self.assertEqual(net + vat, Decimal(total).quantize(Decimal('0.01')))
                expected_vat = (net * Decimal(rate) / 100).quantize(Decimal('0.01'))
                self.assertLessEqual(abs(expected_vat - vat), Decimal('0.01'))


@override_settings(**WSFE_SETTINGS)
class WsfeAuthorizationTests(TestCase):
    def setUp(self):
        ArcaAccessTicket.objects.create(
            environment='homologacion',
            service='wsfe',
            cuit=CUIT,
            token='TOKEN',
            sign='SIGN',
            generated_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=10),
        )
        self.invoice = Invoice.objects.create(
            source=Invoice.Source.GETNET,
            point_of_sale=4,
            voucher_type=6,
            total_amount=Decimal('24363.00'),
            net_amount=Decimal('24363.00'),
            idempotency_key='test-invoice-1',
            meta={'vat_rate': '10.5'},
        )

    def authorize(self, transport):
        arca_services.set_transport_factory(lambda: transport)
        self.addCleanup(arca_services.set_transport_factory, None)
        return authorize_invoice_wsfe(self.invoice)

    def test_uses_next_number_from_arca_and_stores_cae(self):
        transport = FakeTransport({
            'FECompUltimoAutorizado': [last_authorized_response(41)],
            'FECAESolicitar': [cae_response('A', cae='76111222333444')],
        })

        invoice = self.authorize(transport)

        self.assertEqual(invoice.status, Invoice.Status.AUTHORIZED)
        self.assertEqual(invoice.voucher_number, 42)
        self.assertEqual(invoice.cae, '76111222333444')
        self.assertEqual(invoice.cae_due_date, date(2026, 12, 1))
        self.assertEqual(invoice.net_amount + invoice.vat_amount, Decimal('24363.00'))
        body = transport.body('FECAESolicitar')
        self.assertIn('<ar:CbteDesde>42</ar:CbteDesde>', body)
        self.assertIn('<ar:CbteTipo>6</ar:CbteTipo>', body)
        self.assertIn('<ar:DocTipo>99</ar:DocTipo>', body)
        self.assertIn('<ar:CondicionIVAReceptorId>5</ar:CondicionIVAReceptorId>', body)
        self.assertIn('<ar:Id>4</ar:Id>', body)
        self.assertIn('<ar:ImpTotal>24363.00</ar:ImpTotal>', body)
        self.assertIn(f'<ar:Cuit>{CUIT}</ar:Cuit>', body)

    def test_rejection_is_saved_and_not_rolled_back(self):
        transport = FakeTransport({
            'FECompUltimoAutorizado': [last_authorized_response(5)],
            'FECAESolicitar': [cae_response('R', errors=[(10013, 'Error de prueba')])],
        })

        with self.assertRaises(ArcaServiceError):
            self.authorize(transport)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.REJECTED)
        self.assertIn('10013', self.invoice.error_message)
        self.assertIsNone(self.invoice.voucher_number)
        self.assertNotIn('arca_pending_number', self.invoice.meta)

    def test_sequence_error_retries_with_fresh_number(self):
        transport = FakeTransport({
            'FECompUltimoAutorizado': [last_authorized_response(9), last_authorized_response(10)],
            'FECAESolicitar': [
                cae_response('R', errors=[(10016, 'El numero no es el proximo a autorizar')]),
                cae_response('A'),
            ],
        })

        invoice = self.authorize(transport)

        self.assertEqual(invoice.status, Invoice.Status.AUTHORIZED)
        self.assertEqual(invoice.voucher_number, 11)
        self.assertEqual(transport.count('FECAESolicitar'), 2)

    def test_uncertain_attempt_is_recovered_without_issuing_twice(self):
        failing = FakeTransport({
            'FECompUltimoAutorizado': [last_authorized_response(20)],
            'FECAESolicitar': [ArcaServiceError('timeout')],
        })
        with self.assertRaises(ArcaServiceError):
            self.authorize(failing)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.ERROR)
        self.assertEqual(self.invoice.meta['arca_pending_number'], 21)

        retry = FakeTransport({
            'FECompConsultar': [consult_response(21, '24363.00', timezone.localdate())],
        })
        invoice = self.authorize(retry)

        self.assertEqual(invoice.status, Invoice.Status.AUTHORIZED)
        self.assertEqual(invoice.voucher_number, 21)
        self.assertEqual(invoice.cae, '76999999999999')
        self.assertEqual(retry.count('FECAESolicitar'), 0)
        self.assertNotIn('arca_pending_number', invoice.meta)

    @override_settings(ARCA_ANONYMOUS_CONSUMER_LIMIT='1000')
    def test_blocks_anonymous_consumer_above_limit(self):
        with self.assertRaises(Exception) as ctx:
            self.authorize(FakeTransport({}))
        self.assertIn('identificar al consumidor final', str(ctx.exception))


@override_settings(**WSFE_SETTINGS)
class WsaaTicketTests(TestCase):
    def test_ticket_is_requested_once_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            cert_path, key_path = _self_signed_credentials(directory)
            expires = (timezone.localtime() + timedelta(hours=12)).replace(microsecond=0).isoformat()
            transport = FakeTransport({'loginCms': [login_response(expires)]})
            with override_settings(ARCA_CERT_PATH=cert_path, ARCA_KEY_PATH=key_path):
                first = get_access_ticket('wsfe', transport=transport)
                second = get_access_ticket('wsfe', transport=transport)

        self.assertEqual(first.token, 'TOKEN-ABC')
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(transport.count('loginCms'), 1)
        self.assertIn('<wsaa:in0>', transport.body('loginCms'))


@override_settings(ARCA_PROVIDER='mock', ARCA_DEFAULT_POINT_OF_SALE=4, ARCA_GETNET_VOUCHER_TYPE=6)
class GetnetInvoicingApiTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username='admin', password='admin123', is_staff=True, is_superuser=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(user)
        terminal = GetnetTerminal.objects.create(code='AR002R9R')
        today = timezone.localdate()
        self.payment = Payment.objects.create(
            source=Payment.Source.GETNET,
            status=Payment.Status.RECONCILED,
            date=today,
            amount=Decimal('24363.00'),
            external_id='getnet-1',
            idempotency_key='getnet:getnet-1',
            terminal=terminal,
            meta={'getnet_csv': {'brand': 'VISA', 'coupon_number': '16362', 'card_last_four': '1234'}},
        )
        Payment.objects.create(
            source=Payment.Source.GETNET,
            status=Payment.Status.REJECTED,
            date=today,
            amount=Decimal('500.00'),
            external_id='getnet-rejected',
            idempotency_key='getnet:getnet-rejected',
            terminal=terminal,
        )
        Payment.objects.create(
            source=Payment.Source.GETNET,
            status=Payment.Status.RECONCILED,
            date=today,
            amount=Decimal('-300.00'),
            external_id='getnet-reversal',
            idempotency_key='getnet:getnet-reversal',
            terminal=terminal,
        )
        self.params = {'year': today.year, 'month': today.month}

    def test_lists_only_approved_positive_uninvoiced_coupons(self):
        response = self.api.get('/api/billing/getnet/invoiceable/', self.params)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['external_id'] for item in response.data], ['getnet-1'])
        self.assertEqual(response.data[0]['coupon_number'], '16362')
        self.assertEqual(response.data[0]['brand'], 'VISA')

    def test_invoices_selected_coupon_once(self):
        response = self.api.post(
            '/api/billing/getnet/invoices/',
            {'payment_ids': [str(self.payment.id)], 'vat_rate': '10.5'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['authorized'], 1)
        self.payment.refresh_from_db()
        invoice = self.payment.invoice
        self.assertEqual(invoice.status, Invoice.Status.AUTHORIZED)
        self.assertEqual(invoice.source, Invoice.Source.GETNET)
        self.assertEqual(invoice.voucher_type, 6)
        self.assertEqual(invoice.point_of_sale, 4)
        self.assertEqual(invoice.total_amount, Decimal('24363.00'))
        self.assertIn('VISA', invoice.lines.get().description)

        listed = self.api.get('/api/billing/getnet/invoiceable/', self.params)
        self.assertEqual(listed.data, [])

        again = self.api.post(
            '/api/billing/getnet/invoices/',
            {'payment_ids': [str(self.payment.id)]},
            format='json',
        )
        self.assertEqual(again.data['authorized'], 0)
        self.assertIn('ya esta facturado', again.data['results'][0]['detail'])
        self.assertEqual(Invoice.objects.filter(source=Invoice.Source.GETNET).count(), 1)

    def test_rejects_unsupported_vat_rate(self):
        response = self.api.post(
            '/api/billing/getnet/invoices/',
            {'payment_ids': [str(self.payment.id)], 'vat_rate': '27'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_arca_status_reports_mock_mode(self):
        response = self.api.get('/api/billing/arca/status/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['provider'], 'mock')
        self.assertFalse(response.data['ready'])
