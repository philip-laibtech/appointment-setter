from django.urls import path

from . import views

app_name = "services"

urlpatterns = [
    path("", views.service_list_view, name="list"),
    path("create/", views.service_create_view, name="create"),
    path("<int:service_id>/edit/", views.service_edit_view, name="edit"),
    path("<int:service_id>/delete/", views.service_delete_view, name="delete"),
]
