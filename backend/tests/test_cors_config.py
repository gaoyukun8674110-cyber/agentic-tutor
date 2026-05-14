import unittest

from fastapi.testclient import TestClient

from app.main import app, build_cors_options


class CorsConfigTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_debug_preflight_allows_configured_origin(self):
        response = self.client.options(
            '/health',
            headers={
                'Origin': 'http://localhost:4173',
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'authorization',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('access-control-allow-origin'), 'http://localhost:4173')
        self.assertEqual(response.headers.get('access-control-allow-credentials'), 'true')

    def test_debug_preflight_rejects_unconfigured_origin(self):
        response = self.client.options(
            '/health',
            headers={
                'Origin': 'https://example.com',
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'authorization',
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.headers.get('access-control-allow-origin'), '*')

    def test_production_cors_uses_configured_origins_and_credentials(self):
        origins, allow_credentials = build_cors_options(False, ['https://app.example.com'])

        self.assertEqual(origins, ['https://app.example.com'])
        self.assertTrue(allow_credentials)


if __name__ == '__main__':
    unittest.main()
