import unittest

from fastapi.testclient import TestClient

from app.main import app


class CorsConfigTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_debug_preflight_allows_configured_origin(self):
        response = self.client.options(
            "/health",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:4173")
        self.assertEqual(response.headers.get("access-control-allow-credentials"), "true")

    def test_debug_preflight_rejects_unconfigured_origin(self):
        response = self.client.options(
            "/health",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.headers.get("access-control-allow-origin"), "*")

    def test_preflight_limits_methods_and_headers_to_api_contract(self):
        response = self.client.options(
            "/health",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization, content-type, accept-language",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("POST", response.headers.get("access-control-allow-methods", ""))
        allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
        self.assertIn("authorization", allowed_headers)
        self.assertIn("content-type", allowed_headers)
        self.assertIn("accept-language", allowed_headers)


if __name__ == "__main__":
    unittest.main()
