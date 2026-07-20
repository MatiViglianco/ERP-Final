from datetime import date

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import AccountClient, Employee, EmployeeAlias, EmployeeMovement
from .salary_services import (
    aguinaldo_estimate,
    assign_employee_movement,
    confirm_account_deductions,
    create_employee,
    employee_payload,
    ensure_salary_category_employees,
    ensure_employee_alias,
    find_employee_by_document_identity,
    month_range,
    movement_payload,
    normalize_account_discount_percent,
    normalize_hire_date,
    save_aguinaldo_remunerations,
    salaries_monthly_summary,
    salaries_summary,
    normalize_employee_document,
    validate_account_client_assignment,
)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def salaries_dashboard(request):
    start, end = month_range(request.query_params.get('year'), request.query_params.get('month'))
    should_sync = (request.query_params.get('sync') or '1').strip().lower() not in {'0', 'false', 'no'}
    return Response(salaries_summary(start, end, sync=should_sync))


@api_view(['GET'])
@permission_classes([IsAdminUser])
def salaries_monthly(request):
    try:
        year = int(request.query_params.get('year'))
        if year < 2000 or year > 2100:
            raise ValueError
    except (TypeError, ValueError):
        return Response({'detail': 'Anio invalido'}, status=status.HTTP_400_BAD_REQUEST)
    should_sync = (request.query_params.get('sync') or '1').strip().lower() not in {'0', 'false', 'no'}
    return Response(salaries_monthly_summary(year, sync=should_sync))


