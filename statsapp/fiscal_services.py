import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import (
    AccountClient,
    AccountTransaction,
    BankTransaction,
    ExternalEvent,
    Invoice,
    InvoiceAccountTransaction,
    InvoiceLine,
    Payment,
)


GETNET_APPROVED_STATUSES = {
    'approved',
    'authorized',
    'captured',
    'paid',
    'confirmed',
    'succeeded',
    'success',
}
GETNET_REJECTED_STATUSES = {'denied', 'declined', 'cancelled', 'canceled', 'failed', 'rejected', 'error'}


class FiscalError(ValueError):
    pass


class ProviderConfigurationError(FiscalError):
    pass


def parse_decimal(value, default='0'):
    if value in (None, ''):
        return Decimal(default)
    try:
        if isinstance(value, dict):
            value = value.get('value') or value.get('amount') or value.get('total') or default
        text = str(value).strip().replace(' ', '').replace('$', '')
        if ',' in text and '.' in text and text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '')  # formato argentino: 1.500,50
        return Decimal(text.replace(',', '.')).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def money(value):
    return parse_decimal(value)


def invoice_payload(invoice, include_lines=True):
    client = invoice.client
    branch = invoice.branch
    data = {
        'id': str(invoice.id),
        'client_id': str(client.id) if client else None,
        'client_name': client.full_name if client else '',
        'branch': {
            'id': branch.id,
            'name': branch.name,
        } if branch else None,
        'source': invoice.source,
        'source_label': invoice.get_source_display(),
        'status': invoice.status,
        'status_label': invoice.get_status_display(),
        'issue_date': invoice.issue_date.isoformat() if invoice.issue_date else None,
        'point_of_sale': invoice.point_of_sale,
        'voucher_type': invoice.voucher_type,
        'voucher_number': invoice.voucher_number,
        'total_amount': float(invoice.total_amount or 0),
        'net_amount': float(invoice.net_amount or 0),
        'vat_amount': float(invoice.vat_amount or 0),
        'cae': invoice.cae,
        'cae_due_date': invoice.cae_due_date.isoformat() if invoice.cae_due_date else None,
        'external_reference': invoice.external_reference,
        'is_credit_note': invoice.voucher_type in {3, 8, 13},
        'cancels_id': str(invoice.cancels_id) if invoice.cancels_id else None,
        'cancelled_by_voucher': (invoice.meta or {}).get('cancelled_voucher', ''),
        'cancels_voucher': (invoice.meta or {}).get('cancels_voucher', ''),
        'reason': (invoice.meta or {}).get('reason') or (invoice.meta or {}).get('cancel_reason', ''),
        'error_message': invoice.error_message,
        'created_at': invoice.created_at.isoformat() if invoice.created_at else None,
    }
    if include_lines:
        data['lines'] = [
            {
                'id': line.id,
                'description': line.description,
                'quantity': float(line.quantity or 0),
                'unit_price': float(line.unit_price or 0),
                'total': float(line.total or 0),
                'account_transaction_id': line.account_transaction.external_id if line.account_transaction else None,
            }
            for line in invoice.lines.all().order_by('id')
        ]
    return data


def payment_payload(payment):
    terminal = payment.terminal
    branch = payment.branch
    return {
        'id': str(payment.id),
        'source': payment.source,
        'source_label': payment.get_source_display(),
        'status': payment.status,
        'status_label': payment.get_status_display(),
        'date': payment.date.isoformat() if payment.date else None,
        'amount': float(payment.amount or 0),
        'external_id': payment.external_id,
        'provider_status': payment.provider_status,
        'terminal': {
            'id': terminal.id,
            'code': terminal.code,
        } if terminal else None,
        'branch': {
            'id': branch.id,
            'name': branch.name,
        } if branch else None,
        'client_id': str(payment.client_id) if payment.client_id else None,
        'client_name': payment.client.full_name if payment.client else '',
        'invoice_id': str(payment.invoice_id) if payment.invoice_id else None,
        'created_at': payment.created_at.isoformat() if payment.created_at else None,
    }


def _transaction_remaining_expr():
    return Q(original_amount__gt=F('paid_amount'))


