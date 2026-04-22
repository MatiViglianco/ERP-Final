import base64
import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection, transaction as db_transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    AccountClient,
    AccountClientAlias,
    AccountTransaction,
    ValeImportBatch,
    ValeImportItem,
)
from .text_utils import build_initials, normalize_name_shape, normalize_search_text, simple_soundex


User = get_user_model()


MOCK_OCR_RESULT = {
    'fecha_detectada': '2026-04-07',
    'vales': [
        {'importe': 54731, 'cliente_raw': 'Silvi Farias', 'detalle': '', 'confianza': 0.94, 'source_index': 0},
        {'importe': 63868, 'cliente_raw': 'Juan Cornavilla', 'detalle': '', 'confianza': 0.88, 'source_index': 0},
        {'importe': 7560, 'cliente_raw': 'Valery', 'detalle': '', 'confianza': 0.95, 'source_index': 0},
        {'importe': 16944, 'cliente_raw': 'Heliosa', 'detalle': '', 'confianza': 0.62, 'source_index': 0},
    ],
}


def safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_client_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed:
        return parsed
    if isinstance(value, str) and value.endswith('Z'):
        return parse_datetime(value[:-1] + '+00:00')
    return None


def parse_client_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    cleaned = str(value).strip()
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        pass
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    for fmt in ('%d/%m', '%d-%m'):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            today = timezone.localdate()
            return date(today.year, parsed.month, parsed.day)
        except ValueError:
            continue
    return None


def parse_decimal(value, default='0'):
    if value in (None, ''):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def full_client_name(client):
    if not client:
        return ''
    name = client.full_name if hasattr(client, 'full_name') else ''
    return (name or '').strip()


def client_payload(client):
    if not client:
        return None
    reference_date = client.source_created_at or client.created_at
    return {
        'id': str(client.id),
        'codigo': client.external_id,
        'nombre': full_client_name(client),
        'activo': True,
        'phone': client.phone or '',
        'created_at': reference_date.isoformat() if reference_date else None,
        'status': client.status,
        'status_label': client.get_status_display(),
        'total_debt': float(client.total_debt or 0),
    }


def alias_payload(alias):
    return {
        'id': alias.id,
        'alias': alias.alias,
        'cliente': client_payload(alias.client),
        'auto_detected': alias.auto_detected,
        'usos': alias.uses,
        'confirmed_at': alias.confirmed_at.isoformat() if alias.confirmed_at else None,
    }


def auth_user_payload(user):
    first = (getattr(user, 'first_name', '') or '').strip()
    last = (getattr(user, 'last_name', '') or '').strip()
    display = ' '.join(part for part in [first, last] if part).strip() or user.get_username()
    return {
        'id': user.id,
        'username': user.get_username(),
        'user': user.get_username(),
        'nombre': display,
        'rol': 'admin' if user.is_superuser else 'operador',
        'iniciales': build_initials(first or user.get_username(), last),
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
    }


def _normalize_reason(alias_value, normalized_full, normalized_first, normalized_last, score, prefix, phonetic, handwritten_hint=False):
    normalized_alias = normalize_search_text(alias_value)
    tokens = [token for token in normalized_full.split() if token]
    if normalized_alias == normalized_full:
        return 'exacto'
    if normalized_alias and normalized_alias == normalized_last:
        return 'apellido'
    if normalized_alias and normalized_alias == normalized_first:
        return 'exacto'
    if normalized_alias and any(token.startswith(normalized_alias) for token in tokens):
        return 'prefijo'
    if handwritten_hint:
        return 'manuscrito'
    if phonetic:
        return 'fonetico'
    if prefix:
        return 'prefijo'
    if score >= 0.82:
        return 'diminutivo'
    return 'trigram'


def _prefix_related(left, right, min_size=3):
    left = (left or '').strip()
    right = (right or '').strip()
    if not left or not right:
        return False
    if min(len(left), len(right)) < min_size:
        return False
    if min(len(left), len(right)) / max(len(left), len(right)) < 0.7:
        return False
    return left.startswith(right) or right.startswith(left)


