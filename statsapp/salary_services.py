from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from threading import Lock
from time import sleep

from django.db import OperationalError, transaction
from django.db.models import Max, Q, Sum
from django.utils import timezone

from .models import (
    AccountTransaction,
    BankTransaction,
    Employee,
    EmployeeAlias,
    EmployeeMovement,
    ExpenseEntry,
)
from .text_utils import normalize_search_text


SALARY_CATEGORY = 'SUELDOS'
_SYNC_LOCK = Lock()
_SYNC_RETRY_DELAYS = (0.05, 0.15, 0.3)


def ensure_employee_alias(employee, alias):
    alias_value = (alias or '').strip()
    normalized = normalize_search_text(alias_value)
    if not normalized:
        return None
    existing = EmployeeAlias.objects.filter(normalized_alias=normalized).first()
    if existing:
        if existing.employee_id != employee.id:
            raise ValueError(f'El alias "{alias_value}" ya esta asociado a otro empleado')
        return existing
    return EmployeeAlias.objects.create(employee=employee, alias=alias_value)


def month_range(year=None, month=None):
    today = timezone.localdate()
    year = int(year or today.year)
    month = int(month or today.month)
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def employee_payload(employee):
    aliases = [alias.alias for alias in employee.aliases.all().order_by('alias')]
    return {
        'id': str(employee.id),
        'name': employee.name,
        'active': employee.active,
        'account_client_id': str(employee.account_client_id) if employee.account_client_id else None,
        'account_client_name': employee.account_client.full_name if employee.account_client else '',
        'aliases': aliases,
        'notes': employee.notes or '',
    }


def movement_payload(movement):
    return {
        'id': str(movement.id),
        'employee_id': str(movement.employee_id),
        'employee_name': movement.employee.name,
        'source': movement.source,
        'source_label': movement.get_source_display(),
        'status': movement.status,
        'status_label': movement.get_status_display(),
        'date': movement.date.isoformat() if movement.date else None,
        'amount': float(movement.amount or 0),
        'description': movement.description or '',
        'matched_alias': movement.matched_alias or '',
        'bank_transaction_id': movement.bank_transaction_id,
        'expense_entry_id': str(movement.expense_entry_id) if movement.expense_entry_id else None,
        'account_transaction_id': movement.account_transaction.external_id if movement.account_transaction else None,
    }


def _bank_movement_description(tx):
    detail = ' - '.join(part.strip() for part in (tx.concept, tx.description) if part and part.strip())
    return f"{tx.batch.get_bank_display()}: {detail}"


def _latest_bank_dates():
    dates = {'santander': None, 'bancon': None}
    for row in (
        BankTransaction.objects
        .values('batch__bank')
        .annotate(latest_date=Max('date'))
    ):
        bank = row.get('batch__bank')
        if bank in dates and row.get('latest_date'):
            dates[bank] = row['latest_date'].isoformat()
    return dates


