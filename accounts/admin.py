from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ("email", "first_name", "last_name", "role", "is_vip", "is_active", "date_joined")
    list_filter = ("role", "is_vip", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name", "phone")
    ordering = ("-date_joined",)
    fieldsets = UserAdmin.fieldsets + (
        ("EventLead", {"fields": ("role", "phone", "avatar", "is_vip", "vip_since")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("EventLead", {"fields": ("email", "role", "phone")}),
    )