def _python_suggest_clients(alias_value, limit):
    normalized_alias = normalize_search_text(alias_value)
    if not normalized_alias:
        return []

    candidates = []
    soundex_alias = simple_soundex(normalized_alias)
    shape_alias = normalize_name_shape(normalized_alias)
    for client in AccountClient.objects.all().order_by('last_name', 'first_name'):
        full_name = full_client_name(client)
        if not full_name:
            continue
        normalized_full = normalize_search_text(full_name)
        normalized_first = normalize_search_text(client.first_name)
        normalized_last = normalize_search_text(client.last_name)
        if not normalized_full:
            continue

        search_variants = [
            normalized_full,
            normalized_first,
            normalized_last,
            ' '.join(token for token in [normalized_first, normalized_last] if token),
            ' '.join(token for token in [normalized_last, normalized_first] if token),
        ]
        exact = normalized_alias == normalized_full or normalized_alias in normalized_full.split()
        prefix = any(_prefix_related(normalized_alias, variant) for variant in search_variants if variant)
        phonetic = any(soundex_alias and soundex_alias == simple_soundex(variant) for variant in search_variants if variant)
        ratio = max(SequenceMatcher(None, normalized_alias, variant).ratio() for variant in search_variants if variant)
        shape_variants = [normalize_name_shape(variant) for variant in search_variants if variant]
        shape_exact = bool(shape_alias) and any(shape_alias == variant for variant in shape_variants if variant)
        shape_prefix = bool(shape_alias) and any(_prefix_related(shape_alias, variant) for variant in shape_variants if variant)
        shape_ratio = max(
            (SequenceMatcher(None, shape_alias, variant).ratio() for variant in shape_variants if variant and shape_alias),
            default=0,
        )
        handwritten_hint = shape_exact or shape_prefix or shape_ratio >= 0.88
        score = ratio

        if exact:
            score = max(score, 0.98)
        elif prefix:
            score = max(score, 0.86)
        elif phonetic:
            score = max(score, 0.72)
        elif shape_exact:
            score = max(score, 0.88)
        elif shape_prefix:
            score = max(score, 0.84)
        elif shape_ratio >= 0.9:
            score = max(score, 0.81)

        if score < 0.25 and not prefix and not phonetic and not handwritten_hint:
            continue

        candidates.append({
            'cliente': client_payload(client),
            'similitud': round(min(score, 0.99), 4),
            'motivo': _normalize_reason(
                alias_value,
                normalized_full,
                normalized_first,
                normalized_last,
                score,
                prefix,
                phonetic,
                handwritten_hint=handwritten_hint,
            ),
        })

    candidates.sort(key=lambda item: (-item['similitud'], item['cliente']['nombre']))
    return candidates[:limit]


def _postgres_suggest_clients(alias_value, limit):
    if connection.vendor != 'postgresql':
        return []
    sql = """
        SELECT
            id,
            external_id,
            first_name,
            last_name,
            similarity(
                lower(unaccent(trim(concat_ws(' ', coalesce(last_name, ''), coalesce(first_name, ''))))),
                lower(unaccent(%s))
            ) AS trgm_score,
            (soundex(trim(concat_ws(' ', coalesce(last_name, ''), coalesce(first_name, '')))) = soundex(%s)) AS fonetico,
            (
                lower(unaccent(trim(concat_ws(' ', coalesce(last_name, ''), coalesce(first_name, '')))))
                LIKE lower(unaccent(%s)) || '%%'
            ) AS prefijo
        FROM statsapp_accountclient
        WHERE similarity(
                lower(unaccent(trim(concat_ws(' ', coalesce(last_name, ''), coalesce(first_name, ''))))),
                lower(unaccent(%s))
            ) > 0.25
           OR soundex(trim(concat_ws(' ', coalesce(last_name, ''), coalesce(first_name, '')))) = soundex(%s)
           OR lower(unaccent(trim(concat_ws(' ', coalesce(last_name, ''), coalesce(first_name, '')))))
                LIKE lower(unaccent(%s)) || '%%'
        ORDER BY GREATEST(
            similarity(
                lower(unaccent(trim(concat_ws(' ', coalesce(last_name, ''), coalesce(first_name, ''))))),
                lower(unaccent(%s))
            ),
            CASE
                WHEN soundex(trim(concat_ws(' ', coalesce(last_name, ''), coalesce(first_name, '')))) = soundex(%s) THEN 0.7
                ELSE 0
            END
        ) DESC,
        last_name ASC,
        first_name ASC
        LIMIT %s
    """
    params = [alias_value, alias_value, alias_value, alias_value, alias_value, alias_value, alias_value, alias_value, limit]
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
    except Exception:
        return []

    suggestions = []
    for client_id, external_id, first_name, last_name, score, phonetic, prefix in rows:
        client = AccountClient(
            id=client_id,
            external_id=external_id,
            first_name=first_name or '',
            last_name=last_name or '',
        )
        normalized_full = normalize_search_text(full_client_name(client))
        suggestions.append({
            'cliente': {
                'id': str(client_id),
                'codigo': external_id,
                'nombre': full_client_name(client),
                'activo': True,
            },
            'similitud': round(float(score or 0), 4),
            'motivo': _normalize_reason(alias_value, normalized_full, normalize_search_text(first_name), normalize_search_text(last_name), float(score or 0), bool(prefix), bool(phonetic)),
        })
    return suggestions


