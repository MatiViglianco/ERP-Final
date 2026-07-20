from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from threading import Lock
from time import sleep

from django.db import OperationalError, transaction
from django.db.models import F, Max, Q, Sum
from django.utils import timezone

from .models import (
    AccountClient,
    AccountTransaction,
    BankTransaction,
    Branch,
    Employee,
    EmployeeAlias,
    EmployeeMovement,
    EmployeeRemuneration,
    ExpenseEntry,
    ExpenseSubcategory,
)
from .text_utils import normalize_search_text


SALARY_CATEGORY = 'SUELDOS'
_SYNC_LOCK = Lock()
_SYNC_RETRY_DELAYS = (0.05, 0.15, 0.3)
MONTH_LABELS = (
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
)


def normalize_employee_document(document_type, document_number):
    doc_type = (document_type or '').strip().lower()
    number = re.sub(r'\D', '', str(document_number or ''))
    if not doc_type and not number:
        return '', None
    if doc_type not in Employee.DocumentType.values:
        raise ValueError('Tipo de documento invalido')
    if not number:
        raise ValueError('Numero de documento requerido')
    if doc_type == Employee.DocumentType.DNI:
        if len(number) not in {7, 8}:
            raise ValueError('El DNI debe tener 7 u 8 digitos')
    elif len(number) != 11:
        raise ValueError('El CUIL/CUIT debe tener 11 digitos')
    elif not _valid_cuil_cuit(number):
        raise ValueError('El CUIL/CUIT no es valido')
    return doc_type, number


def normalize_hire_date(value):
    if value is None or value == '':
        return None
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError('Fecha de ingreso invalida') from exc
    if parsed > timezone.localdate():
        raise ValueError('La fecha de ingreso no puede ser futura')
    return parsed


def normalize_account_discount_percent(value):
    if value is None or value == '':
        return Decimal('0.00')
    try:
        percent = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Porcentaje de descuento invalido') from exc
    if percent < 0 or percent > 100:
        raise ValueError('El descuento debe estar entre 0 y 100')
    return percent


def _valid_cuil_cuit(number):
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    remainder = sum(int(digit) * weight for digit, weight in zip(number[:10], weights)) % 11
    check_digit = 11 - remainder
    if check_digit == 11:
        check_digit = 0
    elif check_digit == 10:
        check_digit = 9
    return check_digit == int(number[-1])


def _document_identity_key(document_type, document_number):
    number = re.sub(r'\D', '', str(document_number or ''))
    if document_type == Employee.DocumentType.DNI and len(number) in {7, 8}:
        return number.lstrip('0') or '0'
    if document_type == Employee.DocumentType.CUIL_CUIT and len(number) == 11:
        return number[2:10].lstrip('0') or '0'
    return ''


def find_employee_by_document_identity(document_type, document_number, exclude_pk=None, exclude_name=''):
    identity_key = _document_identity_key(document_type, document_number)
    if not identity_key:
        return None
    employees = Employee.objects.exclude(document_number__isnull=True).exclude(document_number='')
    if exclude_pk:
        employees = employees.exclude(pk=exclude_pk)
    if exclude_name:
        employees = employees.exclude(name__iexact=exclude_name)
    for employee in employees.only('id', 'name', 'document_type', 'document_number'):
        if _document_identity_key(employee.document_type, employee.document_number) == identity_key:
            return employee
    return None


def validate_account_client_assignment(account_client, employee=None):
    if not account_client:
        return
    linked = Employee.objects.filter(account_client=account_client)
    if employee:
        linked = linked.exclude(pk=employee.pk)
    linked_employee = linked.first()
    if linked_employee:
        raise ValueError(f'La cuenta corriente ya esta vinculada a {linked_employee.name}')


def ensure_employee_alias(employee, alias):
    alias_value = (alias or '').strip()
    normalized = normalize_search_text(alias_value)
    if not normalized:
        return None
    alias_obj, _ = EmployeeAlias.objects.get_or_create(
        normalized_alias=normalized,
        defaults={'employee': employee, 'alias': alias_value},
    )
    if alias_obj.employee_id != employee.id:
        raise ValueError(f'El alias "{alias_value}" ya esta asociado a otro empleado')
    return alias_obj


