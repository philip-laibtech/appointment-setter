from django.contrib.auth.views import (
    PasswordResetConfirmView,
    PasswordResetCompleteView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.urls import path, reverse_lazy

from . import views

app_name = "company_accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("tos-reaccept/", views.tos_reaccept_view, name="tos_reaccept"),
    path("delete-account/", views.request_account_deletion_view, name="request_account_deletion"),
    path("delete-account/confirm/", views.submit_account_deletion_view, name="submit_account_deletion"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("settings/", views.settings_view, name="settings"),

    # Password reset flow
    path(
        "password-reset/",
        PasswordResetView.as_view(
            template_name="company_accounts/password_reset.html",
            email_template_name="company_accounts/password_reset_email.html",
            subject_template_name="company_accounts/password_reset_subject.txt",
            success_url=reverse_lazy("company_accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        PasswordResetDoneView.as_view(
            template_name="company_accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="company_accounts/password_reset_confirm.html",
            success_url=reverse_lazy("company_accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        PasswordResetCompleteView.as_view(
            template_name="company_accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