def _merge_suggestions(*groups, limit=5):
    merged = {}
    for group in groups:
        for item in group or []:
            client_id = str((item.get('cliente') or {}).get('id') or '')
            if not client_id:
                continue
            current = merged.get(client_id)
            if current is None or float(item.get('similitud') or 0) > float(current.get('similitud') or 0):
                merged[client_id] = item
    return sorted(
        merged.values(),
        key=lambda item: (-float(item.get('similitud') or 0), (item.get('cliente') or {}).get('nombre') or ''),
    )[:limit]


def _score_alias_feedback(alias_value, known_alias):
    normalized_alias = normalize_search_text(alias_value)
    normalized_known = (known_alias.normalized_alias or '').strip() or normalize_search_text(known_alias.alias)
    if not normalized_alias or not normalized_known:
        return 0.0
    if normalized_alias == normalized_known:
        return 1.0

    prefix = _prefix_related(normalized_alias, normalized_known)
    phonetic = simple_soundex(normalized_alias) and simple_soundex(normalized_alias) == simple_soundex(normalized_known)
    ratio = SequenceMatcher(None, normalized_alias, normalized_known).ratio()

    shape_alias = normalize_name_shape(normalized_alias)
    shape_known = normalize_name_shape(normalized_known)
    shape_exact = bool(shape_alias and shape_known) and shape_alias == shape_known
    shape_prefix = bool(shape_alias and shape_known) and _prefix_related(shape_alias, shape_known)
    shape_ratio = SequenceMatcher(None, shape_alias, shape_known).ratio() if shape_alias and shape_known else 0

    score = 0.0
    if shape_exact:
        score = 0.9
    elif prefix or shape_prefix:
        score = 0.84
    elif phonetic:
        score = 0.76
    elif max(ratio, shape_ratio) >= 0.82:
        score = 0.72

    if score <= 0:
        return 0.0

    usage_bonus = min(0.08, float(known_alias.uses or 0) * 0.01)
    return round(min(score + usage_bonus, 0.98), 4)