def _salary_source_diagnostics(start_date, end_date, limit=100):
    bank_period = BankTransaction.objects.filter(date__gte=start_date, date__lte=end_date)
    bank_candidates = (
        bank_period
        .filter(amount__lt=0, employee_movement__isnull=True)
        .filter(Q(concept__icontains='transfer') | Q(description__icontains='transfer'))
        .select_related('batch')
    )
    cash_period = ExpenseEntry.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        category__iexact=SALARY_CATEGORY,
    )
    cash_candidates = cash_period.filter(employee_movement__isnull=True)
    account_period = AccountTransaction.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        original_amount__gt=0,
    )
    account_candidates = (
        account_period
        .filter(employee_movement__isnull=True, client__employee_profile__isnull=True)
        .select_related('client')
    )

    items = []
    for tx in bank_candidates.order_by('-date', '-id')[:limit]:
        suggested_alias = (tx.description or tx.concept or '').strip()
        items.append({
            'source': EmployeeMovement.Source.BANK_TRANSFER,
            'source_label': EmployeeMovement.Source.BANK_TRANSFER.label,
            'source_id': str(tx.id),
            'date': tx.date.isoformat(),
            'amount': abs(float(tx.amount or 0)),
            'description': _bank_movement_description(tx),
            'suggested_name': suggested_alias,
            'suggested_alias': suggested_alias,
            'account_client_id': None,
        })
    for expense in cash_candidates.order_by('-date', '-created_at')[:limit]:
        suggested_alias = (expense.subcategory or expense.description or '').strip()
        items.append({
            'source': EmployeeMovement.Source.CASH_EXPENSE,
            'source_label': EmployeeMovement.Source.CASH_EXPENSE.label,
            'source_id': str(expense.id),
            'date': expense.date.isoformat(),
            'amount': float(expense.amount or 0),
            'description': f"{expense.method}: {expense.subcategory or expense.description}",
            'suggested_name': suggested_alias,
            'suggested_alias': suggested_alias,
            'account_client_id': None,
        })
    for tx in account_candidates.order_by('-date', '-id')[:limit]:
        client_name = tx.client.full_name if tx.client else ''
        items.append({
            'source': EmployeeMovement.Source.ACCOUNT_CURRENT,
            'source_label': EmployeeMovement.Source.ACCOUNT_CURRENT.label,
            'source_id': tx.external_id,
            'date': tx.date.isoformat() if tx.date else None,
            'amount': float(tx.original_amount or 0),
            'description': f"Cuenta corriente: {tx.description or tx.external_id}",
            'suggested_name': client_name,
            'suggested_alias': client_name,
            'account_client_id': str(tx.client_id),
        })
    items.sort(key=lambda item: (item.get('date') or '', item['source_id']), reverse=True)

    pending_counts = {
        EmployeeMovement.Source.BANK_TRANSFER: bank_candidates.count(),
        EmployeeMovement.Source.CASH_EXPENSE: cash_candidates.count(),
        EmployeeMovement.Source.ACCOUNT_CURRENT: account_candidates.count(),
    }
    return {
        'sources': {
            'active_employees': Employee.objects.filter(active=True).count(),
            'bank_transactions': bank_period.count(),
            'bank_outgoing': bank_period.filter(amount__lt=0).count(),
            'salary_cash_expenses': cash_period.count(),
            'account_current_transactions': account_period.count(),
            'latest_bank_dates': _latest_bank_dates(),
        },
        'unmatched': {
            'count': sum(pending_counts.values()),
            'counts': pending_counts,
            'items': items[:limit],
            'truncated': sum(pending_counts.values()) > limit,
        },
    }


def _employee_matchers():
    employees = list(
        Employee.objects
        .filter(active=True)
        .select_related('account_client')
        .prefetch_related('aliases')
        .order_by('name')
    )
    matchers = []
    for employee in employees:
        names = [employee.name]
        if employee.account_client:
            names.append(employee.account_client.full_name)
            names.append(employee.account_client.external_id)
        names.extend(alias.alias for alias in employee.aliases.all())
        for raw in names:
            normalized = normalize_search_text(raw)
            if len(normalized) < 3:
                continue
            matchers.append({
                'employee': employee,
                'alias': raw,
                'normalized': normalized,
            })
    matchers.sort(key=lambda item: len(item['normalized']), reverse=True)
    return matchers


def _match_employee(text, matchers):
    normalized_text = normalize_search_text(text)
    if not normalized_text:
        return None, ''
    padded = f" {normalized_text} "
    for item in matchers:
        alias = item['normalized']
        if f" {alias} " in padded or alias in normalized_text:
            return item['employee'], item['alias']
    return None, ''


def _movement_defaults(employee, source, movement_date, amount, description, alias):
    return {
        'employee': employee,
        'source': source,
        'status': EmployeeMovement.Status.AUTO,
        'date': movement_date,
        'amount': amount.copy_abs().quantize(Decimal('0.01')),
        'description': description[:500],
        'matched_alias': alias[:160],
    }


