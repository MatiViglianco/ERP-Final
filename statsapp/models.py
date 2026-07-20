import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone

from .text_utils import normalize_search_text


class Branch(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['active', 'name']),
        ]

    def __str__(self):
        return self.name


class UploadBatch(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    original_filename = models.CharField(max_length=255, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='upload_batches')

    # Período de datos cargados
    fecha_desde = models.DateField(null=True, blank=True)
    fecha_hasta = models.DateField(null=True, blank=True)
    single_date = models.DateField(null=True, blank=True)
    is_single_day = models.BooleanField(default=False)
    is_only_today = models.BooleanField(default=False)

    note = models.CharField(max_length=255, blank=True)

    def __str__(self):
        label = self.single_date.isoformat() if self.single_date else f"{self.fecha_desde}..{self.fecha_hasta}"
        return f"Batch {self.id} ({label})"


class Record(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE, related_name='records')

    cod_seccion = models.CharField(max_length=32, blank=True)
    dsc_seccion = models.CharField(max_length=128, blank=True)
    cod_familia = models.CharField(max_length=32, blank=True)
    dsc_familia = models.CharField(max_length=128, blank=True)
    nro_plu = models.CharField(max_length=64, blank=True)
    nom_plu = models.CharField(max_length=255, blank=True)
    uni = models.CharField(max_length=16, blank=True)

    peso = models.FloatField(default=0.0)
    imp = models.FloatField(default=0.0)
    units = models.FloatField(default=0.0)

    class Meta:
        indexes = [
            models.Index(fields=['dsc_seccion']),
            models.Index(fields=['nom_plu']),
        ]


class BankUploadBatch(models.Model):
    BANK_CHOICES = [
        ('santander', 'Santander'),
        ('bancon', 'Bancón'),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    bank = models.CharField(max_length=32, choices=BANK_CHOICES)
    original_filename = models.CharField(max_length=255, blank=True)
    fecha_desde = models.DateField(null=True, blank=True)
    fecha_hasta = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_bank_display()} ({self.fecha_desde} - {self.fecha_hasta})"


class BankTransaction(models.Model):
    batch = models.ForeignKey(BankUploadBatch, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField()
    concept = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    raw_details = models.TextField(blank=True)
    amount = models.FloatField(default=0.0)

    class Meta:
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['concept']),
            models.Index(fields=['batch', 'date']),
        ]


class AccountClient(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Activo'
        PARTIAL = 'partial', 'Parcial'
        OVERDUE = 'overdue', 'Vencido'
        PAID = 'paid', 'Pagado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(max_length=64, unique=True)
    first_name = models.CharField(max_length=128, blank=True)
    last_name = models.CharField(max_length=128, blank=True)
    source_created_at = models.DateTimeField(null=True, blank=True)
    total_debt = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    phone = models.CharField(max_length=32, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['status']),
            models.Index(fields=['-total_debt']),
        ]

    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.last_name}, {self.first_name}"
        return self.last_name or self.first_name or self.external_id


class AccountTransaction(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'activo', 'Activo'
        PARTIAL = 'parcial', 'Parcial'
        OVERDUE = 'vencido', 'Vencido'
        PAID = 'pagado', 'Pagado'

    client = models.ForeignKey(AccountClient, on_delete=models.CASCADE, related_name='transactions')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='account_transactions')
    external_id = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=255, blank=True)
    date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    original_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    payments = models.JSONField(default=list, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['client', '-date']),
            models.Index(fields=['status']),
        ]

    @property
    def remaining_amount(self):
        remaining = (self.original_amount or Decimal('0')) - (self.paid_amount or Decimal('0'))
        return remaining if remaining > Decimal('0') else Decimal('0')


class SalesManualEntry(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE, related_name='sales_manual_entries')
    date = models.DateField()
    anulado = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    fc_inicial = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    pagos = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    debitos = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    gastos = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    vales = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    fc_final = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('batch', 'date')
        indexes = [
            models.Index(fields=['batch', 'date']),
        ]
        ordering = ['date']

    def __str__(self):
        return f"Manual {self.batch_id} {self.date}"


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ExpenseSubcategory(models.Model):
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name='subcategories')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('category', 'name')
        ordering = ['name']
        indexes = [
            models.Index(fields=['category', 'name']),
        ]

    def __str__(self):
        return f"{self.category.name} / {self.name}"


class ExpenseEntry(models.Model):
    class Method(models.TextChoices):
        CASH = 'EFECTIVO', 'Efectivo'
        TRANSFER = 'TRANSFERENCIA', 'Transferencia'
        CHECK = 'CHEQUE', 'Cheque'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    method = models.CharField(max_length=32, choices=Method.choices, default=Method.CASH)
    category = models.CharField(max_length=100, blank=True)
    subcategory = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['category']),
            models.Index(fields=['subcategory']),
        ]

    def __str__(self):
        return f"{self.date} {self.amount} {self.category}/{self.subcategory}"


