import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class AdminUrlSettingTests(SimpleTestCase):
    """Closes AUDIT.md 2.4: refuse to start in production without a custom
    admin URL, rather than silently falling back to the well-known /admin/."""

    def _run_with_env(self, env_overrides):
        env = {**os.environ, **env_overrides}
        return subprocess.run(
            [sys.executable, "-c", "import django; django.setup()"],
            env=env,
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_missing_admin_url_in_production_raises(self):
        env = {"DJANGO_DEBUG": "false", "DJANGO_SETTINGS_MODULE": "core.settings"}
        env.pop("DJANGO_ADMIN_URL", None)
        result = self._run_with_env(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ADMIN_URL", result.stderr)

    def test_admin_url_set_in_production_starts_cleanly(self):
        env = {
            "DJANGO_DEBUG": "false",
            "DJANGO_SETTINGS_MODULE": "core.settings",
            "DJANGO_ADMIN_URL": "manage-secret/",
        }
        result = self._run_with_env(env)
        self.assertEqual(result.returncode, 0, result.stderr)
