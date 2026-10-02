from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("avis/", views.submit_review, name="submit_review"),
    path("contact/", views.submit_contact, name="submit_contact"),
    path("aide/", views.help_page, name="help"),
]
