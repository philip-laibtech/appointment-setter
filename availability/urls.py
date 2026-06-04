from django.urls import path

from . import views

app_name = "availability"

urlpatterns = [
    path("", views.slot_list_view, name="list"),
    path("create/", views.slot_create_view, name="create"),
    path("create/recurring/", views.recurring_create_view, name="create_recurring"),
    path("<int:slot_id>/edit/", views.slot_edit_view, name="edit"),
    path("<int:slot_id>/delete/", views.slot_delete_view, name="delete"),
]
