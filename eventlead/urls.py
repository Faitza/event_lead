from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import views_errors

admin.site.site_header = "EventLead - Back-office"
admin.site.site_title = "EventLead"
admin.site.index_title = "Administration"

urlpatterns = [
    path("sante/", views_errors.health, name="health"),
    path("journal/erreur-navigateur/", views_errors.browser_error, name="browser_error"),
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

handler400 = "core.views_errors.bad_request"
handler403 = "core.views_errors.permission_denied"
handler404 = "core.views_errors.page_not_found"
handler500 = "core.views_errors.server_error"