def _apply_alias_feedback(alias_value, suggestions, limit=5):
    client_ids = [
        str((item.get('cliente') or {}).get('id') or '')
        for item in suggestions or []
        if (item.get('cliente') or {}).get('id')
    ]
    if not client_ids:
        return []

    aliases = (
        AccountClientAlias.objects
        .select_related('client')
        .filter(client_id__in=client_ids)
        .order_by('-uses', 'alias')
    )
    aliases_by_client = {}
    for alias in aliases:
        aliases_by_client.setdefault(str(alias.client_id), []).append(alias)

    reranked = []
    for item in suggestions or []:
        client = item.get('cliente') or {}
        client_id = str(client.get('id') or '')
        current_score = float(item.get('similitud') or 0)
        best_alias = None
        best_support = 0.0

        for known_alias in aliases_by_client.get(client_id, []):
            support = _score_alias_feedback(alias_value, known_alias)
            if support > best_support:
                best_support = support
                best_alias = known_alias

        if best_alias and best_support > current_score + 0.02:
            reranked.append({
                **item,
                'similitud': round(min(best_support, 0.99), 4),
                'motivo': 'aprendido',
                'feedback_alias': best_alias.alias,
                'feedback_usos': best_alias.uses,
            })
        elif best_alias and best_alias.uses >= 3:
            reranked.append({
                **item,
                'similitud': round(min(current_score + 0.02, 0.99), 4),
                'feedback_alias': best_alias.alias,
                'feedback_usos': best_alias.uses,
            })
        else:
            reranked.append(item)

    return sorted(
        reranked,
        key=lambda item: (-float(item.get('similitud') or 0), (item.get('cliente') or {}).get('nombre') or ''),
    )[:limit]


def suggest_clients(alias_value, limit=5):
    normalized_alias = normalize_search_text(alias_value)
    if not normalized_alias:
        return []

    exact_aliases = (
        AccountClientAlias.objects
        .select_related('client')
        .filter(normalized_alias=normalized_alias)
        .order_by('-uses', 'alias')
    )
    if exact_aliases.exists():
        return [
            {
                'cliente': client_payload(alias.client),
                'similitud': 1.0,
                'motivo': 'exacto',
            }
            for alias in exact_aliases[:limit]
        ]

    postgres_results = _postgres_suggest_clients(alias_value, limit)
    python_results = _python_suggest_clients(alias_value, limit)
    merged = _merge_suggestions(postgres_results, python_results, limit=limit)
    return _apply_alias_feedback(alias_value, merged, limit=limit)


def ensure_alias(cliente, alias_value, auto_detected=False):
    normalized = normalize_search_text(alias_value)
    if not normalized:
        raise ValueError('El alias no puede estar vacio')

    existing = AccountClientAlias.objects.filter(normalized_alias=normalized).select_related('client').first()
    now = timezone.now()
    if existing and existing.client_id != cliente.id:
        raise LookupError(existing.alias)
    if existing:
        updates = []
        if existing.alias != alias_value.strip():
            existing.alias = alias_value.strip()
            updates.append('alias')
        if auto_detected and not existing.auto_detected:
            existing.auto_detected = True
            updates.append('auto_detected')
        if existing.confirmed_at is None:
            existing.confirmed_at = now
            updates.append('confirmed_at')
        if updates:
            existing.save(update_fields=updates + ['updated_at'])
        return existing, False

    created = AccountClientAlias.objects.create(
        client=cliente,
        alias=alias_value.strip(),
        auto_detected=auto_detected,
        confirmed_at=now,
    )
    return created, True


def _build_manual_external_id():
    external_id = f'MANUAL-{uuid4().hex[:8].upper()}'
    while AccountClient.objects.filter(external_id=external_id).exists():
        external_id = f'MANUAL-{uuid4().hex[:8].upper()}'
    return external_id


def create_account_client(display_name, phone='', external_id=None):
    cleaned_name = ' '.join(str(display_name or '').split()).strip()
    cleaned_phone = ' '.join(str(phone or '').split()).strip()
    if len(cleaned_name) < 2:
        raise ValueError('El nombre del cliente es obligatorio')

    normalized = normalize_search_text(cleaned_name)
    existing = next(
        (
            client
            for client in AccountClient.objects.all().order_by('last_name', 'first_name')
            if normalize_search_text(full_client_name(client)) == normalized
        ),
        None,
    )
    if existing:
        return existing, False

    assigned_external_id = (external_id or '').strip() or _build_manual_external_id()
    while AccountClient.objects.filter(external_id=assigned_external_id).exists():
        assigned_external_id = _build_manual_external_id()

    first_name = ''
    last_name = cleaned_name
    if ',' in cleaned_name:
        raw_last, raw_first = cleaned_name.split(',', 1)
        first_name = raw_first.strip()
        last_name = raw_last.strip() or cleaned_name

    client = AccountClient.objects.create(
        external_id=assigned_external_id,
        first_name=first_name,
        last_name=last_name,
        phone=cleaned_phone,
        status=AccountClient.Status.ACTIVE,
    )
    return client, True