def pending_account_transactions(client, branch=None):
    queryset = (
        client.transactions
        .filter(_transaction_remaining_expr())
        .filter(invoice_link__isnull=True)
    )
    if branch is not None:
        queryset = queryset.filter(branch=branch)
    return queryset.order_by('date', 'created_at', 'id')


def account_invoice_preview(client, branch=None):
    transactions = list(pending_account_transactions(client, branch=branch).select_related('branch'))
    total = sum((tx.remaining_amount for tx in transactions), Decimal('0'))
    return {
        'client': {
            'id': str(client.id),
            'name': client.full_name,
            'external_id': client.external_id,
            'total_debt': float(client.total_debt or 0),
        },
        'branch': {
            'id': branch.id,
            'name': branch.name,
        } if branch else None,
        'total_pending_to_invoice': float(total),
        'transactions': [
            {
                'id': tx.external_id,
                'date': tx.date.isoformat() if tx.date else None,
                'description': tx.description,
                'original': float(tx.original_amount or 0),
                'paid': float(tx.paid_amount or 0),
                'remaining': float(tx.remaining_amount),
                'status': tx.status,
                'branch': {
                    'id': tx.branch.id,
                    'name': tx.branch.name,
                } if tx.branch else None,
            }
            for tx in transactions
        ],
    }


def _default_point_of_sale():
    return int(getattr(settings, 'ARCA_DEFAULT_POINT_OF_SALE', 0) or 0)


def _default_voucher_type():
    return int(getattr(settings, 'ARCA_DEFAULT_VOUCHER_TYPE', 0) or 0)


def create_account_invoice(client, transaction_ids, authorize=False, created_by=None, branch=None):
    if not transaction_ids:
        raise FiscalError('Selecciona al menos un movimiento para facturar')

    with db_transaction.atomic():
        txs = list(
            pending_account_transactions(client, branch=branch)
            .select_related('branch')
            .select_for_update(of=('self',))
            .filter(external_id__in=transaction_ids)
        )
        found = {tx.external_id for tx in txs}
        missing = [tx_id for tx_id in transaction_ids if tx_id not in found]
        if missing:
            raise FiscalError('Hay movimientos inexistentes o ya facturados')

        transaction_branch_ids = {tx.branch_id for tx in txs}
        if len(transaction_branch_ids) > 1:
            raise FiscalError('No se pueden facturar movimientos de distintas sucursales juntos')
        invoice_branch = branch
        if invoice_branch is None and txs and txs[0].branch_id:
            invoice_branch = txs[0].branch

        total = sum((tx.remaining_amount for tx in txs), Decimal('0'))
        if total <= Decimal('0'):
            raise FiscalError('No hay saldo pendiente para facturar')

        invoice = Invoice.objects.create(
            client=client,
            branch=invoice_branch,
            source=Invoice.Source.ACCOUNT,
            status=Invoice.Status.DRAFT,
            point_of_sale=_default_point_of_sale(),
            voucher_type=_default_voucher_type(),
            net_amount=total,
            total_amount=total,
            idempotency_key=f"account:{client.id}:{uuid4().hex}",
            meta={
                'created_by': getattr(created_by, 'username', '') if created_by else '',
                'branch_id': invoice_branch.id if invoice_branch else None,
            },
        )

        lines = []
        links = []
        for tx in txs:
            amount = tx.remaining_amount
            description = tx.description or f"Cuenta corriente {tx.date.isoformat() if tx.date else tx.external_id}"
            lines.append(InvoiceLine(
                invoice=invoice,
                description=description[:255],
                quantity=Decimal('1'),
                unit_price=amount,
                total=amount,
                account_transaction=tx,
            ))
            links.append(InvoiceAccountTransaction(invoice=invoice, transaction=tx, amount=amount))

        InvoiceLine.objects.bulk_create(lines)
        InvoiceAccountTransaction.objects.bulk_create(links)

        if authorize:
            invoice = authorize_invoice(invoice)
        return invoice


def _next_mock_voucher_number(invoice):
    latest = (
        Invoice.objects
        .filter(point_of_sale=invoice.point_of_sale, voucher_type=invoice.voucher_type, voucher_number__isnull=False)
        .exclude(pk=invoice.pk)
        .order_by('-voucher_number')
        .first()
    )
    return (latest.voucher_number if latest else 0) + 1


