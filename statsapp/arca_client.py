"""Cliente minimo para los web services de ARCA (ex AFIP).

- WSAA (LoginCms): obtiene token y firma a partir de un TRA firmado en CMS con
  el certificado del computador fiscal.
- WSFEv1: consulta el ultimo comprobante autorizado, consulta un comprobante y
  solicita CAE.

No depende de zeep: arma el SOAP a mano y lo parsea con ElementTree. Toda la
red pasa por ``ArcaTransport.post`` para poder reemplazarla en los tests.
"""

import base64
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from xml.sax.saxutils import escape

import requests
from requests.adapters import HTTPAdapter

WSAA_URLS = {
    'homologacion': 'https://wsaahomo.afip.gov.ar/ws/services/LoginCms',
    'produccion': 'https://wsaa.afip.gov.ar/ws/services/LoginCms',
}
WSFE_URLS = {
    'homologacion': 'https://wswhomo.afip.gov.ar/wsfev1/service.asmx',
    'produccion': 'https://servicios1.afip.gov.ar/wsfev1/service.asmx',
}
WSFE_NS = 'http://ar.gov.afip.dif.FEV1/'
SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'

# Codigos de alicuota de IVA de WSFEv1.
VAT_RATE_IDS = {
    Decimal('0'): 3,
    Decimal('2.5'): 9,
    Decimal('5'): 8,
    Decimal('10.5'): 4,
    Decimal('21'): 5,
    Decimal('27'): 6,
}

# Error de WSFE cuando el numero enviado no es el siguiente al ultimo autorizado.
WSFE_SEQUENCE_ERROR_CODES = {10016}


class ArcaError(Exception):
    pass


class ArcaConfigurationError(ArcaError):
    pass


class ArcaServiceError(ArcaError):
    def __init__(self, message, code=None, errors=None):
        super().__init__(message)
        self.code = code
        self.errors = errors or []


class _LegacyTLSAdapter(HTTPAdapter):
    """Los servidores de ARCA negocian claves DH chicas que OpenSSL 3 rechaza por defecto."""

    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.set_ciphers('DEFAULT@SECLEVEL=1')
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)


class ArcaTransport:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.mount('https://', _LegacyTLSAdapter())

    def post(self, url, body, soap_action):
        try:
            response = self.session.post(
                url,
                data=body.encode('utf-8'),
                headers={
                    'Content-Type': 'text/xml; charset=utf-8',
                    'SOAPAction': f'"{soap_action}"',
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ArcaServiceError(f'No se pudo conectar con ARCA: {exc}') from exc
        if response.status_code >= 500 and b'Fault' not in response.content:
            raise ArcaServiceError(f'ARCA respondio HTTP {response.status_code}')
        return response.content


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _find(node, *names):
    """Busca descendientes por nombre local, ignorando namespaces."""
    current = node
    for name in names:
        if current is None:
            return None
        current = next((child for child in current.iter() if _local(child.tag) == name and child is not current), None)
    return current


def _text(node, *names, default=''):
    found = _find(node, *names)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def _children(node, name):
    if node is None:
        return []
    return [child for child in node.iter() if _local(child.tag) == name]


def _soap_fault(root):
    fault = _find(root, 'Fault')
    if fault is None:
        return None
    return _text(fault, 'faultstring') or 'Error SOAP de ARCA'


def _parse_arca_datetime(value):
    value = (value or '').strip()
    if not value:
        return None
    # Ej: 2026-11-21T00:15:30.123-03:00
    if '.' in value:
        head, _, tail = value.partition('.')
        offset = ''
        for sign in ('+', '-'):
            if sign in tail:
                offset = sign + tail.split(sign, 1)[1]
                break
        value = head + offset
    return datetime.fromisoformat(value)


def _parse_yyyymmdd(value):
    value = (value or '').strip()
    if len(value) != 8:
        return None
    return datetime.strptime(value, '%Y%m%d').date()


@dataclass
class AccessTicket:
    token: str
    sign: str
    generated_at: datetime
    expires_at: datetime


@dataclass
class CaeResult:
    approved: bool
    result: str
    voucher_number: int
    cae: str = ''
    cae_due_date: object = None
    observations: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def messages(self):
        return [f"{item['code']}: {item['msg']}" for item in [*self.errors, *self.observations]]


def load_credentials(cert_path, key_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    if not cert_path or not key_path:
        raise ArcaConfigurationError('Faltan ARCA_CERT_PATH y/o ARCA_KEY_PATH')
    try:
        with open(cert_path, 'rb') as handle:
            certificate = x509.load_pem_x509_certificate(handle.read())
        with open(key_path, 'rb') as handle:
            private_key = serialization.load_pem_private_key(handle.read(), password=None)
    except FileNotFoundError as exc:
        raise ArcaConfigurationError(f'No se encontro el archivo {exc.filename}') from exc
    except ValueError as exc:
        raise ArcaConfigurationError(f'Certificado o clave privada invalidos: {exc}') from exc
    return certificate, private_key


def build_login_ticket_request(service, now):
    generation = (now - timedelta(minutes=10)).replace(microsecond=0)
    expiration = (now + timedelta(minutes=10)).replace(microsecond=0)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<loginTicketRequest version="1.0">'
        '<header>'
        f'<uniqueId>{int(now.timestamp())}</uniqueId>'
        f'<generationTime>{generation.isoformat()}</generationTime>'
        f'<expirationTime>{expiration.isoformat()}</expirationTime>'
        '</header>'
        f'<service>{escape(service)}</service>'
        '</loginTicketRequest>'
    )


def sign_login_ticket_request(tra_xml, certificate, private_key):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7

    signed = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra_xml.encode('utf-8'))
        .add_signer(certificate, private_key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [])
    )
    return base64.b64encode(signed).decode('ascii')


