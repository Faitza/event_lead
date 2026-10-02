from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "EventLead - Back-office"
admin.site.site_title = "EventLead"
admin.site.index_title = "Administration"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),  # connexion Google (django-allauth)
    path("admin-dashboard/", include("core.dashboard_urls")),
    path("", include("accounts.urls")),
    path("", include("events.urls")),
    path("", include("payments.urls")),
    path("", include("ads.urls")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "core.views_errors.permission_denied"
handler404 = "core.views_errors.page_not_found"