def authorize_invoice(invoice):
    invoice = _authorize_invoice(invoice)
    if invoice.cancels_id:
        # Una nota de credito reintentada tambien tiene que anular su factura.
        finalize_credit_note(invoice)
    return invoice


def _authorize_invoice(invoice):
    if invoice.status == Invoice.Status.AUTHORIZED:
        return invoice
    if invoice.status == Invoice.Status.CANCELLED:
        raise FiscalError('La factura esta anulada y no se puede volver a autorizar')
    if invoice.total_amount <= Decimal('0'):
        raise FiscalError('La factura debe tener importe mayor a cero')

    provider = getattr(settings, 'ARCA_PROVIDER', 'mock').lower()
    if provider == 'wsfe':
        from .arca_client import ArcaError
        from .arca_services import authorize_invoice_wsfe

        try:
            return authorize_invoice_wsfe(invoice)
        except ArcaError as exc:
            raise FiscalError(str(exc)) from exc
    if provider not in {'mock', 'disabled'}:
        raise ProviderConfigurationError(
            'ARCA_PROVIDER debe ser mock, disabled o wsfe'
        )
    if provider == 'disabled':
        raise ProviderConfigurationError('ARCA_PROVIDER esta deshabilitado')

    with db_transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.status == Invoice.Status.AUTHORIZED:
            return locked
        locked.voucher_number = _next_mock_voucher_number(locked)
        vat_rate = (locked.meta or {}).get('vat_rate')
        if vat_rate:
            # Mismo desglose que WSFE, para que el modo simulado muestre neto e IVA reales.
            from .arca_services import split_vat_included

            locked.net_amount, locked.vat_amount = split_vat_included(locked.total_amount, vat_rate)
        locked.cae = f"MOCK{locked.issue_date.strftime('%Y%m%d')}{locked.voucher_number:08d}"[:32]
        locked.cae_due_date = locked.issue_date + timedelta(days=10)
        locked.status = Invoice.Status.AUTHORIZED
        locked.error_message = ''
        locked.provider_result = {
            'provider': 'mock',
            'mode': 'homologacion-local',
            'note': 'Reemplazar por WSFEv1 real al configurar credenciales ARCA',
        }
        locked.save(update_fields=[
            'voucher_number',
            'cae',
            'cae_due_date',
            'status',
            'error_message',
            'provider_result',
            'net_amount',
            'vat_amount',
            'updated_at',
        ])
        return locked


CREDIT_NOTE_TYPES = {1: 3, 6: 8, 11: 13}
CREDIT_NOTE_VOUCHER_TYPES = set(CREDIT_NOTE_TYPES.values())


def _format_voucher(invoice):
    letters = {1: 'Factura A', 3: 'Nota de credito A', 6: 'Factura B', 8: 'Nota de credito B',
               11: 'Factura C', 13: 'Nota de credito C'}
    label = letters.get(invoice.voucher_type, f'Comprobante {invoice.voucher_type}')
    if not invoice.voucher_number:
        return label
    return f'{label} {invoice.point_of_sale:05d}-{invoice.voucher_number:08d}'


