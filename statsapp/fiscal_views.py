from datetime import date, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from .getnet_services import GetnetImportError, import_getnet_csv, terminal_payload
from .fiscal_services import (
    FiscalError,
    account_invoice_preview,
    authorize_invoice,
    billing_summary,
    create_account_invoice,
    create_manual_payment,
    invoice_payload,
    payment_payload,
    process_getnet_webhook,
)
from .models import AccountClient, Branch, GetnetTerminal, Invoice, Payment


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _month_range(request):
    today = timezone.localdate()
    year = int(request.query_params.get('year') or today.year)
    month = int(request.query_params.get('month') or today.month)
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


@api_view(['GET'])
@permission_classes([IsAdminUser])
def billing_dashboard(request):
    start = _parse_date(request.query_params.get('start_date'))
    end = _parse_date(request.query_params.get('end_date'))
    if not start or not end:
        start, end = _month_range(request)
    terminal_id = _positive_int(request.query_params.get('terminal_id'))
    return Response(billing_summary(start, end, getnet_terminal_id=terminal_id))


@api_view(['GET'])
@permission_classes([IsAdminUser])
def invoices_list(request):
    start = _parse_date(request.query_params.get('start_date'))
    end = _parse_date(request.query_params.get('end_date'))
    if not start or not end:
        start, end = _month_range(request)
    qs = (
        Invoice.objects
        .select_related('client', 'branch')
        .prefetch_related('lines')
        .filter(issue_date__gte=start, issue_date__lte=end)
    )
    status_filter = (request.query_params.get('status') or '').strip()
    if status_filter:
        qs = qs.filter(status=status_filter)
    source_filter = (request.query_params.get('source') or '').strip()
    if source_filter:
        qs = qs.filter(source=source_filter)
    return Response([invoice_payload(invoice, include_lines=False) for invoice in qs[:500]])


@api_view(['GET'])
@permission_classes([IsAdminUser])
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('client', 'branch').prefetch_related('lines'),
        pk=pk,
    )
    return Response(invoice_payload(invoice))


@api_view(['POST'])
@permission_classes([IsAdminUser])
def invoice_authorize(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    try:
        invoice = authorize_invoice(invoice)
    except FiscalError as exc:
        invoice.status = Invoice.Status.ERROR
        invoice.error_message = str(exc)
        invoice.save(update_fields=['status', 'error_message', 'updated_at'])
        return Response({'detail': str(exc), 'invoice': invoice_payload(invoice)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(invoice_payload(invoice))


@api_view(['GET'])
@permission_classes([IsAdminUser])
def account_invoice_preview_view(request, pk):
    client = get_object_or_404(AccountClient, pk=pk)
    branch_value = request.query_params.get('branch_id')
    branch_id = _positive_int(branch_value)
    if branch_value not in (None, '') and not branch_id:
        return Response({'detail': 'Sucursal invalida'}, status=status.HTTP_400_BAD_REQUEST)
    branch = get_object_or_404(Branch, pk=branch_id, active=True) if branch_id else None
    return Response(account_invoice_preview(client, branch=branch))


@api_view(['POST'])
@permission_classes([IsAdminUser])
def account_invoice_create_view(request, pk):
    client = get_object_or_404(AccountClient, pk=pk)
    transaction_ids = request.data.get('transaction_ids') or []
    authorize = bool(request.data.get('authorize', True))
    branch_value = request.data.get('branch_id')
    branch_id = _positive_int(branch_value)
    if branch_value not in (None, '') and not branch_id:
        return Response({'detail': 'Sucursal invalida'}, status=status.HTTP_400_BAD_REQUEST)
    branch = get_object_or_404(Branch, pk=branch_id, active=True) if branch_id else None
    try:
        invoice = create_account_invoice(
            client,
            transaction_ids,
            authorize=authorize,
            created_by=request.user,
            branch=branch,
        )
    except FiscalError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(invoice_payload(invoice), status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def payments_list(request):
    if request.method == 'POST':
        data = request.data or {}
        client = None
        invoice = None
        if data.get('client_id'):
            client = get_object_or_404(AccountClient, pk=data.get('client_id'))
        if data.get('invoice_id'):
            invoice = get_object_or_404(Invoice, pk=data.get('invoice_id'))
            client = client or invoice.client
        try:
            payment = create_manual_payment(
                source=data.get('source'),
                amount=data.get('amount'),
                payment_date=_parse_date(data.get('date')) or timezone.localdate(),
                client=client,
                invoice=invoice,
                external_id=(data.get('external_id') or '').strip(),
                meta={'created_by': request.user.username},
            )
        except FiscalError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payment_payload(payment), status=status.HTTP_201_CREATED)

    start = _parse_date(request.query_params.get('start_date'))
    end = _parse_date(request.query_params.get('end_date'))
    if not start or not end:
        start, end = _month_range(request)
    qs = Payment.objects.select_related('client', 'invoice', 'terminal', 'branch').filter(
        date__gte=start,
        date__lte=end,
    )
    source_filter = (request.query_params.get('source') or '').strip()
    if source_filter:
        qs = qs.filter(source=source_filter)
    terminal_id = _positive_int(request.query_params.get('terminal_id'))
    if terminal_id:
        qs = qs.filter(terminal_id=terminal_id)
    return Response([payment_payload(payment) for payment in qs[:500]])


@api_view(['POST'])
@permission_classes([IsAdminUser])
def getnet_import(request):
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return Response({'detail': 'Falta el archivo CSV de Getnet'}, status=status.HTTP_400_BAD_REQUEST)
    if uploaded_file.size > 20 * 1024 * 1024:
        return Response({'detail': 'El archivo Getnet supera el limite de 20 MB'}, status=status.HTTP_400_BAD_REQUEST)

    branch = None
    branch_id = _positive_int(request.data.get('branch_id'))
    if branch_id:
        branch = get_object_or_404(Branch, pk=branch_id, active=True)
    try:
        result = import_getnet_csv(uploaded_file, default_branch=branch)
    except GetnetImportError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def getnet_terminals(request):
    qs = GetnetTerminal.objects.select_related('branch').order_by('code')
    return Response([terminal_payload(terminal) for terminal in qs])


@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def getnet_terminal_detail(request, pk):
    terminal = get_object_or_404(GetnetTerminal.objects.select_related('branch'), pk=pk)
    branch_id = _positive_int(request.data.get('branch_id'))
    branch = get_object_or_404(Branch, pk=branch_id, active=True) if branch_id else None
    terminal.branch = branch
    terminal.save(update_fields=['branch', 'updated_at'])
    Payment.objects.filter(terminal=terminal).update(branch=branch)
    terminal.refresh_from_db()
    return Response(terminal_payload(terminal))


@api_view(['POST'])
@permission_classes([AllowAny])
def getnet_webhook(request):
    signature = (
        request.headers.get('X-Getnet-Signature')
        or request.headers.get('X-Hub-Signature-256')
        or ''
    )
    try:
        result = process_getnet_webhook(request.body, signature=signature)
    except FiscalError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    payment = result.get('payment')
    return Response({
        'detail': 'Evento procesado',
        'duplicate': result.get('duplicate', False),
        'event_id': result['event'].event_id,
        'payment': payment_payload(payment) if payment else None,
    })