class WsaaClient:
    def __init__(self, environment, cert_path, key_path, transport):
        if environment not in WSAA_URLS:
            raise ArcaConfigurationError(f'ARCA_ENVIRONMENT invalido: {environment}')
        self.environment = environment
        self.cert_path = cert_path
        self.key_path = key_path
        self.transport = transport

    def login(self, service, now):
        certificate, private_key = load_credentials(self.cert_path, self.key_path)
        cms = sign_login_ticket_request(build_login_ticket_request(service, now), certificate, private_key)
        body = (
            f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}" '
            'xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">'
            '<soapenv:Header/><soapenv:Body><wsaa:loginCms>'
            f'<wsaa:in0>{cms}</wsaa:in0>'
            '</wsaa:loginCms></soapenv:Body></soapenv:Envelope>'
        )
        raw = self.transport.post(WSAA_URLS[self.environment], body, '')
        root = ET.fromstring(raw)
        fault = _soap_fault(root)
        if fault:
            raise ArcaServiceError(f'WSAA: {fault}')
        ticket_xml = _text(root, 'loginCmsReturn')
        if not ticket_xml:
            raise ArcaServiceError('WSAA no devolvio un ticket de acceso')
        ticket = ET.fromstring(ticket_xml.encode('utf-8'))
        token = _text(ticket, 'token')
        sign = _text(ticket, 'sign')
        generated = _parse_arca_datetime(_text(ticket, 'generationTime'))
        expires = _parse_arca_datetime(_text(ticket, 'expirationTime'))
        if not token or not sign or not expires:
            raise ArcaServiceError('WSAA devolvio un ticket incompleto')
        return AccessTicket(token=token, sign=sign, generated_at=generated or now, expires_at=expires)


def _money(value):
    return f'{Decimal(value).quantize(Decimal("0.01"))}'


