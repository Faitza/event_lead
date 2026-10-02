from django.contrib import admin

from .models import ContactMessage, HelpRequest, Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("name", "stars", "is_published", "created_at")
    list_filter = ("stars", "is_published")
    list_editable = ("is_published",)
    search_fields = ("name", "text")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("name", "email", "message")


@admin.register(HelpRequest)
class HelpRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "contact", "topic", "status", "created_at")
    list_filter = ("status", "topic")
    list_editable = ("status",)
    search_fields = ("name", "contact", "message")
    readonly_fields = ("created_at",)