class BankExpenseAssignment(models.Model):
    external_id = models.CharField(max_length=128, unique=True)
    category = models.CharField(max_length=100, blank=True)
    subcategory = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['external_id']),
        ]

    def __str__(self):
        return f"{self.external_id} -> {self.category}/{self.subcategory}"


class Employee(models.Model):
    class DocumentType(models.TextChoices):
        DNI = 'dni', 'DNI'
        CUIL_CUIT = 'cuil_cuit', 'CUIL/CUIT'

    class TerminationReason(models.TextChoices):
        RESIGNATION = 'resignation', 'Renuncia'
        DISMISSAL = 'dismissal', 'Despido'
        OTHER = 'other', 'Otro'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160, unique=True)
    active = models.BooleanField(default=True)
    document_type = models.CharField(max_length=12, choices=DocumentType.choices, blank=True)
    document_number = models.CharField(max_length=16, unique=True, null=True, blank=True)
    account_client = models.OneToOneField(
        AccountClient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee_profile',
    )
    hire_date = models.DateField(null=True, blank=True)
    termination_reason = models.CharField(max_length=16, choices=TerminationReason.choices, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['active', 'name']),
        ]

    def __str__(self):
        return self.name


class EmployeeRemuneration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='remunerations')
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_employee_remunerations',
    )
    confirmed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year', '-month', 'employee__name']
        constraints = [
            models.UniqueConstraint(fields=['employee', 'year', 'month'], name='unique_employee_remuneration_month'),
            models.CheckConstraint(check=models.Q(month__gte=1, month__lte=12), name='employee_remuneration_valid_month'),
            models.CheckConstraint(check=models.Q(amount__gte=0), name='employee_remuneration_nonnegative'),
        ]
        indexes = [
            models.Index(fields=['employee', 'year', 'month']),
        ]

    def __str__(self):
        return f"{self.employee.name} {self.year}-{self.month:02d} {self.amount}"


class EmployeeAlias(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='aliases')
    alias = models.CharField(max_length=160)
    normalized_alias = models.CharField(max_length=160, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['alias']
        indexes = [
            models.Index(fields=['normalized_alias']),
            models.Index(fields=['employee', 'alias']),
        ]

    def save(self, *args, **kwargs):
        self.alias = (self.alias or '').strip()
        self.normalized_alias = normalize_search_text(self.alias)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.alias} -> {self.employee.name}"


class EmployeeMovement(models.Model):
    class Source(models.TextChoices):
        BANK_TRANSFER = 'bank_transfer', 'Transferencia bancaria'
        CASH_EXPENSE = 'cash_expense', 'Efectivo por gastos'
        ACCOUNT_CURRENT = 'account_current', 'Cuenta corriente'

    class Status(models.TextChoices):
        AUTO = 'auto', 'Automatico'
        REVIEW = 'review', 'Revisar'
        MANUAL = 'manual', 'Manual'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='movements')
    source = models.CharField(max_length=24, choices=Source.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AUTO)
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.TextField(blank=True)
    bank_transaction = models.OneToOneField(
        BankTransaction,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='employee_movement',
    )
    expense_entry = models.OneToOneField(
        ExpenseEntry,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='employee_movement',
    )
    account_transaction = models.OneToOneField(
        AccountTransaction,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='employee_movement',
    )
    matched_alias = models.CharField(max_length=160, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['employee', '-date']),
            models.Index(fields=['source', 'date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.employee.name} {self.source} {self.amount}"


class UserActivity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activity')
    last_activity = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['last_activity']),
        ]

    def touch(self):
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])


class AccountClientAlias(models.Model):
    client = models.ForeignKey(AccountClient, on_delete=models.CASCADE, related_name='aliases')
    alias = models.CharField(max_length=120)
    normalized_alias = models.CharField(max_length=120, unique=True)
    auto_detected = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['alias']
        indexes = [
            models.Index(fields=['normalized_alias']),
            models.Index(fields=['client', 'alias']),
        ]

    def save(self, *args, **kwargs):
        self.alias = (self.alias or '').strip()
        self.normalized_alias = normalize_search_text(self.alias)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.alias} -> {self.client.full_name}"


class ValeImportBatch(models.Model):
    lote_id = models.CharField(max_length=32, unique=True)
    date = models.DateField()
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='vale_batches')
    source_photo = models.FileField(upload_to='vales/', null=True, blank=True)
    source_filenames = models.JSONField(default=list, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"{self.lote_id} ({self.date})"


class ValeImportItem(models.Model):
    batch = models.ForeignKey(ValeImportBatch, on_delete=models.CASCADE, related_name='items')
    transaction = models.ForeignKey(AccountTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='vale_items')
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    client = models.ForeignKey(AccountClient, on_delete=models.PROTECT, null=True, blank=True, related_name='vale_items')
    client_raw = models.CharField(max_length=120)
    detail = models.CharField(max_length=255, blank=True)
    pending_review = models.BooleanField(default=False)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('1'))
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['batch', 'date']),
            models.Index(fields=['client', 'date']),
            models.Index(fields=['pending_review']),
        ]

    def __str__(self):
        return f"{self.batch.lote_id} - {self.client_raw} - {self.amount}"


