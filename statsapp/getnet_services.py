import csv
import io
import unicodedata
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import GetnetTerminal, Payment


REQUIRED_HEADERS = {
    'Nro de Establecimiento',
    'Nombre Establecimiento',
    'Fecha de Operación',
    'Tipo de Transacción',
    'Canal',
    'Código del POS',
    'Estado',
    'Cód. de Transacción',
    'Moneda',
    'Monto Bruto Transacción',
    'Monto Neto Transacción',
}

RECONCILED_STATUSES = {'liquidado', 'conciliado', 'reconciled', 'settled'}
APPROVED_STATUSES = {'aprobado', 'approved', 'authorized', 'captured', 'paid'}
PENDING_STATUSES = {'pendiente', 'pagando', 'pending', 'processing', 'in progress'}
REJECTED_STATUSES = {'rechazado', 'denegado', 'cancelado', 'cancelled', 'rejected', 'failed'}
REVERSAL_TYPES = {'anulacion', 'anulacion de venta', 'devolucion', 'reversa', 'refund', 'reversal'}


class GetnetImportError(ValueError):
    pass


def _normalize(value):
    text = unicodedata.normalize('NFKD', str(value or '').strip().lower())
    return ''.join(char for char in text if not unicodedata.combining(char))


def _decode_csv(raw_bytes):
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise GetnetImportError('El CSV no usa una codificacion UTF-8 o Windows-1252 valida')


def _parse_decimal(value, field_name):
    text = str(value or '').strip().replace('\u00a0', '').replace(' ', '')
    if not text:
        return Decimal('0.00')
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    elif ',' in text:
        text = text.replace(',', '.')
    try:
        return Decimal(text).quantize(Decimal('0.01'))
    except InvalidOperation as exc:
        raise GetnetImportError(f'Importe invalido en {field_name}: {value}') from exc


def _parse_operation_date(value):
    try:
        return datetime.strptime(str(value or '').strip(), '%d/%m/%Y %H:%M:%S')
    except ValueError as exc:
        raise GetnetImportError(f'Fecha de operacion invalida: {value}') from exc


def _payment_status(provider_status):
    normalized = _normalize(provider_status)
    if normalized in RECONCILED_STATUSES:
        return Payment.Status.RECONCILED
    if normalized in APPROVED_STATUSES:
        return Payment.Status.APPROVED
    if normalized in PENDING_STATUSES:
        return Payment.Status.PENDING
    if normalized in REJECTED_STATUSES:
        return Payment.Status.REJECTED
    return Payment.Status.NEEDS_REVIEW


def _signed_amount(row):
    amount = abs(_parse_decimal(row.get('Monto Bruto Transacción'), 'Monto Bruto Transacción'))
    transaction_type = _normalize(row.get('Tipo de Transacción'))
    if transaction_type in REVERSAL_TYPES:
        return -amount
    return amount


def _safe_metadata(row, filename):
    return {
        'source_file': filename,
        'establishment_number': str(row.get('Nro de Establecimiento') or '').strip(),
        'establishment_name': str(row.get('Nombre Establecimiento') or '').strip(),
        'provider_status': str(row.get('Estado') or '').strip(),
        'transaction_type': str(row.get('Tipo de Transacción') or '').strip(),
        'channel': str(row.get('Canal') or '').strip(),
        'channel_mode': str(row.get('Modo de Canal') or '').strip(),
        'wallet': str(row.get('Billetera') or '').strip(),
        'brand': str(row.get('Marca') or '').strip(),
        'card_last_four': str(row.get('Tarjeta') or '').strip(),
        'currency': str(row.get('Moneda') or '').strip(),
        'gross_amount': str(row.get('Monto Bruto Transacción') or '').strip(),
        'net_amount': str(row.get('Monto Neto Transacción') or '').strip(),
        'fee': str(row.get('Arancel') or '').strip(),
        'fee_vat': str(row.get('IVA Arancel') or '').strip(),
        'coupon_number': str(row.get('Nro de Cupón') or '').strip(),
        'authorization_code': str(row.get('Cód. Aut.') or '').strip(),
        'external_transaction_id': str(row.get('Cód. Transacción Externo') or '').strip(),
        'settlement_date': str(row.get('Fecha de Liquidación') or '').strip(),
        'expected_payment_date': str(row.get('Fecha Estimada de Pago') or '').strip(),
        'settlement_id': str(row.get('Cód. de Liquidación') or '').strip(),
    }


def terminal_payload(terminal):
    return {
        'id': terminal.id,
        'code': terminal.code,
        'branch': {
            'id': terminal.branch_id,
            'name': terminal.branch.name,
        } if terminal.branch_id else None,
        'establishment_number': terminal.establishment_number,
        'establishment_name': terminal.establishment_name,
        'active': terminal.active,
        'last_seen_at': terminal.last_seen_at.isoformat() if terminal.last_seen_at else None,
    }


