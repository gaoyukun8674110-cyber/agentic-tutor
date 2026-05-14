from app.auth.passwords import hash_password
from app.auth.tokens import encode_access_token
from app.models.user import User


def create_test_user(db, username: str = "alice", password: str = "password-123") -> User:
    user = User(
        username=username,
        email=None,
        password_hash=hash_password(password),
        is_active=True,
        created_at="2026-05-13T00:00:00+00:00",
        updated_at="2026-05-13T00:00:00+00:00",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def bearer_headers(username: str = "alice") -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(username)}"}