def ensure_salary_category_employees():
    created = 0
    configured = 0
    names = (
        ExpenseSubcategory.objects
        .filter(category__name__iexact=SALARY_CATEGORY)
        .exclude(name='')
        .order_by('name')
        .values_list('name', flat=True)
    )
    for raw_name in names:
        name = (raw_name or '').strip()
        normalized = normalize_search_text(name)
        if len(normalized) < 2:
            continue
        configured += 1
        if EmployeeAlias.objects.filter(normalized_alias=normalized).exists():
            continue
        employee = Employee.objects.filter(name__iexact=name).first()
        if not employee:
            employee, was_created = Employee.objects.get_or_create(
                name=name,
                defaults={
                    'branch': default_employee_branch(),
                    'notes': 'Sincronizado desde Gastos / SUELDOS',
                },
            )
            created += 1 if was_created else 0
        elif not employee.branch_id:
            employee.branch = default_employee_branch()
            employee.save(update_fields=['branch', 'updated_at'])
        ensure_employee_alias(employee, name)
    return {'configured': configured, 'created': created}


def default_employee_branch():
    return (
        Branch.objects.filter(slug='sucursal-primaria', active=True).first()
        or Branch.objects.filter(active=True).order_by('name', 'id').first()
    )


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
        'branch_id': employee.branch_id,
        'branch_name': employee.branch.name if employee.branch else '',
        'document_type': employee.document_type or '',
        'document_type_label': employee.get_document_type_display() if employee.document_type else '',
        'document_number': employee.document_number or '',
        'account_client_id': str(employee.account_client_id) if employee.account_client_id else None,
        'account_client_name': employee.account_client.full_name if employee.account_client else '',
        'account_discount_percent': float(employee.account_discount_percent or 0),
        'hire_date': employee.hire_date.isoformat() if employee.hire_date else None,
        'aliases': aliases,
        'termination_reason': employee.termination_reason or '',
        'termination_reason_label': employee.get_termination_reason_display() if employee.termination_reason else '',
        'termination_date': employee.termination_date.isoformat() if employee.termination_date else None,
        'notes': employee.notes or '',
    }


def movement_payload(movement):
    payload = {
        'id': str(movement.id),
        'employee_id': str(movement.employee_id),
        'employee_name': movement.employee.name,
        'branch_id': movement.branch_id,
        'branch_name': movement.branch.name if movement.branch else '',
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
    if movement.source == EmployeeMovement.Source.ACCOUNT_CURRENT:
        payload['account_deduction'] = {
            'gross_amount': float(movement.gross_amount if movement.gross_amount is not None else movement.amount or 0),
            'discount_percent': float(movement.discount_percent or 0),
            'discount_amount': float(movement.discount_amount or 0),
            'net_amount': float(movement.amount or 0),
            'status': movement.deduction_status or EmployeeMovement.DeductionStatus.PENDING,
            'status_label': movement.get_deduction_status_display() if movement.deduction_status else EmployeeMovement.DeductionStatus.PENDING.label,
            'confirmed_at': movement.deduction_confirmed_at.isoformat() if movement.deduction_confirmed_at else None,
            'branch_name': movement.account_transaction.branch.name if movement.account_transaction and movement.account_transaction.branch else '',
        }
    return payload


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


def _salary_source_diagnostics(start_date, end_date, branch_id=None, limit=100):
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
    if branch_id:
        cash_period = cash_period.filter(branch_id=branch_id)
    cash_candidates = cash_period.filter(employee_movement__isnull=True)
    account_period = AccountTransaction.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        original_amount__gt=0,
    )
    if branch_id:
        account_period = account_period.filter(branch_id=branch_id)
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
            'description': f"Cuenta corriente - {client_name}: {tx.description or tx.external_id}",
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
            'active_employees': Employee.objects.filter(active=True, **({'branch_id': branch_id} if branch_id else {})).count(),
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
        document_number = employee.document_number or ''
        document_identity = _document_identity_key(employee.document_type, document_number)
        for raw in names:
            normalized = normalize_search_text(raw)
            if len(normalized) < 3:
                continue
            matchers.append({
                'employee': employee,
                'alias': raw,
                'normalized': normalized,
                'document_number': document_number,
                'document_identity': document_identity,
            })
    matchers.sort(key=lambda item: len(item['normalized']), reverse=True)
    return matchers


def _document_identities_in_text(text):
    identities = set()
    pattern = r'(?<!\d)(?:\d[.\-\s]?){6,10}\d(?!\d)'
    for match in re.finditer(pattern, str(text or '')):
        number = re.sub(r'\D', '', match.group(0))
        if len(number) in {7, 8}:
            identities.add(number.lstrip('0') or '0')
        elif len(number) == 11 and _valid_cuil_cuit(number):
            identities.add(number[2:10].lstrip('0') or '0')
    return identities


