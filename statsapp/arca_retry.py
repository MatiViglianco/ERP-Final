"""Reintento automatico de facturas que no se emitieron porque ARCA no respondio,
y verificacion de lo facturado contra ARCA.

Reintento:
- Candidatas: facturas en error marcadas con ``meta['arca_retry']`` (falla de
  conexion con ARCA), o con el mensaje de conexion de versiones anteriores.
  Un rechazo de ARCA (datos invalidos) nunca se reintenta solo.
- Antes de reintentar se consulta FEDummy: si ARCA sigue caido no se toca nada.
- ``authorize_invoice_wsfe`` ya evita emitir dos veces: si un intento quedo en
  duda, primero consulta ese numero en ARCA y adopta el CAE.
- Corre en un hilo de cada worker de gunicorn (``start_retry_scheduler``); un
  lock (advisory lock en Postgres) evita que dos workers reintenten a la vez.

Verificacion:
- ``verify_invoices_with_arca`` consulta con FECompConsultar cada comprobante que
  el ERP tiene autorizado en el periodo y compara CAE, importe y fecha. Tambien
  busca numeros salteados del rango por si ARCA emitio algo que el ERP no tiene.
"""

import logging
import random
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import close_old_connections, connection
from django.db.models import Q, Sum
from django.utils import timezone

from .arca_client import CREDIT_NOTE_VOUCHER_TYPES, ArcaConnectionError, ArcaError
from .models import Invoice

logger = logging.getLogger(__name__)

LEGACY_CONNECTION_ERROR_PREFIXES = ('No se pudo conectar con ARCA', 'ARCA respondio HTTP')
ADVISORY_LOCK_KEY = 8_420_261_126
MAX_GAP_LOOKUPS = 200

_process_lock = threading.Lock()
_scheduler_started = False


def _provider():
    return (getattr(settings, 'ARCA_PROVIDER', 'mock') or 'mock').lower()


def retryable_invoices():
    max_age = int(getattr(settings, 'ARCA_AUTO_RETRY_MAX_AGE_DAYS', 10) or 10)
    connection_failure = Q(meta__arca_retry=True)
    for prefix in LEGACY_CONNECTION_ERROR_PREFIXES:
        connection_failure |= Q(error_message__startswith=prefix)
    return (
        Invoice.objects
        .filter(
            status=Invoice.Status.ERROR,
            point_of_sale__gt=0,
            voucher_type__gt=0,
            total_amount__gt=0,
            created_at__gte=timezone.now() - timedelta(days=max_age),
        )
        .filter(connection_failure)
        .order_by('created_at')
    )


def pending_retry_summary():
    qs = retryable_invoices()
    return {
        'count': qs.count(),
        'total': float(qs.aggregate(total=Sum('total_amount')).get('total') or 0),
    }


@contextmanager
def _single_runner():
    """Un solo reintento a la vez, entre hilos y entre workers de gunicorn."""
    if not _process_lock.acquire(blocking=False):
        yield False
        return
    try:
        if connection.vendor != 'postgresql':
            yield True
            return
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s)', [ADVISORY_LOCK_KEY])
            acquired = cursor.fetchone()[0]
        try:
            yield acquired
        finally:
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_unlock(%s)', [ADVISORY_LOCK_KEY])
    finally:
        _process_lock.release()


def _arca_is_up(client):
    try:
        servers = client.dummy()
    except ArcaError as exc:
        return False, str(exc)
    down = [name for name, value in servers.items() if (value or '').upper() != 'OK']
    if down:
        return False, 'ARCA informa servidores sin servicio: ' + ', '.join(down)
    return True, ''


