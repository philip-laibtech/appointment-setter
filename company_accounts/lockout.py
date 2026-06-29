"""Per-account login lockout after repeated failed attempts.

Complements the existing IP- and username-based django-ratelimit decorators
on login_view: those throttle request *rate*, this throttles repeated
failures against one specific account regardless of which IP they come from
(closes AUDIT.md finding 2.3 — distributed/botnet brute force).

Uses Django's configured cache, same as django-ratelimit. In a multi-worker
production deployment this requires a shared cache backend (Redis/Memcached)
to be effective across all workers — see AUDIT.md finding 1.3 and
docs/deployment.md.
"""
from django.conf import settings
from django.core.cache import cache


def _cache_key(email: str) -> str:
    return f"login-lockout:{email.strip().lower()}"


def is_locked_out(email: str) -> bool:
    count = cache.get(_cache_key(email), 0)
    return count >= settings.ACCOUNT_LOCKOUT_THRESHOLD


def record_failed_attempt(email: str) -> None:
    key = _cache_key(email)
    timeout = settings.ACCOUNT_LOCKOUT_DURATION_MINUTES * 60
    cache.add(key, 0, timeout=timeout)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)


def clear_failed_attempts(email: str) -> None:
    cache.delete(_cache_key(email))