@transaction.atomic
def import_getnet_csv(uploaded_file, default_branch=None):
    raw_bytes = uploaded_file.read()
    if not raw_bytes:
        raise GetnetImportError('El archivo Getnet esta vacio')

    text = _decode_csv(raw_bytes)
    reader = csv.DictReader(io.StringIO(text, newline=''))
    headers = set(reader.fieldnames or [])
    missing_headers = sorted(REQUIRED_HEADERS - headers)
    if missing_headers:
        raise GetnetImportError(f'Faltan columnas obligatorias: {", ".join(missing_headers)}')

    rows = list(reader)
    if not rows:
        raise GetnetImportError('El CSV Getnet no contiene transacciones')
    if len(rows) > 50000:
        raise GetnetImportError('El CSV Getnet supera el limite de 50.000 transacciones')

    transaction_ids = []
    terminal_codes = set()
    for row_number, row in enumerate(rows, start=2):
        transaction_id = str(row.get('Cód. de Transacción') or '').strip()
        terminal_code = str(row.get('Código del POS') or '').strip()
        if not transaction_id:
            raise GetnetImportError(f'Fila {row_number}: falta Cód. de Transacción')
        if not terminal_code:
            raise GetnetImportError(f'Fila {row_number}: falta Código del POS')
        transaction_ids.append(transaction_id)
        terminal_codes.add(terminal_code)

    if len(transaction_ids) != len(set(transaction_ids)):
        raise GetnetImportError('El CSV contiene Cód. de Transacción duplicados')
    if default_branch and len(terminal_codes) != 1:
        raise GetnetImportError('El archivo contiene varias terminales; asigna cada una desde Facturacion')

    now = timezone.now()
    terminals = {}
    for terminal_code in sorted(terminal_codes):
        sample = next(row for row in rows if str(row.get('Código del POS') or '').strip() == terminal_code)
        terminal, _ = GetnetTerminal.objects.select_for_update().get_or_create(
            code=terminal_code,
            defaults={'branch': default_branch},
        )
        if default_branch and terminal.branch_id not in (None, default_branch.id):
            raise GetnetImportError(
                f'La terminal {terminal.code} ya esta asignada a {terminal.branch.name}'
            )
        terminal.branch = default_branch or terminal.branch
        terminal.establishment_number = str(sample.get('Nro de Establecimiento') or '').strip()
        terminal.establishment_name = str(sample.get('Nombre Establecimiento') or '').strip()
        terminal.last_seen_at = now
        terminal.save(update_fields=[
            'branch',
            'establishment_number',
            'establishment_name',
            'last_seen_at',
            'updated_at',
        ])
        terminals[terminal_code] = terminal

    created_count = 0
    updated_count = 0
    totals_by_terminal = defaultdict(lambda: {'rows': 0, 'gross_total': Decimal('0.00')})
    filename = str(getattr(uploaded_file, 'name', '') or '')[:255]

    for row in rows:
        transaction_id = str(row.get('Cód. de Transacción') or '').strip()
        terminal_code = str(row.get('Código del POS') or '').strip()
        terminal = terminals[terminal_code]
        operation_datetime = _parse_operation_date(row.get('Fecha de Operación'))
        amount = _signed_amount(row)
        provider_status = str(row.get('Estado') or '').strip()
        key = f'getnet:{transaction_id}'

        existing = Payment.objects.filter(idempotency_key=key).first()
        meta = dict(existing.meta or {}) if existing else {}
        meta['getnet_csv'] = _safe_metadata(row, filename)
        payment, created = Payment.objects.update_or_create(
            idempotency_key=key,
            defaults={
                'source': Payment.Source.GETNET,
                'status': _payment_status(provider_status),
                'provider_status': provider_status,
                'date': operation_datetime.date(),
                'amount': amount,
                'external_id': transaction_id,
                'terminal': terminal,
                'branch': terminal.branch,
                'meta': meta,
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1
        totals_by_terminal[terminal_code]['rows'] += 1
        totals_by_terminal[terminal_code]['gross_total'] += amount

    terminal_results = []
    for terminal_code in sorted(terminals):
        terminal = terminals[terminal_code]
        terminal_results.append({
            **terminal_payload(terminal),
            'rows': totals_by_terminal[terminal_code]['rows'],
            'gross_total': float(totals_by_terminal[terminal_code]['gross_total']),
        })

    return {
        'detail': 'Importacion Getnet completada',
        'rows': len(rows),
        'created': created_count,
        'updated': updated_count,
        'terminals': terminal_results,
        'unassigned_terminals': [
            terminal_payload(terminal)
            for terminal in terminals.values()
            if not terminal.branch_id
        ],
    }
