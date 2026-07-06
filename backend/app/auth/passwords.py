"""Password hashing helpers."""

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    """Hash a plaintext password with argon2id."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return True when the plaintext password matches the stored hash."""
    try:
        return bool(_password_hasher.verify(password_hash, password))
    except Argon2Error:
        return False
