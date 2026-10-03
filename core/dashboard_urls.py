"""URLs du tableau de bord administrateur (/admin-dashboard/)."""
from django.urls import path

from ads import views_admin as ads_admin
from events import views_admin as events_admin
from events import views_checkin as checkin_admin
from gifts import views_admin as gifts_admin
from payments import views as payments_views

from . import views_admin as core_admin

app_name = "dashboard"

urlpatterns = [
    path("", core_admin.home, name="home"),
    path("messages/", core_admin.inbox, name="inbox"),
    path("messages/<int:pk>/lu/", core_admin.message_toggle_read, name="message_toggle_read"),
    path("avis/<int:pk>/publication/", core_admin.review_toggle, name="review_toggle"),
    # Demandes d'aide
    path("aide/", core_admin.help_list, name="help_list"),
    path("aide/export.csv", core_admin.help_export_csv, name="help_export_csv"),
    path("aide/<int:pk>/statut/", core_admin.help_set_status, name="help_set_status"),
    # Événements
    path("evenements/", events_admin.event_list, name="event_list"),
    path("evenements/nouveau/", events_admin.event_create, name="event_create"),
    path("evenements/<int:pk>/", events_admin.event_detail, name="event_detail"),
    path("evenements/<int:pk>/suivi/", events_admin.event_live, name="event_live"),
    path("evenements/<int:pk>/modifier/", events_admin.event_edit, name="event_edit"),
    path("evenements/<int:pk>/supprimer/", events_admin.event_delete, name="event_delete"),
    path("geocoder/", events_admin.geocode, name="geocode"),
    # Catégories d'événements
    path("categories/", events_admin.category_list, name="category_list"),
    path("categories/nouvelle/", events_admin.category_create, name="category_create"),
    path("categories/<int:pk>/modifier/", events_admin.category_edit, name="category_edit"),
    path("categories/<int:pk>/supprimer/", events_admin.category_delete, name="category_delete"),
    # Invités
    path("invites/", events_admin.guest_list, name="guest_list"),
    path("invites/nouveau/", events_admin.guest_create, name="guest_create"),
    path("invites/<int:pk>/modifier/", events_admin.guest_edit, name="guest_edit"),
    path("invites/<int:pk>/supprimer/", events_admin.guest_delete, name="guest_delete"),
    path("invites/<int:pk>/envoye/", events_admin.guest_mark_sent, name="guest_mark_sent"),
    path("invites/export.csv", events_admin.guest_export_csv, name="guest_export_csv"),
    path("invites/export.pdf", events_admin.guest_export_pdf, name="guest_export_pdf"),
    # Pointage à l'entrée (jour J)
    path("pointage/", checkin_admin.checkin_index, name="checkin_index"),
    path("pointage/<int:pk>/", checkin_admin.checkin_event, name="checkin_event"),
    path("pointage/<int:pk>/live/", checkin_admin.checkin_live, name="checkin_live"),
    path("pointage/<int:pk>/scan/", checkin_admin.checkin_scan, name="checkin_scan"),
    path("pointage/<int:pk>/manuel/", checkin_admin.checkin_manual, name="checkin_manual"),
    path("pointage/<int:pk>/chercher/", checkin_admin.checkin_search, name="checkin_search"),
    path("pointage/<int:pk>/ajouter/", checkin_admin.checkin_walk_in, name="checkin_walk_in"),
    path("pointage/<int:pk>/<int:guest_pk>/annuler/", checkin_admin.checkin_cancel, name="checkin_cancel"),
    # Cadeaux
    path("cadeaux/", gifts_admin.gift_list, name="gift_list"),
    path("cadeaux/nouveau/", gifts_admin.gift_create, name="gift_create"),
    path("cadeaux/<int:pk>/modifier/", gifts_admin.gift_edit, name="gift_edit"),
    path("cadeaux/<int:pk>/supprimer/", gifts_admin.gift_delete, name="gift_delete"),
    path("cadeaux/export.csv", gifts_admin.gift_export_csv, name="gift_export_csv"),
    # Publicités
    path("publicites/", ads_admin.ad_list, name="ad_list"),
    path("publicites/nouvelle/", ads_admin.ad_create, name="ad_create"),
    path("publicites/<int:pk>/modifier/", ads_admin.ad_edit, name="ad_edit"),
    path("publicites/<int:pk>/supprimer/", ads_admin.ad_delete, name="ad_delete"),
    path("publicites/<int:pk>/basculer/", ads_admin.ad_toggle, name="ad_toggle"),
    # Paiements
    path("paiements/", payments_views.history, name="payment_history"),
]