def create_credit_note(invoice_id, reason='', created_by=None):
    """Anula una factura autorizada emitiendo su nota de credito por el total.

    Si un intento anterior fallo, reutiliza esa nota de credito en lugar de crear otra.
    Cuando ARCA la autoriza, la factura queda anulada y los cupones que cubria
    vuelven a quedar disponibles para facturar.
    """
    reason = (reason or '').strip()[:255]
    with db_transaction.atomic():
        original = Invoice.objects.select_for_update().get(pk=invoice_id)
        if original.voucher_type in CREDIT_NOTE_VOUCHER_TYPES:
            raise FiscalError('Una nota de credito no se puede anular desde aca')
        if original.status == Invoice.Status.CANCELLED:
            raise FiscalError('La factura ya esta anulada')
        if original.status != Invoice.Status.AUTHORIZED or not original.voucher_number:
            raise FiscalError('Solo se pueden anular facturas autorizadas por ARCA')
        credit_type = CREDIT_NOTE_TYPES.get(original.voucher_type)
        if credit_type is None:
            raise FiscalError('Este tipo de comprobante no se puede anular con nota de credito')

        credit_note = Invoice.objects.filter(cancels=original).first()
        if credit_note and credit_note.status == Invoice.Status.AUTHORIZED:
            raise FiscalError('La factura ya tiene una nota de credito autorizada')
        if credit_note is None:
            meta = {
                'created_by': getattr(created_by, 'username', '') if created_by else '',
                'reason': reason,
                'cancels_voucher': _format_voucher(original),
            }
            if (original.meta or {}).get('vat_rate'):
                meta['vat_rate'] = original.meta['vat_rate']
            credit_note = Invoice.objects.create(
                client=original.client,
                branch=original.branch,
                source=original.source,
                status=Invoice.Status.DRAFT,
                point_of_sale=original.point_of_sale,
                voucher_type=credit_type,
                net_amount=original.net_amount,
                vat_amount=original.vat_amount,
                total_amount=original.total_amount,
                external_reference=original.external_reference,
                cancels=original,
                idempotency_key=f'credit-note:{original.id}',
                meta=meta,
            )
            InvoiceLine.objects.create(
                invoice=credit_note,
                description=f'Anulacion de {_format_voucher(original)}'[:255],
                quantity=Decimal('1'),
                unit_price=original.total_amount,
                total=original.total_amount,
            )
        elif reason:
            meta = dict(credit_note.meta or {})
            meta['reason'] = reason
            credit_note.meta = meta
            credit_note.save(update_fields=['meta', 'updated_at'])

    try:
        credit_note = authorize_invoice(credit_note)
    except FiscalError:
        credit_note.refresh_from_db()
        if credit_note.status == Invoice.Status.DRAFT:
            credit_note.status = Invoice.Status.ERROR
            credit_note.save(update_fields=['status', 'updated_at'])
        raise

    finalize_credit_note(credit_note, reason=reason)
    return credit_note


def finalize_credit_note(credit_note, reason=''):
    """Con la nota de credito autorizada, anula la factura original y libera sus cupones.

    Es idempotente: tambien la usa el reintento automatico cuando ARCA autoriza una
    nota de credito que habia quedado pendiente.
    """
    if credit_note.status != Invoice.Status.AUTHORIZED or not credit_note.cancels_id:
        return None
    reason = reason or (credit_note.meta or {}).get('reason', '')
    with db_transaction.atomic():
        original = Invoice.objects.select_for_update().get(pk=credit_note.cancels_id)
        if original.status == Invoice.Status.CANCELLED:
            return original
        meta = dict(original.meta or {})
        meta['cancelled_by'] = str(credit_note.id)
        meta['cancelled_voucher'] = _format_voucher(credit_note)
        if reason:
            meta['cancel_reason'] = reason
        original.status = Invoice.Status.CANCELLED
        original.meta = meta
        original.save(update_fields=['status', 'meta', 'updated_at'])
        # Los cupones vuelven a estar disponibles para facturar.
        Payment.objects.filter(invoice=original).update(invoice=None)
    return original


GETNET_INVOICEABLE_PAYMENT_STATUSES = (Payment.Status.APPROVED, Payment.Status.RECONCILED)
GETNET_RETRYABLE_INVOICE_STATUSES = (Invoice.Status.DRAFT, Invoice.Status.ERROR, Invoice.Status.REJECTED)
SUPPORTED_VAT_RATES = (Decimal('10.5'), Decimal('21'))


def getnet_invoiceable_payments(start_date, end_date, terminal_id=None, branch_id=None):
    """Cupones Getnet cobrados que todavia no tienen factura autorizada."""
    queryset = (
        Payment.objects
        .select_related('terminal', 'branch', 'invoice')
        .filter(
            source=Payment.Source.GETNET,
            status__in=GETNET_INVOICEABLE_PAYMENT_STATUSES,
            amount__gt=0,
            date__gte=start_date,
            date__lte=end_date,
        )
        .filter(Q(invoice__isnull=True) | Q(invoice__status__in=GETNET_RETRYABLE_INVOICE_STATUSES))
    )
    if terminal_id:
        queryset = queryset.filter(terminal_id=terminal_id)
    if branch_id:
        queryset = queryset.filter(branch_id=branch_id)
    return queryset.order_by('date', 'created_at')