class WsfeClient:
    def __init__(self, environment, cuit, ticket_provider, transport):
        if environment not in WSFE_URLS:
            raise ArcaConfigurationError(f'ARCA_ENVIRONMENT invalido: {environment}')
        if not cuit or not cuit.isdigit() or len(cuit) != 11:
            raise ArcaConfigurationError('ARCA_CUIT debe tener 11 digitos')
        self.environment = environment
        self.cuit = cuit
        self.ticket_provider = ticket_provider
        self.transport = transport

    def _auth(self):
        ticket = self.ticket_provider()
        return (
            '<ar:Auth>'
            f'<ar:Token>{escape(ticket.token)}</ar:Token>'
            f'<ar:Sign>{escape(ticket.sign)}</ar:Sign>'
            f'<ar:Cuit>{self.cuit}</ar:Cuit>'
            '</ar:Auth>'
        )

    def _call(self, method, inner_xml):
        body = (
            f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}" xmlns:ar="{WSFE_NS}">'
            '<soapenv:Header/><soapenv:Body>'
            f'<ar:{method}>{inner_xml}</ar:{method}>'
            '</soapenv:Body></soapenv:Envelope>'
        )
        raw = self.transport.post(WSFE_URLS[self.environment], body, f'{WSFE_NS}{method}')
        root = ET.fromstring(raw)
        fault = _soap_fault(root)
        if fault:
            raise ArcaServiceError(f'WSFE {method}: {fault}')
        result = _find(root, f'{method}Result')
        if result is None:
            raise ArcaServiceError(f'WSFE {method}: respuesta sin resultado')
        return result

    @staticmethod
    def _errors(result):
        return [
            {'code': int(_text(err, 'Code') or 0), 'msg': _text(err, 'Msg')}
            for err in _children(_find(result, 'Errors'), 'Err')
        ]

    def dummy(self):
        result = self._call('FEDummy', '')
        return {
            'app_server': _text(result, 'AppServer'),
            'db_server': _text(result, 'DbServer'),
            'auth_server': _text(result, 'AuthServer'),
        }

    def last_authorized(self, point_of_sale, voucher_type):
        result = self._call(
            'FECompUltimoAutorizado',
            f'{self._auth()}<ar:PtoVta>{int(point_of_sale)}</ar:PtoVta><ar:CbteTipo>{int(voucher_type)}</ar:CbteTipo>',
        )
        errors = self._errors(result)
        if errors:
            raise ArcaServiceError(
                'WSFE FECompUltimoAutorizado: ' + '; '.join(f"{e['code']}: {e['msg']}" for e in errors),
                code=errors[0]['code'],
                errors=errors,
            )
        return int(_text(result, 'CbteNro') or 0)

    def get_voucher(self, point_of_sale, voucher_type, number):
        result = self._call(
            'FECompConsultar',
            f'{self._auth()}<ar:FeCompConsReq><ar:CbteTipo>{int(voucher_type)}</ar:CbteTipo>'
            f'<ar:CbteNro>{int(number)}</ar:CbteNro><ar:PtoVta>{int(point_of_sale)}</ar:PtoVta></ar:FeCompConsReq>',
        )
        errors = self._errors(result)
        if errors:
            # 602: no existe el comprobante consultado.
            if any(err['code'] == 602 for err in errors):
                return None
            raise ArcaServiceError(
                'WSFE FECompConsultar: ' + '; '.join(f"{e['code']}: {e['msg']}" for e in errors),
                code=errors[0]['code'],
                errors=errors,
            )
        get = _find(result, 'ResultGet')
        if get is None:
            return None
        return {
            'number': int(_text(get, 'CbteDesde') or 0),
            'date': _parse_yyyymmdd(_text(get, 'CbteFch')),
            'total': Decimal(_text(get, 'ImpTotal') or '0'),
            'doc_type': int(_text(get, 'DocTipo') or 0),
            'doc_number': int(_text(get, 'DocNro') or 0),
            'cae': _text(get, 'CodAutorizacion'),
            'cae_due_date': _parse_yyyymmdd(_text(get, 'FchVto')),
            'result': _text(get, 'Resultado'),
        }

    def request_cae(self, *, point_of_sale, voucher_type, number, issue_date, total, net, vat, vat_rate,
                    doc_type=99, doc_number=0, receiver_vat_condition=5, concept=1):
        vat_id = VAT_RATE_IDS.get(Decimal(str(vat_rate)))
        if vat_id is None:
            raise ArcaConfigurationError(f'Alicuota de IVA no soportada: {vat_rate}')
        detail = (
            '<ar:FECAEDetRequest>'
            f'<ar:Concepto>{int(concept)}</ar:Concepto>'
            f'<ar:DocTipo>{int(doc_type)}</ar:DocTipo>'
            f'<ar:DocNro>{int(doc_number)}</ar:DocNro>'
            f'<ar:CbteDesde>{int(number)}</ar:CbteDesde>'
            f'<ar:CbteHasta>{int(number)}</ar:CbteHasta>'
            f'<ar:CbteFch>{issue_date.strftime("%Y%m%d")}</ar:CbteFch>'
            f'<ar:ImpTotal>{_money(total)}</ar:ImpTotal>'
            '<ar:ImpTotConc>0.00</ar:ImpTotConc>'
            f'<ar:ImpNeto>{_money(net)}</ar:ImpNeto>'
            '<ar:ImpOpEx>0.00</ar:ImpOpEx>'
            '<ar:ImpTrib>0.00</ar:ImpTrib>'
            f'<ar:ImpIVA>{_money(vat)}</ar:ImpIVA>'
            '<ar:MonId>PES</ar:MonId>'
            '<ar:MonCotiz>1</ar:MonCotiz>'
            f'<ar:CondicionIVAReceptorId>{int(receiver_vat_condition)}</ar:CondicionIVAReceptorId>'
            '<ar:Iva><ar:AlicIva>'
            f'<ar:Id>{vat_id}</ar:Id>'
            f'<ar:BaseImp>{_money(net)}</ar:BaseImp>'
            f'<ar:Importe>{_money(vat)}</ar:Importe>'
            '</ar:AlicIva></ar:Iva>'
            '</ar:FECAEDetRequest>'
        )
        inner = (
            f'{self._auth()}<ar:FeCAEReq>'
            '<ar:FeCabReq><ar:CantReg>1</ar:CantReg>'
            f'<ar:PtoVta>{int(point_of_sale)}</ar:PtoVta><ar:CbteTipo>{int(voucher_type)}</ar:CbteTipo>'
            '</ar:FeCabReq>'
            f'<ar:FeDetReq>{detail}</ar:FeDetReq>'
            '</ar:FeCAEReq>'
        )
        result = self._call('FECAESolicitar', inner)
        errors = self._errors(result)
        det = _find(result, 'FECAEDetResponse')
        observations = [
            {'code': int(_text(obs, 'Code') or 0), 'msg': _text(obs, 'Msg')}
            for obs in _children(_find(det, 'Observaciones'), 'Obs')
        ] if det is not None else []
        outcome = _text(det, 'Resultado') if det is not None else ''
        outcome = outcome or _text(result, 'FeCabResp', 'Resultado') or 'R'
        cae = _text(det, 'CAE') if det is not None else ''
        return CaeResult(
            approved=outcome == 'A' and bool(cae),
            result=outcome,
            voucher_number=int(number),
            cae=cae,
            cae_due_date=_parse_yyyymmdd(_text(det, 'CAEFchVto')) if det is not None else None,
            observations=observations,
            errors=errors,
            raw={'result': outcome, 'errors': errors, 'observations': observations},
        )