def _match_employee(text, matchers, match_documents=False):
    if match_documents:
        text_identities = _document_identities_in_text(text)
        document_matches = {}
        for item in matchers:
            identity = item.get('document_identity') or ''
            if not identity or identity not in text_identities:
                continue
            employee = item['employee']
            document_matches[str(employee.pk)] = (
                employee,
                f"{employee.get_document_type_display()} {item['document_number']}",
            )
        if len(document_matches) == 1:
            return next(iter(document_matches.values()))
    normalized_text = normalize_search_text(text)
    if not normalized_text:
        return None, ''
    padded = f" {normalized_text} "
    for item in matchers:
        alias = item['normalized']
        if f" {alias} " in padded or alias in normalized_text:
            return item['employee'], item['alias']
    return None, ''


def _movement_branch(employee, existing=None):
    if existing and existing.branch_id:
        return existing.branch
    return employee.branch or default_employee_branch()


def _movement_defaults(employee, source, movement_date, amount, description, alias, existing=None):
    return {
        'employee': employee,
        'branch': _movement_branch(employee, existing),
        'source': source,
        'status': EmployeeMovement.Status.AUTO,
        'date': movement_date,
        'amount': amount.copy_abs().quantize(Decimal('0.01')),
        'description': description[:500],
        'matched_alias': alias[:160],
    }


