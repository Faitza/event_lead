from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "kind", "method", "amount_htg", "status", "user", "event", "created_at")
    list_filter = ("status", "method", "kind", "created_at")
    search_fields = ("reference", "user__email", "event__title", "payer_detail")
    readonly_fields = ("created_at",)
