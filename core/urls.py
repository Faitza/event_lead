from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("avis/", views.submit_review, name="submit_review"),
    path("contact/", views.submit_contact, name="submit_contact"),
    path("aide/", views.help_page, name="help"),
    path("recherche/", views.search_page, name="search"),
    path("langue/", views.set_language, name="set_language"),
    path("confidentialite/", views.privacy, name="privacy"),
    path("conditions-utilisation/", views.terms, name="terms"),
]
