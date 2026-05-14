import unittest

from app.auth.passwords import hash_password, verify_password


class AuthPasswordTests(unittest.TestCase):
    def test_argon2_hash_round_trips_for_correct_password(self):
        password_hash = hash_password("correct horse battery staple")

        self.assertTrue(password_hash.startswith("$argon2"))
        self.assertTrue(verify_password("correct horse battery staple", password_hash))

    def test_argon2_hash_rejects_wrong_password(self):
        password_hash = hash_password("correct horse battery staple")

        self.assertFalse(verify_password("wrong password", password_hash))


if __name__ == "__main__":
    unittest.main()