def match_client_by_name(raw_name):
    normalized = normalize_search_text(raw_name)
    if not normalized:
        return None

    alias = AccountClientAlias.objects.select_related('client').filter(normalized_alias=normalized).first()
    if alias:
        return alias.client

    clients = list(AccountClient.objects.all())
    exact = next((client for client in clients if normalize_search_text(full_client_name(client)) == normalized), None)
    if exact:
        return exact
    suggestions = suggest_clients(raw_name, 1)
    if suggestions and suggestions[0]['similitud'] >= 0.92:
        return AccountClient.objects.filter(pk=suggestions[0]['cliente']['id']).first()
    return None


def recalc_account_totals(client_ids=None):
    qs = AccountTransaction.objects.all()
    if client_ids is not None:
        qs = qs.filter(client_id__in=client_ids)

    updated_ids = set()
    for client in AccountClient.objects.filter(id__in=qs.values_list('client_id', flat=True).distinct()):
        pending = Decimal('0')
        has_partial = False
        has_overdue = False
        for tx in client.transactions.all():
            remaining = tx.remaining_amount
            pending += remaining
            if tx.status == AccountTransaction.Status.OVERDUE and remaining > Decimal('0'):
                has_overdue = True
            if tx.status == AccountTransaction.Status.PARTIAL and remaining > Decimal('0'):
                has_partial = True

        if pending <= Decimal('0'):
            status_value = AccountClient.Status.PAID
        elif has_overdue:
            status_value = AccountClient.Status.OVERDUE
        elif has_partial:
            status_value = AccountClient.Status.PARTIAL
        else:
            status_value = AccountClient.Status.ACTIVE
        AccountClient.objects.filter(id=client.id).update(total_debt=pending, status=status_value)
        updated_ids.add(client.id)

    if client_ids is not None:
        missing_ids = set(client_ids) - updated_ids
        if missing_ids:
            AccountClient.objects.filter(id__in=missing_ids).update(total_debt=Decimal('0'), status=AccountClient.Status.PAID)


def serialize_batch(batch, include_items=False):
    payload = {
        'lote_id': batch.lote_id,
        'fecha': batch.date.isoformat() if batch.date else None,
        'total': float(batch.total or 0),
        'cargado_por': auth_user_payload(batch.uploaded_by) if batch.uploaded_by else None,
        'cargado_en': batch.created_at.isoformat() if batch.created_at else None,
        'source_filenames': batch.source_filenames or [],
        'vales_count': getattr(batch, 'vales_count', None) or batch.items.count(),
        'pendientes_count': getattr(batch, 'pendientes_count', None),
    }
    if payload['pendientes_count'] is None:
        payload['pendientes_count'] = batch.items.filter(pending_review=True).count()
    if include_items:
        payload['vales'] = [
            serialize_vale_item(item)
            for item in batch.items.select_related('client').order_by('id')
        ]
    return payload


def serialize_vale_item(item):
    return {
        'id': item.id,
        'fecha': item.date.isoformat() if item.date else None,
        'importe': float(item.amount or 0),
        'cliente': client_payload(item.client),
        'cliente_raw': item.client_raw,
        'detalle': item.detail or '',
        'pendiente_revision': item.pending_review,
        'confianza': float(item.confidence or 0),
    }


def _http_json(url, payload, headers, timeout=90):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={**headers, 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore')
        raise RuntimeError(f'OCR provider error {exc.code}: {body}') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'No se pudo conectar al proveedor OCR: {exc.reason}') from exc


def _make_data_url(upload):
    content_type = getattr(upload, 'content_type', None) or 'image/jpeg'
    encoded = base64.b64encode(upload.read()).decode('utf-8')
    return f'data:{content_type};base64,{encoded}'


