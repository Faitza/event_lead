from django.contrib import admin

from .models import Block, Listing, MeetRequest, Message, Profile, Report


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("first_name", "user", "city", "warned_at", "removed_at", "created_at")
    search_fields = ("first_name", "user__email", "city")
    raw_id_fields = ("user",)


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "wants_company", "wants_transport", "wants_group", "created_at")
    list_filter = ("event",)
    raw_id_fields = ("user", "event")


@admin.register(MeetRequest)
class MeetRequestAdmin(admin.ModelAdmin):
    list_display = ("sender", "receiver", "event", "status", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("sender", "receiver", "event")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("request", "sender", "created_at")
    raw_id_fields = ("request", "sender")


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("blocker", "blocked", "created_at")
    raw_id_fields = ("blocker", "blocked")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("reported", "reporter", "reason", "status", "created_at")
    list_filter = ("status", "reason")
    raw_id_fields = ("reporter", "reported", "event", "handled_by")
