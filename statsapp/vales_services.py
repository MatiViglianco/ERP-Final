import base64
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection, transaction as db_transaction
from django.db.models import F, Sum
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

OCR_NAME_STOPWORDS = {
    'a',
    'al',
    'de',
    'del',
    'el',
    'la',
    'las',
    'los',
    'mp',
    'por',
    'retiro',
    'retiros',
    'transferencia',
    'transf',
    'vale',
    'vales',
}

TOKEN_ALIASES = {
    'ale': ['alejandro', 'alejandra'],
    'cezar': ['cesar'],
    'cris': ['cristian', 'cristina'],
    'crist': ['cristian', 'cristina'],
    'facu': ['facundo'],
    'gabi': ['gabriel', 'gabriela'],
    'gonza': ['gonzalo'],
    'jony': ['jonathan'],
    'juancho': ['juan'],
    'lucho': ['luis'],
    'mati': ['matias'],
    'max': ['maximiliano', 'maximo'],
    'maxi': ['maximiliano', 'maximo'],
    'mica': ['micaela'],
    'nacho': ['ignacio'],
    'nati': ['natalia'],
    'naty': ['natalia'],
    'nico': ['nicolas'],
    'pancho': ['francisco'],
    'seba': ['sebastian'],
    'tincho': ['martin'],
    'vale': ['valeria', 'valentina'],
    'valen': ['valeria', 'valentina'],
    'valeny': ['valeria', 'valentina'],
    'valery': ['valeria'],
}


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


def normalize_vale_date_year(value):
    parsed = parse_client_date(value)
    if not parsed:
        return None
    current_year = timezone.localdate().year
    if parsed.year == current_year:
        return parsed
    try:
        return parsed.replace(year=current_year)
    except ValueError:
        return parsed.replace(year=current_year, day=28)


def parse_decimal(value, default='0'):
    if value in (None, ''):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _parse_ocr_amount_component(value):
    if value in (None, ''):
        return Decimal('0')
    if isinstance(value, (int, float, Decimal)):
        return parse_decimal(value)

    raw = str(value).strip()
    if not raw:
        return Decimal('0')
    cleaned = re.sub(r'[^\d,.\-]', '', raw)
    if not re.search(r'\d', cleaned):
        return Decimal('0')

    negative = cleaned.startswith('-')
    cleaned = cleaned.lstrip('-')

    # OCR de importes argentinos suele usar "." como miles: 13.570 => 13570.
    if re.search(r'[.,]\d{1,2}$', cleaned) and not re.search(r'[.,]\d{3}([.,]|$)', cleaned):
        decimal_sep = cleaned[-3]
        if decimal_sep == ',':
            normalized = cleaned.replace('.', '').replace(',', '.')
        else:
            normalized = cleaned.replace(',', '')
    else:
        normalized = re.sub(r'\D', '', cleaned)

    if not normalized:
        return Decimal('0')
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        amount = Decimal('0')
    return -amount if negative else amount


