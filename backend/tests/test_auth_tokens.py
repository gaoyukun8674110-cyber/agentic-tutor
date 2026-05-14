import time
import unittest

from app.auth.exceptions import InvalidTokenError, TokenExpiredError
from app.auth.tokens import decode_access_token, encode_access_token, generate_refresh_token, hash_refresh_token
from app.config import settings


class AuthTokenTests(unittest.TestCase):
    def setUp(self):
        self.previous_secret = settings.JWT_SECRET
        settings.JWT_SECRET = "test-secret-with-at-least-32-bytes!!"

    def tearDown(self):
        settings.JWT_SECRET = self.previous_secret

    def test_access_token_encodes_subject_and_expiry(self):
        token = encode_access_token("alice", ttl_seconds=900)

        claims = decode_access_token(token)

        self.assertEqual(claims["sub"], "alice")
        self.assertEqual(claims["type"], "access")
        self.assertIn("exp", claims)
        self.assertIn("iat", claims)

    def test_expired_access_token_raises_token_expired(self):
        token = encode_access_token("alice", ttl_seconds=-1)
        time.sleep(0.01)

        with self.assertRaises(TokenExpiredError):
            decode_access_token(token)

    def test_malformed_access_token_raises_invalid_token(self):
        with self.assertRaises(InvalidTokenError):
            decode_access_token("not-a-jwt")

    def test_refresh_token_is_random_and_hashable(self):
        first = generate_refresh_token()
        second = generate_refresh_token()

        self.assertNotEqual(first, second)
        self.assertEqual(len(hash_refresh_token(first)), 64)
        self.assertEqual(hash_refresh_token(first), hash_refresh_token(first))
        self.assertNotEqual(hash_refresh_token(first), hash_refresh_token(second))


if __name__ == "__main__":
    unittest.main()
