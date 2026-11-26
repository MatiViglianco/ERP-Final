"""Emision de comprobantes reales con ARCA (WSAA + WSFEv1).

Reglas importantes:
- La numeracion siempre sale de FECompUltimoAutorizado: el punto de venta puede
  estar compartido con otro sistema, asi que el ERP nunca inventa numeros.
- Se emite de a un comprobante por punto de venta y tipo (fila ArcaSequence
  bloqueada con select_for_update).
- Si una emision quedo en duda (error de red despues de enviar), el siguiente
  intento consulta FECompConsultar con el numero pendiente y, si coincide con la
  factura, adopta ese CAE en lugar de emitir otra.
- Si ARCA no respondio, la factura queda en error con ``meta['arca_retry']`` y
  ``arca_retry.py`` la vuelve a intentar sola cuando el servicio se recupera.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from .arca_client import (
    CREDIT_NOTE_VOUCHER_TYPES,
    WSFE_SEQUENCE_ERROR_CODES,
    ArcaConfigurationError,
    ArcaConnectionError,
    ArcaError,
    ArcaServiceError,
    ArcaTransport,
    WsaaClient,
    WsfeClient,
)
from .models import ArcaAccessTicket, ArcaSequence, Invoice

CENT = Decimal('0.01')
TICKET_SAFETY_MARGIN = timedelta(minutes=10)
CONSUMER_FINAL_VAT_CONDITION = 5
ANONYMOUS_DOC_TYPE = 99

_transport_factory = None


def set_transport_factory(factory):
    """Permite a los tests reemplazar la red por un transporte falso."""
    global _transport_factory
    _transport_factory = factory


def _transport():
    if _transport_factory is not None:
        return _transport_factory()
    return ArcaTransport(timeout=getattr(settings, 'ARCA_HTTP_TIMEOUT', 30))


def arca_environment():
    return (getattr(settings, 'ARCA_ENVIRONMENT', 'homologacion') or 'homologacion').lower()


def arca_cuit():
    return (getattr(settings, 'ARCA_CUIT', '') or '').replace('-', '').strip()


def get_access_ticket(service='wsfe', transport=None):
    environment = arca_environment()
    cuit = arca_cuit()
    now = timezone.now()
    cached = ArcaAccessTicket.objects.filter(environment=environment, service=service, cuit=cuit).first()
    if cached and cached.expires_at - TICKET_SAFETY_MARGIN > now:
        return cached

    wsaa = WsaaClient(
        environment,
        getattr(settings, 'ARCA_CERT_PATH', ''),
        getattr(settings, 'ARCA_KEY_PATH', ''),
        transport or _transport(),
    )
    ticket = wsaa.login(service, timezone.localtime(now))
    stored, _ = ArcaAccessTicket.objects.update_or_create(
        environment=environment,
        service=service,
        cuit=cuit,
        defaults={
            'token': ticket.token,
            'sign': ticket.sign,
            'generated_at': ticket.generated_at,
            'expires_at': ticket.expires_at,
        },
    )
    return stored


def wsfe_client(transport=None):
    transport = transport or _transport()
    return WsfeClient(
        arca_environment(),
        arca_cuit(),
        lambda: get_access_ticket('wsfe', transport=transport),
        transport,
    )


def split_vat_included(total, vat_rate):
    """Separa neto e IVA de un importe final, de forma que neto + IVA == total.

    ARCA valida que el IVA informado sea neto * alicuota (redondeado), asi que se
    busca el neto cuyo IVA redondeado completa exactamente el total cobrado.
    """
    total = Decimal(total).quantize(CENT)
    rate = Decimal(str(vat_rate))
    if rate == 0:
        return total, Decimal('0.00')
    factor = rate / Decimal('100')
    estimate = (total / (Decimal('1') + factor)).quantize(CENT, rounding=ROUND_HALF_UP)
    for delta in (0, 1, -1, 2, -2, 3, -3):
        net = estimate + CENT * delta
        vat = (net * factor).quantize(CENT, rounding=ROUND_HALF_UP)
        if net + vat == total:
            return net, vat
    vat = total - estimate
    return estimate, vat


def _invoice_vat_rate(invoice):
    value = (invoice.meta or {}).get('vat_rate') or getattr(settings, 'ARCA_DEFAULT_VAT_RATE', '10.5')
    return Decimal(str(value))


def _validate_ready(invoice):
    if arca_environment() not in {'homologacion', 'produccion'}:
        raise ArcaConfigurationError('ARCA_ENVIRONMENT debe ser homologacion o produccion')
    if len(arca_cuit()) != 11:
        raise ArcaConfigurationError('Configura ARCA_CUIT con los 11 digitos del emisor')
    if not invoice.point_of_sale:
        raise ArcaConfigurationError('La factura no tiene punto de venta (ARCA_DEFAULT_POINT_OF_SALE)')
    if not invoice.voucher_type:
        raise ArcaConfigurationError('La factura no tiene tipo de comprobante')
    if invoice.voucher_type not in {6, 7, 8}:
        raise ArcaConfigurationError('Por ahora solo se emiten comprobantes B a consumidor final')
    if invoice.voucher_type in CREDIT_NOTE_VOUCHER_TYPES:
        original = invoice.cancels
        if original is None or not original.voucher_number:
            raise ArcaConfigurationError('La nota de credito no tiene una factura autorizada asociada')
        if original.point_of_sale != invoice.point_of_sale:
            raise ArcaConfigurationError('La nota de credito debe emitirse en el mismo punto de venta que la factura')
        if invoice.total_amount != original.total_amount:
            raise ArcaConfigurationError('La nota de credito debe anular el total de la factura')
        return
    limit = Decimal(str(getattr(settings, 'ARCA_ANONYMOUS_CONSUMER_LIMIT', '10000000')))
    if invoice.total_amount >= limit:
        raise ArcaConfigurationError(
            f'El importe supera {limit} y ARCA exige identificar al consumidor final'
        )


def _associated_vouchers(invoice):
    if invoice.voucher_type not in CREDIT_NOTE_VOUCHER_TYPES:
        return None
    original = invoice.cancels
    return [{
        'voucher_type': original.voucher_type,
        'point_of_sale': original.point_of_sale,
        'number': original.voucher_number,
        'cuit': arca_cuit(),
        'issue_date': original.issue_date,
    }]


def _sequence_row(invoice):
    row, _ = ArcaSequence.objects.get_or_create(
        environment=arca_environment(),
        cuit=arca_cuit(),
        point_of_sale=invoice.point_of_sale,
        voucher_type=invoice.voucher_type,
    )
    return ArcaSequence.objects.select_for_update().get(pk=row.pk)


def _mark_authorized(invoice, number, cae, cae_due_date, provider_result):
    invoice.voucher_number = number
    invoice.cae = cae
    invoice.cae_due_date = cae_due_date
    invoice.status = Invoice.Status.AUTHORIZED
    invoice.error_message = ''
    invoice.provider_result = provider_result
    meta = dict(invoice.meta or {})
    meta.pop('arca_pending_number', None)
    meta.pop('arca_pending_date', None)
    meta.pop('arca_retry', None)
    invoice.meta = meta
    invoice.save(update_fields=[
        'voucher_number', 'cae', 'cae_due_date', 'status', 'error_message',
        'provider_result', 'meta', 'net_amount', 'vat_amount', 'issue_date', 'updated_at',
    ])
    return invoice


def _recover_pending(client, invoice, previous_issue_date=None):
    """Si un intento previo quedo en duda, adopta el CAE si ARCA ya lo emitio."""
    pending = (invoice.meta or {}).get('arca_pending_number')
    if not pending:
        return None
    found = client.get_voucher(invoice.point_of_sale, invoice.voucher_type, int(pending))
    # El intento en duda pudo ser otro dia: se compara con la fecha que se envio entonces.
    pending_date = (invoice.meta or {}).get('arca_pending_date')
    if pending_date:
        sent_date = date.fromisoformat(pending_date)
    else:
        sent_date = previous_issue_date or invoice.issue_date
    if (
        found
        and found.get('cae')
        and found['total'] == invoice.total_amount
        and found['date'] == sent_date
        and not Invoice.objects.filter(
            point_of_sale=invoice.point_of_sale,
            voucher_type=invoice.voucher_type,
            voucher_number=found['number'],
        ).exclude(pk=invoice.pk).exists()
    ):
        invoice.issue_date = sent_date
        return _mark_authorized(invoice, found['number'], found['cae'], found['cae_due_date'], {
            'provider': 'wsfe',
            'environment': arca_environment(),
            'recovered': True,
            'result': 'A',
        })
    meta = dict(invoice.meta or {})
    meta.pop('arca_pending_number', None)
    meta.pop('arca_pending_date', None)
    invoice.meta = meta
    return None


def authorize_invoice_wsfe(invoice, client=None):
    """Emite la factura en ARCA. Los errores se guardan en la factura antes de propagarse."""
    client = client or wsfe_client()
    try:
        invoice, failure = _authorize_invoice_wsfe(invoice, client)
    except ArcaError as exc:
        # Fallo antes de pedir el CAE (ticket, ultimo autorizado, consulta): nada se guardo.
        _record_failure(invoice.pk, exc)
        raise
    if failure is not None:
        _record_failure(invoice.pk, failure)
        raise failure
    return invoice


def _record_failure(invoice_pk, exc):
    """Deja la factura en error y marca si conviene reintentarla sola (ARCA no respondio)."""
    with db_transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice_pk)
        if locked.status in (Invoice.Status.AUTHORIZED, Invoice.Status.CANCELLED):
            return locked
        meta = dict(locked.meta or {})
        retryable = isinstance(exc, ArcaConnectionError)
        if retryable:
            meta['arca_retry'] = True
        else:
            meta.pop('arca_retry', None)
        locked.meta = meta
        fields = ['meta', 'updated_at']
        if locked.status in (Invoice.Status.DRAFT, Invoice.Status.ERROR):
            locked.status = Invoice.Status.ERROR
            locked.error_message = str(exc)
            fields += ['status', 'error_message']
        locked.save(update_fields=fields)
        return locked


def _authorize_invoice_wsfe(invoice, client):
    with db_transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.status == Invoice.Status.AUTHORIZED:
            return locked, None
        if locked.status == Invoice.Status.CANCELLED:
            return locked, ArcaConfigurationError('La factura esta anulada y no se puede volver a autorizar')
        _validate_ready(locked)
        sequence = _sequence_row(locked)

        vat_rate = _invoice_vat_rate(locked)
        net, vat = split_vat_included(locked.total_amount, vat_rate)
        locked.net_amount = net
        locked.vat_amount = vat
        previous_issue_date = locked.issue_date
        locked.issue_date = timezone.localdate()

        recovered = _recover_pending(client, locked, previous_issue_date)
        if recovered:
            return recovered, None

        attempts = 0
        while True:
            attempts += 1
            number = client.last_authorized(locked.point_of_sale, locked.voucher_type) + 1
            meta = dict(locked.meta or {})
            meta['arca_pending_number'] = number
            meta['arca_pending_date'] = locked.issue_date.isoformat()
            meta['vat_rate'] = str(vat_rate)
            locked.meta = meta
            try:
                result = client.request_cae(
                    point_of_sale=locked.point_of_sale,
                    voucher_type=locked.voucher_type,
                    number=number,
                    issue_date=locked.issue_date,
                    total=locked.total_amount,
                    net=net,
                    vat=vat,
                    vat_rate=vat_rate,
                    doc_type=ANONYMOUS_DOC_TYPE,
                    doc_number=0,
                    receiver_vat_condition=CONSUMER_FINAL_VAT_CONDITION,
                    associated=_associated_vouchers(locked),
                )
            except ArcaError as exc:
                # Quedo en duda: se guarda el numero para recuperarlo en el proximo intento.
                locked.status = Invoice.Status.ERROR
                locked.error_message = str(exc)
                locked.save(update_fields=[
                    'status', 'error_message', 'meta', 'net_amount', 'vat_amount', 'issue_date', 'updated_at',
                ])
                return locked, exc

            provider_result = {
                'provider': 'wsfe',
                'environment': arca_environment(),
                **result.raw,
            }
            if result.approved:
                sequence.last_number = number
                sequence.save(update_fields=['last_number', 'updated_at'])
                return _mark_authorized(locked, number, result.cae, result.cae_due_date, provider_result), None

            sequence_error = any(err['code'] in WSFE_SEQUENCE_ERROR_CODES for err in result.errors)
            if sequence_error and attempts < 2:
                continue

            meta = dict(locked.meta or {})
            meta.pop('arca_pending_number', None)
            meta.pop('arca_pending_date', None)
            locked.meta = meta
            locked.status = Invoice.Status.REJECTED
            locked.error_message = '; '.join(result.messages) or 'ARCA rechazo el comprobante'
            locked.provider_result = provider_result
            locked.save(update_fields=[
                'status', 'error_message', 'provider_result', 'meta',
                'net_amount', 'vat_amount', 'issue_date', 'updated_at',
            ])
            return locked, ArcaServiceError(locked.error_message, errors=result.errors)


def arca_status():
    provider = (getattr(settings, 'ARCA_PROVIDER', 'mock') or 'mock').lower()
    data = {
        'provider': provider,
        'environment': arca_environment(),
        'cuit': arca_cuit(),
        'point_of_sale': int(getattr(settings, 'ARCA_DEFAULT_POINT_OF_SALE', 0) or 0),
        'voucher_type': int(getattr(settings, 'ARCA_GETNET_VOUCHER_TYPE', 6) or 6),
        'vat_rate': str(getattr(settings, 'ARCA_DEFAULT_VAT_RATE', '10.5')),
        'ready': False,
        'servers': None,
        'last_voucher_number': None,
        'error': '',
        'auto_retry_seconds': int(getattr(settings, 'ARCA_AUTO_RETRY_SECONDS', 0) or 0),
        'pending_retry': {'count': 0, 'total': 0.0},
    }
    if provider != 'wsfe':
        data['error'] = 'ARCA_PROVIDER no es wsfe: las facturas se simulan y no tienen validez fiscal'
        return data
    from .arca_retry import pending_retry_summary

    data['pending_retry'] = pending_retry_summary()
    try:
        client = wsfe_client()
        data['servers'] = client.dummy()
        data['last_voucher_number'] = client.last_authorized(data['point_of_sale'], data['voucher_type'])
        data['ready'] = True
    except ArcaError as exc:
        data['error'] = str(exc)
    return data
