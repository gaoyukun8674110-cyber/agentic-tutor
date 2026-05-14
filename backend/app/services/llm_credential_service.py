"""CRUD, encryption, and safe metadata for user LLM credentials."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.llm_credentials import UserLLMCredential
from app.models.user import User
from app.services.llm_provider_registry import provider_registry


class CredentialAADMismatch(Exception):
    """Encrypted credential does not belong to the expected user/provider row."""


class CredentialEncryptionUnavailable(Exception):
    """Server cannot encrypt user credentials because no key is configured."""


class CredentialCorrupted(Exception):
    """Stored credential cannot be decrypted for provider use."""


class InvalidProviderBaseURL(Exception):
    """Custom provider base URL failed SSRF/whitelist checks."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad_prefix(user_id: int, provider_id: str) -> str:
    return f"v1|{user_id}|{provider_id}|"


def _fernet_from_key(raw_key: str) -> Fernet:
    return Fernet(raw_key.encode("utf-8"))


class LLMCredentialService:
    """Owns encrypted credential persistence and safe display metadata."""

    def __init__(self, db: Session | None = None):
        self.db = db

    def _fernet(self) -> MultiFernet:
        if not settings.LLM_CREDENTIAL_ENCRYPTION_KEY:
            raise CredentialEncryptionUnavailable()
        keys = [settings.LLM_CREDENTIAL_ENCRYPTION_KEY]
        keys.extend(key.strip() for key in (settings.LLM_CREDENTIAL_PREVIOUS_KEYS or "").split(",") if key.strip())
        return MultiFernet([_fernet_from_key(key) for key in keys])

    def _fingerprint_secret(self) -> str:
        if settings.LLM_FINGERPRINT_HMAC_KEY:
            return settings.LLM_FINGERPRINT_HMAC_KEY
        if settings.LLM_CREDENTIAL_ENCRYPTION_KEY:
            return hashlib.sha256(settings.LLM_CREDENTIAL_ENCRYPTION_KEY.encode("utf-8")).hexdigest()
        raise CredentialEncryptionUnavailable()

    def encrypt_api_key(self, api_key: str, user_id: int, provider_id: str) -> str:
        payload = f"{_aad_prefix(user_id, provider_id)}{api_key}"
        return self._fernet().encrypt(payload.encode("utf-8")).decode("utf-8")

    def decrypt_api_key(self, encrypted_api_key: str, user_id: int, provider_id: str) -> str:
        try:
            plaintext = self._fernet().decrypt(encrypted_api_key.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError) as error:
            raise CredentialCorrupted() from error
        expected = _aad_prefix(user_id, provider_id)
        if not plaintext.startswith(expected):
            raise CredentialAADMismatch()
        return plaintext[len(expected) :]

    def decrypt_for_provider_call(
        self,
        credential: UserLLMCredential,
        user_id: int,
        provider_id: str,
    ) -> str:
        if not credential.encrypted_api_key:
            return "ollama"
        return self.decrypt_api_key(credential.encrypted_api_key, user_id=user_id, provider_id=provider_id)

    def fingerprint_api_key(self, api_key: str) -> str:
        return hmac.new(
            key=self._fingerprint_secret().encode("utf-8"),
            msg=api_key.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()[:16]

    def get_user_credentials(self, user: User) -> list[UserLLMCredential]:
        if self.db is None:
            return []
        try:
            return (
                self.db.query(UserLLMCredential)
                .filter(UserLLMCredential.user_id == user.id)
                .order_by(UserLLMCredential.updated_at.desc())
                .all()
            )
        except OperationalError:
            self.db.rollback()
            return []

    def get_user_credential(self, user: User, provider_id: str) -> UserLLMCredential | None:
        if self.db is None:
            return None
        return (
            self.db.query(UserLLMCredential)
            .filter(UserLLMCredential.user_id == user.id, UserLLMCredential.provider_id == provider_id)
            .first()
        )

    def to_safe_metadata(self, credential: UserLLMCredential) -> dict[str, object]:
        return {
            "provider_id": credential.provider_id,
            "configured": bool(credential.encrypted_api_key) or credential.provider_id == "ollama",
            "enabled": bool(credential.is_enabled),
            "is_default": bool(credential.is_default),
            "base_url": credential.base_url,
            "default_model": credential.default_model,
            "api_key_fingerprint": credential.api_key_fingerprint,
            "last_validated_at": credential.last_validated_at,
            "last_validation_error_code": credential.last_validation_error_code,
            "last_used_at": credential.last_used_at,
            "updated_at": credential.updated_at,
        }

    def _unset_other_defaults(self, user: User, except_id: int | None = None) -> None:
        if self.db is None:
            return
        query = self.db.query(UserLLMCredential).filter(
            UserLLMCredential.user_id == user.id,
            UserLLMCredential.is_default.is_(True),
        )
        if except_id is not None:
            query = query.filter(UserLLMCredential.id != except_id)
        query.update({"is_default": False}, synchronize_session=False)

    def put_credential(
        self,
        *,
        user: User,
        provider_id: str,
        api_key: str | None,
        base_url: str | None,
        default_model: str | None,
        is_default: bool,
        is_enabled: bool,
    ) -> UserLLMCredential:
        if self.db is None:
            raise RuntimeError("database session required")
        registry = provider_registry()
        provider = registry[provider_id]
        if provider.requires_api_key and not (api_key and api_key.strip()):
            raise ValueError("api_key_required")
        now = utc_now_iso()
        credential = self.get_user_credential(user, provider_id)
        if credential is None:
            credential = UserLLMCredential(
                user_id=user.id,
                provider_id=provider_id,
                created_at=now,
                updated_at=now,
            )
            self.db.add(credential)

        cleaned_key = api_key.strip() if api_key else None
        credential.encrypted_api_key = (
            self.encrypt_api_key(cleaned_key, user_id=user.id, provider_id=provider_id)
            if cleaned_key
            else None
        )
        credential.api_key_fingerprint = self.fingerprint_api_key(cleaned_key) if cleaned_key else None
        credential.base_url = base_url.strip() if base_url else None
        credential.default_model = default_model.strip() if default_model else None
        credential.is_default = is_default
        credential.is_enabled = is_enabled
        credential.updated_at = now

        if is_default:
            self.db.flush()
            self._unset_other_defaults(user, credential.id)
            credential.is_default = True

        self.db.commit()
        self.db.refresh(credential)
        return credential

    def patch_credential(
        self,
        *,
        user: User,
        provider_id: str,
        base_url: str | None = None,
        default_model: str | None = None,
        is_default: bool | None = None,
        is_enabled: bool | None = None,
    ) -> UserLLMCredential:
        if self.db is None:
            raise RuntimeError("database session required")
        credential = self.get_user_credential(user, provider_id)
        if credential is None:
            raise KeyError(provider_id)
        if base_url is not None:
            credential.base_url = base_url.strip() or None
        if default_model is not None:
            credential.default_model = default_model.strip() or None
        if is_enabled is not None:
            credential.is_enabled = is_enabled
        if is_default is not None:
            credential.is_default = is_default
            if is_default:
                self.db.flush()
                self._unset_other_defaults(user, credential.id)
                credential.is_default = True
        credential.updated_at = utc_now_iso()
        self.db.commit()
        self.db.refresh(credential)
        return credential

    def delete_credential(self, *, user: User, provider_id: str) -> bool:
        if self.db is None:
            raise RuntimeError("database session required")
        credential = self.get_user_credential(user, provider_id)
        if credential is None:
            return False
        was_default = bool(credential.is_default)
        self.db.delete(credential)
        self.db.flush()
        if was_default:
            replacement = (
                self.db.query(UserLLMCredential)
                .filter(UserLLMCredential.user_id == user.id, UserLLMCredential.is_enabled.is_(True))
                .order_by(UserLLMCredential.updated_at.desc())
                .first()
            )
            if replacement:
                replacement.is_default = True
        self.db.commit()
        return True

    def record_used(self, credential_id: int | None) -> None:
        if self.db is None or credential_id is None:
            return
        credential = self.db.get(UserLLMCredential, credential_id)
        if not credential:
            return
        credential.last_used_at = utc_now_iso()
        credential.updated_at = credential.updated_at or credential.last_used_at
        self.db.commit()


ALLOWED_PROVIDER_HOSTS = {
    "api.openai.com",
    "api.deepseek.com",
    "dashscope.aliyuncs.com",
    "api.linkapi.ai",
}


def validate_provider_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    parsed = urlparse(base_url)
    if parsed.scheme != "https":
        if not (settings.DEBUG and parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise InvalidProviderBaseURL()
    if not parsed.hostname:
        raise InvalidProviderBaseURL()

    hostname = parsed.hostname.lower()
    if hostname not in ALLOWED_PROVIDER_HOSTS:
        if not (settings.DEBUG and hostname in {"localhost", "127.0.0.1", "::1"}):
            raise InvalidProviderBaseURL()
        _reject_private_host(hostname)
    return base_url.rstrip("/")


def _reject_private_host(hostname: str) -> None:
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        if settings.DEBUG and hostname == "localhost":
            return
        try:
            addresses = [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(hostname, None)]
        except socket.gaierror as error:
            raise InvalidProviderBaseURL() from error

    for address in addresses:
        if address.is_loopback and settings.DEBUG and hostname in {"localhost", "127.0.0.1", "::1"}:
            continue
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise InvalidProviderBaseURL()
