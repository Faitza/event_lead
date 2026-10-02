from django.contrib import admin

from gifts.models import Gift

from .models import Event, EventEvaluation, EventGroup, Guest


class GuestInline(admin.TabularInline):
    model = Guest
    extra = 0
    fields = ("name", "email", "phone", "sent_via", "status", "companions", "replied_at")
    readonly_fields = ("replied_at",)


class GiftInline(admin.TabularInline):
    model = Gift
    extra = 0
    fields = ("name", "icon_name", "quantity")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "group", "event_type", "status", "date", "time", "venue", "max_guests", "price_htg")
    list_filter = ("event_type", "status", "group", "allow_companions", "date")
    search_fields = ("title", "venue", "description")
    date_hierarchy = "date"
    inlines = [GuestInline, GiftInline]
    readonly_fields = ("created_at",)


@admin.register(EventGroup)
class EventGroupAdmin(admin.ModelAdmin):
    list_display = ("title", "created_at")
    search_fields = ("title", "description")
    readonly_fields = ("created_at",)


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "status", "companions", "sent_via", "wants_gift", "replied_at")
    list_filter = ("status", "sent_via", "event")
    search_fields = ("name", "email", "phone", "event__title")
    readonly_fields = ("magic_token", "replied_at", "created_at")
    autocomplete_fields = ("user",)


@admin.register(EventEvaluation)
class EventEvaluationAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "stars", "created_at")
    list_filter = ("stars", "event")
