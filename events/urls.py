from django.urls import path

from . import views, views_invitation as inv

app_name = "events"

urlpatterns = [
    path("evenements/", views.explore, name="explore"),
    path("evenements/<int:pk>/", views.public_detail, name="public_detail"),
    path("organisateur/", views.organizer_portal, name="organizer_portal"),
    path("organisateur/evenements/<int:pk>/", views.organizer_event_detail, name="organizer_event_detail"),
    path("organisateur/evenements/<int:pk>/evaluer/", views.evaluate_event, name="evaluate"),
    # Flux invité (lien magique, sans connexion)
    path("invitation/<uuid:token>/", inv.invitation_presence, name="invitation"),
    path("invitation/<uuid:token>/cadeaux/", inv.invitation_gift_question, name="invitation_gift_question"),
    path("invitation/<uuid:token>/cadeaux/liste/", inv.invitation_gift_list, name="invitation_gift_list"),
    path("invitation/<uuid:token>/cadeaux/disponibilites/", inv.invitation_gift_availability, name="invitation_gift_availability"),
    path("invitation/<uuid:token>/recapitulatif/", inv.invitation_recap, name="invitation_recap"),
    path("invitation/<uuid:token>/confirmation/", inv.invitation_done, name="invitation_done"),
    path("invitation/<uuid:token>/publicite/<int:ad_id>/", inv.invitation_ad, name="invitation_ad"),
    path("invitation/<uuid:token>/billet/", inv.invitation_ticket, name="invitation_ticket"),
    path("invitation/<uuid:token>/billet.png", inv.invitation_ticket_png, name="invitation_ticket_png"),
    path("entree/<str:code>/", inv.entry_code, name="entry_code"),
]
