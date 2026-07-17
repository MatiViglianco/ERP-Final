from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404

from .models import AccountClient, Employee, EmployeeAlias, EmployeeMovement
from .salary_services import (
    assign_employee_movement,
    create_employee,
    employee_payload,
    ensure_salary_category_employees,
    ensure_employee_alias,
    month_range,
    movement_payload,
    salaries_monthly_summary,
    salaries_summary,
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
        employee.save(update_fields=['active', 'updated_at'])
        return Response(employee_payload(employee))

    data = request.data or {}
    updated_fields = []
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if len(name) < 2:
            return Response({'detail': 'Nombre de empleado requerido'}, status=status.HTTP_400_BAD_REQUEST)
        employee.name = name
        updated_fields.append('name')
    if 'active' in data:
        employee.active = bool(data.get('active'))
        updated_fields.append('active')
    if 'notes' in data:
        employee.notes = data.get('notes') or ''
        updated_fields.append('notes')
    if 'account_client_id' in data:
        account_client_id = data.get('account_client_id')
        employee.account_client = AccountClient.objects.filter(pk=account_client_id).first() if account_client_id else None
        updated_fields.append('account_client')
    if updated_fields:
        employee.save(update_fields=updated_fields + ['updated_at'])
    if isinstance(data.get('aliases'), list):
        EmployeeAlias.objects.filter(employee=employee).delete()
        try:
            ensure_employee_alias(employee, employee.name)
            for alias in data.get('aliases'):
                ensure_employee_alias(employee, alias)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(employee_payload(employee))
