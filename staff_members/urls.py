from django.urls import path

from . import views

app_name = "staff_members"

urlpatterns = [
    path("", views.staff_list_view, name="list"),
    path("create/", views.staff_create_view, name="create"),
    path("<int:member_id>/edit/", views.staff_edit_view, name="edit"),
    path("<int:member_id>/delete/", views.staff_delete_view, name="delete"),
]
