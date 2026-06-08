import unittest
from unittest.mock import patch

from app.config import Settings


class SettingsTests(unittest.TestCase):
    def test_debug_generates_ephemeral_jwt_secret_when_unset(self):
        with patch("app.config.secrets.token_urlsafe", return_value="temporary-secret"):
            settings = Settings(DEBUG=True, JWT_SECRET=None)

        self.assertEqual(settings.JWT_SECRET, "temporary-secret")

    def test_production_requires_explicit_jwt_secret(self):
        with self.assertRaisesRegex(RuntimeError, "JWT_SECRET must be set in production"):
            Settings(DEBUG=False, JWT_SECRET=None)

    def test_global_llm_fallback_is_disabled_by_default(self):
        settings = Settings()

        self.assertFalse(settings.ALLOW_GLOBAL_LLM_FALLBACK)


if __name__ == "__main__":
    unittest.main()