def _split_ocr_amount_values(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and '+' in value:
        return [part for part in value.split('+') if part.strip()]
    return [value]


def _format_ocr_amount_part(value):
    amount = _parse_ocr_amount_component(value)
    if amount <= Decimal('0'):
        return ''
    if amount == amount.to_integral_value():
        return str(int(amount))
    return str(amount).rstrip('0').rstrip('.')


def _parse_ocr_amount(entry):
    raw_values = (
        entry.get('importes')
        or entry.get('montos')
        or _split_ocr_amount_values(entry.get('importe'))
    )
    if not isinstance(raw_values, list):
        raw_values = [raw_values]

    parts = [_parse_ocr_amount_component(value) for value in raw_values]
    parts = [part for part in parts if part > Decimal('0')]
    amount = sum(parts, Decimal('0'))

    breakdown = ''
    if len(parts) > 1:
        formatted = [_format_ocr_amount_part(value) for value in raw_values]
        breakdown = ' + '.join(part for part in formatted if part)
    return amount, breakdown


def _coerce_bbox_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_ocr_bbox(value):
    if not value:
        return None

    if isinstance(value, dict):
        raw_values = {
            'x': value.get('x', value.get('left')),
            'y': value.get('y', value.get('top')),
            'w': value.get('w', value.get('width')),
            'h': value.get('h', value.get('height')),
            'right': value.get('right'),
            'bottom': value.get('bottom'),
        }
    elif isinstance(value, (list, tuple)) and len(value) >= 4:
        raw_values = {'x': value[0], 'y': value[1], 'w': value[2], 'h': value[3]}
    else:
        return None

    numeric = {
        key: _coerce_bbox_number(raw)
        for key, raw in raw_values.items()
        if raw not in (None, '')
    }
    if numeric.get('x') is None or numeric.get('y') is None:
        return None

    max_value = max((abs(item) for item in numeric.values()), default=0)
    if max_value > 100:
        return None
    scale = Decimal('0.01') if max_value > 1 else Decimal('1')

    x = Decimal(str(numeric['x'])) * scale
    y = Decimal(str(numeric['y'])) * scale
    if numeric.get('w') is not None and numeric.get('h') is not None:
        w = Decimal(str(numeric['w'])) * scale
        h = Decimal(str(numeric['h'])) * scale
    elif numeric.get('right') is not None and numeric.get('bottom') is not None:
        right = Decimal(str(numeric['right'])) * scale
        bottom = Decimal(str(numeric['bottom'])) * scale
        w = right - x
        h = bottom - y
    else:
        return None

    x = max(Decimal('0'), min(x, Decimal('1')))
    y = max(Decimal('0'), min(y, Decimal('1')))
    w = max(Decimal('0'), min(w, Decimal('1') - x))
    h = max(Decimal('0'), min(h, Decimal('1') - y))
    if w <= Decimal('0.005') or h <= Decimal('0.005'):
        return None

    return {
        'x': float(round(x, 4)),
        'y': float(round(y, 4)),
        'w': float(round(w, 4)),
        'h': float(round(h, 4)),
    }


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


def _name_tokens(value, *, keep_stopwords=False):
    tokens = [
        token
        for token in normalize_search_text(value).split()
        if len(token) >= 2
    ]
    if keep_stopwords:
        return tokens
    return [
        token
        for token in tokens
        if token not in OCR_NAME_STOPWORDS and len(token) >= 3
    ]


def _token_variants(token):
    variants = {token}
    variants.update(TOKEN_ALIASES.get(token, []))
    if token.endswith('y') and len(token) > 3:
        variants.add(token[:-1] + 'i')
    if token.endswith('o') and len(token) > 4:
        variants.add(token[:-1] + 'a')
    if token.endswith('a') and len(token) > 4:
        variants.add(token[:-1] + 'o')
    return variants


def _single_token_similarity(left, right):
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    best = 0.0
    for left_variant in _token_variants(left):
        for right_variant in _token_variants(right):
            if left_variant == right_variant:
                best = max(best, 0.98)
                continue
            shorter, longer = sorted([left_variant, right_variant], key=len)
            if len(shorter) >= 4 and longer.startswith(shorter):
                best = max(best, 0.92)
            elif len(shorter) >= 3 and longer.startswith(shorter) and len(longer) <= 7:
                best = max(best, 0.84)
            best = max(best, SequenceMatcher(None, left_variant, right_variant).ratio())

            shape_left = normalize_name_shape(left_variant)
            shape_right = normalize_name_shape(right_variant)
            if shape_left and shape_right:
                if shape_left == shape_right:
                    best = max(best, 0.9)
                elif _prefix_related(shape_left, shape_right):
                    best = max(best, 0.84)
                best = max(best, SequenceMatcher(None, shape_left, shape_right).ratio() * 0.96)

            if len(left_variant) >= 4 and len(right_variant) >= 4 and simple_soundex(left_variant) == simple_soundex(right_variant):
                best = max(best, 0.76)
    return min(best, 1.0)


def _token_match_score(raw_name, client):
    raw_tokens = _name_tokens(raw_name)
    if not raw_tokens:
        return 0.0, False

    client_tokens = []
    for token in _name_tokens(client.first_name, keep_stopwords=True) + _name_tokens(client.last_name, keep_stopwords=True):
        if token and token not in client_tokens:
            client_tokens.append(token)
    if not client_tokens:
        return 0.0, False

    remaining = list(client_tokens)
    scores = []
    for raw_token in raw_tokens:
        best_idx = -1
        best_score = 0.0
        for idx, client_token in enumerate(remaining):
            score = _single_token_similarity(raw_token, client_token)
            if score > best_score:
                best_idx = idx
                best_score = score
        if best_idx >= 0:
            remaining.pop(best_idx)
        scores.append(best_score)

    if not scores:
        return 0.0, False

    strong_matches = sum(1 for score in scores if score >= 0.84)
    usable_matches = sum(1 for score in scores if score >= 0.72)
    avg_score = sum(scores) / len(scores)
    best_score = max(scores)

    if len(raw_tokens) == 1:
        token = raw_tokens[0]
        if len(token) < 4 or token in TOKEN_ALIASES:
            return (best_score if best_score >= 0.94 else 0.0), best_score >= 0.94
        return best_score, best_score >= 0.88

    if usable_matches == len(scores) and strong_matches >= 1:
        avg_score = max(avg_score, 0.84)
    if strong_matches == len(scores):
        avg_score = max(avg_score, 0.9)
    if best_score >= 0.94 and usable_matches >= len(scores) - 1:
        avg_score = max(avg_score, 0.86)

    return min(avg_score, 0.99), usable_matches == len(scores)


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
        token_score, token_coverage = _token_match_score(alias_value, client)
        shape_variants = [normalize_name_shape(variant) for variant in search_variants if variant]
        shape_exact = bool(shape_alias) and any(shape_alias == variant for variant in shape_variants if variant)
        shape_prefix = bool(shape_alias) and any(_prefix_related(shape_alias, variant) for variant in shape_variants if variant)
        shape_ratio = max(
            (SequenceMatcher(None, shape_alias, variant).ratio() for variant in shape_variants if variant and shape_alias),
            default=0,
        )
        handwritten_hint = shape_exact or shape_prefix or shape_ratio >= 0.88 or (token_coverage and token_score >= 0.82)
        score = max(ratio, token_score)

        if exact:
            score = max(score, 0.98)
        elif prefix:
            score = max(score, 0.86)
        elif token_score >= 0.9:
            score = max(score, token_score)
        elif token_coverage and token_score >= 0.82:
            score = max(score, token_score)
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
                'motivo': 'aprendido' if best_support >= 0.72 else item.get('motivo', 'similar'),
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

    if not _name_tokens(alias_value):
        return []

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
    match = match_client_for_ocr(raw_name, limit=1)
    return match.get('client')


def _should_auto_match(suggestions):
    if not suggestions:
        return False
    best = suggestions[0]
    score = float(best.get('similitud') or 0)
    motivo = best.get('motivo') or ''
    second_score = float(suggestions[1].get('similitud') or 0) if len(suggestions) > 1 else 0
    gap = score - second_score

    if score >= 0.94:
        return True
    if score >= 0.9 and gap >= 0.04:
        return True
    if score >= 0.84 and gap >= 0.08 and motivo in {'aprendido', 'exacto', 'manuscrito', 'prefijo', 'diminutivo'}:
        return True
    return False


def match_client_for_ocr(raw_name, limit=4):
    normalized = normalize_search_text(raw_name)
    if not normalized:
        return {'client': None, 'suggestions': [], 'auto': False, 'match': None}

    alias = AccountClientAlias.objects.select_related('client').filter(normalized_alias=normalized).first()
    if alias:
        suggestion = {
            'cliente': client_payload(alias.client),
            'similitud': 1.0,
            'motivo': 'alias',
        }
        return {'client': alias.client, 'suggestions': [suggestion], 'auto': True, 'match': suggestion}

    exact = next(
        (
            client
            for client in AccountClient.objects.all().order_by('last_name', 'first_name')
            if normalize_search_text(full_client_name(client)) == normalized
        ),
        None,
    )
    if exact:
        suggestion = {
            'cliente': client_payload(exact),
            'similitud': 1.0,
            'motivo': 'exacto',
        }
        return {'client': exact, 'suggestions': [suggestion], 'auto': True, 'match': suggestion}

    suggestions = suggest_clients(raw_name, limit)
    if _should_auto_match(suggestions):
        client = AccountClient.objects.filter(pk=suggestions[0]['cliente']['id']).first()
        return {'client': client, 'suggestions': suggestions, 'auto': bool(client), 'match': suggestions[0] if client else None}
    return {'client': None, 'suggestions': suggestions, 'auto': False, 'match': suggestions[0] if suggestions else None}


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
    account_items_qs = batch.items.filter(transaction__isnull=False)
    account_total = account_items_qs.aggregate(total=Sum('amount')).get('total') or Decimal('0')
    payload = {
        'lote_id': batch.lote_id,
        'fecha': batch.date.isoformat() if batch.date else None,
        'total': float(batch.total or 0),
        'cuenta_corriente_total': float(account_total),
        'cargado_por': auth_user_payload(batch.uploaded_by) if batch.uploaded_by else None,
        'cargado_en': batch.created_at.isoformat() if batch.created_at else None,
        'source_filenames': batch.source_filenames or [],
        'vales_count': getattr(batch, 'vales_count', None) or batch.items.count(),
        'cuenta_corriente_count': account_items_qs.count(),
        'pendientes_count': getattr(batch, 'pendientes_count', None),
    }
    if payload['pendientes_count'] is None:
        payload['pendientes_count'] = batch.items.filter(pending_review=True).count()
    if include_items:
        payload['vales'] = [
            serialize_vale_item(item)
            for item in batch.items.select_related('client', 'transaction').order_by('id')
        ]
    return payload


def serialize_vale_item(item):
    meta = item.meta or {}
    return {
        'id': item.id,
        'fecha': item.date.isoformat() if item.date else None,
        'importe': float(item.amount or 0),
        'cliente': client_payload(item.client),
        'cliente_raw': item.client_raw,
        'detalle': item.detail or '',
        'pendiente_revision': item.pending_review,
        'en_cuenta_corriente': bool(item.transaction_id),
        'confianza': float(item.confidence or 0),
        'bbox': meta.get('bbox'),
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
    parsed_date = normalize_vale_date_year(result.get('fecha_detectada'))
    vales = []
    source_count = max(safe_int(result.get('source_count'), 0), 0)
    for entry in result.get('vales') or []:
        amount, amount_breakdown = _parse_ocr_amount(entry)
        if amount <= Decimal('0'):
            continue
        detail = str(entry.get('detalle') or '').strip()
        if amount_breakdown and amount_breakdown not in detail:
            detail = amount_breakdown if not detail else f'{amount_breakdown} - {detail}'
        source_index = safe_int(entry.get('source_index'), -1)
        if source_count == 1 and source_index < 0:
            source_index = 0
        if source_index < 0 or (source_count and source_index >= source_count):
            source_index = None
        bbox = _normalize_ocr_bbox(
            entry.get('bbox') or entry.get('line_bbox') or entry.get('bounds')
        )
        vales.append({
            'importe': float(amount),
            'cliente_raw': str(entry.get('cliente_raw') or '').strip(),
            'detalle': detail,
            'confianza': max(0.0, min(float(entry.get('confianza') or 0), 1.0)),
            'source_index': source_index,
            'bbox': bbox,
        })
    return {
        'fecha_detectada': parsed_date.isoformat() if parsed_date else None,
        'vales': vales,
    }


def _ocr_prompt():
    today = timezone.localdate()
    return (
        'Extrae de fotos de hojas manuscritas de una carniceria solamente la seccion VALES. '
        'Devuelve JSON estricto con fecha_detectada en formato YYYY-MM-DD o null y un array vales. '
        f'Hoy es {today.isoformat()} y el ano operativo es {today.year}; si la hoja muestra solo dia/mes o el ano no se ve claro, usa {today.year}. '
        'Recibiras una o mas imagenes en orden; para cada vale incluye source_index empezando en 0 segun la imagen donde aparece. '
        'Para cada vale incluye bbox con la caja aproximada de todo el renglon del vale en coordenadas normalizadas 0 a 1 relativas a la imagen completa: x, y, w, h. '
        'La caja debe cubrir importe y nombre del mismo renglon; si no podes ubicarlo con confianza, usa bbox null. '
        'Ignora encabezados, gastos, retiros, transferencias, totales, tachaduras decorativas y notas que no sean vales. '
        'Cada linea de vale suele tener importe a la izquierda y nombre o alias de cliente a la derecha. '
        'Si una misma linea trae dos o mas importes para el mismo cliente, como "4388 + 9182 Cesar Ferrero", devolve un solo vale con importe igual a la suma y detalle con el desglose "4388 + 9182". '
        'No conviertas palabras genericas como "vale", "vales", "mp", "gastos" o "retiros" en cliente_raw. '
        'Si un nombre esta abreviado o parecido al real, conserva el texto tal como se lee: por ejemplo "Maxi Camp", "Matias Vigli", "Valen Belande". '
        'No fuerces apellidos completos ni inventes clientes; el sistema despues hara el match contra la base. '
        'En manuscritos, a/o/e/u pueden parecerse, n/m/r pueden confundirse y una coma puede indicar apellido-nombre; usa el contexto de toda la linea. '
        'Cada vale debe tener importe numerico, cliente_raw string, detalle string, source_index integer y confianza de 0 a 1. '
        'Si no estas seguro de un nombre, manten cliente_raw con tu mejor lectura y baja confianza. '
        'Si no estas seguro de la fecha, usa null. No inventes importes ni nombres.'
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
                            'description': 'Importe numerico total del vale, sin moneda ni separadores de miles. Si la linea tiene varios importes para el mismo cliente, usar la suma.',
                        },
                        'cliente_raw': {
                            'type': 'string',
                            'description': 'Nombre del cliente tal como se lee en la hoja.',
                        },
                        'detalle': {
                            'type': 'string',
                            'description': 'Detalle adicional del vale. Si la linea trae varios importes para el mismo cliente, incluir el desglose, por ejemplo "4388 + 9182".',
                        },
                        'source_index': {
                            'type': 'integer',
                            'description': 'Indice 0-based de la imagen donde aparece el vale.',
                        },
                        'confianza': {
                            'type': 'number',
                            'description': 'Confianza entre 0 y 1.',
                        },
                        'bbox': {
                            'type': ['object', 'null'],
                            'description': 'Caja aproximada del renglon del vale en coordenadas normalizadas 0..1 de la imagen completa. Null si no se puede ubicar.',
                            'properties': {
                                'x': {
                                    'type': 'number',
                                    'description': 'Posicion horizontal izquierda normalizada entre 0 y 1.',
                                },
                                'y': {
                                    'type': 'number',
                                    'description': 'Posicion vertical superior normalizada entre 0 y 1.',
                                },
                                'w': {
                                    'type': 'number',
                                    'description': 'Ancho normalizado entre 0 y 1.',
                                },
                                'h': {
                                    'type': 'number',
                                    'description': 'Alto normalizado entre 0 y 1.',
                                },
                            },
                            'required': ['x', 'y', 'w', 'h'],
                            'additionalProperties': False,
                        },
                    },
                    'required': ['importe', 'cliente_raw', 'detalle', 'source_index', 'confianza', 'bbox'],
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

    model = os.environ.get('GEMINI_OCR_MODEL', 'gemini-3-flash-preview').strip() or 'gemini-3-flash-preview'
    payload = {
        'contents': [{'parts': parts}],
        'generationConfig': {
            'responseMimeType': 'application/json',
            'responseJsonSchema': _ocr_response_schema(),
            'thinkingConfig': {
                'thinkingBudget': safe_int(os.environ.get('GEMINI_THINKING_BUDGET', 0), 0),
            },
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
    item_meta = item.meta or {}
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
            'bbox': item_meta.get('bbox'),
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


def update_vale_batch_date(*, batch, batch_date):
    batch_date = normalize_vale_date_year(batch_date)
    if not batch_date:
        raise ValueError('La fecha del lote es obligatoria')
    touched_client_ids = set()
    with db_transaction.atomic():
        batch.date = batch_date
        batch.save(update_fields=['date'])

        items = list(batch.items.select_related('client', 'transaction'))
        now = timezone.now()
        transactions = []
        for item in items:
            item.date = batch_date
            if item.client_id:
                touched_client_ids.add(item.client_id)
            if item.transaction_id:
                transaction_obj = item.transaction
                transaction_obj.date = batch_date
                if transaction_obj.status in {
                    AccountTransaction.Status.ACTIVE,
                    AccountTransaction.Status.OVERDUE,
                }:
                    transaction_obj.status = _transaction_status_for_date(batch_date)
                transaction_obj.updated_at = now
                transactions.append(transaction_obj)

        if items:
            ValeImportItem.objects.bulk_update(items, ['date'], batch_size=500)
        if transactions:
            AccountTransaction.objects.bulk_update(transactions, ['date', 'status', 'updated_at'], batch_size=500)
        if touched_client_ids:
            recalc_account_totals(list(touched_client_ids))

    batch.refresh_from_db()
    return batch


def delete_vale_batch(*, batch):
    touched_client_ids = set(
        batch.items
        .filter(client_id__isnull=False)
        .values_list('client_id', flat=True)
    )
    transaction_ids = set(
        batch.items
        .filter(transaction_id__isnull=False)
        .values_list('transaction_id', flat=True)
    )
    transaction_ids.update(
        AccountTransaction.objects
        .filter(meta__lote_id=batch.lote_id)
        .values_list('id', flat=True)
    )
    touched_client_ids.update(
        AccountTransaction.objects
        .filter(id__in=transaction_ids, client_id__isnull=False)
        .values_list('client_id', flat=True)
    )

    deleted_items = batch.items.count()
    deleted_transactions = len(transaction_ids)
    lote_id = batch.lote_id

    with db_transaction.atomic():
        if transaction_ids:
            AccountTransaction.objects.filter(id__in=transaction_ids).delete()
        batch.delete()
        if touched_client_ids:
            recalc_account_totals(list(touched_client_ids))

    return {
        'lote_id': lote_id,
        'items_deleted': deleted_items,
        'transactions_deleted': deleted_transactions,
    }


def create_vale_batch(*, user, batch_date, vales_payload, source_filenames=None):
    batch_date = normalize_vale_date_year(batch_date)
    if not batch_date:
        raise ValueError('La fecha del lote es obligatoria')
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
            bbox = _normalize_ocr_bbox(entry.get('bbox'))
            item_meta = {
                'source': 'transform_vales_carni',
                'row_index': idx,
            }
            if bbox:
                item_meta['bbox'] = bbox
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
                        'bbox': bbox,
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
                meta=item_meta,
            )
            total += amount

        batch.total = total
        batch.save(update_fields=['total'])
        if touched_client_ids:
            recalc_account_totals(list(touched_client_ids))

    if pending_count:
        warnings.append(f'{pending_count} vales con cliente sin vincular: quedaron pendientes de revision.')
    return batch, warnings
