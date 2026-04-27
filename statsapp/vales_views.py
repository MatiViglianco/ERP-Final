from time import perf_counter
from decimal import Decimal

from django.db import connection
from django.db.models import CharField, Count, Max, Q
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AccountClient, AccountClientAlias, ValeImportBatch, ValeImportItem
from .vales_services import (
    alias_payload,
    client_payload,
    create_account_client,
    create_vale_batch,
    delete_vale_batch,
    ensure_alias,
    match_client_for_ocr,
    parse_client_date,
    process_ocr_uploads,
    resolve_vale_import_item,
    safe_int,
    serialize_batch,
    serialize_vale_item,
    suggest_clients,
    update_vale_batch_date,
)


def _latest_sync_iso():
    latest_batch = ValeImportBatch.objects.aggregate(last=Max('created_at')).get('last')
    latest_client = AccountClient.objects.aggregate(last=Max('updated_at')).get('last')
    latest = latest_batch or latest_client
    if latest_batch and latest_client:
        latest = max(latest_batch, latest_client)
    return latest.isoformat() if latest else None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def health_status(request):
    started = perf_counter()
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()
    latency_ms = round((perf_counter() - started) * 1000)
    return Response({
        'db': 'ok',
        'latencia_ms': latency_ms,
        'last_sync': _latest_sync_iso(),
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def clientes_list(request):
    if request.method == 'POST':
        display_name = (
            request.data.get('nombre')
            or request.data.get('name')
            or request.data.get('full_name')
            or ''
        ).strip()
        phone = (request.data.get('phone') or '').strip()
        external_id = (request.data.get('external_id') or '').strip()
        try:
            client, created = create_account_client(display_name, phone=phone, external_id=external_id)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(client_payload(client), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    page = max(safe_int(request.query_params.get('page', 1), 1), 1)
    page_size = min(max(safe_int(request.query_params.get('page_size', 500), 500), 1), 1000)
    search = (request.query_params.get('search') or '').strip()

    qs = AccountClient.objects.all().order_by('last_name', 'first_name')
    if search:
        for token in search.split():
            qs = qs.filter(Q(first_name__icontains=token) | Q(last_name__icontains=token) | Q(external_id__icontains=token))

    total = qs.count()
    offset = (page - 1) * page_size
    results = [client_payload(client) for client in qs[offset:offset + page_size]]
    response = Response(results)
    response['X-Total-Count'] = str(total)
    return response


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def clientes_aliases(request):
    if request.method == 'GET':
        aliases = AccountClientAlias.objects.select_related('client').order_by('alias')
        return Response([alias_payload(item) for item in aliases])

    client_id = request.data.get('cliente_id')
    alias_value = (request.data.get('alias') or '').strip()
    auto_detected = bool(request.data.get('auto_detected'))
    if not client_id or not alias_value:
        return Response({'detail': 'cliente_id y alias son obligatorios'}, status=status.HTTP_400_BAD_REQUEST)

    client = AccountClient.objects.filter(pk=client_id).first()
    if not client:
        return Response({'detail': 'Cliente no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    try:
        alias, created = ensure_alias(client, alias_value, auto_detected=auto_detected)
    except LookupError:
        return Response({'detail': 'Ese alias ya existe vinculado a otro cliente'}, status=status.HTTP_409_CONFLICT)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(alias_payload(alias), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def clientes_alias_detail(request, pk):
    alias = AccountClientAlias.objects.filter(pk=pk).first()
    if not alias:
        return Response(status=status.HTTP_404_NOT_FOUND)
    alias.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def clientes_sugerencias(request):
    alias_value = (request.query_params.get('alias') or '').strip()
    limit = min(max(safe_int(request.query_params.get('limit', 5), 5), 1), 20)
    if not alias_value:
        return Response([], status=status.HTTP_200_OK)
    return Response(suggest_clients(alias_value, limit=limit))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ocr_procesar(request):
    uploads = request.FILES.getlist('fotos') or request.FILES.getlist('files')
    if not uploads:
        return Response({'detail': 'Debes adjuntar al menos una foto en el campo "fotos"'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = process_ocr_uploads(uploads)
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except (TypeError, ValueError) as exc:
        return Response(
            {'detail': f'No se pudo interpretar la respuesta del OCR: {exc}'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    enriched = []
    for idx, vale in enumerate(result.get('vales') or [], start=1):
        match_result = match_client_for_ocr(vale.get('cliente_raw'), limit=4)
        client = match_result.get('client')
        source_index = safe_int(vale.get('source_index'), -1)
        source_filename = uploads[source_index].name if 0 <= source_index < len(uploads) else None
        enriched.append({
            'id': idx,
            **vale,
            'source_index': source_index if source_index >= 0 else None,
            'source_filename': source_filename,
            'cliente_id': str(client.id) if client else None,
            'cliente_nombre': client_payload(client)['nombre'] if client else None,
            'cliente_codigo': client_payload(client)['codigo'] if client else None,
            'cliente_match': match_result.get('match'),
            'sugerencias': match_result.get('suggestions') or [],
        })

    return Response({
        'fecha_detectada': result.get('fecha_detectada'),
        'vales': enriched,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def vales_cargar(request):
    batch_date = parse_client_date(request.data.get('fecha') or request.data.get('date'))
    vales = request.data.get('vales') or []
    source_filenames = request.data.get('source_filenames') or []
    if not batch_date:
        return Response({'detail': 'La fecha es obligatoria'}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(vales, list) or not vales:
        return Response({'detail': 'Debes enviar una lista de vales'}, status=status.HTTP_400_BAD_REQUEST)

    batch, warnings = create_vale_batch(
        user=request.user,
        batch_date=batch_date,
        vales_payload=vales,
        source_filenames=source_filenames if isinstance(source_filenames, list) else [],
    )
    account_items = batch.items.filter(transaction__isnull=False)
    account_total = sum((item.amount for item in account_items), start=Decimal('0'))
    pending_count = batch.items.filter(pending_review=True).count()
    current_year = timezone.localdate().year
    if batch.date and batch.date.year != current_year:
        warnings.append(
            f'La fecha del lote quedo en {batch.date.isoformat()}, fuera del ano operativo actual {current_year}. '
            'Si el vale era del ano actual, corregi la fecha antes de revisar cuentas.'
        )
    return Response({
        'lote_id': batch.lote_id,
        'importados': batch.items.count(),
        'cuenta_corriente_importados': account_items.count(),
        'pendientes': pending_count,
        'fecha': batch.date.isoformat(),
        'total': float(batch.total or 0),
        'cuenta_corriente_total': float(account_total or 0),
        'warnings': warnings,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def vales_lotes(request):
    page = max(safe_int(request.query_params.get('page', 1), 1), 1)
    page_size = min(max(safe_int(request.query_params.get('page_size', 20), 20), 1), 20)
    search = (request.query_params.get('q') or request.query_params.get('search') or '').strip()
    estado = (request.query_params.get('estado') or request.query_params.get('status') or '').strip().lower()
    fecha_desde = parse_client_date(request.query_params.get('fecha_desde') or request.query_params.get('date_from'))
    fecha_hasta = parse_client_date(request.query_params.get('fecha_hasta') or request.query_params.get('date_to'))

    qs = (
        ValeImportBatch.objects
        .select_related('uploaded_by')
        .annotate(source_text=Cast('source_filenames', output_field=CharField()))
    )

    if search:
        for token in search.split():
            qs = qs.filter(
                Q(lote_id__icontains=token)
                | Q(source_text__icontains=token)
                | Q(uploaded_by__username__icontains=token)
                | Q(uploaded_by__first_name__icontains=token)
                | Q(uploaded_by__last_name__icontains=token)
                | Q(items__client_raw__icontains=token)
                | Q(items__detail__icontains=token)
                | Q(items__client__first_name__icontains=token)
                | Q(items__client__last_name__icontains=token)
            )

    if fecha_desde:
        qs = qs.filter(date__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(date__lte=fecha_hasta)

    qs = (
        qs.distinct()
        .annotate(
            vales_count=Count('items', distinct=True),
            pendientes_count=Count('items', filter=Q(items__pending_review=True), distinct=True),
        )
    )

    if estado in {'pendiente', 'pendientes', 'pending'}:
        qs = qs.filter(pendientes_count__gt=0)
    elif estado in {'importado', 'importados', 'resuelto', 'resueltos', 'ok'}:
        qs = qs.filter(pendientes_count=0)

    qs = qs.order_by('-created_at')
    total = qs.count()
    offset = (page - 1) * page_size
    batches = qs[offset:offset + page_size]
    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max((total + page_size - 1) // page_size, 1),
        'results': [serialize_batch(batch) for batch in batches],
    })


@api_view(['GET', 'PATCH', 'DELETE', 'POST'])
@permission_classes([IsAuthenticated])
def vales_lote_detail(request, lote_id):
    batch = ValeImportBatch.objects.select_related('uploaded_by').filter(lote_id=lote_id).first()
    if not batch:
        return Response({'detail': 'Lote no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'DELETE':
        return Response(delete_vale_batch(batch=batch), status=status.HTTP_200_OK)

    if request.method == 'POST':
        action = (request.data.get('action') or request.data.get('_method') or '').strip().lower()
        if action in {'delete', 'eliminar', 'borrar'}:
            return Response(delete_vale_batch(batch=batch), status=status.HTTP_200_OK)
        return Response({'detail': 'Accion no soportada'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'PATCH':
        next_date = parse_client_date(request.data.get('fecha') or request.data.get('date'))
        if not next_date:
            return Response({'detail': 'La fecha es obligatoria'}, status=status.HTTP_400_BAD_REQUEST)
        batch = update_vale_batch_date(batch=batch, batch_date=next_date)

    return Response(serialize_batch(batch, include_items=True))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def vales_item_resolver(request, item_id):
    item = (
        ValeImportItem.objects
        .select_related('batch', 'client', 'transaction')
        .filter(pk=item_id)
        .first()
    )
    if not item:
        return Response({'detail': 'Vale no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    client_id = request.data.get('cliente_id')
    if not client_id:
        return Response({'detail': 'cliente_id es obligatorio'}, status=status.HTTP_400_BAD_REQUEST)

    client = AccountClient.objects.filter(pk=client_id).first()
    if not client:
        return Response({'detail': 'Cliente no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    create_alias = request.data.get('crear_alias', True)
    if isinstance(create_alias, str):
        create_alias = create_alias.strip().lower() not in {'0', 'false', 'no'}

    item, warnings = resolve_vale_import_item(
        item=item,
        client=client,
        user=request.user,
        create_alias=bool(create_alias),
    )
    return Response({
        'item': serialize_vale_item(item),
        'lote_id': item.batch.lote_id,
        'pendientes_count': item.batch.items.filter(pending_review=True).count(),
        'warnings': warnings,
    })