def _normalize_ocr_response(payload):
    result = payload if isinstance(payload, dict) else {}
    parsed_date = parse_client_date(result.get('fecha_detectada'))
    vales = []
    source_count = max(safe_int(result.get('source_count'), 0), 0)
    for entry in result.get('vales') or []:
        amount = parse_decimal(entry.get('importe'))
        if amount <= Decimal('0'):
            continue
        source_index = safe_int(entry.get('source_index'), -1)
        if source_count == 1 and source_index < 0:
            source_index = 0
        if source_index < 0 or (source_count and source_index >= source_count):
            source_index = None
        vales.append({
            'importe': float(amount),
            'cliente_raw': str(entry.get('cliente_raw') or '').strip(),
            'detalle': str(entry.get('detalle') or '').strip(),
            'confianza': max(0.0, min(float(entry.get('confianza') or 0), 1.0)),
            'source_index': source_index,
        })
    return {
        'fecha_detectada': parsed_date.isoformat() if parsed_date else None,
        'vales': vales,
    }


def _ocr_prompt():
    return (
        'Extrae de esta hoja manuscrita de vales los items en JSON estricto. '
        'Devuelve un objeto con fecha_detectada en formato YYYY-MM-DD o null y un array vales. '
        'Recibiras una o mas imagenes en orden; para cada vale incluye source_index empezando en 0 segun la imagen donde aparece. '
        'Si la hoja muestra solo dia y mes, completa el año actual. '
        'En los nombres manuscritos, la letra a muchas veces aparece cerrada o pegada al resto del trazo; '
        'no la confundas automaticamente con o, e o u y compara el nombre completo antes de decidir. '
        'Cada vale debe tener importe numerico, cliente_raw string, detalle string, source_index integer y confianza de 0 a 1. '
        'Si no estas seguro, usa null para la fecha y baja la confianza del vale. '
        'Ignora ruido visual y no inventes valores.'
    )


def _mock_ocr_process(_uploads):
    return MOCK_OCR_RESULT


def _ocr_response_schema():
    return {
        'type': 'object',
        'properties': {
            'fecha_detectada': {
                'type': ['string', 'null'],
                'description': 'Fecha de la hoja en formato YYYY-MM-DD o null si no se ve con claridad.',
            },
            'vales': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'importe': {
                            'type': 'number',
                            'description': 'Importe numerico del vale, sin moneda ni separadores de miles.',
                        },
                        'cliente_raw': {
                            'type': 'string',
                            'description': 'Nombre del cliente tal como se lee en la hoja.',
                        },
                        'detalle': {
                            'type': 'string',
                            'description': 'Detalle adicional del vale si existe; vacio si no hay.',
                        },
                        'source_index': {
                            'type': 'integer',
                            'description': 'Indice 0-based de la imagen donde aparece el vale.',
                        },
                        'confianza': {
                            'type': 'number',
                            'description': 'Confianza entre 0 y 1.',
                        },
                    },
                    'required': ['importe', 'cliente_raw', 'detalle', 'source_index', 'confianza'],
                    'additionalProperties': False,
                },
            },
        },
        'required': ['fecha_detectada', 'vales'],
        'additionalProperties': False,
    }


def _response_text_from_gemini(payload):
    texts = []
    for candidate in payload.get('candidates') or []:
        content = candidate.get('content') or {}
        for part in content.get('parts') or []:
            if part.get('text'):
                texts.append(part['text'])
    if texts:
        return '\n'.join(texts)
    raise RuntimeError('Gemini no devolvio texto util para OCR')


def _openai_ocr_process(uploads):
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError('OPENAI_API_KEY no configurada')
    image_inputs = [{'type': 'input_image', 'image_url': _make_data_url(upload)} for upload in uploads]
    payload = {
        'model': os.environ.get('OPENAI_OCR_MODEL', 'gpt-4.1-mini'),
        'input': [
            {
                'role': 'user',
                'content': [
                    {'type': 'input_text', 'text': _ocr_prompt()},
                    *image_inputs,
                ],
            }
        ],
    }
    headers = {'Authorization': f'Bearer {api_key}'}
    response = _http_json('https://api.openai.com/v1/responses', payload, headers)
    output_text = ''
    for item in response.get('output', []):
        for content in item.get('content', []):
            if content.get('type') in {'output_text', 'text'} and content.get('text'):
                output_text += content['text']
    if not output_text and response.get('output_text'):
        output_text = response['output_text']
    return json.loads(output_text)


