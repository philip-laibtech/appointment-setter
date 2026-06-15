from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    # ── Internal company management (must precede slug-based public routes) ──
    path(
        "manage/pending/",
        views.pending_bookings_view,
        name="pending_bookings",
    ),
    path(
        "manage/bookings/",
        views.all_bookings_view,
        name="all_bookings",
    ),
    path(
        "manage/past/",
        views.past_bookings_view,
        name="past_bookings",
    ),
    path(
        "manage/<int:booking_id>/",
        views.booking_detail_view,
        name="booking_detail",
    ),
    path(
        "manage/<int:booking_id>/confirm/",
        views.confirm_booking_view,
        name="confirm_booking",
    ),
    path(
        "manage/<int:booking_id>/decline/",
        views.decline_booking_view,
        name="decline_booking",
    ),
    path(
        "manage/<int:booking_id>/delete/",
        views.delete_booking_view,
        name="delete_booking",
    ),

    # ── Public booking flow ──────────────────────────────────────────────────
    path(
        "<slug:company_slug>/",
        views.public_booking_entry_view,
        name="entry",
    ),
    path(
        "<slug:company_slug>/staff/<uuid:staff_uid>/services/",
        views.public_service_select_view,
        name="service_select",
    ),
    # Step 3a: day selection
    path(
        "<slug:company_slug>/staff/<uuid:staff_uid>/services/<uuid:service_uid>/slots/",
        views.public_slot_select_view,
        name="slot_select",
    ),
    # Step 3b: time-window selection for a chosen day
    path(
        "<slug:company_slug>/staff/<uuid:staff_uid>/services/<uuid:service_uid>/slots/<str:date>/",
        views.public_time_select_view,
        name="time_select",
    ),
    # Step 4: booking form — date=YYYY-MM-DD, start_time=HH-MM
    path(
        "<slug:company_slug>/staff/<uuid:staff_uid>/services/<uuid:service_uid>/book/<str:date>/<str:start_time>/",
        views.public_booking_form_view,
        name="book",
    ),
    # Any Employee flow
    path(
        "<slug:company_slug>/any/services/",
        views.any_service_select_view,
        name="any_service_select",
    ),
    # Step 2: day selection
    path(
        "<slug:company_slug>/any/services/<uuid:service_uid>/slots/",
        views.any_slot_select_view,
        name="any_slot_select",
    ),
    # Step 3: time-window selection for a chosen day
    path(
        "<slug:company_slug>/any/services/<uuid:service_uid>/slots/<str:date>/",
        views.any_time_select_view,
        name="any_time_select",
    ),
    # Step 4: booking form — date=YYYY-MM-DD, start_time=HH-MM
    path(
        "<slug:company_slug>/any/services/<uuid:service_uid>/book/<str:date>/<str:start_time>/",
        views.any_booking_form_view,
        name="any_book",
    ),
    path(
        "<slug:company_slug>/booking/<str:public_token>/confirmed/",
        views.public_booking_confirmed_view,
        name="confirmed",
    ),
    path(
        "<slug:company_slug>/booking/<str:public_token>/cancel/",
        views.public_booking_cancel_view,
        name="cancel",
    ),
]