def retry_pending_invoices(limit=50, client=None):
    """Reintenta las facturas pendientes si ARCA responde. Devuelve un resumen."""
    from .arca_services import authorize_invoice_wsfe, wsfe_client
    from .fiscal_services import finalize_credit_note

    summary = {'ran': False, 'arca_up': None, 'candidates': 0, 'authorized': 0, 'failed': 0,
               'still_pending': 0, 'detail': ''}
    if _provider() != 'wsfe':
        summary['detail'] = 'ARCA_PROVIDER no es wsfe'
        return summary

    with _single_runner() as acquired:
        if not acquired:
            summary['detail'] = 'Otro proceso ya esta reintentando'
            return summary
        candidates = list(retryable_invoices()[:limit])
        summary['candidates'] = len(candidates)
        if not candidates:
            summary['detail'] = 'No hay facturas pendientes de reintento'
            return summary

        client = client or wsfe_client()
        up, reason = _arca_is_up(client)
        summary['arca_up'] = up
        if not up:
            summary['still_pending'] = len(candidates)
            summary['detail'] = reason
            return summary

        summary['ran'] = True
        for index, invoice in enumerate(candidates):
            try:
                authorized = authorize_invoice_wsfe(invoice, client=client)
            except ArcaConnectionError as exc:
                # ARCA se volvio a caer: el resto espera al proximo ciclo.
                summary['still_pending'] = len(candidates) - index
                summary['detail'] = str(exc)
                break
            except ArcaError as exc:
                summary['failed'] += 1
                logger.warning('Reintento ARCA fallo para factura %s: %s', invoice.pk, exc)
                continue
            _note_auto_retry(authorized)
            if authorized.cancels_id:
                finalize_credit_note(authorized)
            summary['authorized'] += 1
        logger.info('Reintento ARCA: %s', summary)
        return summary


def _note_auto_retry(invoice):
    meta = dict(invoice.meta or {})
    meta['auto_retried_at'] = timezone.now().isoformat()
    Invoice.objects.filter(pk=invoice.pk).update(meta=meta)
    invoice.meta = meta


def _retry_loop(interval):
    # Arranque escalonado para que los workers no consulten ARCA al mismo tiempo.
    time.sleep(random.uniform(5, 20))
    while True:
        try:
            close_old_connections()
            retry_pending_invoices()
        except Exception:  # noqa: BLE001 - el hilo nunca debe morir
            logger.exception('Error en el reintento automatico de ARCA')
        finally:
            close_old_connections()
        time.sleep(interval + random.uniform(0, 10))


def start_retry_scheduler():
    """Arranca el hilo de reintento (una vez por proceso). Se llama desde wsgi.py."""
    global _scheduler_started
    interval = int(getattr(settings, 'ARCA_AUTO_RETRY_SECONDS', 0) or 0)
    if interval <= 0 or _provider() != 'wsfe' or _scheduler_started:
        return False
    _scheduler_started = True
    thread = threading.Thread(target=_retry_loop, args=(interval,), name='arca-retry', daemon=True)
    thread.start()
    return True


def _voucher_label(voucher_type, point_of_sale, number):
    letters = {6: 'FB', 7: 'NDB', 8: 'NCB', 1: 'FA', 3: 'NCA', 11: 'FC', 13: 'NCC'}
    return f'{letters.get(voucher_type, voucher_type)} {point_of_sale:05d}-{number:08d}'


def _is_simulated(invoice):
    return (invoice.provider_result or {}).get('provider') == 'mock' or (invoice.cae or '').startswith('MOCK')