class Invoice(models.Model):
    class Source(models.TextChoices):
        ACCOUNT = 'account', 'Cuenta corriente'
        GETNET = 'getnet', 'Getnet'
        MANUAL = 'manual', 'Manual'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Borrador'
        AUTHORIZED = 'authorized', 'Autorizada'
        REJECTED = 'rejected', 'Rechazada'
        ERROR = 'error', 'Error'
        CANCELLED = 'cancelled', 'Anulada'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(AccountClient, on_delete=models.PROTECT, null=True, blank=True, related_name='invoices')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    issue_date = models.DateField(default=timezone.localdate)
    point_of_sale = models.PositiveIntegerField(default=0)
    voucher_type = models.PositiveIntegerField(default=0)
    voucher_number = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=8, default='PES')
    net_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    vat_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    exempt_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    cae = models.CharField(max_length=32, blank=True)
    cae_due_date = models.DateField(null=True, blank=True)
    external_reference = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    provider_result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issue_date', '-created_at']
        indexes = [
            models.Index(fields=['status', 'issue_date']),
            models.Index(fields=['source', 'issue_date']),
            models.Index(fields=['client', '-issue_date']),
            models.Index(fields=['branch', '-issue_date']),
            models.Index(fields=['external_reference']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['point_of_sale', 'voucher_type', 'voucher_number'],
                condition=models.Q(voucher_number__isnull=False),
                name='unique_invoice_voucher_number',
            ),
        ]

    def __str__(self):
        number = self.voucher_number or 'sin numero'
        return f"{self.get_source_display()} {number} - {self.total_amount}"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('1'))
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    account_transaction = models.ForeignKey(
        AccountTransaction,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='invoice_lines',
    )

    class Meta:
        indexes = [
            models.Index(fields=['invoice']),
            models.Index(fields=['account_transaction']),
        ]

    def __str__(self):
        return f"{self.description} - {self.total}"


class InvoiceAccountTransaction(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='account_links')
    transaction = models.OneToOneField(AccountTransaction, on_delete=models.PROTECT, related_name='invoice_link')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['invoice']),
            models.Index(fields=['transaction']),
        ]


class GetnetTerminal(models.Model):
    code = models.CharField(max_length=32, unique=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='getnet_terminals',
    )
    establishment_number = models.CharField(max_length=32, blank=True)
    establishment_name = models.CharField(max_length=160, blank=True)
    active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        indexes = [
            models.Index(fields=['branch', 'active']),
            models.Index(fields=['establishment_number']),
        ]

    def __str__(self):
        return f"{self.code} - {self.branch or 'sin sucursal'}"


class Payment(models.Model):
    class Source(models.TextChoices):
        GETNET = 'getnet', 'Getnet'
        SANTANDER = 'santander', 'Santander'
        BANCON = 'bancon', 'Bancor'
        CASH = 'cash', 'Efectivo'
        TRANSFER = 'transfer', 'Transferencia'
        MANUAL = 'manual', 'Manual'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        APPROVED = 'approved', 'Aprobado'
        REJECTED = 'rejected', 'Rechazado'
        RECONCILED = 'reconciled', 'Conciliado'
        NEEDS_REVIEW = 'needs_review', 'Revisar'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=16, choices=Source.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    external_id = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    provider_status = models.CharField(max_length=64, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    terminal = models.ForeignKey(
        GetnetTerminal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
    )
    client = models.ForeignKey(AccountClient, on_delete=models.PROTECT, null=True, blank=True, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    bank_transaction = models.OneToOneField(
        BankTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment',
    )
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['source', 'status', 'date']),
            models.Index(fields=['external_id']),
            models.Index(fields=['client', '-date']),
            models.Index(fields=['invoice']),
            models.Index(fields=['terminal', '-date']),
            models.Index(fields=['branch', '-date']),
        ]

    def __str__(self):
        return f"{self.get_source_display()} {self.amount} ({self.status})"


class ExternalEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = 'received', 'Recibido'
        PROCESSED = 'processed', 'Procesado'
        DUPLICATE = 'duplicate', 'Duplicado'
        ERROR = 'error', 'Error'

    provider = models.CharField(max_length=32)
    event_id = models.CharField(max_length=128)
    event_type = models.CharField(max_length=64, blank=True)
    payload_hash = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    error_message = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('provider', 'event_id')
        indexes = [
            models.Index(fields=['provider', 'event_type']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.provider}:{self.event_id}"

