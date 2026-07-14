from django.contrib.auth.views import (
    PasswordResetConfirmView,
    PasswordResetCompleteView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.urls import path, reverse_lazy
from django_ratelimit.decorators import ratelimit

from . import views

app_name = "company_accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("2fa/verify/", views.two_factor_verify_view, name="two_factor_verify"),
    path("2fa/verify/cancel/", views.two_factor_cancel_view, name="two_factor_cancel"),
    path("tos-reaccept/", views.tos_reaccept_view, name="tos_reaccept"),
    path("delete-account/", views.request_account_deletion_view, name="request_account_deletion"),
    path("delete-account/confirm/", views.submit_account_deletion_view, name="submit_account_deletion"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/support/", views.support_request_view, name="support_request"),
    path("settings/2fa/", views.two_factor_status_view, name="two_factor_status"),
    path("settings/2fa/setup/", views.two_factor_setup_view, name="two_factor_setup"),
    path("settings/2fa/disable/", views.two_factor_disable_view, name="two_factor_disable"),
    path(
        "settings/2fa/backup-codes/regenerate/",
        views.two_factor_regenerate_backup_codes_view,
        name="two_factor_regenerate_backup_codes",
    ),

    # Password reset flow
    path(
        "password-reset/",
        ratelimit(key="ip", rate="5/m", block=True)(
            PasswordResetView.as_view(
                template_name="company_accounts/password_reset.html",
                email_template_name="company_accounts/password_reset_email.html",
                subject_template_name="company_accounts/password_reset_subject.txt",
                success_url=reverse_lazy("company_accounts:password_reset_done"),
            )
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