def getnet_candidate_payload(payment):
    getnet = (payment.meta or {}).get('getnet_csv') or {}
    invoice = payment.invoice
    return {
        **payment_payload(payment),
        'brand': getnet.get('brand', ''),
        'card_last_four': getnet.get('card_last_four', ''),
        'coupon_number': getnet.get('coupon_number', ''),
        'transaction_type': getnet.get('transaction_type', ''),
        'invoice_status': invoice.status if invoice else None,
        'invoice_error': invoice.error_message if invoice else '',
    }


def parse_vat_rate(value):
    if value in (None, ''):
        value = getattr(settings, 'ARCA_DEFAULT_VAT_RATE', '10.5')
    try:
        rate = Decimal(str(value).replace(',', '.'))
    except InvalidOperation as exc:
        raise FiscalError('Alicuota de IVA invalida') from exc
    if rate not in SUPPORTED_VAT_RATES:
        raise FiscalError('La alicuota de IVA debe ser 10,5% o 21%')
    return rate


def _getnet_line_description(payment):
    getnet = (payment.meta or {}).get('getnet_csv') or {}
    parts = ['Venta con tarjeta']
    if getnet.get('brand'):
        parts.append(getnet['brand'])
    if payment.terminal:
        parts.append(f'terminal {payment.terminal.code}')
    if getnet.get('coupon_number'):
        parts.append(f'cupon {getnet["coupon_number"]}')
    return ' - '.join(parts)[:255]


def _getnet_invoice_for_payment(payment_id, vat_rate, created_by):
    """Crea (o reutiliza si fallo antes) la factura de un cupon. Bloquea el cupon."""
    with db_transaction.atomic():
        payment = (
            Payment.objects
            .select_for_update(of=('self',))
            .select_related('terminal', 'branch', 'invoice')
            .get(pk=payment_id)
        )
        if payment.source != Payment.Source.GETNET:
            raise FiscalError('El cobro no es un cupon Getnet')
        if payment.status not in GETNET_INVOICEABLE_PAYMENT_STATUSES or payment.amount <= Decimal('0'):
            raise FiscalError('El cupon no esta aprobado o no tiene importe a facturar')
        invoice = payment.invoice
        if invoice and invoice.status == Invoice.Status.AUTHORIZED:
            raise FiscalError('El cupon ya esta facturado')
        if invoice and invoice.status not in GETNET_RETRYABLE_INVOICE_STATUSES:
            raise FiscalError('El cupon tiene una factura anulada; revisala antes de volver a facturar')
        if invoice:
            meta = dict(invoice.meta or {})
            meta['vat_rate'] = str(vat_rate)
            invoice.meta = meta
            invoice.save(update_fields=['meta', 'updated_at'])
            return invoice

        invoice = Invoice.objects.create(
            branch=payment.branch,
            source=Invoice.Source.GETNET,
            status=Invoice.Status.DRAFT,
            point_of_sale=_default_point_of_sale(),
            voucher_type=int(getattr(settings, 'ARCA_GETNET_VOUCHER_TYPE', 6) or 6),
            total_amount=payment.amount,
            net_amount=payment.amount,
            external_reference=payment.external_id[:128],
            # Un cupon puede volver a facturarse si su factura anterior se anulo.
            idempotency_key=f'getnet-invoice:{payment.id}:{uuid4().hex[:12]}',
            meta={
                'created_by': getattr(created_by, 'username', '') if created_by else '',
                'payment_id': str(payment.id),
                'vat_rate': str(vat_rate),
            },
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description=_getnet_line_description(payment),
            quantity=Decimal('1'),
            unit_price=payment.amount,
            total=payment.amount,
        )
        payment.invoice = invoice
        payment.save(update_fields=['invoice', 'updated_at'])
        return invoice


