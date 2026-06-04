from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path(
        "<slug:company_slug>/",
        views.public_booking_entry_view,
        name="entry",
    ),
    path(
        "<slug:company_slug>/staff/<int:staff_id>/services/",
        views.public_service_select_view,
        name="service_select",
    ),
    # Step 3a: day selection
    path(
        "<slug:company_slug>/staff/<int:staff_id>/services/<int:service_id>/slots/",
        views.public_slot_select_view,
        name="slot_select",
    ),
    # Step 3b: time-window selection for a chosen day
    path(
        "<slug:company_slug>/staff/<int:staff_id>/services/<int:service_id>/slots/<str:date>/",
        views.public_time_select_view,
        name="time_select",
    ),
    # Step 4: booking form — date=YYYY-MM-DD, start_time=HH-MM
    path(
        "<slug:company_slug>/staff/<int:staff_id>/services/<int:service_id>/book/<str:date>/<str:start_time>/",
        views.public_booking_form_view,
        name="book",
    ),
    path(
        "<slug:company_slug>/booking/<str:public_token>/confirmed/",
        views.public_booking_confirmed_view,
        name="confirmed",
    ),
]