def _sync_employee_movements_once(start_date, end_date):
    matchers = _employee_matchers()
    created = 0
    updated = 0

    for tx in (
        BankTransaction.objects
        .select_related('batch')
        .filter(date__gte=start_date, date__lte=end_date, amount__lt=0)
    ):
        employee, alias = _match_employee(f"{tx.concept} {tx.description}", matchers)
        if not employee:
            continue
        defaults = _movement_defaults(
            employee=employee,
            source=EmployeeMovement.Source.BANK_TRANSFER,
            movement_date=tx.date,
            amount=Decimal(str(tx.amount or 0)),
            description=_bank_movement_description(tx),
            alias=alias,
        )
        _, was_created = EmployeeMovement.objects.update_or_create(
            bank_transaction=tx,
            defaults=defaults,
        )
        created += 1 if was_created else 0
        updated += 0 if was_created else 1

    salary_expenses = (
        ExpenseEntry.objects
        .filter(date__gte=start_date, date__lte=end_date)
        .filter(Q(category__iexact=SALARY_CATEGORY) | Q(method=ExpenseEntry.Method.CASH))
    )
    for expense in salary_expenses:
        employee, alias = _match_employee(
            f"{expense.category} {expense.subcategory} {expense.description}",
            matchers,
        )
        if not employee:
            continue
        defaults = _movement_defaults(
            employee=employee,
            source=EmployeeMovement.Source.CASH_EXPENSE,
            movement_date=expense.date,
            amount=expense.amount or Decimal('0'),
            description=f"{expense.method}: {expense.subcategory or expense.description}",
            alias=alias,
        )
        _, was_created = EmployeeMovement.objects.update_or_create(
            expense_entry=expense,
            defaults=defaults,
        )
        created += 1 if was_created else 0
        updated += 0 if was_created else 1

    account_transactions = (
        AccountTransaction.objects
        .select_related('client')
        .filter(date__gte=start_date, date__lte=end_date)
        .filter(original_amount__gt=0)
    )
    employee_by_client = {
        employee.account_client_id: employee
        for employee in Employee.objects.filter(active=True, account_client__isnull=False)
    }
    for tx in account_transactions:
        employee = employee_by_client.get(tx.client_id)
        alias = employee.account_client.full_name if employee and employee.account_client else ''
        if not employee:
            employee, alias = _match_employee(f"{tx.client.full_name if tx.client else ''} {tx.description}", matchers)
        if not employee:
            continue
        defaults = _movement_defaults(
            employee=employee,
            source=EmployeeMovement.Source.ACCOUNT_CURRENT,
            movement_date=tx.date,
            amount=tx.original_amount or Decimal('0'),
            description=f"Cuenta corriente: {tx.description or tx.external_id}",
            alias=alias,
        )
        _, was_created = EmployeeMovement.objects.update_or_create(
            account_transaction=tx,
            defaults=defaults,
        )
        created += 1 if was_created else 0
        updated += 0 if was_created else 1

    return {'created': created, 'updated': updated}


def sync_employee_movements(start_date, end_date):
    # A failed source must not leave the month partially synchronized.
    with transaction.atomic():
        return _sync_employee_movements_once(start_date, end_date)


def _sync_employee_movements_with_retry(start_date, end_date):
    for attempt in range(len(_SYNC_RETRY_DELAYS) + 1):
        try:
            return sync_employee_movements(start_date, end_date)
        except OperationalError:
            if attempt >= len(_SYNC_RETRY_DELAYS):
                raise
            sleep(_SYNC_RETRY_DELAYS[attempt])


def salaries_summary(start_date, end_date, sync=True):
    if sync:
        with _SYNC_LOCK:
            try:
                sync_result = _sync_employee_movements_with_retry(start_date, end_date)
            except OperationalError as exc:
                sync_result = {'created': 0, 'updated': 0, 'skipped': str(exc)}
    else:
        sync_result = {'created': 0, 'updated': 0}
    qs = (
        EmployeeMovement.objects
        .select_related('employee', 'bank_transaction', 'expense_entry', 'account_transaction')
        .filter(date__gte=start_date, date__lte=end_date)
    )
    totals = {
        EmployeeMovement.Source.BANK_TRANSFER: Decimal('0'),
        EmployeeMovement.Source.CASH_EXPENSE: Decimal('0'),
        EmployeeMovement.Source.ACCOUNT_CURRENT: Decimal('0'),
    }
    by_employee = defaultdict(lambda: {
        'employee_id': '',
        'employee_name': '',
        'bank_transfer': Decimal('0'),
        'cash_expense': Decimal('0'),
        'account_current': Decimal('0'),
        'total': Decimal('0'),
    })
    movements = []
    for movement in qs.order_by('-date', 'employee__name'):
        amount = movement.amount or Decimal('0')
        totals[movement.source] = totals.get(movement.source, Decimal('0')) + amount
        entry = by_employee[movement.employee_id]
        entry['employee_id'] = str(movement.employee_id)
        entry['employee_name'] = movement.employee.name
        entry[movement.source] += amount
        entry['total'] += amount
        movements.append(movement_payload(movement))

    employee_rows = []
    for entry in by_employee.values():
        employee_rows.append({
            'employee_id': entry['employee_id'],
            'employee_name': entry['employee_name'],
            'bank_transfer': float(entry['bank_transfer']),
            'cash_expense': float(entry['cash_expense']),
            'account_current': float(entry['account_current']),
            'total': float(entry['total']),
        })
    employee_rows.sort(key=lambda item: item['total'], reverse=True)

    total_amount = sum(totals.values(), Decimal('0'))
    return {
        'period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
        },
        'sync': sync_result,
        'totals': {
            'bank_transfer': float(totals[EmployeeMovement.Source.BANK_TRANSFER]),
            'cash_expense': float(totals[EmployeeMovement.Source.CASH_EXPENSE]),
            'account_current': float(totals[EmployeeMovement.Source.ACCOUNT_CURRENT]),
            'total': float(total_amount),
        },
        'employees': employee_rows,
        'movements': movements,
        **_salary_source_diagnostics(start_date, end_date),
    }