@api_view(['GET', 'PUT'])
@permission_classes([IsAdminUser])
def salaries_aguinaldo(request):
    employee_id = request.query_params.get('employee_id')
    try:
        employee = Employee.objects.select_related('account_client').prefetch_related('aliases').filter(pk=employee_id).first()
    except (TypeError, ValueError, ValidationError):
        employee = None
    if not employee:
        return Response({'detail': 'Empleado invalido'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        year = int(request.query_params.get('year'))
        semester = int(request.query_params.get('semester'))
        if request.method == 'PUT':
            result = save_aguinaldo_remunerations(
                employee,
                year,
                semester,
                (request.data or {}).get('remunerations'),
                user=request.user,
            )
        else:
            result = aguinaldo_estimate(employee, year, semester)
    except (TypeError, ValueError) as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def salaries_account_deductions_confirm(request):
    data = request.data or {}
    try:
        employee = Employee.objects.filter(pk=data.get('employee_id')).first()
    except (TypeError, ValueError, ValidationError):
        employee = None
    if not employee:
        return Response({'detail': 'Empleado invalido'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        start, end = month_range(data.get('year'), data.get('month'))
        salaries_summary(start, end, sync=True)
        result = confirm_account_deductions(
            employee,
            start.year,
            start.month,
            user=request.user,
        )
    except (TypeError, ValueError) as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def employees_list(request):
    if request.method == 'GET':
        ensure_salary_category_employees()
        employees = Employee.objects.select_related('account_client').prefetch_related('aliases').order_by('name')
        return Response([employee_payload(employee) for employee in employees])

    data = request.data or {}
    account_client = None
    if data.get('account_client_id'):
        account_client = get_object_or_404(AccountClient, pk=data.get('account_client_id'))
    try:
        employee = create_employee(
            name=data.get('name'),
            aliases=data.get('aliases') if isinstance(data.get('aliases'), list) else [],
            account_client=account_client,
            notes=data.get('notes') or '',
            document_type=data.get('document_type') if 'document_type' in data else None,
            document_number=data.get('document_number') if 'document_number' in data else None,
            hire_date=data.get('hire_date'),
            account_discount_percent=data.get('account_discount_percent') if 'account_discount_percent' in data else None,
        )
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(employee_payload(employee), status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def salary_movement_assign(request):
    data = request.data or {}
    employee_id = data.get('employee_id')
    if not employee_id:
        return Response({'detail': 'Empleado requerido'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        employee = Employee.objects.filter(pk=employee_id).first()
    except (TypeError, ValueError, ValidationError):
        employee = None
    if not employee:
        return Response({'detail': 'Empleado invalido'}, status=status.HTTP_400_BAD_REQUEST)
    source = (data.get('source') or '').strip()
    if source not in EmployeeMovement.Source.values:
        return Response({'detail': 'Origen de movimiento invalido'}, status=status.HTTP_400_BAD_REQUEST)
    source_id = str(data.get('source_id') or '').strip()
    if not source_id:
        return Response({'detail': 'Movimiento requerido'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        movement = assign_employee_movement(
            employee=employee,
            source=source,
            source_id=source_id,
            alias=data.get('alias') or '',
        )
    except (TypeError, ValueError, ValidationError) as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(movement_payload(movement), status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAdminUser])
def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'DELETE':
        employee.active = False
        employee.termination_reason = Employee.TerminationReason.OTHER
        employee.termination_date = timezone.localdate()
        employee.save(update_fields=['active', 'termination_reason', 'termination_date', 'updated_at'])
        return Response(employee_payload(employee))

    data = request.data or {}
    try:
        with transaction.atomic():
            updated_fields = []
            if 'name' in data:
                name = (data.get('name') or '').strip()
                if len(name) < 2:
                    raise ValueError('Nombre de empleado requerido')
                if Employee.objects.filter(name__iexact=name).exclude(pk=employee.pk).exists():
                    raise ValueError('Ya existe otro empleado con ese nombre')
                employee.name = name
                updated_fields.append('name')

            if 'document_type' in data or 'document_number' in data:
                doc_type, doc_number = normalize_employee_document(
                    data.get('document_type', employee.document_type),
                    data.get('document_number', employee.document_number),
                )
                linked_document = find_employee_by_document_identity(
                    doc_type,
                    doc_number,
                    exclude_pk=employee.pk,
                ) if doc_number else None
                if linked_document:
                    raise ValueError(f'El documento ya esta vinculado a {linked_document.name}')
                employee.document_type = doc_type
                employee.document_number = doc_number
                updated_fields.extend(['document_type', 'document_number'])

            if 'active' in data:
                active_value = data.get('active')
                if not isinstance(active_value, bool):
                    raise ValueError('Estado de empleado invalido')
                employee.active = active_value
                updated_fields.append('active')
                if active_value:
                    employee.termination_reason = ''
                    employee.termination_date = None
                    updated_fields.extend(['termination_reason', 'termination_date'])
                else:
                    reason = (data.get('termination_reason') or '').strip()
                    if reason not in Employee.TerminationReason.values:
                        raise ValueError('Motivo de baja requerido')
                    try:
                        termination_date = date.fromisoformat(str(data.get('termination_date') or ''))
                    except ValueError as exc:
                        raise ValueError('Fecha de baja invalida') from exc
                    if termination_date > timezone.localdate():
                        raise ValueError('La fecha de baja no puede ser futura')
                    if employee.hire_date and termination_date < employee.hire_date:
                        raise ValueError('La fecha de baja no puede ser anterior al ingreso')
                    employee.termination_reason = reason
                    employee.termination_date = termination_date
                    updated_fields.extend(['termination_reason', 'termination_date'])

            if 'notes' in data:
                employee.notes = data.get('notes') or ''
                updated_fields.append('notes')
            if 'hire_date' in data:
                hire_date = normalize_hire_date(data.get('hire_date'))
                if employee.termination_date and hire_date and hire_date > employee.termination_date:
                    raise ValueError('La fecha de ingreso no puede ser posterior a la baja')
                employee.hire_date = hire_date
                updated_fields.append('hire_date')
            if 'account_discount_percent' in data:
                employee.account_discount_percent = normalize_account_discount_percent(data.get('account_discount_percent'))
                updated_fields.append('account_discount_percent')
            if 'account_client_id' in data:
                account_client_id = data.get('account_client_id')
                account_client = None
                if account_client_id:
                    account_client = AccountClient.objects.filter(pk=account_client_id).first()
                    if not account_client:
                        raise ValueError('Cliente de cuenta corriente invalido')
                validate_account_client_assignment(account_client, employee)
                employee.account_client = account_client
                updated_fields.append('account_client')

            if updated_fields:
                employee.save(update_fields=list(dict.fromkeys(updated_fields)) + ['updated_at'])
            if isinstance(data.get('aliases'), list):
                EmployeeAlias.objects.filter(employee=employee).delete()
                ensure_employee_alias(employee, employee.name)
                for alias in data.get('aliases'):
                    ensure_employee_alias(employee, alias)
    except (ValueError, IntegrityError) as exc:
        detail = str(exc) if isinstance(exc, ValueError) else 'No se pudo guardar el empleado por un dato duplicado'
        return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)
    return Response(employee_payload(employee))
