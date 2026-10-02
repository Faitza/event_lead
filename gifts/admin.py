from django.contrib import admin

from .models import Gift, GiftClaim


class GiftClaimInline(admin.TabularInline):
    model = GiftClaim
    extra = 0
    readonly_fields = ("guest", "claimed_at")
    can_delete = False


@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "icon_name", "quantity", "taken", "remaining_units")
    list_filter = ("event",)
    search_fields = ("name", "event__title")
    inlines = [GiftClaimInline]

    @admin.display(description="choisis")
    def taken(self, obj):
        return obj.claims.count()

    @admin.display(description="restants")
    def remaining_units(self, obj):
        return obj.remaining

    def has_delete_permission(self, request, obj=None):
        # Règle métier : un cadeau déjà choisi ne peut pas être supprimé.
        if obj is not None and obj.claims.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(GiftClaim)
class GiftClaimAdmin(admin.ModelAdmin):
    list_display = ("gift", "guest", "claimed_at")
    list_filter = ("gift__event",)
    search_fields = ("gift__name", "guest__name")
    readonly_fields = ("gift", "guest", "claimed_at")