def create_getnet_invoices(payment_ids, vat_rate=None, created_by=None):
    """Emite una factura B a consumidor final por cada cupon. Devuelve el resultado de cada uno."""
    if not payment_ids:
        raise FiscalError('Selecciona al menos un cupon para facturar')
    if len(payment_ids) > 200:
        raise FiscalError('Se pueden facturar hasta 200 cupones por vez')
    rate = parse_vat_rate(vat_rate)
    ordered_ids = list(
        Payment.objects
        .filter(pk__in=payment_ids)
        .order_by('date', 'created_at')
        .values_list('pk', flat=True)
    )
    missing = {str(pk) for pk in payment_ids} - {str(pk) for pk in ordered_ids}

    results = [
        {'payment_id': payment_id, 'ok': False, 'detail': 'Cupon inexistente', 'invoice': None}
        for payment_id in sorted(missing)
    ]
    for payment_id in ordered_ids:
        entry = {'payment_id': str(payment_id), 'ok': False, 'detail': '', 'invoice': None}
        try:
            invoice = _getnet_invoice_for_payment(payment_id, rate, created_by)
            invoice = authorize_invoice(invoice)
            entry['ok'] = True
            entry['detail'] = 'Factura autorizada'
        except FiscalError as exc:
            entry['detail'] = str(exc)
            invoice = Invoice.objects.filter(payments__pk=payment_id).first()
            if invoice and invoice.status == Invoice.Status.DRAFT:
                invoice.status = Invoice.Status.ERROR
                invoice.error_message = str(exc)
                invoice.save(update_fields=['status', 'error_message', 'updated_at'])
        if invoice is not None:
            invoice.refresh_from_db()
            entry['invoice'] = invoice_payload(invoice, include_lines=False)
        results.append(entry)
    return results


MAX_MANUAL_INVOICES_PER_REQUEST = 100


def create_manual_invoices(items, vat_rate=None, branch=None, created_by=None):
    """Emite una Factura B a consumidor final por cada importe cargado a mano.

    Sirve para ventas que no pasaron por el posnet (efectivo, transferencia).
    Devuelve el resultado de cada item; un error no frena a los demas.
    """
    if not items:
        raise FiscalError('Carga al menos un importe para facturar')
    if len(items) > MAX_MANUAL_INVOICES_PER_REQUEST:
        raise FiscalError(f'Se pueden emitir hasta {MAX_MANUAL_INVOICES_PER_REQUEST} facturas por vez')
    rate = parse_vat_rate(vat_rate)

    parsed = []
    for index, item in enumerate(items, start=1):
        item = item if isinstance(item, dict) else {'amount': item}
        amount = parse_decimal(item.get('amount'), default='-1')
        if amount <= Decimal('0'):
            raise FiscalError(f'Fila {index}: el importe debe ser mayor a cero')
        description = str(item.get('description') or '').strip()[:255] or 'Venta mostrador'
        parsed.append((amount, description))

    voucher_type = int(getattr(settings, 'ARCA_GETNET_VOUCHER_TYPE', 6) or 6)
    username = getattr(created_by, 'username', '') if created_by else ''
    results = []
    for index, (amount, description) in enumerate(parsed, start=1):
        entry = {'row': index, 'amount': float(amount), 'ok': False, 'detail': '', 'invoice': None}
        with db_transaction.atomic():
            invoice = Invoice.objects.create(
                branch=branch,
                source=Invoice.Source.MANUAL,
                status=Invoice.Status.DRAFT,
                point_of_sale=_default_point_of_sale(),
                voucher_type=voucher_type,
                total_amount=amount,
                net_amount=amount,
                idempotency_key=f'manual-invoice:{uuid4().hex}',
                meta={'created_by': username, 'vat_rate': str(rate), 'description': description},
            )
            InvoiceLine.objects.create(
                invoice=invoice,
                description=description,
                quantity=Decimal('1'),
                unit_price=amount,
                total=amount,
            )
        try:
            invoice = authorize_invoice(invoice)
            entry['ok'] = True
            entry['detail'] = 'Factura autorizada'
        except FiscalError as exc:
            entry['detail'] = str(exc)
            invoice.refresh_from_db()
            if invoice.status == Invoice.Status.DRAFT:
                invoice.status = Invoice.Status.ERROR
                invoice.error_message = str(exc)
                invoice.save(update_fields=['status', 'error_message', 'updated_at'])
        invoice.refresh_from_db()
        entry['invoice'] = invoice_payload(invoice, include_lines=False)
        results.append(entry)
    return results


def verify_getnet_signature(raw_body, signature):
    secret = getattr(settings, 'GETNET_WEBHOOK_SECRET', '')
    if not secret:
        return True
    if not signature:
        return False
    expected = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
    normalized = signature.replace('sha256=', '').strip()
    return hmac.compare_digest(expected, normalized)


def _payload_hash(raw_body):
    return hashlib.sha256(raw_body).hexdigest()


def _first_present(payload, *paths):
    for path in paths:
        current = payload
        for part in path.split('.'):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, ''):
            return current
    return None


