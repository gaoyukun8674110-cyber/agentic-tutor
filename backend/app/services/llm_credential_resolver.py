"""Resolve the effective LLM provider for a user request."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import settings
from app.models.llm_credentials import UserLLMCredential
from app.models.user import User
from app.services.llm_credential_service import LLMCredentialService
from app.services.llm_provider_registry import global_provider_credentials, provider_registry


@dataclass(frozen=True)
class ResolvedProvider:
    provider_id: str
    api_key: str = field(repr=False)
    base_url: str
    default_model: str
    source: str
    fingerprint: str | None = None
    credential_id: int | None = None


class LLMCredentialResolver:
    """Combines registry, user credentials, and optional global fallback."""

    def __init__(self, db: Session):
        self.db = db
        self.credential_service = LLMCredentialService(db)

    def resolve(self, user: User, requested_provider: str | None = "auto") -> ResolvedProvider:
        registry = provider_registry()
        provider_id = self._choose_provider_id(user, requested_provider or "auto")
        if not provider_id or provider_id not in registry:
            raise ValueError("unsupported_provider")
        definition = registry[provider_id]
        if not definition.implemented or definition.adapter != "openai-compatible":
            raise ValueError("unsupported_provider")

        user_credential = self._enabled_credential(user, provider_id)
        if user_credential:
            return self._from_user_credential(user, user_credential)

        if definition.requires_api_key and not settings.ALLOW_GLOBAL_LLM_FALLBACK:
            raise ValueError("llm_provider_not_configured")

        global_credentials = global_provider_credentials(provider_id)
        api_key = global_credentials["api_key"]
        base_url = global_credentials["base_url"] or definition.base_url
        if definition.requires_api_key and not api_key:
            raise ValueError("llm_provider_not_configured")
        if not base_url:
            raise ValueError("llm_provider_not_configured")

        return ResolvedProvider(
            provider_id=provider_id,
            api_key=api_key or "ollama",
            base_url=base_url,
            default_model=definition.default_model,
            source="local" if provider_id == "ollama" else "global",
            fingerprint=None,
            credential_id=None,
        )

    def _choose_provider_id(self, user: User, requested_provider: str) -> str | None:
        if requested_provider != "auto":
            return requested_provider

        default_credential = (
            self.db.query(UserLLMCredential)
            .filter(
                UserLLMCredential.user_id == user.id,
                UserLLMCredential.is_enabled.is_(True),
                UserLLMCredential.is_default.is_(True),
            )
            .first()
        )
        if default_credential:
            return default_credential.provider_id

        registry = provider_registry()
        if settings.DEFAULT_LLM_PROVIDER != "auto":
            return settings.DEFAULT_LLM_PROVIDER

        for provider_id, definition in registry.items():
            if not definition.implemented or definition.adapter != "openai-compatible":
                continue
            if self._enabled_credential(user, provider_id):
                return provider_id
            global_credentials = global_provider_credentials(provider_id)
            if (
                settings.ALLOW_GLOBAL_LLM_FALLBACK
                and global_credentials["base_url"]
                and (not definition.requires_api_key or global_credentials["api_key"])
            ):
                return provider_id
        return None

    def _enabled_credential(self, user: User, provider_id: str) -> UserLLMCredential | None:
        return (
            self.db.query(UserLLMCredential)
            .filter(
                UserLLMCredential.user_id == user.id,
                UserLLMCredential.provider_id == provider_id,
                UserLLMCredential.is_enabled.is_(True),
            )
            .first()
        )

    def _from_user_credential(self, user: User, credential: UserLLMCredential) -> ResolvedProvider:
        definition = provider_registry()[credential.provider_id]
        api_key = self.credential_service.decrypt_for_provider_call(credential, user.id, credential.provider_id)
        return ResolvedProvider(
            provider_id=credential.provider_id,
            api_key=api_key,
            base_url=credential.base_url or definition.base_url or "",
            default_model=credential.default_model or definition.default_model,
            source="user",
            fingerprint=credential.api_key_fingerprint,
            credential_id=credential.id,
        )
