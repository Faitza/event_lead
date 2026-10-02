from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("billetterie/", views.ticketing, name="ticketing"),
    path("billetterie/<int:event_id>/payer/", views.checkout, name="checkout"),
    path("organisateur/devenir-vip/", views.vip, name="vip"),
    path("paiement/<str:reference>/succes/", views.success, name="success"),
]
