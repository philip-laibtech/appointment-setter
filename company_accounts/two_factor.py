"""Helpers for TOTP-based two-factor authentication.

Kept separate from views.py so the QR/backup-code generation logic
(and its qrcode/base64 details) can be tested and reasoned about in isolation.
"""
import base64
import io

import qrcode
from django.conf import settings

from django_otp.plugins.otp_static.models import StaticDevice, StaticToken

BACKUP_DEVICE_NAME = "backup"


def build_qr_data_uri(data: str) -> str:
    """Render `data` (a otpauth:// URI) as a PNG QR code, inlined as a data: URI.

    Rendered entirely server-side so no external QR-rendering script or
    third-party image host is ever contacted by the browser.
    """
    img = qrcode.make(data, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def format_secret(device) -> str:
    """Human-readable base32 secret matching the QR code, grouped for easy typing."""
    raw = base64.b32encode(device.bin_key).decode("ascii")
    return " ".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def issue_backup_codes(user) -> list[str]:
    """(Re)generate single-use recovery codes for `user`, replacing any existing set."""
    StaticDevice.objects.filter(user=user, name=BACKUP_DEVICE_NAME).delete()
    device = StaticDevice.objects.create(user=user, name=BACKUP_DEVICE_NAME, confirmed=True)
    count = getattr(settings, "TWO_FACTOR_BACKUP_CODE_COUNT", 10)
    codes = [StaticToken.random_token() for _ in range(count)]
    StaticToken.objects.bulk_create(StaticToken(device=device, token=code) for code in codes)
    return codes


def backup_codes_remaining(user) -> int:
    return StaticToken.objects.filter(device__user=user, device__name=BACKUP_DEVICE_NAME).count()