def _anthropic_ocr_process(uploads):
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY no configurada')
    content = [{'type': 'text', 'text': _ocr_prompt()}]
    for upload in uploads:
        data_url = _make_data_url(upload)
        prefix, base64_data = data_url.split(',', 1)
        media_type = prefix.split(':', 1)[1].split(';', 1)[0]
        content.append({
            'type': 'image',
            'source': {
                'type': 'base64',
                'media_type': media_type,
                'data': base64_data,
            },
        })
    payload = {
        'model': os.environ.get('ANTHROPIC_OCR_MODEL', 'claude-3-5-sonnet-latest'),
        'max_tokens': 1800,
        'messages': [{'role': 'user', 'content': content}],
    }
    headers = {
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
    }
    response = _http_json('https://api.anthropic.com/v1/messages', payload, headers)
    text_blocks = [block.get('text', '') for block in response.get('content', []) if block.get('type') == 'text']
    return json.loads('\n'.join(text_blocks))


def _gemini_ocr_process(uploads):
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY no configurada')

    parts = [{'text': _ocr_prompt()}]
    for upload in uploads:
        data_url = _make_data_url(upload)
        prefix, base64_data = data_url.split(',', 1)
        media_type = prefix.split(':', 1)[1].split(';', 1)[0]
        parts.append({
            'inline_data': {
                'mime_type': media_type,
                'data': base64_data,
            }
        })

    model = os.environ.get('GEMINI_OCR_MODEL', 'gemini-2.5-flash').strip() or 'gemini-2.5-flash'
    payload = {
        'contents': [{'parts': parts}],
        'generationConfig': {
            'responseMimeType': 'application/json',
            'responseJsonSchema': _ocr_response_schema(),
        },
    }
    headers = {'x-goog-api-key': api_key}
    response = _http_json(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        payload,
        headers,
    )
    return json.loads(_response_text_from_gemini(response))


def process_ocr_uploads(uploads):
    provider = os.environ.get('OCR_PROVIDER', 'mock').strip().lower() or 'mock'
    if provider == 'mock':
        raw = _mock_ocr_process(uploads)
    elif provider == 'openai':
        raw = _openai_ocr_process(uploads)
    elif provider == 'anthropic':
        raw = _anthropic_ocr_process(uploads)
    elif provider == 'gemini':
        raw = _gemini_ocr_process(uploads)
    else:
        raise RuntimeError(f'OCR provider no soportado: {provider}')
    if isinstance(raw, dict):
        raw = {
            **raw,
            'source_count': len(uploads or []),
        }
    return _normalize_ocr_response(raw)


def _transaction_status_for_date(tx_date):
    today = timezone.localdate()
    start_of_month = date(today.year, today.month, 1)
    if tx_date and tx_date < start_of_month:
        return AccountTransaction.Status.OVERDUE
    return AccountTransaction.Status.ACTIVE


def _vale_row_index(item):
    meta_value = safe_int((item.meta or {}).get('row_index'), 0)
    if meta_value > 0:
        return meta_value
    return (
        item.batch.items
        .filter(id__lte=item.id)
        .count()
    )


def _create_or_update_vale_transaction(*, item, client):
    row_index = _vale_row_index(item)
    payload = {
        'client': client,
        'description': item.detail or f"Vale {item.batch.lote_id}",
        'date': item.date,
        'created_at': timezone.now(),
        'original_amount': item.amount,
        'paid_amount': Decimal('0'),
        'status': _transaction_status_for_date(item.date),
        'payments': [],
        'meta': {
            'source': 'transform_vales_carni',
            'cliente_raw': item.client_raw,
            'lote_id': item.batch.lote_id,
            'row_index': row_index,
        },
    }

    if item.transaction_id:
        transaction_obj = item.transaction
        for field, value in payload.items():
            setattr(transaction_obj, field, value)
        transaction_obj.save(update_fields=[
            'client',
            'description',
            'date',
            'created_at',
            'original_amount',
            'paid_amount',
            'status',
            'payments',
            'meta',
            'updated_at',
        ])
        return transaction_obj

    return AccountTransaction.objects.create(
        external_id=f"vale-{uuid4().hex}",
        **payload,
    )