@transaction.atomic
def assign_employee_movement(employee, source, source_id, alias=''):
    if not employee.active:
        raise ValueError('El empleado seleccionado esta inactivo')

    matched_alias = (alias or '').strip()
    if source == EmployeeMovement.Source.BANK_TRANSFER:
        tx = BankTransaction.objects.select_related('batch').filter(pk=source_id, amount__lt=0).first()
        if not tx:
            raise ValueError('Transferencia bancaria no encontrada')
        matched_alias = matched_alias or (tx.description or tx.concept or '').strip()
        defaults = _movement_defaults(
            employee,
            source,
            tx.date,
            Decimal(str(tx.amount or 0)),
            _bank_movement_description(tx),
            matched_alias,
        )
        lookup = {'bank_transaction': tx}
    elif source == EmployeeMovement.Source.CASH_EXPENSE:
        expense = ExpenseEntry.objects.filter(pk=source_id).first()
        if not expense:
            raise ValueError('Gasto en efectivo no encontrado')
        matched_alias = matched_alias or (expense.subcategory or expense.description or '').strip()
        defaults = _movement_defaults(
            employee,
            source,
            expense.date,
            expense.amount or Decimal('0'),
            f"{expense.method}: {expense.subcategory or expense.description}",
            matched_alias,
        )
        lookup = {'expense_entry': expense}
    elif source == EmployeeMovement.Source.ACCOUNT_CURRENT:
        account_tx = AccountTransaction.objects.select_related('client').filter(external_id=source_id).first()
        if not account_tx:
            raise ValueError('Movimiento de cuenta corriente no encontrado')
        linked_employee = Employee.objects.filter(account_client=account_tx.client).exclude(pk=employee.pk).first()
        if linked_employee:
            raise ValueError(f'La cuenta corriente ya esta vinculada a {linked_employee.name}')
        if employee.account_client_id and employee.account_client_id != account_tx.client_id:
            raise ValueError('El empleado ya tiene otra cuenta corriente vinculada')
        if employee.account_client_id != account_tx.client_id:
            employee.account_client = account_tx.client
            employee.save(update_fields=['account_client', 'updated_at'])
        matched_alias = matched_alias or account_tx.client.full_name
        defaults = _movement_defaults(
            employee,
            source,
            account_tx.date,
            account_tx.original_amount or Decimal('0'),
            f"Cuenta corriente: {account_tx.description or account_tx.external_id}",
            matched_alias,
        )
        lookup = {'account_transaction': account_tx}
    else:
        raise ValueError('Origen de movimiento invalido')

    if matched_alias:
        ensure_employee_alias(employee, matched_alias)
    defaults['status'] = EmployeeMovement.Status.MANUAL
    movement, _ = EmployeeMovement.objects.update_or_create(defaults=defaults, **lookup)
    return movement


def create_employee(name, aliases=None, account_client=None, notes=''):
    cleaned_name = (name or '').strip()
    if len(cleaned_name) < 2:
        raise ValueError('Nombre de empleado requerido')
    employee, _ = Employee.objects.get_or_create(
        name=cleaned_name,
        defaults={'account_client': account_client, 'notes': notes or ''},
    )
    changed = []
    if account_client and employee.account_client_id != account_client.id:
        employee.account_client = account_client
        changed.append('account_client')
    if notes is not None and employee.notes != notes:
        employee.notes = notes
        changed.append('notes')
    if changed:
        employee.save(update_fields=changed + ['updated_at'])

    ensure_employee_alias(employee, cleaned_name)
    for alias in aliases or []:
        ensure_employee_alias(employee, alias)
    return employee
