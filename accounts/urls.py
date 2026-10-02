from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("connexion/", views.login_view, name="login"),
    path("inscription/", views.register_view, name="register"),
    path("inscription/organisateur/", views.register_view, {"organizer": True}, name="register_organizer"),
    path("deconnexion/", views.logout_view, name="logout"),
    path("tableau-de-bord/", views.dispatch_view, name="dispatch"),
    path("devenir-organisateur/", views.become_organizer, name="become_organizer"),
    path("mon-espace/", views.guest_space, name="guest_space"),
    path("mon-profil/", views.profile_view, name="profile"),
]
