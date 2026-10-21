from django.contrib import admin

from .models import Ad


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ("title", "advertiser", "is_paid", "start_date", "end_date", "is_active", "show_after_reply", "order", "views", "clicks", "ctr_display")
    list_filter = ("is_paid", "is_active", "show_after_reply")
    list_editable = ("is_paid", "is_active", "show_after_reply", "order")
    search_fields = ("title", "advertiser", "message")
    readonly_fields = ("views", "clicks")

    @admin.display(description="CTR")
    def ctr_display(self, obj):
        return f"{obj.ctr} %"