def resolve_vale_import_item(*, item, client, user=None, create_alias=True):
    touched_client_ids = set()
    warnings = []

    with db_transaction.atomic():
        previous_client_id = item.client_id
        transaction_obj = _create_or_update_vale_transaction(item=item, client=client)
        item.client = client
        item.transaction = transaction_obj
        item.pending_review = False
        meta = dict(item.meta or {})
        meta.update({
            'source': 'transform_vales_carni',
            'resolved_by': getattr(user, 'username', '') or getattr(user, 'get_username', lambda: '')(),
            'resolved_at': timezone.now().isoformat(),
            'row_index': _vale_row_index(item),
        })
        item.meta = meta
        item.save(update_fields=['client', 'transaction', 'pending_review', 'meta'])
        touched_client_ids.add(client.id)
        if previous_client_id and previous_client_id != client.id:
            touched_client_ids.add(previous_client_id)

        if create_alias and item.client_raw:
            try:
                alias, _ = ensure_alias(client, item.client_raw, auto_detected=True)
                AccountClientAlias.objects.filter(pk=alias.pk).update(uses=F('uses') + 1)
            except LookupError:
                warnings.append('El alias OCR ya estaba vinculado a otro cliente y no se reemplazo.')

        recalc_account_totals(list(touched_client_ids))

    item.refresh_from_db()
    return item, warnings


def create_vale_batch(*, user, batch_date, vales_payload, source_filenames=None):
    lote_id = f"lote-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    source_filenames = source_filenames or []
    warnings = []
    touched_client_ids = set()
    pending_count = 0

    with db_transaction.atomic():
        batch = ValeImportBatch.objects.create(
            lote_id=lote_id,
            date=batch_date,
            total=Decimal('0'),
            uploaded_by=user,
            source_filenames=source_filenames,
        )
        total = Decimal('0')
        for idx, entry in enumerate(vales_payload, start=1):
            amount = parse_decimal(entry.get('importe'))
            if amount <= Decimal('0'):
                continue
            client = None
            client_id = entry.get('cliente_id')
            if client_id:
                client = AccountClient.objects.filter(pk=client_id).first()
            client_raw = str(entry.get('cliente_raw') or '').strip()
            detail = str(entry.get('detalle') or '').strip()
            confidence = parse_decimal(entry.get('confianza') or 0, default='0')
            pending = client is None
            transaction_obj = None
            if client:
                transaction_obj = AccountTransaction.objects.create(
                    client=client,
                    external_id=f"vale-{uuid4().hex}",
                    description=detail or f"Vale {lote_id}",
                    date=batch_date,
                    created_at=timezone.now(),
                    original_amount=amount,
                    paid_amount=Decimal('0'),
                    status=_transaction_status_for_date(batch_date),
                    payments=[],
                    meta={
                        'source': 'transform_vales_carni',
                        'cliente_raw': client_raw,
                        'lote_id': lote_id,
                        'row_index': idx,
                    },
                )
                touched_client_ids.add(client.id)
                alias = AccountClientAlias.objects.filter(
                    client=client,
                    normalized_alias=normalize_search_text(client_raw),
                ).first()
                if alias:
                    AccountClientAlias.objects.filter(pk=alias.pk).update(uses=F('uses') + 1)
            else:
                pending_count += 1
            ValeImportItem.objects.create(
                batch=batch,
                transaction=transaction_obj,
                date=batch_date,
                amount=amount,
                client=client,
                client_raw=client_raw,
                detail=detail,
                pending_review=pending,
                confidence=confidence,
                meta={'source': 'transform_vales_carni'},
            )
            total += amount

        batch.total = total
        batch.save(update_fields=['total'])
        if touched_client_ids:
            recalc_account_totals(list(touched_client_ids))

    if pending_count:
        warnings.append(f'{pending_count} vales con cliente sin vincular: quedaron pendientes de revision.')
    return batch, warnings
