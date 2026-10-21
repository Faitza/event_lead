from django.urls import path

from . import views

app_name = "ensemble"

urlpatterns = [
    path("ensemble/evenement/<int:pk>/", views.people, name="people"),
    path("ensemble/evenement/<int:pk>/profil/", views.join, name="join"),
    path("ensemble/evenement/<int:pk>/retirer/", views.leave, name="leave"),
    path("ensemble/evenement/<int:pk>/demande/<int:user_id>/", views.send_request, name="send_request"),
    path("ensemble/demandes/", views.requests_list, name="requests"),
    path("ensemble/demandes/<int:pk>/reponse/", views.answer_request, name="answer"),
    path("ensemble/messages/", views.inbox, name="inbox"),
    path("ensemble/messages/<int:pk>/", views.conversation, name="conversation"),
    path("ensemble/personne/<int:user_id>/bloquer/", views.block, name="block"),
    path("ensemble/personne/<int:user_id>/signaler/", views.report, name="report"),
]