def _account_deduction_values(account_transaction, discount_percent):
    percent = normalize_account_discount_percent(discount_percent)
    gross_amount = account_transaction.remaining_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    original_amount = (account_transaction.original_amount or Decimal('0')).quantize(
        Decimal('0.01'),
        rounding=ROUND_HALF_UP,
    )
    discount_amount = (original_amount * percent / Decimal('100')).quantize(
        Decimal('0.01'),
        rounding=ROUND_HALF_UP,
    )
    discount_amount = min(discount_amount, gross_amount)
    net_amount = (gross_amount - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return gross_amount, percent, discount_amount, net_amount


def _account_movement_defaults(employee, account_transaction, alias, status=EmployeeMovement.Status.AUTO, existing=None):
    gross_amount, percent, discount_amount, net_amount = _account_deduction_values(
        account_transaction,
        employee.account_discount_percent,
    )
    defaults = _movement_defaults(
        employee=employee,
        source=EmployeeMovement.Source.ACCOUNT_CURRENT,
        movement_date=account_transaction.date,
        amount=net_amount,
        description=f"Cuenta corriente: {account_transaction.description or account_transaction.external_id}",
        alias=alias,
        existing=existing,
    )
    defaults.update({
        'status': status,
        'gross_amount': gross_amount,
        'discount_percent': percent,
        'discount_amount': discount_amount,
        'deduction_status': EmployeeMovement.DeductionStatus.PENDING,
        'deduction_confirmed_by': None,
        'deduction_confirmed_at': None,
    })
    return defaults


def _sync_employee_movements_once(start_date, end_date):
    matchers = _employee_matchers()
    created = 0
    updated = 0

    for tx in (
        BankTransaction.objects
        .select_related('batch')
        .filter(date__gte=start_date, date__lte=end_date, amount__lt=0)
    ):
        employee, alias = _match_employee(
            f"{tx.concept} {tx.description} {tx.raw_details}",
            matchers,
            match_documents=True,
        )
        if not employee:
            continue
        existing = EmployeeMovement.objects.select_related('branch').filter(bank_transaction=tx).first()
        defaults = _movement_defaults(
            employee=employee,
            source=EmployeeMovement.Source.BANK_TRANSFER,
            movement_date=tx.date,
            amount=Decimal(str(tx.amount or 0)),
            description=_bank_movement_description(tx),
            alias=alias,
            existing=existing,
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
        existing = EmployeeMovement.objects.select_related('branch').filter(expense_entry=expense).first()
        defaults = _movement_defaults(
            employee=employee,
            source=EmployeeMovement.Source.CASH_EXPENSE,
            movement_date=expense.date,
            amount=expense.amount or Decimal('0'),
            description=f"{expense.method}: {expense.subcategory or expense.description}",
            alias=alias,
            existing=existing,
        )
        _, was_created = EmployeeMovement.objects.update_or_create(
            expense_entry=expense,
            defaults=defaults,
        )
        created += 1 if was_created else 0
        updated += 0 if was_created else 1

    pending_account_movements = (
        EmployeeMovement.objects
        .select_related('account_transaction')
        .filter(
            source=EmployeeMovement.Source.ACCOUNT_CURRENT,
            date__gte=start_date,
            date__lte=end_date,
        )
        .exclude(deduction_status=EmployeeMovement.DeductionStatus.CONFIRMED)
    )
    for movement in pending_account_movements:
        if not movement.account_transaction or movement.account_transaction.remaining_amount <= Decimal('0'):
            movement.delete()

    account_transactions = (
        AccountTransaction.objects
        .select_related('client', 'branch')
        .filter(date__gte=start_date, date__lte=end_date)
        .filter(original_amount__gt=F('paid_amount'))
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
        existing = EmployeeMovement.objects.select_related('branch').filter(account_transaction=tx).first()
        if existing and existing.deduction_status == EmployeeMovement.DeductionStatus.CONFIRMED:
            continue
        defaults = _account_movement_defaults(employee, tx, alias, existing=existing)
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


def salaries_summary(start_date, end_date, sync=True, branch_id=None):
    employee_sync = ensure_salary_category_employees()
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
        .select_related('employee__branch', 'branch', 'bank_transaction', 'expense_entry', 'account_transaction__branch')
        .filter(
            date__gte=start_date,
            date__lte=end_date,
            employee__active=True,
        )
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
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
    account_deductions = {
        'gross_amount': Decimal('0'),
        'discount_amount': Decimal('0'),
        'net_amount': Decimal('0'),
        'pending_gross_amount': Decimal('0'),
        'pending_discount_amount': Decimal('0'),
        'pending_net_amount': Decimal('0'),
        'confirmed_net_amount': Decimal('0'),
    }
    deductions_by_employee = defaultdict(lambda: {
        'employee_id': '',
        'employee_name': '',
        'gross_amount': Decimal('0'),
        'discount_amount': Decimal('0'),
        'net_amount': Decimal('0'),
        'pending_gross_amount': Decimal('0'),
        'pending_discount_amount': Decimal('0'),
        'pending_net_amount': Decimal('0'),
        'confirmed_net_amount': Decimal('0'),
        'pending_count': 0,
        'confirmed_count': 0,
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
        if movement.source == EmployeeMovement.Source.ACCOUNT_CURRENT:
            gross_amount = movement.gross_amount if movement.gross_amount is not None else amount
            discount_amount = movement.discount_amount or Decimal('0')
            deduction_status = movement.deduction_status or EmployeeMovement.DeductionStatus.PENDING
            account_deductions['gross_amount'] += gross_amount
            account_deductions['discount_amount'] += discount_amount
            account_deductions['net_amount'] += amount
            deduction_entry = deductions_by_employee[movement.employee_id]
            deduction_entry['employee_id'] = str(movement.employee_id)
            deduction_entry['employee_name'] = movement.employee.name
            deduction_entry['gross_amount'] += gross_amount
            deduction_entry['discount_amount'] += discount_amount
            deduction_entry['net_amount'] += amount
            if deduction_status == EmployeeMovement.DeductionStatus.CONFIRMED:
                account_deductions['confirmed_net_amount'] += amount
                deduction_entry['confirmed_net_amount'] += amount
                deduction_entry['confirmed_count'] += 1
            else:
                account_deductions['pending_gross_amount'] += gross_amount
                account_deductions['pending_discount_amount'] += discount_amount
                account_deductions['pending_net_amount'] += amount
                deduction_entry['pending_gross_amount'] += gross_amount
                deduction_entry['pending_discount_amount'] += discount_amount
                deduction_entry['pending_net_amount'] += amount
                deduction_entry['pending_count'] += 1
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

    deduction_rows = [{
        **entry,
        'gross_amount': float(entry['gross_amount']),
        'discount_amount': float(entry['discount_amount']),
        'net_amount': float(entry['net_amount']),
        'pending_gross_amount': float(entry['pending_gross_amount']),
        'pending_discount_amount': float(entry['pending_discount_amount']),
        'pending_net_amount': float(entry['pending_net_amount']),
        'confirmed_net_amount': float(entry['confirmed_net_amount']),
    } for entry in deductions_by_employee.values()]
    deduction_rows.sort(key=lambda item: (item['pending_count'] == 0, -item['pending_net_amount'], item['employee_name']))

    total_amount = sum(totals.values(), Decimal('0'))
    return {
        'period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
        },
        'branch_id': branch_id,
        'sync': sync_result,
        'employee_sync': employee_sync,
        'totals': {
            'bank_transfer': float(totals[EmployeeMovement.Source.BANK_TRANSFER]),
            'cash_expense': float(totals[EmployeeMovement.Source.CASH_EXPENSE]),
            'account_current': float(totals[EmployeeMovement.Source.ACCOUNT_CURRENT]),
            'total': float(total_amount),
        },
        'employees': employee_rows,
        'movements': movements,
        'account_deductions': {
            'gross_amount': float(account_deductions['gross_amount']),
            'discount_amount': float(account_deductions['discount_amount']),
            'net_amount': float(account_deductions['net_amount']),
            'pending_gross_amount': float(account_deductions['pending_gross_amount']),
            'pending_discount_amount': float(account_deductions['pending_discount_amount']),
            'pending_net_amount': float(account_deductions['pending_net_amount']),
            'confirmed_net_amount': float(account_deductions['confirmed_net_amount']),
            'employees': deduction_rows,
        },
        **_salary_source_diagnostics(start_date, end_date, branch_id=branch_id),
    }


def salaries_monthly_summary(year, sync=True, branch_id=None):
    selected_year = int(year)
    start_date = date(selected_year, 1, 1)
    end_date = date(selected_year, 12, 31)
    employee_sync = ensure_salary_category_employees()
    if sync:
        with _SYNC_LOCK:
            try:
                sync_result = _sync_employee_movements_with_retry(start_date, end_date)
            except OperationalError as exc:
                sync_result = {'created': 0, 'updated': 0, 'skipped': str(exc)}
    else:
        sync_result = {'created': 0, 'updated': 0}

    by_employee = defaultdict(lambda: {
        'employee_id': '',
        'employee_name': '',
        'bank_transfer': Decimal('0'),
        'cash_expense': Decimal('0'),
        'account_current': Decimal('0'),
        'total': Decimal('0'),
        'months': defaultdict(lambda: {
            'bank_transfer': Decimal('0'),
            'cash_expense': Decimal('0'),
            'account_current': Decimal('0'),
            'total': Decimal('0'),
        }),
    })
    movements = (
        EmployeeMovement.objects
        .select_related('employee__branch', 'branch')
        .filter(
            date__gte=start_date,
            date__lte=end_date,
            employee__active=True,
        )
        .order_by('employee__name', 'date')
    )
    if branch_id:
        movements = movements.filter(branch_id=branch_id)
    for movement in movements:
        amount = movement.amount or Decimal('0')
        entry = by_employee[movement.employee_id]
        entry['employee_id'] = str(movement.employee_id)
        entry['employee_name'] = movement.employee.name
        entry[movement.source] += amount
        entry['total'] += amount
        month_entry = entry['months'][movement.date.month]
        month_entry[movement.source] += amount
        month_entry['total'] += amount

    employee_rows = []
    for entry in by_employee.values():
        employee_rows.append({
            'employee_id': entry['employee_id'],
            'employee_name': entry['employee_name'],
            'bank_transfer': float(entry['bank_transfer']),
            'cash_expense': float(entry['cash_expense']),
            'account_current': float(entry['account_current']),
            'total': float(entry['total']),
            'months': [
                {
                    'month': month_number,
                    'bank_transfer': float(entry['months'][month_number]['bank_transfer']),
                    'cash_expense': float(entry['months'][month_number]['cash_expense']),
                    'account_current': float(entry['months'][month_number]['account_current']),
                    'total': float(entry['months'][month_number]['total']),
                }
                for month_number in range(1, 13)
            ],
        })
    employee_rows.sort(key=lambda item: item['total'], reverse=True)
    return {
        'year': selected_year,
        'branch_id': branch_id,
        'sync': sync_result,
        'employee_sync': employee_sync,
        'employees': employee_rows,
    }


def _semester_bounds(year, semester):
    try:
        selected_year = int(year)
    except (TypeError, ValueError) as exc:
        raise ValueError('Anio invalido') from exc
    try:
        selected_semester = int(semester)
    except (TypeError, ValueError) as exc:
        raise ValueError('Semestre invalido') from exc
    if selected_year < 2000 or selected_year > 2100:
        raise ValueError('Anio invalido')
    if selected_semester not in {1, 2}:
        raise ValueError('Semestre invalido')
    if selected_semester == 1:
        return selected_year, selected_semester, date(selected_year, 1, 1), date(selected_year, 6, 30), range(1, 7)
    return selected_year, selected_semester, date(selected_year, 7, 1), date(selected_year, 12, 31), range(7, 13)


def aguinaldo_estimate(employee, year, semester):
    selected_year, selected_semester, start_date, end_date, semester_months = _semester_bounds(year, semester)
    detected = {
        row['date__month']: row['total'] or Decimal('0')
        for row in (
            EmployeeMovement.objects
            .filter(employee=employee, date__gte=start_date, date__lte=end_date)
            .values('date__month')
            .annotate(total=Sum('amount'))
        )
    }
    confirmed = {
        row.month: row
        for row in EmployeeRemuneration.objects.filter(
            employee=employee,
            year=selected_year,
            month__in=semester_months,
        ).select_related('confirmed_by')
    }

    months = []
    effective_by_month = {}
    for month_number in semester_months:
        remuneration = confirmed.get(month_number)
        detected_amount = detected.get(month_number, Decimal('0'))
        effective_amount = remuneration.amount if remuneration else detected_amount
        effective_by_month[month_number] = effective_amount
        months.append({
            'month': month_number,
            'month_label': MONTH_LABELS[month_number],
            'detected_amount': float(detected_amount),
            'confirmed_amount': float(remuneration.amount) if remuneration else None,
            'effective_amount': float(effective_amount),
            'confirmed': bool(remuneration),
            'confirmed_by': remuneration.confirmed_by.get_username() if remuneration and remuneration.confirmed_by else '',
            'confirmed_at': remuneration.confirmed_at.isoformat() if remuneration else None,
        })

    period_start = max(start_date, employee.hire_date) if employee.hire_date else start_date
    period_end = min(end_date, employee.termination_date) if employee.termination_date else end_date
    semester_days = Decimal((end_date - start_date).days + 1)
    worked_days = Decimal(max((period_end - period_start).days + 1, 0)) if period_start <= period_end else Decimal('0')
    proportion = worked_days / semester_days if semester_days else Decimal('0')
    eligible_months = [
        item for item in months
        if date(selected_year, item['month'], 1) <= period_end
        and month_range(selected_year, item['month'])[1] >= period_start
    ] if worked_days else []
    best_month = max(eligible_months, key=lambda item: (effective_by_month[item['month']], -item['month'])) if eligible_months else None
    best_remuneration = effective_by_month[best_month['month']] if best_month else Decimal('0')
    sac_amount = (best_remuneration / Decimal('2') * proportion).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return {
        'employee': employee_payload(employee),
        'year': selected_year,
        'semester': selected_semester,
        'period': {'start': start_date.isoformat(), 'end': end_date.isoformat()},
        'months': months,
        'best_month': best_month['month'] if best_month else None,
        'best_month_label': best_month['month_label'] if best_month else 'Sin datos',
        'best_remuneration': float(best_remuneration),
        'worked_days': int(worked_days),
        'semester_days': int(semester_days),
        'proportion': float(proportion),
        'sac_amount': float(sac_amount),
        'confirmed_months': sum(1 for item in eligible_months if item['confirmed']),
        'required_months': len(eligible_months),
        'complete': all(item['confirmed'] for item in eligible_months),
        'employment_period_confirmed': employee.hire_date is not None,
    }


@transaction.atomic
def save_aguinaldo_remunerations(employee, year, semester, rows, user=None):
    selected_year, _, _, _, semester_months = _semester_bounds(year, semester)
    allowed_months = set(semester_months)
    if not isinstance(rows, list):
        raise ValueError('Remuneraciones invalidas')
    seen_months = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Remuneracion invalida')
        try:
            month_number = int(row.get('month'))
        except (TypeError, ValueError) as exc:
            raise ValueError('Mes invalido') from exc
        if month_number not in allowed_months or month_number in seen_months:
            raise ValueError('Mes invalido o repetido')
        seen_months.add(month_number)
        raw_amount = row.get('amount')
        if raw_amount is None or raw_amount == '':
            EmployeeRemuneration.objects.filter(
                employee=employee,
                year=selected_year,
                month=month_number,
            ).delete()
            continue
        try:
            amount = Decimal(str(raw_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError('Importe de remuneracion invalido') from exc
        if amount < 0 or amount > Decimal('999999999999.99'):
            raise ValueError('Importe de remuneracion fuera de rango')
        EmployeeRemuneration.objects.update_or_create(
            employee=employee,
            year=selected_year,
            month=month_number,
            defaults={
                'amount': amount,
                'confirmed_by': user if getattr(user, 'is_authenticated', False) else None,
                'confirmed_at': timezone.now(),
            },
        )
    return aguinaldo_estimate(employee, selected_year, semester)


def _refresh_account_clients(client_ids):
    for client_id in set(client_ids):
        transactions = list(AccountTransaction.objects.filter(client_id=client_id))
        pending = sum((tx.remaining_amount for tx in transactions), Decimal('0'))
        pending_transactions = [tx for tx in transactions if tx.remaining_amount > Decimal('0')]
        client_status = AccountClient.Status.PAID
        if pending > Decimal('0'):
            if any(tx.status == AccountTransaction.Status.OVERDUE for tx in pending_transactions):
                client_status = AccountClient.Status.OVERDUE
            elif any(tx.status == AccountTransaction.Status.PARTIAL for tx in pending_transactions):
                client_status = AccountClient.Status.PARTIAL
            else:
                client_status = AccountClient.Status.ACTIVE
        AccountClient.objects.filter(pk=client_id).update(total_debt=pending, status=client_status)


@transaction.atomic
def confirm_account_deductions(employee, year, month, user=None):
    start_date, end_date = month_range(year, month)
    movements = list(
        EmployeeMovement.objects
        .select_for_update()
        .select_related('account_transaction')
        .filter(
            employee=employee,
            source=EmployeeMovement.Source.ACCOUNT_CURRENT,
            deduction_status=EmployeeMovement.DeductionStatus.PENDING,
            date__gte=start_date,
            date__lte=end_date,
            account_transaction__isnull=False,
        )
        .order_by('date', 'created_at')
    )
    if not movements:
        raise ValueError('No hay consumos pendientes para confirmar')

    totals = {
        'gross_amount': Decimal('0'),
        'discount_amount': Decimal('0'),
        'net_amount': Decimal('0'),
    }
    confirmed_at = timezone.now()
    payment_date = timezone.localdate()
    client_ids = set()
    confirmed_count = 0
    for movement in movements:
        account_transaction = AccountTransaction.objects.select_for_update().get(pk=movement.account_transaction_id)
        if account_transaction.remaining_amount <= Decimal('0'):
            movement.delete()
            continue
        gross_amount, percent, discount_amount, net_amount = _account_deduction_values(
            account_transaction,
            movement.discount_percent,
        )
        payments = list(account_transaction.payments or [])
        if net_amount > Decimal('0'):
            payments.append({
                'fecha': payment_date.isoformat(),
                'monto': float(net_amount),
                'tipo': 'descuento_sueldo',
                'empleado': employee.name,
                'movimiento_sueldo_id': str(movement.id),
            })
        if discount_amount > Decimal('0'):
            payments.append({
                'fecha': payment_date.isoformat(),
                'monto': float(discount_amount),
                'tipo': 'beneficio_empleado',
                'empleado': employee.name,
                'movimiento_sueldo_id': str(movement.id),
            })
        account_transaction.paid_amount = account_transaction.original_amount
        account_transaction.status = AccountTransaction.Status.PAID
        account_transaction.payments = payments
        account_transaction.save(update_fields=['paid_amount', 'status', 'payments', 'updated_at'])

        movement.gross_amount = gross_amount
        movement.discount_percent = percent
        movement.discount_amount = discount_amount
        movement.amount = net_amount
        movement.deduction_status = EmployeeMovement.DeductionStatus.CONFIRMED
        movement.deduction_confirmed_by = user if getattr(user, 'is_authenticated', False) else None
        movement.deduction_confirmed_at = confirmed_at
        movement.save(update_fields=[
            'gross_amount',
            'discount_percent',
            'discount_amount',
            'amount',
            'deduction_status',
            'deduction_confirmed_by',
            'deduction_confirmed_at',
            'updated_at',
        ])
        totals['gross_amount'] += gross_amount
        totals['discount_amount'] += discount_amount
        totals['net_amount'] += net_amount
        client_ids.add(account_transaction.client_id)
        confirmed_count += 1

    if not confirmed_count:
        raise ValueError('No hay consumos pendientes para confirmar')
    _refresh_account_clients(client_ids)
    return {
        'employee_id': str(employee.id),
        'employee_name': employee.name,
        'year': start_date.year,
        'month': start_date.month,
        'confirmed_count': confirmed_count,
        'gross_amount': float(totals['gross_amount']),
        'discount_amount': float(totals['discount_amount']),
        'net_amount': float(totals['net_amount']),
        'confirmed_at': confirmed_at.isoformat(),
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
        existing_movement = EmployeeMovement.objects.select_related('branch').filter(bank_transaction=tx).first()
        defaults = _movement_defaults(
            employee,
            source,
            tx.date,
            Decimal(str(tx.amount or 0)),
            _bank_movement_description(tx),
            matched_alias,
            existing=existing_movement,
        )
        lookup = {'bank_transaction': tx}
    elif source == EmployeeMovement.Source.CASH_EXPENSE:
        expense = ExpenseEntry.objects.filter(pk=source_id).first()
        if not expense:
            raise ValueError('Gasto en efectivo no encontrado')
        matched_alias = matched_alias or (expense.subcategory or expense.description or '').strip()
        existing_movement = EmployeeMovement.objects.select_related('branch').filter(expense_entry=expense).first()
        defaults = _movement_defaults(
            employee,
            source,
            expense.date,
            expense.amount or Decimal('0'),
            f"{expense.method}: {expense.subcategory or expense.description}",
            matched_alias,
            existing=existing_movement,
        )
        lookup = {'expense_entry': expense}
    elif source == EmployeeMovement.Source.ACCOUNT_CURRENT:
        account_tx = AccountTransaction.objects.select_related('client', 'branch').filter(external_id=source_id).first()
        if not account_tx:
            raise ValueError('Movimiento de cuenta corriente no encontrado')
        if account_tx.remaining_amount <= Decimal('0'):
            raise ValueError('El movimiento de cuenta corriente ya esta cancelado')
        linked_employee = Employee.objects.filter(account_client=account_tx.client).exclude(pk=employee.pk).first()
        if linked_employee:
            raise ValueError(f'La cuenta corriente ya esta vinculada a {linked_employee.name}')
        if employee.account_client_id and employee.account_client_id != account_tx.client_id:
            raise ValueError('El empleado ya tiene otra cuenta corriente vinculada')
        if employee.account_client_id != account_tx.client_id:
            employee.account_client = account_tx.client
            employee.save(update_fields=['account_client', 'updated_at'])
        matched_alias = matched_alias or account_tx.client.full_name
        existing_movement = EmployeeMovement.objects.select_related('branch').filter(account_transaction=account_tx).first()
        if existing_movement and existing_movement.deduction_status == EmployeeMovement.DeductionStatus.CONFIRMED:
            raise ValueError('El descuento de cuenta corriente ya fue confirmado')
        defaults = _account_movement_defaults(
            employee,
            account_tx,
            matched_alias,
            status=EmployeeMovement.Status.MANUAL,
            existing=existing_movement,
        )
        lookup = {'account_transaction': account_tx}
    else:
        raise ValueError('Origen de movimiento invalido')

    if matched_alias:
        ensure_employee_alias(employee, matched_alias)
    defaults['status'] = EmployeeMovement.Status.MANUAL
    movement, _ = EmployeeMovement.objects.update_or_create(defaults=defaults, **lookup)
    return movement


@transaction.atomic
def create_employee(
    name,
    aliases=None,
    account_client=None,
    notes='',
    document_type=None,
    document_number=None,
    hire_date=None,
    account_discount_percent=None,
    branch=None,
):
    cleaned_name = (name or '').strip()
    if len(cleaned_name) < 2:
        raise ValueError('Nombre de empleado requerido')
    document_provided = document_type is not None or document_number is not None
    doc_type, doc_number = normalize_employee_document(document_type, document_number) if document_provided else ('', None)
    parsed_hire_date = normalize_hire_date(hire_date)
    discount_provided = account_discount_percent is not None
    parsed_discount = normalize_account_discount_percent(account_discount_percent) if discount_provided else Decimal('0.00')
    existing_employee = Employee.objects.filter(name__iexact=cleaned_name).select_related('branch').first()
    selected_branch = branch or (existing_employee.branch if existing_employee else None) or default_employee_branch()
    if not selected_branch:
        raise ValueError('No hay una sucursal activa para asignar al empleado')
    linked_document = find_employee_by_document_identity(
        doc_type,
        doc_number,
        exclude_name=cleaned_name,
    ) if doc_number else None
    if linked_document:
        raise ValueError(f'El documento ya esta vinculado a {linked_document.name}')
    validate_account_client_assignment(account_client, existing_employee)
    employee, _ = Employee.objects.get_or_create(
        name=cleaned_name,
        defaults={
            'account_client': account_client,
            'notes': notes or '',
            'document_type': doc_type,
            'document_number': doc_number,
            'hire_date': parsed_hire_date,
            'account_discount_percent': parsed_discount,
            'branch': selected_branch,
        },
    )
    changed = []
    if employee.branch_id != selected_branch.id:
        employee.branch = selected_branch
        changed.append('branch')
    if account_client and employee.account_client_id != account_client.id:
        employee.account_client = account_client
        changed.append('account_client')
    if notes is not None and employee.notes != notes:
        employee.notes = notes
        changed.append('notes')
    if document_provided and employee.document_type != doc_type:
        employee.document_type = doc_type
        changed.append('document_type')
    if document_provided and employee.document_number != doc_number:
        employee.document_number = doc_number
        changed.append('document_number')
    if parsed_hire_date and employee.hire_date != parsed_hire_date:
        employee.hire_date = parsed_hire_date
        changed.append('hire_date')
    if discount_provided and employee.account_discount_percent != parsed_discount:
        employee.account_discount_percent = parsed_discount
        changed.append('account_discount_percent')
    if changed:
        employee.save(update_fields=changed + ['updated_at'])

    ensure_employee_alias(employee, cleaned_name)
    for alias in aliases or []:
        ensure_employee_alias(employee, alias)
    return employee
