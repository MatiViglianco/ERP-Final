from django.contrib import admin

from .models import (
    Branch,
    UploadBatch,
    Record,
    BankUploadBatch,
    BankTransaction,
    AccountClient,
    AccountTransaction,
    ExternalEvent,
    GetnetTerminal,
    Employee,
    EmployeeAlias,
    EmployeeMovement,
    Invoice,
    InvoiceAccountTransaction,
    InvoiceLine,
    Payment,
)


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'active', 'updated_at')
    list_filter = ('active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'branch', 'created_at', 'fecha_desde', 'fecha_hasta', 'single_date', 'is_single_day', 'original_filename')
    list_filter = ('branch', 'is_single_day', 'created_at')
    search_fields = ('original_filename',)
    date_hierarchy = 'created_at'


@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'batch', 'dsc_seccion', 'nom_plu', 'peso', 'units', 'imp')
    list_filter = ('dsc_seccion', 'batch')
    search_fields = ('dsc_seccion', 'nom_plu', 'nro_plu')
    autocomplete_fields = ('batch',)


@admin.register(BankUploadBatch)
class BankUploadBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'bank', 'fecha_desde', 'fecha_hasta', 'original_filename', 'created_at')
    list_filter = ('bank', 'created_at')
    search_fields = ('original_filename',)
    date_hierarchy = 'created_at'


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'batch', 'date', 'concept', 'amount')
    list_filter = ('batch__bank', 'date')
    search_fields = ('concept', 'description')
    autocomplete_fields = ('batch',)


@admin.register(AccountClient)
class AccountClientAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'external_id', 'phone', 'status', 'total_debt', 'source_created_at')
    list_filter = ('status',)
    search_fields = ('first_name', 'last_name', 'external_id')
    ordering = ('last_name', 'first_name')


@admin.register(AccountTransaction)
class AccountTransactionAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'client', 'branch', 'date', 'status', 'original_amount', 'paid_amount')
    list_filter = ('branch', 'status')
    search_fields = ('external_id', 'client__first_name', 'client__last_name')
    autocomplete_fields = ('client', 'branch')


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    autocomplete_fields = ('account_transaction',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'branch', 'source', 'status', 'issue_date', 'voucher_number', 'total_amount', 'cae')
    list_filter = ('branch', 'source', 'status', 'issue_date')
    search_fields = ('id', 'client__first_name', 'client__last_name', 'cae', 'external_reference')
    autocomplete_fields = ('client', 'branch')
    inlines = (InvoiceLineInline,)
    date_hierarchy = 'issue_date'


@admin.register(InvoiceAccountTransaction)
class InvoiceAccountTransactionAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'transaction', 'amount', 'created_at')
    autocomplete_fields = ('invoice', 'transaction')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'source', 'status', 'provider_status', 'terminal', 'branch', 'date', 'amount', 'client', 'invoice', 'external_id')
    list_filter = ('source', 'status', 'terminal', 'branch', 'date')
    search_fields = ('id', 'external_id', 'client__first_name', 'client__last_name')
    autocomplete_fields = ('client', 'invoice', 'bank_transaction', 'terminal', 'branch')


@admin.register(GetnetTerminal)
class GetnetTerminalAdmin(admin.ModelAdmin):
    list_display = ('code', 'branch', 'establishment_number', 'establishment_name', 'active', 'last_seen_at')
    list_filter = ('active', 'branch')
    search_fields = ('code', 'establishment_number', 'establishment_name')
    autocomplete_fields = ('branch',)


@admin.register(ExternalEvent)
class ExternalEventAdmin(admin.ModelAdmin):
    list_display = ('provider', 'event_id', 'event_type', 'status', 'created_at', 'processed_at')
    list_filter = ('provider', 'event_type', 'status')
    search_fields = ('event_id', 'event_type')


class EmployeeAliasInline(admin.TabularInline):
    model = EmployeeAlias
    extra = 0


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'document_type', 'document_number', 'active', 'account_client', 'termination_date', 'updated_at')
    list_filter = ('active', 'document_type', 'termination_reason')
    search_fields = ('name', 'document_number', 'aliases__alias', 'account_client__first_name', 'account_client__last_name')
    autocomplete_fields = ('account_client',)
    inlines = (EmployeeAliasInline,)


@admin.register(EmployeeMovement)
class EmployeeMovementAdmin(admin.ModelAdmin):
    list_display = ('employee', 'source', 'status', 'date', 'amount', 'matched_alias')
    list_filter = ('source', 'status', 'date')
    search_fields = ('employee__name', 'description', 'matched_alias')
    autocomplete_fields = ('employee', 'bank_transaction', 'account_transaction')
