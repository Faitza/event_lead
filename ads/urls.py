from django.urls import path

from . import views

app_name = "ads"

urlpatterns = [
    path("publicites/", views.ad_list, name="list"),
    path("publicites/<int:pk>/visiter/", views.ad_click, name="click"),
]
