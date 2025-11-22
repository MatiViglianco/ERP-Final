from django.contrib import admin

from .models import (
    UploadBatch,
    Record,
    BankUploadBatch,
    BankTransaction,
    AccountClient,
    AccountTransaction,
)


@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'fecha_desde', 'fecha_hasta', 'single_date', 'is_single_day', 'original_filename')
    list_filter = ('is_single_day', 'created_at')
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
    list_display = ('external_id', 'client', 'date', 'status', 'original_amount', 'paid_amount')
    list_filter = ('status',)
    search_fields = ('external_id', 'client__first_name', 'client__last_name')
    autocomplete_fields = ('client',)
