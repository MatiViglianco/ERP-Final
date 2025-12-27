import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone


class UploadBatch(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    original_filename = models.CharField(max_length=255, blank=True)

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