def normalize_getnet_status(value):
    normalized = str(value or '').strip().lower()
    if normalized in GETNET_APPROVED_STATUSES:
        return Payment.Status.APPROVED
    if normalized in GETNET_REJECTED_STATUSES:
        return Payment.Status.REJECTED
    return Payment.Status.PENDING


def process_getnet_webhook(raw_body, signature=''):
    if not verify_getnet_signature(raw_body, signature):
        raise FiscalError('Firma Getnet invalida')

    try:
        payload = json.loads(raw_body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FiscalError(f'Payload Getnet invalido: {exc}') from exc

    event_id = str(_first_present(payload, 'id', 'event_id', 'notification_id', 'payment.payment_id', 'payment_id') or uuid4())
    event_type = str(_first_present(payload, 'type', 'event_type', 'status', 'payment.status') or 'payment')
    payload_digest = _payload_hash(raw_body)

    event, created = ExternalEvent.objects.get_or_create(
        provider='getnet',
        event_id=event_id,
        defaults={
            'event_type': event_type[:64],
            'payload_hash': payload_digest,
            'payload': payload,
        },
    )
    if not created and event.status == ExternalEvent.Status.PROCESSED:
        event.status = ExternalEvent.Status.DUPLICATE
        event.save(update_fields=['status'])
        return {'event': event, 'payment': None, 'duplicate': True}

    try:
        payment = upsert_getnet_payment_from_payload(payload)
        event.status = ExternalEvent.Status.PROCESSED
        event.error_message = ''
        event.processed_at = timezone.now()
        event.payload_hash = payload_digest
        event.payload = payload
        event.save(update_fields=['status', 'error_message', 'processed_at', 'payload_hash', 'payload'])
        return {'event': event, 'payment': payment, 'duplicate': False}
    except Exception as exc:
        event.status = ExternalEvent.Status.ERROR
        event.error_message = str(exc)
        event.processed_at = timezone.now()
        event.save(update_fields=['status', 'error_message', 'processed_at'])
        raise


def upsert_getnet_payment_from_payload(payload):
    payment_id = str(_first_present(payload, 'payment_id', 'payment.payment_id', 'id') or '').strip()
    order_id = str(_first_present(payload, 'order_id', 'order.order_id', 'reference', 'merchant_order_id') or '').strip()
    status_value = _first_present(payload, 'status', 'payment.status', 'transaction.status')
    amount_value = _first_present(payload, 'amount', 'payment.amount', 'transaction.amount', 'order.amount')
    amount = money(amount_value)
    if amount <= Decimal('0'):
        raise FiscalError('El webhook Getnet no informo un monto valido')
    normalized_status = normalize_getnet_status(status_value)
    invoice = None
    if order_id:
        invoice = Invoice.objects.filter(Q(external_reference=order_id) | Q(idempotency_key=order_id)).first()
    if not invoice:
        invoice_id = _first_present(payload, 'metadata.invoice_id', 'invoice_id')
        if invoice_id:
            invoice = Invoice.objects.filter(pk=invoice_id).first()

    payment_status = normalized_status
    if normalized_status == Payment.Status.APPROVED and not invoice:
        payment_status = Payment.Status.NEEDS_REVIEW

    payment, _ = Payment.objects.update_or_create(
        idempotency_key=f"getnet:{payment_id or order_id or hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()}",
        defaults={
            'source': Payment.Source.GETNET,
            'status': payment_status,
            'amount': amount,
            'date': timezone.localdate(),
            'external_id': payment_id or order_id,
            'invoice': invoice,
            'client': invoice.client if invoice else None,
            'meta': payload,
        },
    )

    if invoice and normalized_status == Payment.Status.APPROVED and invoice.status == Invoice.Status.DRAFT:
        authorize_invoice(invoice)
    return payment


def create_manual_payment(source, amount, payment_date=None, client=None, invoice=None, external_id='', meta=None):
    source = (source or '').strip().lower()
    if source not in Payment.Source.values:
        raise FiscalError('Medio de pago invalido')
    amount = money(amount)
    if amount <= Decimal('0'):
        raise FiscalError('El pago debe ser mayor a cero')
    key_seed = external_id or f"{source}:{client.id if client else ''}:{invoice.id if invoice else ''}:{amount}:{uuid4().hex}"
    payment = Payment.objects.create(
        source=source,
        status=Payment.Status.APPROVED,
        date=payment_date or timezone.localdate(),
        amount=amount,
        external_id=external_id,
        idempotency_key=f"manual:{hashlib.sha256(str(key_seed).encode('utf-8')).hexdigest()}",
        client=client,
        invoice=invoice,
        meta=meta or {},
    )
    return payment


def billing_summary(start_date, end_date, getnet_terminal_id=None):
    invoices = Invoice.objects.filter(issue_date__gte=start_date, issue_date__lte=end_date)
    credit_notes = invoices.filter(voucher_type__in=CREDIT_NOTE_VOUCHER_TYPES)
    invoices = invoices.exclude(voucher_type__in=CREDIT_NOTE_VOUCHER_TYPES)
    # Una factura anulada sale del total; su nota de credito no se descuenta otra vez.
    authorized = invoices.filter(status=Invoice.Status.AUTHORIZED)
    payments = Payment.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        status__in=[Payment.Status.APPROVED, Payment.Status.RECONCILED],
    )
    getnet_payments = payments.filter(source=Payment.Source.GETNET)
    pending_getnet = Payment.objects.filter(
        source=Payment.Source.GETNET,
        date__gte=start_date,
        date__lte=end_date,
        status__in=[Payment.Status.PENDING, Payment.Status.NEEDS_REVIEW],
    )
    if getnet_terminal_id:
        getnet_payments = getnet_payments.filter(terminal_id=getnet_terminal_id)
        pending_getnet = pending_getnet.filter(terminal_id=getnet_terminal_id)
    bank_income = BankTransaction.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        amount__gt=0,
    )
    getnet_bank_filter = Q(concept__icontains='getnet') | Q(description__icontains='getnet')
    bank_transfer_income = (
        bank_income
        .exclude(getnet_bank_filter)
        .values('batch__bank')
        .annotate(total=Sum('amount'))
    )
    getnet_bank_income = (
        bank_income
        .filter(getnet_bank_filter)
        .values('batch__bank')
        .annotate(total=Sum('amount'))
    )
    bank_totals = {row['batch__bank']: float(row['total'] or 0) for row in bank_transfer_income}
    getnet_bank_totals = {row['batch__bank']: float(row['total'] or 0) for row in getnet_bank_income}
    payment_totals = {}
    for row in payments.exclude(source=Payment.Source.GETNET).values('source').annotate(total=Sum('amount')):
        payment_totals[row['source']] = float(row['total'] or 0)
    payment_totals[Payment.Source.GETNET] = float(
        getnet_payments.aggregate(total=Sum('amount')).get('total') or 0
    )

    account_debt = AccountClient.objects.aggregate(total=Sum('total_debt')).get('total') or Decimal('0')
    return {
        'period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
        },
        'invoices': {
            'authorized_total': float(authorized.aggregate(total=Sum('total_amount')).get('total') or 0),
            'draft_total': float(invoices.filter(status=Invoice.Status.DRAFT).aggregate(total=Sum('total_amount')).get('total') or 0),
            'count': invoices.count(),
            'authorized_count': authorized.count(),
            'cancelled_count': invoices.filter(status=Invoice.Status.CANCELLED).count(),
            'credit_notes_count': credit_notes.filter(status=Invoice.Status.AUTHORIZED).count(),
        },
        'collections': {
            'getnet': payment_totals.get(Payment.Source.GETNET, 0.0),
            'santander': bank_totals.get('santander', 0.0) + payment_totals.get(Payment.Source.SANTANDER, 0.0),
            'bancon': bank_totals.get('bancon', 0.0) + payment_totals.get(Payment.Source.BANCON, 0.0),
            'cash': payment_totals.get(Payment.Source.CASH, 0.0),
            'transfer': payment_totals.get(Payment.Source.TRANSFER, 0.0),
        },
        'getnet': {
            'terminal_id': getnet_terminal_id,
            'pending_total': float(pending_getnet.aggregate(total=Sum('amount')).get('total') or 0),
            'pending_count': pending_getnet.count(),
            'bank_settled_total': sum(getnet_bank_totals.values()),
            'bank_settled_by_bank': getnet_bank_totals,
        },
        'account_current': {
            'total_debt': float(account_debt),
        },
    }
