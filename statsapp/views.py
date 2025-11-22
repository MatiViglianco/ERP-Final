import json
from decimal import Decimal
from datetime import date, datetime
from uuid import uuid4
from collections import OrderedDict, defaultdict
from django.db import transaction as db_transaction
from django.db.models import Sum, Count, Q, Min, Max, F, DecimalField, ExpressionWrapper, Case, When, Value
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status

from .utils import parse_csv_and_aggregate, parse_csv_rows, _to_float, aggregate_rows, _parse_units, parse_santander_csv, parse_bancon_file
from .models import UploadBatch, Record, BankUploadBatch, BankTransaction, AccountClient, AccountTransaction, SalesManualEntry

SPANISH_MONTHS = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
]

SPANISH_WEEKDAYS = [
    'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'
]

def _format_spanish_month(date_obj):
    return f"{SPANISH_MONTHS[date_obj.month - 1]} de {date_obj.year}".capitalize()

def _format_spanish_day(date_obj):
    weekday = SPANISH_WEEKDAYS[date_obj.weekday()]
    month = SPANISH_MONTHS[date_obj.month - 1]
    return f"{weekday}, {date_obj.day} de {month} de {date_obj.year}".capitalize()


@api_view(['POST'])
@permission_classes([IsAdminUser])
def upload_csv(request):
    f = request.FILES.get('file')
    if not f:
        return Response({'detail': 'Falta el archivo "file"'}, status=status.HTTP_400_BAD_REQUEST)

    truthy = {'1', 'true', 'on', 'yes', 'si', 'sí', 's'}
    overwrite_requested = (request.POST.get('overwrite') or '').strip().lower() in truthy

    try:
        rows = parse_csv_rows(f.file)

        fecha_desde_str = (request.POST.get('fecha_desde') or '').strip() or None
        fecha_hasta_str = (request.POST.get('fecha_hasta') or '').strip() or None
        fecha_str = (request.POST.get('fecha') or '').strip() or None
        solo_hoy = (request.POST.get('solo_hoy') or '').strip().lower() in truthy

        def to_date(s):
            if not s:
                return None
            return date.fromisoformat(s)

        fecha_desde = to_date(fecha_desde_str)
        fecha_hasta = to_date(fecha_hasta_str)
        single_date_input = to_date(fecha_str)

        single_date_final = None
        if solo_hoy:
            single_date_final = date.today()
        elif single_date_input is not None:
            single_date_final = single_date_input
        elif (fecha_desde is not None) and (fecha_hasta is not None) and (fecha_desde == fecha_hasta):
            single_date_final = fecha_desde

        is_single = single_date_final is not None

        conflict_q = None
        if is_single:
            target = single_date_final or fecha_desde or fecha_hasta
            if target:
                conflict_q = (
                    Q(is_single_day=True, single_date=target) |
                    (Q(is_single_day=False, fecha_desde__lte=target) & Q(fecha_hasta__gte=target))
                )
        else:
            if fecha_desde and fecha_hasta:
                conflict_q = (
                    Q(is_single_day=True, single_date__range=[fecha_desde, fecha_hasta]) |
                    (Q(is_single_day=False, fecha_desde__lte=fecha_hasta) & Q(fecha_hasta__gte=fecha_desde))
                )

        if conflict_q is not None:
            conflicts = UploadBatch.objects.filter(conflict_q)
            if conflicts.exists():
                if not overwrite_requested:
                    conflict_info = [
                        {
                            'id': b.id,
                            'fecha': b.single_date.isoformat() if b.single_date else None,
                            'desde': b.fecha_desde.isoformat() if b.fecha_desde else None,
                            'hasta': b.fecha_hasta.isoformat() if b.fecha_hasta else None,
                        }
                        for b in conflicts
                    ]
                    return Response(
                        {
                            'detail': 'Ya existen datos cargados para ese período. ¿Deseás sobrescribirlos?',
                            'requires_overwrite': True,
                            'conflicts': conflict_info,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                conflicts.delete()

        batch = UploadBatch.objects.create(
            original_filename=getattr(f, 'name', ''),
            fecha_desde=None if is_single else fecha_desde,
            fecha_hasta=None if is_single else fecha_hasta,
            single_date=single_date_final,
            is_single_day=is_single,
            is_only_today=solo_hoy,
        )

        objs = []
        for r in rows:
            units = _parse_units(r)
            objs.append(Record(
                batch=batch,
                cod_seccion=(r.get('CODSECCION') or '').strip(),
                dsc_seccion=(r.get('DSCSECCION') or '').strip(),
                cod_familia=(r.get('CODFAMILIA') or '').strip(),
                dsc_familia=(r.get('DSCFAMILIA') or '').strip(),
                nro_plu=(r.get('NROPLU') or '').strip(),
                nom_plu=(r.get('NOMPLU') or '').strip(),
                uni=(r.get('UNI') or '').strip(),
                peso=_to_float(r.get('PESO')),
                imp=_to_float(r.get('IMP')),
                units=units,
            ))
        if objs:
            Record.objects.bulk_create(objs, batch_size=1000)

        data = aggregate_rows(rows)
        data['period'] = {
            'fecha': single_date_final.isoformat() if single_date_final else None,
            'desde': fecha_desde.isoformat() if fecha_desde and not is_single else None,
            'hasta': fecha_hasta.isoformat() if fecha_hasta and not is_single else None,
        }
        data['batch_id'] = batch.id
        return Response(data)
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

def _filter_qs(params):
    qs = Record.objects.select_related('batch').all()
    desde_s = params.get('fecha_desde')
    hasta_s = params.get('fecha_hasta')
    seccion = params.get('seccion')
    familia = params.get('familia')
    producto = params.get('producto')
    only_today = (params.get('only_today') or '').lower() in ['1', 'true', 'on', 'yes', 'si', 'sí']
    batch_id = params.get('batch_id')

    def to_date(s):
        try:
            return date.fromisoformat(s) if s else None
        except Exception:
            return None

    desde = to_date(desde_s)
    hasta = to_date(hasta_s)

    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    else:
        q = Q()
        if only_today:
            q &= Q(batch__is_only_today=True) | Q(batch__single_date=date.today())
        if desde and hasta:
            # Batches de un día: entre rango; rangos: solapamiento
            q &= (
                Q(batch__single_date__range=[desde, hasta]) |
                (Q(batch__fecha_desde__lte=hasta) & Q(batch__fecha_hasta__gte=desde))
            )
        elif desde:
            q &= (Q(batch__single_date__gte=desde) | Q(batch__fecha_hasta__gte=desde))
        elif hasta:
            q &= (Q(batch__single_date__lte=hasta) | Q(batch__fecha_desde__lte=hasta))
        qs = qs.filter(q)

    if seccion:
        qs = qs.filter(dsc_seccion=seccion)
    if familia:
        qs = qs.filter(dsc_familia=familia)
    if producto:
        qs = qs.filter(nom_plu=producto)
    return qs


def _parse_query_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@api_view(['GET'])
@permission_classes([IsAdminUser])
def stats(request):
    qs = _filter_qs(request.GET)

    totals = qs.aggregate(
        rows=Count('id'),
        peso=Sum('peso'),
        units=Sum('units'),
        imp=Sum('imp'),
    )

    period = qs.aggregate(
        start=Min(Coalesce('batch__single_date', 'batch__fecha_desde')),
        end=Max(Coalesce('batch__single_date', 'batch__fecha_hasta')),
    )

    by_seccion = (
        qs.values('dsc_seccion')
        .annotate(count=Count('id'), peso=Sum('peso'), units=Sum('units'), imp=Sum('imp'))
        .order_by('-imp')
    )
    by_producto = (
        qs.values('nom_plu')
        .annotate(count=Count('id'), peso=Sum('peso'), units=Sum('units'), imp=Sum('imp'))
        .order_by('-imp')[:20]
    )

    def _fmt_list(iterable, key):
        return [
            {
                'label': (row.get(key) or '').strip() or '(vacío)',
                'count': row['count'] or 0,
                'peso': round((row['peso'] or 0.0), 3),
                'units': round((row['units'] or 0.0), 3),
                'imp': round((row['imp'] or 0.0), 2),
            } for row in iterable
        ]

    return Response({
        'totals': {
            'rows': totals.get('rows') or 0,
            'peso': round((totals.get('peso') or 0.0), 3),
            'units': round((totals.get('units') or 0.0), 3),
            'imp': round((totals.get('imp') or 0.0), 2),
        },
        'by_seccion': _fmt_list(by_seccion, 'dsc_seccion'),
        'top_productos': _fmt_list(by_producto, 'nom_plu'),
        'period': {
            'desde': period.get('start').isoformat() if period.get('start') else None,
            'hasta': period.get('end').isoformat() if period.get('end') else None,
        }
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def list_filters(request):
    qs = _filter_qs(request.GET)
    secciones = sorted(set(qs.values_list('dsc_seccion', flat=True)))
    familias = sorted(set(qs.values_list('dsc_familia', flat=True)))
    productos = sorted(set(qs.values_list('nom_plu', flat=True)))
    return Response({
        'secciones': [s for s in secciones if (s or '').strip() != ''],
        'familias': [f for f in familias if (f or '').strip() != ''],
        'productos': [p for p in productos if (p or '').strip() != ''],
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def list_batches(request):
    batches = UploadBatch.objects.order_by('-created_at')[:100]
    def to_dict(b):
        return {
            'id': b.id,
            'created_at': b.created_at.isoformat(),
            'filename': b.original_filename,
            'fecha': b.single_date.isoformat() if b.single_date else None,
            'desde': b.fecha_desde.isoformat() if b.fecha_desde else None,
            'hasta': b.fecha_hasta.isoformat() if b.fecha_hasta else None,
            'is_single_day': b.is_single_day,
            'is_only_today': b.is_only_today,
        }
    return Response([to_dict(b) for b in batches])


@api_view(['GET'])
@permission_classes([IsAdminUser])
def sales_daily(request):
    qs = Record.objects.select_related('batch').annotate(
        day=Coalesce('batch__single_date', 'batch__fecha_desde', 'batch__fecha_hasta'),
    ).exclude(day__isnull=True)
    batch_id = request.query_params.get('batch_id')

    all_years = (
        Record.objects.annotate(day=Coalesce('batch__single_date', 'batch__fecha_desde', 'batch__fecha_hasta'))
        .exclude(day__isnull=True)
        .annotate(year=ExtractYear('day'))
        .values_list('year', flat=True)
        .distinct()
    )
    available_years = sorted([year for year in all_years if year])
    requested_year = _safe_int(request.query_params.get('year'), None)
    if not requested_year:
        requested_year = (available_years[-1] if available_years else date.today().year)
    qs = qs.filter(day__year=requested_year)
    annotated_for_months = qs.annotate(month=ExtractMonth('day'))
    available_months = sorted(annotated_for_months.values_list('month', flat=True).distinct())
    requested_month = _safe_int(request.query_params.get('month'), None)
    if requested_month:
        qs = qs.filter(day__month=requested_month)

    per_day = list(
        qs.values('batch_id', 'day')
        .annotate(
            ventas=Sum('imp'),
            peso=Sum('peso'),
            units=Sum('units'),
            registros=Count('id'),
        )
        .order_by('day')
    )

    batch_ids = {row['batch_id'] for row in per_day if row.get('batch_id')}
    batch_map = {b.id: b for b in UploadBatch.objects.filter(id__in=batch_ids)}
    manual_entries = SalesManualEntry.objects.filter(batch_id__in=batch_ids).filter(date__in=[row['day'] for row in per_day if row['day']])
    manual_map = {(entry.batch_id, entry.date): entry for entry in manual_entries}

    def _batch_label(batch):
        if not batch:
            return ''
        if batch.single_date:
            return batch.single_date.strftime('%d/%m/%Y')
        if batch.fecha_desde and batch.fecha_hasta:
            return f"{batch.fecha_desde.strftime('%d/%m/%Y')} al {batch.fecha_hasta.strftime('%d/%m/%Y')}"
        if batch.fecha_desde:
            return batch.fecha_desde.strftime('%d/%m/%Y')
        if batch.fecha_hasta:
            return batch.fecha_hasta.strftime('%d/%m/%Y')
        return f"Lote #{batch.id}"

    def _manual_field(entry, field):
        if not entry:
            return 0.0
        return float(getattr(entry, field) or 0)

    results = []
    totals = {'ventas': 0.0}
    sorted_rows = sorted(per_day, key=lambda r: r.get('day') or date.today())

    previous_fc_final = 0.0
    for idx, row in enumerate(sorted_rows):
        ventas = float(row.get('ventas') or 0.0)
        totals['ventas'] += ventas
        batch = batch_map.get(row.get('batch_id'))
        day_value = row.get('day')
        manual = manual_map.get((row.get('batch_id'), day_value))
        manual_values = {
            'anulado': _manual_field(manual, 'anulado'),
            'fcInicialManual': _manual_field(manual, 'fc_inicial'),
            'pagos': _manual_field(manual, 'pagos'),
            'debitos': _manual_field(manual, 'debitos'),
            'gastos': _manual_field(manual, 'gastos'),
            'vales': _manual_field(manual, 'vales'),
            'fcFinal': _manual_field(manual, 'fc_final'),
        }
        if idx == 0:
            fc_inicial_value = manual_values['fcInicialManual']
        else:
            fc_inicial_value = previous_fc_final
        previous_fc_final = manual_values['fcFinal']
        row_total = ventas + fc_inicial_value + manual_values['pagos'] - manual_values['fcFinal'] - manual_values['anulado'] - manual_values['debitos'] - manual_values['gastos'] - manual_values['vales']
        results.append({
            'batch_id': row.get('batch_id'),
            'date': day_value.isoformat() if day_value else None,
            'date_label': _format_spanish_day(day_value) if day_value else 'Sin fecha',
            'ventas': round(ventas, 2),
            'rows': row.get('registros') or 0,
            'dataset_label': _batch_label(batch),
            'source': getattr(batch, 'original_filename', '') if batch else '',
            'base_row': idx == 0,
            'fcInicialValue': round(fc_inicial_value, 2),
            'row_total': round(row_total, 2),
            **manual_values,
        })

    month_label = SPANISH_MONTHS[requested_month - 1].capitalize() if requested_month and 1 <= requested_month <= 12 else None
    dataset_info = None
    if batch_id:
        dataset_info = next((row for row in results if str(row.get('batch_id')) == str(batch_id)), None)

    week_summary = OrderedDict()
    stats = {'total_sales': 0.0, 'days': len(results), 'max_day': None}
    for row in results:
        if not row.get('date'):
            continue
        day_obj = date.fromisoformat(row['date'])
        week_key = day_obj.isocalendar()[:2]
        entry = week_summary.setdefault(week_key, {'start': day_obj, 'end': day_obj, 'total': 0.0})
        entry['start'] = min(entry['start'], day_obj)
        entry['end'] = max(entry['end'], day_obj)
        entry['total'] += row['row_total']
        stats['total_sales'] += row['row_total']
        if not stats.get('max_day') or row['row_total'] > stats['max_day']['total']:
            stats['max_day'] = {'date': row['date'], 'label': row['date_label'], 'total': row['row_total']}

    stats['average_daily'] = round(stats['total_sales'] / stats['days'], 2) if stats['days'] else 0.0
    stats['total_sales'] = round(stats['total_sales'], 2)

    formatted_weeks = []
    for (iso_year, iso_week), info in week_summary.items():
        formatted_weeks.append({
            'year': iso_year,
            'week': iso_week,
            'start': info['start'].isoformat(),
            'end': info['end'].isoformat(),
            'total': round(info['total'], 2),
        })

    return Response({
        'results': results,
        'filters': {
            'year': requested_year,
            'month': requested_month,
            'month_label': month_label,
            'batch_id': batch_id,
            'available_years': available_years,
            'available_months': available_months,
        },
        'dataset': dataset_info,
        'stats': stats,
        'week_summary': formatted_weeks,
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def sales_manual_entry(request):
    data = request.data or {}
    batch_id = data.get('batch_id')
    date_str = data.get('date')
    values = data.get('values') or {}
    if not batch_id or not date_str:
        return Response({'detail': 'batch_id y date son obligatorios'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        entry_date = date.fromisoformat(date_str)
    except ValueError:
        return Response({'detail': 'Fecha invalida'}, status=status.HTTP_400_BAD_REQUEST)
    batch = get_object_or_404(UploadBatch, pk=batch_id)

    def _to_decimal(key):
        raw = values.get(key)
        if raw in (None, ''):
            return Decimal('0')
        try:
            return Decimal(str(raw))
        except Exception:
            return Decimal('0')

    entry, _ = SalesManualEntry.objects.update_or_create(
        batch=batch,
        date=entry_date,
        defaults={
            'anulado': _to_decimal('anulado'),
            'fc_inicial': _to_decimal('fc_inicial'),
            'pagos': _to_decimal('pagos'),
            'debitos': _to_decimal('debitos'),
            'gastos': _to_decimal('gastos'),
            'vales': _to_decimal('vales'),
            'fc_final': _to_decimal('fc_final'),
            'total': _to_decimal('total'),
        },
    )
    return Response({
        'batch_id': batch_id,
        'date': entry.date.isoformat(),
        'values': {
            'anulado': float(entry.anulado),
            'fc_inicial': float(entry.fc_inicial),
            'pagos': float(entry.pagos),
            'debitos': float(entry.debitos),
            'gastos': float(entry.gastos),
            'vales': float(entry.vales),
            'fc_final': float(entry.fc_final),
            'total': float(entry.total),
        },
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def product_trend(request):
    product = request.GET.get('product') or request.GET.get('producto') or ''
    product = product.strip()
    if not product:
        return Response({'detail': 'Falta el parámetro "product"'}, status=status.HTTP_400_BAD_REQUEST)

    qs = _filter_qs(request.GET).filter(nom_plu=product)
    qs = qs.annotate(day=Coalesce('batch__single_date', 'batch__fecha_desde', 'batch__fecha_hasta'))
    per_day = (
        qs.values('day')
        .annotate(imp=Sum('imp'), peso=Sum('peso'), units=Sum('units'))
        .order_by('day')
    )
    data = []
    for row in per_day:
        day = row.get('day')
        data.append({
            'date': day.isoformat() if day else None,
            'imp': round((row.get('imp') or 0.0), 2),
            'peso': round((row.get('peso') or 0.0), 3),
            'units': round((row.get('units') or 0.0), 3),
        })
    return Response({'product': product, 'series': data})


@api_view(['POST'])
@permission_classes([IsAdminUser])
def upload_bank_file(request):
    bank = (request.POST.get('bank') or '').strip().lower()
    if bank not in {'santander', 'bancon'}:
        return Response({'detail': 'Banco invalido. Use "santander" o "bancon"'}, status=status.HTTP_400_BAD_REQUEST)

    uploaded = request.FILES.get('file')
    if not uploaded:
        return Response({'detail': 'Falta el archivo a subir'}, status=status.HTTP_400_BAD_REQUEST)

    truthy = {'1', 'true', 'on', 'yes', 'si', 's'}
    overwrite = (request.POST.get('overwrite') or '').strip().lower() in truthy

    parser = parse_santander_csv if bank == 'santander' else parse_bancon_file
    try:
        rows = parser(uploaded)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    dates = sorted([row['date'] for row in rows if row.get('date')])
    if not dates:
        return Response({'detail': 'No se detectaron fechas validas en el archivo'}, status=status.HTTP_400_BAD_REQUEST)
    fecha_desde, fecha_hasta = dates[0], dates[-1]

    conflict_q = BankUploadBatch.objects.filter(bank=bank).filter(
        Q(fecha_desde__lte=fecha_hasta, fecha_hasta__gte=fecha_desde)
    )
    if conflict_q.exists() and not overwrite:
        return Response(
            {
                'detail': 'Ya existen movimientos cargados para ese periodo. Desea sobrescribirlos?',
                'requires_overwrite': True,
                'conflicts': [{'id': b.id, 'desde': b.fecha_desde.isoformat(), 'hasta': b.fecha_hasta.isoformat()} for b in conflict_q],
            },
            status=status.HTTP_409_CONFLICT,
        )

    if overwrite:
        conflict_q.delete()

    batch = BankUploadBatch.objects.create(
        bank=bank,
        original_filename=getattr(uploaded, 'name', ''),
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )

    txs = [
        BankTransaction(
            batch=batch,
            date=row['date'],
            concept=row.get('concept') or '',
            description=row.get('description') or '',
            amount=row.get('amount') or 0.0,
        )
        for row in rows
    ]
    BankTransaction.objects.bulk_create(txs, batch_size=1000)

    ingresos = sum(row['amount'] for row in rows if row['amount'] > 0)
    egresos = sum(row['amount'] for row in rows if row['amount'] < 0)
    return Response({
        'batch_id': batch.id,
        'summary': {
            'ingresos': round(ingresos, 2),
            'egresos': round(abs(egresos), 2),
            'neto': round(ingresos + egresos, 2),
            'desde': fecha_desde.isoformat(),
            'hasta': fecha_hasta.isoformat(),
            'movimientos': len(rows),
        }
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def bank_stats(request):
    base_qs = BankTransaction.objects.select_related('batch')
    selected_bank = (request.GET.get('bank') or '').strip().lower() or 'santander'
    desde = _parse_query_date(request.GET.get('fecha_desde'))
    hasta = _parse_query_date(request.GET.get('fecha_hasta'))

    def apply_filters(queryset, bank_override=None):
        query = queryset
        bank_key = selected_bank if bank_override is None else bank_override
        if bank_key in {'santander', 'bancon'}:
            query = query.filter(batch__bank=bank_key)
        if desde:
            query = query.filter(date__gte=desde)
        if hasta:
            query = query.filter(date__lte=hasta)
        return query

    def summarize(queryset):
        totals = queryset.aggregate(
            ingresos=Sum('amount', filter=Q(amount__gt=0)),
            egresos=Sum('amount', filter=Q(amount__lt=0)),
            movimientos=Count('id'),
        )
        ingresos_total = round((totals.get('ingresos') or 0.0), 2)
        egresos_total = round(abs(totals.get('egresos') or 0.0), 2)

        per_day = queryset.values('date').annotate(
            ingresos=Sum('amount', filter=Q(amount__gt=0)),
            egresos=Sum('amount', filter=Q(amount__lt=0)),
        ).order_by('date')
        series = [
            {
                'date': row['date'].isoformat(),
                'ingresos': round(row.get('ingresos') or 0.0, 2),
                'egresos': round(abs(row.get('egresos') or 0.0), 2),
            } for row in per_day
        ]

        def _concept_list(filtro, kind):
            data = (
                queryset.filter(filtro)
                .values('concept')
                .annotate(total=Sum('amount'), count=Count('id'))
                .order_by('-total' if kind == 'income' else 'total')
            )
            results = []
            for row in data[:20]:
                amount = row['total'] or 0.0
                if kind == 'expense':
                    amount = abs(amount)
                results.append({
                    'label': (row['concept'] or '').strip() or '(sin concepto)',
                    'total': round(amount, 2),
                    'count': row['count'] or 0,
                })
            return results

        def _concept_entries(filtro, kind):
            rows = (
                queryset.filter(filtro)
                .order_by('-date')
                .values('concept', 'description', 'date', 'amount')
            )
            data = {}
            for row in rows:
                concept_label = (row['concept'] or '').strip() or '(sin concepto)'
                description_label = (row['description'] or '').strip() or '(sin descripcion)'
                amount = row['amount'] or 0.0
                if kind == 'expense':
                    amount = abs(amount)
                data.setdefault(concept_label, []).append({
                    'date': row['date'].isoformat() if row['date'] else None,
                    'description': description_label,
                    'amount': round(amount, 2),
                })
            return data

        return {
            'totals': {
                'ingresos': ingresos_total,
                'egresos': egresos_total,
                'neto': round(ingresos_total - egresos_total, 2),
                'movimientos': totals.get('movimientos') or 0,
            },
            'ingresos_por_concepto': _concept_list(Q(amount__gt=0), 'income'),
            'egresos_por_concepto': _concept_list(Q(amount__lt=0), 'expense'),
            'serie_diaria': series,
            'concept_entries': {
                'ingresos': _concept_entries(Q(amount__gt=0), 'income'),
                'egresos': _concept_entries(Q(amount__lt=0), 'expense'),
            },
        }

    main_qs = apply_filters(base_qs)
    summary = summarize(main_qs)

    bounds = main_qs.aggregate(
        start=Min('date'),
        end=Max('date'),
    )

    return Response({
        'filters': {
            'bank': selected_bank,
            'desde': desde.isoformat() if desde else bounds.get('start').isoformat() if bounds.get('start') else None,
            'hasta': hasta.isoformat() if hasta else bounds.get('end').isoformat() if bounds.get('end') else None,
        },
        **summary,
    })


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_client_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed:
        return parsed
    if isinstance(value, str) and value.endswith('Z'):
        return parse_datetime(value[:-1] + '+00:00')
    return None


def _parse_client_date(value):
    if not value:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        # Try ISO first
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            pass
        for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_decimal(value):
    if value is None or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('0')


def _recalc_account_totals(client_ids=None):
    qs = AccountTransaction.objects.all()
    if client_ids is not None:
        qs = qs.filter(client_id__in=client_ids)

    pending_expr = ExpressionWrapper(
        F('original_amount') - F('paid_amount'),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    summary = qs.values('client_id').annotate(
        pending=Sum(
            Case(
                When(original_amount__gt=F('paid_amount'), then=pending_expr),
                default=Value(Decimal('0')),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
        overdue=Count('id', filter=Q(status=AccountTransaction.Status.OVERDUE)),
        partial=Count('id', filter=Q(status=AccountTransaction.Status.PARTIAL)),
    )

    updated_ids = set()
    for row in summary:
        client_id = row['client_id']
        pending = row['pending'] or Decimal('0')
        status_value = AccountClient.Status.PAID
        if pending > Decimal('0'):
            if row['overdue']:
                status_value = AccountClient.Status.OVERDUE
            elif row['partial']:
                status_value = AccountClient.Status.PARTIAL
            else:
                status_value = AccountClient.Status.ACTIVE
        AccountClient.objects.filter(id=client_id).update(total_debt=pending, status=status_value)
        updated_ids.add(client_id)

    if client_ids is None:
        remaining_qs = AccountClient.objects.exclude(id__in=updated_ids)
    else:
        missing_ids = set(client_ids) - updated_ids
        remaining_qs = AccountClient.objects.filter(id__in=missing_ids)
    if remaining_qs.exists():
        remaining_qs.update(total_debt=Decimal('0'), status=AccountClient.Status.PAID)


def _serialize_account_client(client):
    reference_date = client.source_created_at or client.created_at
    return {
        'id': str(client.id),
        'external_id': client.external_id,
        'first_name': client.first_name,
        'last_name': client.last_name,
        'full_name': client.full_name,
        'phone': client.phone or '',
        'created_at': reference_date.isoformat() if reference_date else None,
        'status': client.status,
        'status_label': client.get_status_display(),
        'total_debt': float(client.total_debt or 0),
    }


@api_view(['POST'])
@permission_classes([IsAdminUser])
def upload_account_clients(request):
    upload = request.FILES.get('file')
    if not upload:
        return Response({'detail': 'Falta el archivo "file"'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        payload = json.load(upload)
    except json.JSONDecodeError as exc:
        return Response({'detail': f'JSON inválido: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

    clients = payload.get('clientes')
    transactions = payload.get('transacciones', [])
    if not isinstance(clients, list):
        return Response({'detail': 'La clave "clientes" debe ser una lista'}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(transactions, list):
        return Response({'detail': 'La clave "transacciones" debe ser una lista'}, status=status.HTTP_400_BAD_REQUEST)

    normalized_clients = []
    for entry in clients:
        external_id = str(entry.get('id') or '').strip()
        if not external_id:
            continue
        first_name = (entry.get('nombre') or '').strip()
        last_name = (entry.get('apellido') or '').strip()
        created_at = _parse_client_datetime(entry.get('fechaCreacion'))
        normalized_clients.append({
            'external_id': external_id,
            'first_name': first_name,
            'last_name': last_name,
            'source_created_at': created_at,
            'phone': (entry.get('telefono') or entry.get('phone') or '').strip(),
        })

    if not normalized_clients:
        return Response({'detail': 'No se encontraron clientes válidos'}, status=status.HTTP_400_BAD_REQUEST)

    client_external_ids = [row['external_id'] for row in normalized_clients]
    existing_map = {
        client.external_id: client
        for client in AccountClient.objects.filter(external_id__in=client_external_ids)
    }

    to_create = []
    to_update = []
    touched_clients = set()
    for row in normalized_clients:
        external_id = row['external_id']
        if external_id in existing_map:
            client = existing_map[external_id]
            changed = False
            if client.first_name != row['first_name']:
                client.first_name = row['first_name']
                changed = True
            if client.last_name != row['last_name']:
                client.last_name = row['last_name']
                changed = True
            if row['source_created_at'] and client.source_created_at != row['source_created_at']:
                client.source_created_at = row['source_created_at']
                changed = True
            if client.phone != row['phone']:
                client.phone = row['phone']
                changed = True
            if changed:
                to_update.append(client)
                touched_clients.add(client.id)
        else:
            new_client = AccountClient(
                external_id=external_id,
                first_name=row['first_name'],
                last_name=row['last_name'],
                source_created_at=row['source_created_at'],
                phone=row['phone'],
            )
            to_create.append(new_client)

    with db_transaction.atomic():
        if to_create:
            AccountClient.objects.bulk_create(to_create, batch_size=1000)
            touched_clients.update(client.id for client in to_create)
        if to_update:
            AccountClient.objects.bulk_update(to_update, ['first_name', 'last_name', 'source_created_at'], batch_size=1000)

        client_map = {
            client.external_id: client
            for client in AccountClient.objects.filter(external_id__in=client_external_ids)
        }

        referenced_ids = {str(item.get('clienteId') or '').strip() for item in transactions}
        missing_clients = [external_id for external_id in referenced_ids if external_id and external_id not in client_map]
        if missing_clients:
            new_missing = [
                AccountClient(external_id=ext_id)
                for ext_id in missing_clients
            ]
            AccountClient.objects.bulk_create(new_missing, batch_size=1000)
            for client in new_missing:
                client_map[client.external_id] = client
                touched_clients.add(client.id)

        transaction_ids = [str(tx.get('id') or '').strip() for tx in transactions if str(tx.get('id') or '').strip()]
        existing_tx_map = {
            tx.external_id: tx
            for tx in AccountTransaction.objects.filter(external_id__in=transaction_ids)
        }

        tx_to_create = []
        tx_to_update = []
        touched_clients = set()
        for tx in transactions:
            ext_id = str(tx.get('id') or '').strip()
            client_ext = str(tx.get('clienteId') or '').strip()
            if not ext_id or not client_ext:
                continue
            client = client_map.get(client_ext)
            if not client:
                continue
            touched_clients.add(client.id)
            description = (tx.get('descripcion') or '').strip()
            status_value = (tx.get('estado') or AccountTransaction.Status.ACTIVE).lower()
            if status_value not in AccountTransaction.Status.values:
                status_value = AccountTransaction.Status.ACTIVE
            parsed_date = _parse_client_date(tx.get('fecha'))
            created_at = _parse_client_datetime(tx.get('createdAt'))
            original_amount = _parse_decimal(tx.get('monto'))
            paid_amount = _parse_decimal(tx.get('montoPagado'))
            payments = tx.get('pagos') if isinstance(tx.get('pagos'), list) else []

            if ext_id in existing_tx_map:
                obj = existing_tx_map[ext_id]
                changed = False
                if obj.client_id != client.id:
                    obj.client = client
                    changed = True
                if obj.description != description:
                    obj.description = description
                    changed = True
                if obj.status != status_value:
                    obj.status = status_value
                    changed = True
                if obj.date != parsed_date:
                    obj.date = parsed_date
                    changed = True
                if obj.created_at != created_at:
                    obj.created_at = created_at
                    changed = True
                if obj.original_amount != original_amount:
                    obj.original_amount = original_amount
                    changed = True
                if obj.paid_amount != paid_amount:
                    obj.paid_amount = paid_amount
                    changed = True
                if obj.payments != payments:
                    obj.payments = payments
                    changed = True
                if changed:
                    tx_to_update.append(obj)
            else:
                tx_to_create.append(AccountTransaction(
                    external_id=ext_id,
                    client=client,
                    description=description,
                    status=status_value,
                    date=parsed_date,
                    created_at=created_at,
                    original_amount=original_amount,
                    paid_amount=paid_amount,
                    payments=payments,
                ))

        if tx_to_create:
            AccountTransaction.objects.bulk_create(tx_to_create, batch_size=1000)
        if tx_to_update:
            AccountTransaction.objects.bulk_update(
                tx_to_update,
                ['client', 'description', 'status', 'date', 'created_at', 'original_amount', 'paid_amount', 'payments'],
                batch_size=500,
            )

        if touched_clients:
            _recalc_account_totals(list(touched_clients))

    return Response({
        'detail': 'Datos de cuentas procesados correctamente',
        'clients_created': len(to_create),
        'clients_updated': len(to_update),
        'transactions_created': len(tx_to_create),
        'transactions_updated': len(tx_to_update),
        'clients_total': len(normalized_clients),
        'transactions_total': len(transactions),
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def list_account_clients(request):
    if request.method == 'POST':
        data = request.data or {}
        first = (data.get('first_name') or '').strip()
        last = (data.get('last_name') or '').strip()
        phone = (data.get('phone') or '').strip()
        if len(first) < 2 or len(last) < 2:
            return Response({'detail': 'Nombre y apellido son obligatorios'}, status=status.HTTP_400_BAD_REQUEST)
        external_id = (data.get('external_id') or '').strip() or uuid4().hex
        while AccountClient.objects.filter(external_id=external_id).exists():
            external_id = uuid4().hex
        client = AccountClient.objects.create(
            external_id=external_id,
            first_name=first,
            last_name=last,
            phone=phone,
            status=data.get('status') if data.get('status') in AccountClient.Status.values else AccountClient.Status.ACTIVE,
        )
        return Response(_serialize_account_client(client), status=status.HTTP_201_CREATED)

    search = (request.query_params.get('search') or '').strip()
    ordering = (request.query_params.get('ordering') or 'last_name').strip()
    status_filter = request.query_params.get('status')
    limit = min(max(_safe_int(request.query_params.get('limit', 15), 15), 1), 200)
    offset = max(_safe_int(request.query_params.get('offset', 0), 0), 0)

    qs = AccountClient.objects.all()

    if search:
        tokens = [token for token in search.split() if token]
        for token in tokens:
            qs = qs.filter(
                Q(first_name__icontains=token) |
                Q(last_name__icontains=token) |
                Q(external_id__icontains=token)
            )

    if status_filter and status_filter != 'all':
        qs = qs.filter(status=status_filter)

    ordering_map = {
        'last_name': ('last_name', 'first_name'),
        '-last_name': ('-last_name', '-first_name'),
        'debt': ('-total_debt', 'last_name'),
    }
    qs = qs.order_by(*ordering_map.get(ordering, ordering_map['last_name']))

    total = qs.count()
    clients = list(qs[offset:offset + limit])
    results = [_serialize_account_client(client) for client in clients]

    status_counts = {choice.value: 0 for choice in AccountClient.Status}
    total_clients = AccountClient.objects.count()
    for row in AccountClient.objects.values('status').annotate(total=Count('id')):
        status_counts[row['status']] = row['total']
    status_counts['all'] = total_clients

    return Response({
        'results': results,
        'count': total,
        'limit': limit,
        'offset': offset,
        'summary': status_counts,
    })


def _serialize_transactions(qs):
    data = []
    for tx in qs:
        data.append({
            'id': tx.external_id,
            'date': tx.date.isoformat() if tx.date else None,
            'description': tx.description or '',
            'original': float(tx.original_amount or 0),
            'paid': float(tx.paid_amount or 0),
            'remaining': float(tx.remaining_amount),
            'status': tx.status,
            'status_label': tx.get_status_display(),
            'payments': tx.payments or [],
        })
    return data


@api_view(['GET'])
@permission_classes([IsAdminUser])
def account_clients_stats(request):
    start = _parse_client_date(request.query_params.get('start_date'))
    end = _parse_client_date(request.query_params.get('end_date'))
    year = _safe_int(request.query_params.get('year'), None)
    month = _safe_int(request.query_params.get('month'), None)
    day = _safe_int(request.query_params.get('day'), None)
    qs = AccountTransaction.objects.filter(date__isnull=False).select_related('client')
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    if year:
        qs = qs.filter(date__year=year)
    if month:
        qs = qs.filter(date__month=month)
    if day:
        qs = qs.filter(date__day=day)
    qs = qs.order_by('-date', '-created_at')

    months = OrderedDict()

    year_totals = {'original': Decimal('0'), 'remaining': Decimal('0')}
    client_totals = defaultdict(lambda: Decimal('0'))

    for tx in qs:
        if not tx.date:
            continue
        month_key = tx.date.strftime('%Y-%m')
        month_label = _format_spanish_month(tx.date)
        month_entry = months.setdefault(month_key, {
            'month': month_key,
            'month_label': month_label,
            'totals': {'original': Decimal('0'), 'paid': Decimal('0'), 'remaining': Decimal('0')},
            'days': OrderedDict(),
        })

        remaining = tx.remaining_amount
        month_entry['totals']['original'] += tx.original_amount or Decimal('0')
        month_entry['totals']['paid'] += tx.paid_amount or Decimal('0')
        month_entry['totals']['remaining'] += remaining

        day_key = tx.date.strftime('%Y-%m-%d')
        day_label = _format_spanish_day(tx.date)
        day_entry = month_entry['days'].setdefault(day_key, {
            'date': day_key,
            'label': day_label,
            'totals': {'original': Decimal('0'), 'paid': Decimal('0'), 'remaining': Decimal('0')},
            'transactions': [],
        })

        day_entry['totals']['original'] += tx.original_amount or Decimal('0')
        day_entry['totals']['paid'] += tx.paid_amount or Decimal('0')
        day_entry['totals']['remaining'] += remaining

        day_entry['transactions'].append({
            'client': tx.client.full_name if tx.client else '',
            'description': tx.description or '',
            'original': float(tx.original_amount or 0),
            'paid': float(tx.paid_amount or 0),
            'remaining': float(remaining),
            'status': tx.status,
        })

        year_totals['original'] += tx.original_amount or Decimal('0')
        year_totals['remaining'] += remaining
        if tx.client:
            client_totals[tx.client.full_name] += tx.original_amount or Decimal('0')

    page = max(_safe_int(request.query_params.get('page', 1), 1), 1)
    page_size = min(max(_safe_int(request.query_params.get('page_size', 4), 4), 1), 12)

    response = []
    for month in months.values():
        month['totals'] = {k: float(v) for k, v in month['totals'].items()}
        days_list = []
        for day in month['days'].values():
            day['totals'] = {k: float(v) for k, v in day['totals'].items()}
            days_list.append(day)
        month['days'] = days_list
        response.append(month)

    total_months = len(response)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated = response[start_idx:end_idx]

    top_clients = sorted(client_totals.items(), key=lambda x: x[1], reverse=True)[:8]

    return Response({
        'results': paginated,
        'total_months': total_months,
        'page': page,
        'page_size': page_size,
        'year_totals': {
            'original': float(year_totals['original']),
            'remaining': float(year_totals['remaining']),
        },
        'top_clients': [
            {'client': name, 'original': float(total)}
            for name, total in top_clients
        ],
    })


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAdminUser])
def account_client_view(request, pk):
    client = get_object_or_404(AccountClient, pk=pk)

    if request.method == 'GET':
        limit = min(max(_safe_int(request.query_params.get('limit', 30), 30), 1), 500)
        offset = max(_safe_int(request.query_params.get('offset', 0), 0), 0)
        qs = client.transactions.order_by('-date', '-created_at', '-id')
        total = qs.count()
        page = qs[offset:offset + limit]

        totals = qs.aggregate(
            original=Coalesce(Sum('original_amount'), Decimal('0')),
            paid=Coalesce(Sum('paid_amount'), Decimal('0')),
        )
        remaining_total = totals['original'] - totals['paid']

        return Response({
            'client': _serialize_account_client(client),
            'transactions': _serialize_transactions(page),
            'transactions_total': total,
            'limit': limit,
            'offset': offset,
            'totals': {
                'original': float(totals['original']),
                'paid': float(totals['paid']),
                'remaining': float(remaining_total),
            },
        })

    if request.method == 'PATCH':
        data = request.data
        updated_fields = []
        if 'first_name' in data:
            client.first_name = (data.get('first_name') or '').strip()
            updated_fields.append('first_name')
        if 'last_name' in data:
            client.last_name = (data.get('last_name') or '').strip()
            updated_fields.append('last_name')
        if 'phone' in data:
            client.phone = (data.get('phone') or '').strip()
            updated_fields.append('phone')
        if 'status' in data:
            new_status = data.get('status')
            if new_status in AccountClient.Status.values:
                client.status = new_status
                updated_fields.append('status')
        if updated_fields:
            client.save(update_fields=updated_fields + ['updated_at'])
        return Response(_serialize_account_client(client))

    # DELETE
    client.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


def _apply_payment_to_tx(tx, amount, payment_date):
    if amount <= Decimal('0'):
        return Decimal('0')
    remaining = tx.remaining_amount
    pay_amount = min(remaining, amount)
    if pay_amount <= Decimal('0'):
        return Decimal('0')
    tx.paid_amount = (tx.paid_amount or Decimal('0')) + pay_amount
    payments = list(tx.payments or [])
    payments.append({
        'fecha': payment_date.isoformat(),
        'monto': float(pay_amount),
    })
    tx.payments = payments
    if tx.remaining_amount <= Decimal('0'):
        tx.status = AccountTransaction.Status.PAID
        tx.paid_amount = tx.original_amount
    else:
        tx.status = AccountTransaction.Status.PARTIAL
    tx.save(update_fields=['paid_amount', 'status', 'payments', 'updated_at'])
    return pay_amount


@api_view(['POST'])
@permission_classes([IsAdminUser])
def account_client_pay(request, pk):
    client = get_object_or_404(AccountClient, pk=pk)
    mode = (request.data.get('mode') or 'selected').lower()
    today = date.today()

    with db_transaction.atomic():
        if mode == 'selected':
            tx_ids = request.data.get('transaction_ids') or []
            if not isinstance(tx_ids, list) or not tx_ids:
                return Response({'detail': 'Debes indicar las transacciones a pagar'}, status=status.HTTP_400_BAD_REQUEST)
            txs = list(client.transactions.filter(external_id__in=tx_ids))
            if not txs:
                return Response({'detail': 'No se encontraron las transacciones seleccionadas'}, status=status.HTTP_400_BAD_REQUEST)
            partial_amount = _parse_decimal(request.data.get('amount'))
            if partial_amount > Decimal('0'):
                amount_left = partial_amount
                for tx in txs:
                    remaining = tx.remaining_amount
                    if remaining <= Decimal('0'):
                        continue
                    paid = _apply_payment_to_tx(tx, amount_left, today)
                    amount_left -= paid
                    if amount_left <= Decimal('0'):
                        break
                if amount_left == partial_amount:
                    return Response({'detail': 'No hay movimientos pendientes en la selección'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                for tx in txs:
                    remaining = tx.remaining_amount
                    if remaining <= Decimal('0'):
                        continue
                    _apply_payment_to_tx(tx, remaining, today)

        elif mode == 'full':
            txs = list(client.transactions.filter(original_amount__gt=F('paid_amount')))
            for tx in txs:
                remaining = tx.remaining_amount
                if remaining > Decimal('0'):
                    _apply_payment_to_tx(tx, remaining, today)

        elif mode == 'partial':
            amount = _parse_decimal(request.data.get('amount'))
            if amount <= Decimal('0'):
                return Response({'detail': 'El monto debe ser mayor a cero'}, status=status.HTTP_400_BAD_REQUEST)
            start_limit = request.data.get('start_date')
            end_limit = request.data.get('end_date')
            pending_qs = client.transactions.filter(original_amount__gt=F('paid_amount'))
            if start_limit:
                try:
                    start_dt = date.fromisoformat(start_limit)
                    pending_qs = pending_qs.filter(date__gte=start_dt)
                except ValueError:
                    return Response({'detail': 'Fecha inicial inválida'}, status=status.HTTP_400_BAD_REQUEST)
            if end_limit:
                try:
                    end_dt = date.fromisoformat(end_limit)
                    pending_qs = pending_qs.filter(date__lte=end_dt)
                except ValueError:
                    return Response({'detail': 'Fecha final inválida'}, status=status.HTTP_400_BAD_REQUEST)
            pending = list(pending_qs.order_by('date', 'created_at', 'id'))
            amount_left = amount
            for tx in pending:
                paid = _apply_payment_to_tx(tx, amount_left, today)
                amount_left -= paid
                if amount_left <= Decimal('0'):
                    break
            if amount_left == amount:
                return Response({'detail': 'No hay movimientos pendientes para aplicar el pago'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'detail': 'Modo de pago inválido'}, status=status.HTTP_400_BAD_REQUEST)

        _recalc_account_totals([client.id])
        client.refresh_from_db()

    return Response({
        'detail': 'Pago registrado correctamente',
        'client': _serialize_account_client(client),
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def account_transaction_create(request, pk):
    client = get_object_or_404(AccountClient, pk=pk)
    data = request.data or {}

    amount = _parse_decimal(data.get('amount') or data.get('original') or data.get('monto'))
    if amount <= Decimal('0'):
        return Response({'detail': 'El monto debe ser mayor a cero'}, status=status.HTTP_400_BAD_REQUEST)

    tx_date = _parse_client_date(data.get('date')) or date.today()
    description = (data.get('description') or '').strip()
    status_value = (data.get('status') or AccountTransaction.Status.ACTIVE).lower()
    if status_value not in AccountTransaction.Status.values:
        status_value = AccountTransaction.Status.ACTIVE
    if status_value == AccountTransaction.Status.ACTIVE and tx_date < date.today():
        status_value = AccountTransaction.Status.OVERDUE

    external_id = (data.get('external_id') or '').strip() or uuid4().hex
    if AccountTransaction.objects.filter(external_id=external_id).exists():
        external_id = uuid4().hex

    new_tx = AccountTransaction.objects.create(
        client=client,
        external_id=external_id,
        description=description,
        date=tx_date,
        created_at=timezone.now(),
        original_amount=amount,
        paid_amount=Decimal('0'),
        status=status_value,
        payments=[],
    )

    _recalc_account_totals([client.id])
    client.refresh_from_db()

    return Response({
        'detail': 'Movimiento registrado correctamente',
        'transaction': _serialize_transactions([new_tx])[0],
        'client': _serialize_account_client(client),
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def account_transaction_delete(request, external_id):
    tx = get_object_or_404(AccountTransaction, external_id=external_id)
    client_id = tx.client_id
    tx.delete()
    _recalc_account_totals([client_id])
    return Response(status=status.HTTP_204_NO_CONTENT)