def verify_invoices_with_arca(start, end, client=None):
    """Compara lo que el ERP tiene autorizado en el periodo contra ARCA."""
    from .arca_services import wsfe_client

    if _provider() != 'wsfe':
        raise ArcaError('ARCA_PROVIDER no es wsfe: no hay comprobantes reales para verificar')
    client = client or wsfe_client()

    invoices = list(
        Invoice.objects
        .filter(
            issue_date__gte=start,
            issue_date__lte=end,
            voucher_number__isnull=False,
            status__in=[Invoice.Status.AUTHORIZED, Invoice.Status.CANCELLED],
        )
        .order_by('point_of_sale', 'voucher_type', 'voucher_number')
    )
    checks = []
    totals = {
        'erp_invoices': Decimal('0'),
        'arca_invoices': Decimal('0'),
        'erp_credit_notes': Decimal('0'),
        'arca_credit_notes': Decimal('0'),
        # Lo mismo que muestra "Facturado en ARCA": facturas vigentes (sin anuladas).
        'erp_active_invoices': Decimal('0'),
        'arca_active_invoices': Decimal('0'),
    }
    for invoice in invoices:
        is_credit = invoice.voucher_type in CREDIT_NOTE_VOUCHER_TYPES
        erp_key = 'erp_credit_notes' if is_credit else 'erp_invoices'
        arca_key = 'arca_credit_notes' if is_credit else 'arca_invoices'
        totals[erp_key] += invoice.total_amount
        is_active = not is_credit and invoice.status == Invoice.Status.AUTHORIZED
        if is_active:
            totals['erp_active_invoices'] += invoice.total_amount
        entry = {
            'invoice_id': str(invoice.id),
            'voucher': _voucher_label(invoice.voucher_type, invoice.point_of_sale, invoice.voucher_number),
            'status': invoice.status,
            'issue_date': invoice.issue_date.isoformat(),
            'total': float(invoice.total_amount),
            'cae': invoice.cae,
            'result': 'ok',
            'problems': [],
        }
        if _is_simulated(invoice):
            entry['result'] = 'simulated'
            entry['problems'].append('Comprobante simulado (ARCA_PROVIDER=mock): no existe en ARCA')
            checks.append(entry)
            continue
        found = client.get_voucher(invoice.point_of_sale, invoice.voucher_type, invoice.voucher_number)
        if not found or not found.get('cae'):
            entry['result'] = 'missing'
            entry['problems'].append('ARCA no tiene este comprobante')
            checks.append(entry)
            continue
        totals[arca_key] += found['total']
        if is_active:
            totals['arca_active_invoices'] += found['total']
        if found['cae'] != invoice.cae:
            entry['problems'].append(f"CAE distinto: ARCA {found['cae']}")
        if found['total'] != invoice.total_amount:
            entry['problems'].append(f"Importe distinto: ARCA {found['total']}")
        if found['date'] != invoice.issue_date:
            entry['problems'].append(f"Fecha distinta: ARCA {found['date'].isoformat() if found['date'] else '-'}")
        if entry['problems']:
            entry['result'] = 'mismatch'
        checks.append(entry)

    extra = _vouchers_missing_in_erp(client, invoices, start, end)

    counts = {'ok': 0, 'mismatch': 0, 'missing': 0, 'simulated': 0}
    for entry in checks:
        counts[entry['result']] += 1
    return {
        'period': {'start': start.isoformat(), 'end': end.isoformat()},
        'checked': len(checks),
        'counts': counts,
        'all_ok': counts['ok'] == len(checks) and not extra['vouchers'],
        'totals': {key: float(value) for key, value in totals.items()},
        'problems': [entry for entry in checks if entry['result'] != 'ok'],
        'not_in_erp': extra,
        'checked_at': timezone.now().isoformat(),
    }


def _vouchers_missing_in_erp(client, invoices, start, end):
    """Numeros salteados entre el primero y el ultimo del periodo que ARCA si tiene."""
    by_sequence = {}
    for invoice in invoices:
        by_sequence.setdefault((invoice.point_of_sale, invoice.voucher_type), []).append(invoice.voucher_number)
    vouchers = []
    lookups = 0
    truncated = False
    for (point_of_sale, voucher_type), numbers in by_sequence.items():
        known = set(
            Invoice.objects
            .filter(point_of_sale=point_of_sale, voucher_type=voucher_type, voucher_number__isnull=False)
            .values_list('voucher_number', flat=True)
        )
        for number in range(min(numbers), max(numbers) + 1):
            if number in known:
                continue
            if lookups >= MAX_GAP_LOOKUPS:
                truncated = True
                break
            lookups += 1
            found = client.get_voucher(point_of_sale, voucher_type, number)
            if found and found.get('cae'):
                vouchers.append({
                    'voucher': _voucher_label(voucher_type, point_of_sale, number),
                    'issue_date': found['date'].isoformat() if found['date'] else None,
                    'total': float(found['total']),
                    'cae': found['cae'],
                    'in_period': bool(found['date'] and start <= found['date'] <= end),
                })
    return {'vouchers': vouchers, 'lookups': lookups, 'truncated': truncated}
