"""LLM 相关 API"""

import time
from collections import deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.analytics import AnalyticsService
from app.services.chat_history import ChatHistoryService
from app.services.llm_credential_resolver import LLMCredentialResolver, ResolvedProvider
from app.services.llm_credential_service import (
    CredentialAADMismatch,
    CredentialCorrupted,
    CredentialEncryptionUnavailable,
    InvalidProviderBaseURL,
    LLMCredentialService,
    validate_provider_base_url,
)
from app.services.llm_provider_registry import global_provider_credentials, provider_registry
from app.services.llm_service import LLMService
from app.services.materials import MaterialService
from app.utils.errors import api_error, safe_llm_error

router = APIRouter(prefix="/api/llm", tags=["llm"], dependencies=[Depends(get_current_user)])
_credential_test_windows: dict[tuple[int, str], deque[float]] = {}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    conversation_id: int | None = None
    provider: str = "auto"
    model: str | None = None
    prompt_profile: str = "three_stage"
    system_prompt_override: str | None = None
    messages: list[ChatMessage]
    tutor_context: dict[str, Any] = Field(default_factory=dict)


class HintRequest(BaseModel):
    question_content: str
    student_answer: str | None = None
    step: int = 1


class ExplainRequest(BaseModel):
    question_content: str
    standard_solution: str
    solution_steps: list | None = None


class DiagnoseRequest(BaseModel):
    question_content: str
    student_answer: str
    correct_answer: str
    standard_solution: str


class SummaryRequest(BaseModel):
    session_stats: dict


class UserLLMCredentialPutIn(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    is_default: bool = False
    is_enabled: bool = True


class UserLLMCredentialPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    default_model: str | None = None
    is_default: bool | None = None
    is_enabled: bool | None = None


def get_llm_service(request: Request) -> LLMService:
    llm_service = getattr(request.app.state, "llm_service", None)
    if llm_service is None:
        llm_service = LLMService()
        request.app.state.llm_service = llm_service
    return llm_service


def _validate_provider_for_write(provider_id: str) -> None:
    provider = provider_registry().get(provider_id)
    if not provider or not provider.implemented or provider.adapter != "openai-compatible":
        raise api_error(status.HTTP_400_BAD_REQUEST, "unsupported_provider", "Unsupported provider")


def _resolve_provider_or_raise(db: Session, user: User, provider: str | None = "auto") -> ResolvedProvider:
    try:
        return LLMCredentialResolver(db).resolve(user, provider or "auto")
    except ValueError as error:
        code = str(error)
        if code == "unsupported_provider":
            raise api_error(status.HTTP_400_BAD_REQUEST, "unsupported_provider", "Unsupported provider") from error
        if code == "llm_provider_not_configured":
            raise api_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "llm_provider_not_configured",
                "Model provider is not configured",
            ) from error
        raise
    except (CredentialAADMismatch, CredentialCorrupted) as error:
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "llm_credentials_corrupted",
            "Stored model credential is invalid",
        ) from error


def _enforce_test_rate_limit(user_id: int, provider_id: str) -> None:
    now = time.time()
    key = (user_id, provider_id)
    window = _credential_test_windows.setdefault(key, deque())
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= 5:
        raise api_error(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", "Too many requests")
    window.append(now)


def _safe_provider_metadata_for_user(db: Session, user: User) -> dict[str, Any]:
    credential_service = LLMCredentialService(db)
    credentials = {credential.provider_id: credential for credential in credential_service.get_user_credentials(user)}
    providers = []
    for provider_id, definition in provider_registry().items():
        credential = credentials.get(provider_id)
        global_credentials = global_provider_credentials(provider_id)
        has_global = bool(global_credentials["base_url"]) and (
            not definition.requires_api_key or bool(global_credentials["api_key"])
        )
        has_user = bool(
            credential and credential.is_enabled and (credential.encrypted_api_key or not definition.requires_api_key)
        )
        source = "user" if has_user else ("local" if provider_id == "ollama" else ("global" if has_global else "none"))
        enabled = definition.implemented and (
            has_user or has_global or (provider_id == "ollama" and bool(definition.base_url))
        )
        reason = None
        if not definition.implemented:
            reason = "provider adapter is not implemented yet"
        elif not enabled:
            reason = "provider credentials are not configured"
        providers.append(
            {
                "id": provider_id,
                "name": definition.name,
                "adapter": definition.adapter,
                "enabled": enabled,
                "implemented": definition.implemented,
                "default_model": (
                    credential.default_model if credential and credential.default_model else definition.default_model
                ),
                "models": definition.models,
                "reason": reason,
                "source": source,
                "configured": bool(credential),
                "credential_updated_at": credential.updated_at if credential else None,
            }
        )
    return {"providers": providers}


def _last_user_message(messages: list[ChatMessage]) -> str | None:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return None


def _normalize_material_ids(raw_material_ids: Any) -> list[int] | None:
    if raw_material_ids is None:
        return None
    if not isinstance(raw_material_ids, list):
        return []

    material_ids: list[int] = []
    for raw_id in raw_material_ids:
        try:
            material_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if material_id > 0:
            material_ids.append(material_id)
    return material_ids


def _inject_material_context(
    tutor_context: dict[str, Any],
    last_user_message: str | None,
    material_service: MaterialService,
    user_id: str | None,
    top_k: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_context = dict(tutor_context)
    cleaned_message = (last_user_message or "").strip()
    if not cleaned_message:
        next_context.pop("material_context", None)
        return next_context, []

    selected_material_ids = _normalize_material_ids(next_context.get("material_ids"))
    if "material_ids" in next_context and not selected_material_ids:
        next_context.pop("material_context", None)
        return next_context, []

    chunks = material_service.search_materials(
        query=cleaned_message,
        user_id=user_id,
        material_ids=selected_material_ids,
        top_k=top_k,
    )
    if chunks:
        next_context["material_context"] = {"chunks": chunks}
    else:
        next_context.pop("material_context", None)
    return next_context, chunks


def _prepare_tutor_context(
    request: ChatRequest,
    llm: LLMService,
    db: Session,
    user_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None, str]:
    last_user_message = _last_user_message(request.messages)
    tutor_context = dict(request.tutor_context)
    tutor_context.pop("material_context_error", None)
    detected_learning_phase = llm.detect_learning_phase(last_user_message)
    previous_learning_phase = str(tutor_context.get("learning_phase") or "")
    learning_phase = (
        previous_learning_phase
        if detected_learning_phase == "general" and previous_learning_phase
        else detected_learning_phase
    )
    tutor_context["learning_phase"] = learning_phase

    retrieved_material_chunks: list[dict[str, Any]] = []
    try:
        material_service = MaterialService(db)
        tutor_context, retrieved_material_chunks = _inject_material_context(
            tutor_context=tutor_context,
            last_user_message=last_user_message,
            material_service=material_service,
            user_id=user_id,
            top_k=settings.RAG_TOP_K,
        )
    except Exception:
        tutor_context["material_context_error"] = "Material search is temporarily unavailable"

    return tutor_context, retrieved_material_chunks, last_user_message, learning_phase


def _build_model_messages(
    request: ChatRequest,
    history: ChatHistoryService,
    last_user_message: str | None,
    user_id: str,
) -> tuple[list[dict[str, Any]], str]:
    model_messages = [message.model_dump() for message in request.messages]
    context_policy = "full"
    if request.conversation_id is not None and last_user_message:
        compact_messages = history.build_model_messages(
            conversation_id=request.conversation_id,
            pending_user_message=last_user_message,
            user_id=user_id,
        )
        if compact_messages:
            return compact_messages, "summary_recent"
    return model_messages, context_policy


def _finalize_conversation_response(
    result: dict[str, Any],
    request: ChatRequest,
    history: ChatHistoryService,
    llm: LLMService,
    resolved: ResolvedProvider,
    tutor_context: dict[str, Any],
    last_user_message: str | None,
    user_id: str,
    session_id: int | None,
    analytics: AnalyticsService | None = None,
) -> dict[str, Any]:
    assistant_message = result.get("message", {}).get("content")
    if not last_user_message or not assistant_message:
        return result

    try:
        conversation = history.save_exchange(
            conversation_id=request.conversation_id,
            user_message=last_user_message,
            assistant_message=assistant_message,
            prompt_profile=result.get("prompt_profile", request.prompt_profile),
            provider=result.get("provider", request.provider),
            model=result.get("model", request.model or ""),
            training_mode=str(tutor_context.get("mode") or "") or None,
            user_id=user_id,
            assistant_label="Tutor",
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    summary_generated = False
    if history.needs_summary(conversation["id"], conversation["message_count"]):
        detail = history.get_conversation(conversation["id"], user_id=user_id)
        if detail:
            fallback_summary = history.build_fallback_summary(detail["messages"])
            summary_request = request.model_copy(update={"tutor_context": tutor_context})
            summary = _generate_conversation_summary(
                llm=llm,
                resolved=resolved,
                request=summary_request,
                conversation=detail,
                fallback_summary=fallback_summary,
                user_id=user_id,
                session_id=session_id,
                analytics=analytics,
            )
            history.save_summary(
                conversation_id=conversation["id"],
                content=summary,
                source_message_count=conversation["message_count"],
                user_id=user_id,
            )
            conversation = history.get_conversation(conversation["id"], user_id=user_id) or conversation
            summary_generated = True

    conversation_detail = history.get_conversation(conversation["id"], user_id=user_id) or conversation
    result["conversation_id"] = conversation["id"]
    result["conversation"] = conversation_detail
    result["messages"] = conversation_detail.get("messages", [])
    result["exchange_count"] = conversation_detail.get("exchange_count")
    result["should_suggest_new_chat"] = conversation_detail.get("should_suggest_new_chat", False)
    result["should_start_new_chat"] = conversation_detail.get("should_start_new_chat", False)
    result["summary_generated"] = summary_generated
    return result


def _generate_conversation_summary(
    llm: LLMService,
    resolved: ResolvedProvider,
    request: ChatRequest,
    conversation: dict[str, Any],
    fallback_summary: str,
    user_id: str | None,
    session_id: int | None,
    analytics: AnalyticsService | None = None,
) -> str:
    learning_phase = str(request.tutor_context.get("learning_phase") or "general")
    transcript = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in conversation.get("messages", [])
        if message.get("role") in {"user", "assistant"}
    )
    summary_prompt = (
        "Summarize this AI Tutor learning conversation for the next session.\n"
        f"Current learning phase: {learning_phase}\n"
        "Keep these fields when present: learning goal, the key 20% knowledge points, understood concepts, "
        "stuck concepts, Feynman gaps, tutor hints already given, and next learning step.\n"
        "Do not repeat small talk or irrelevant content. Keep the summary under 300 Chinese characters or 180 English words.\n\n"
        f"Conversation transcript:\n{transcript}"
    )

    result = llm.complete_chat(
        resolved=resolved,
        messages=[{"role": "user", "content": summary_prompt}],
        prompt_profile="custom",
        system_prompt_override="You summarize AI Tutor sessions. Output only reusable learning-state summary text.",
        tutor_context={"task": "conversation_summary", "learning_phase": learning_phase},
        agent_type=f"conversation_summary:{resolved.provider_id}",
        user_id=user_id,
        session_id=session_id,
        analytics=analytics,
        model=request.model,
    )
    if "error" in result:
        return fallback_summary
    return result.get("message", {}).get("content") or fallback_summary


def _mock_e2e_chat_result(request: ChatRequest, learning_phase: str) -> tuple[dict[str, Any], ResolvedProvider]:
    return (
        {
            "message": {
                "role": "assistant",
                "content": "E2E mock tutor response: keep going step by step.",
            },
            "provider": "e2e-mock",
            "model": "e2e-mock",
            "prompt_profile": request.prompt_profile,
            "learning_phase": learning_phase,
            "credential_source": "local",
            "credential_fingerprint": None,
        },
        ResolvedProvider(
            provider_id="e2e-mock",
            api_key="e2e-mock",
            base_url="http://127.0.0.1/e2e-mock",
            default_model="e2e-mock",
            source="local",
        ),
    )


@router.get("/credentials", response_model=dict)
def list_credentials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    credential_service = LLMCredentialService(db)
    return {
        "credentials": [
            credential_service.to_safe_metadata(credential)
            for credential in credential_service.get_user_credentials(current_user)
        ]
    }


@router.put("/credentials/{provider_id}", response_model=dict)
def put_credential(
    provider_id: str,
    payload: UserLLMCredentialPutIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_provider_for_write(provider_id)
    provider = provider_registry()[provider_id]
    if provider.requires_api_key and not (payload.api_key and len(payload.api_key.strip()) >= 8):
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "api_key_required", "API key is required")
    try:
        base_url = validate_provider_base_url(payload.base_url)
        credential = LLMCredentialService(db).put_credential(
            user=current_user,
            provider_id=provider_id,
            api_key=payload.api_key,
            base_url=base_url,
            default_model=payload.default_model,
            is_default=payload.is_default,
            is_enabled=payload.is_enabled,
        )
    except InvalidProviderBaseURL as error:
        raise api_error(
            status.HTTP_400_BAD_REQUEST, "invalid_provider_base_url", "Invalid provider base URL"
        ) from error
    except CredentialEncryptionUnavailable as error:
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "llm_credentials_encryption_unavailable",
            "Credential encryption is not configured",
        ) from error
    return {"credential": LLMCredentialService(db).to_safe_metadata(credential)}


@router.patch("/credentials/{provider_id}", response_model=dict)
def patch_credential(
    provider_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_provider_for_write(provider_id)
    if "api_key" in payload:
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "api_key_must_use_put", "API key updates must use PUT")
    patch = UserLLMCredentialPatchIn.model_validate(payload)
    try:
        base_url = validate_provider_base_url(patch.base_url) if patch.base_url is not None else None
        credential = LLMCredentialService(db).patch_credential(
            user=current_user,
            provider_id=provider_id,
            base_url=base_url,
            default_model=patch.default_model,
            is_default=patch.is_default,
            is_enabled=patch.is_enabled,
        )
    except KeyError as error:
        raise api_error(status.HTTP_404_NOT_FOUND, "not_found", "Credential not found") from error
    except InvalidProviderBaseURL as error:
        raise api_error(
            status.HTTP_400_BAD_REQUEST, "invalid_provider_base_url", "Invalid provider base URL"
        ) from error
    return {"credential": LLMCredentialService(db).to_safe_metadata(credential)}


@router.delete("/credentials/{provider_id}", response_model=dict)
def delete_credential(
    provider_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_provider_for_write(provider_id)
    deleted = LLMCredentialService(db).delete_credential(user=current_user, provider_id=provider_id)
    return {"deleted": deleted}


@router.post("/credentials/{provider_id}/test", response_model=dict)
def test_credential(
    provider_id: str,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
    current_user: User = Depends(get_current_user),
):
    _validate_provider_for_write(provider_id)
    _enforce_test_rate_limit(current_user.id, provider_id)
    resolved = _resolve_provider_or_raise(db, current_user, provider_id)
    result = llm.complete_chat(
        resolved=resolved,
        messages=[{"role": "user", "content": "Reply with OK only."}],
        prompt_profile="custom",
        system_prompt_override="You are a connectivity test. Reply with OK only.",
        agent_type=f"credential_test:{provider_id}",
        user_id=current_user.username,
        session_id=None,
        analytics=None,
        max_tokens=8,
        temperature=0,
    )
    if "error" in result:
        raise api_error(
            status.HTTP_502_BAD_GATEWAY,
            "llm_provider_validation_failed",
            "Model provider is temporarily unavailable",
        )
    if resolved.source == "user":
        LLMCredentialService(db).record_used(resolved.credential_id)
    return {"ok": True, "credential_source": result.get("credential_source")}


@router.get("/providers", response_model=dict)
def provider_metadata(
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
    current_user: User = Depends(get_current_user),
):
    """获取可用模型 Provider 元数据，不返回任何 API Key"""
    return _safe_provider_metadata_for_user(db, current_user)


@router.get("/prompt-profiles", response_model=dict)
def prompt_profiles(
    llm: LLMService = Depends(get_llm_service),
    current_user: User = Depends(get_current_user),
):
    """获取可用 Tutor 系统提示词配置"""
    return llm.get_prompt_profiles()


@router.get("/conversations", response_model=dict)
def conversation_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List persisted Tutor conversations."""
    user_id = current_user.username
    history = ChatHistoryService(db)
    return {"conversations": history.list_conversations(user_id=user_id, limit=limit)}


@router.get("/conversations/search", response_model=dict)
def search_conversation_history(
    query: str,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search persisted Tutor conversations by title, summary, and message text."""
    user_id = current_user.username
    history = ChatHistoryService(db)
    return {"conversations": history.search_conversations(query=query, user_id=user_id, limit=limit)}


@router.get("/conversations/{conversation_id}", response_model=dict)
def conversation_detail(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Load one persisted Tutor conversation with messages."""
    user_id = current_user.username
    history = ChatHistoryService(db)
    conversation = history.get_conversation(conversation_id, user_id=user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/conversations/{conversation_id}/export", response_model=dict)
def export_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export one Tutor conversation as Markdown content."""
    user_id = current_user.username
    history = ChatHistoryService(db)
    exported = history.export_conversation_markdown(conversation_id, user_id=user_id)
    if not exported:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return exported


@router.delete("/conversations/{conversation_id}", response_model=dict)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a persisted Tutor conversation."""
    user_id = current_user.username
    history = ChatHistoryService(db)
    deleted = history.delete_conversation(conversation_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@router.post("/chat", response_model=dict)
async def tutor_chat(
    request: ChatRequest,
    session_id: int | None = None,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
    current_user: User = Depends(get_current_user),
):
    """统一 Tutor 对话入口，支持多 Provider 后端代理"""
    user_id = current_user.username
    analytics = AnalyticsService(db)
    history = ChatHistoryService(db)

    conversation_before = None
    if request.conversation_id is not None:
        conversation_before = history.get_conversation(request.conversation_id, user_id=user_id)
        if not conversation_before:
            raise HTTPException(status_code=404, detail="Conversation not found")

    tutor_context, retrieved_material_chunks, last_user_message, learning_phase = _prepare_tutor_context(
        request=request,
        llm=llm,
        db=db,
        user_id=user_id,
    )
    model_messages, context_policy = _build_model_messages(
        request=request,
        history=history,
        last_user_message=last_user_message,
        user_id=user_id,
    )

    if settings.E2E_MOCK_LLM:
        result, resolved = _mock_e2e_chat_result(request, learning_phase)
        result = _finalize_conversation_response(
            result=result,
            request=request,
            history=history,
            llm=llm,
            resolved=resolved,
            tutor_context=tutor_context,
            last_user_message=last_user_message,
            user_id=user_id,
            session_id=session_id,
            analytics=analytics,
        )
        result["context_policy"] = context_policy
        result["material_context_error"] = tutor_context.get("material_context_error")
        if retrieved_material_chunks:
            result["material_context"] = {"chunks": retrieved_material_chunks}
        return result

    resolved = _resolve_provider_or_raise(db, current_user, request.provider)
    result = await run_in_threadpool(
        llm.complete_chat,
        resolved=resolved,
        model=request.model,
        messages=model_messages,
        prompt_profile=request.prompt_profile,
        system_prompt_override=request.system_prompt_override,
        tutor_context=tutor_context,
        agent_type=f"tutor_chat:{request.prompt_profile}:{resolved.provider_id}",
        user_id=user_id,
        session_id=session_id,
        analytics=analytics,
    )

    if "error" in result:
        detail = result["error"] if isinstance(result["error"], dict) else safe_llm_error(result["error"])
        raise HTTPException(status_code=502, detail=detail)
    if resolved.source == "user":
        LLMCredentialService(db).record_used(resolved.credential_id)

    result = _finalize_conversation_response(
        result=result,
        request=request,
        history=history,
        llm=llm,
        resolved=resolved,
        tutor_context=tutor_context,
        last_user_message=last_user_message,
        user_id=user_id,
        session_id=session_id,
        analytics=analytics,
    )

    result["context_policy"] = context_policy
    result["learning_phase"] = result.get("learning_phase", learning_phase)
    result["material_context_error"] = tutor_context.get("material_context_error")
    if retrieved_material_chunks:
        result["material_context"] = {"chunks": retrieved_material_chunks}

    return result


@router.post("/hint", response_model=dict)
def generate_hint(
    request: HintRequest,
    session_id: int | None = None,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
    current_user: User = Depends(get_current_user),
):
    """生成提示"""
    user_id = current_user.username
    analytics = AnalyticsService(db)
    prompt = f"""题目：{request.question_content}

学生当前答案：{request.student_answer if request.student_answer else "尚未作答"}

请给出第 {request.step} 步的提示（hint），不要直接给答案。提示应该：
1. 引导学生思考下一步应该做什么
2. 用提问的方式，而不是陈述
3. 简短、精准，不超过 50 字"""
    resolved = _resolve_provider_or_raise(db, current_user, "auto")
    result = llm.complete_chat(
        resolved=resolved,
        messages=[{"role": "user", "content": prompt}],
        prompt_profile="custom",
        system_prompt_override=llm.agent_prompts["tutor"],
        agent_type=f"tutor_hint:{resolved.provider_id}",
        user_id=user_id,
        session_id=session_id,
        analytics=analytics,
        max_tokens=200,
        temperature=0.7,
    )

    if "error" in result:
        raise api_error(502, "llm_provider_error", "Model provider is temporarily unavailable")
    if resolved.source == "user":
        LLMCredentialService(db).record_used(resolved.credential_id)

    return {
        "hint": result.get("message", {}).get("content"),
        "step": request.step,
        "agent_type": "tutor",
        "credential_source": result.get("credential_source"),
        "credential_fingerprint": result.get("credential_fingerprint"),
    }


@router.post("/explain", response_model=dict)
def explain_solution(
    request: ExplainRequest,
    session_id: int | None = None,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
    current_user: User = Depends(get_current_user),
):
    """讲解标准解"""
    user_id = current_user.username
    analytics = AnalyticsService(db)
    steps_text = ""
    if request.solution_steps:
        for index, step in enumerate(request.solution_steps, 1):
            steps_text += f"\n步骤 {index}: {step.get('description', '') if isinstance(step, dict) else step}"
    prompt = f"""题目：{request.question_content}

标准答案：{request.standard_solution}
解题步骤：{steps_text}

请用通俗易懂的语言讲解这道题的解法，包括：
1. 解题思路
2. 关键步骤的解释
3. 为什么这样做"""
    resolved = _resolve_provider_or_raise(db, current_user, "auto")
    result = llm.complete_chat(
        resolved=resolved,
        messages=[{"role": "user", "content": prompt}],
        prompt_profile="custom",
        system_prompt_override=llm.agent_prompts["tutor"],
        agent_type=f"tutor_explain:{resolved.provider_id}",
        user_id=user_id,
        session_id=session_id,
        analytics=analytics,
        max_tokens=500,
        temperature=0.7,
    )

    if "error" in result:
        raise api_error(502, "llm_provider_error", "Model provider is temporarily unavailable")
    if resolved.source == "user":
        LLMCredentialService(db).record_used(resolved.credential_id)

    return {
        "explanation": result.get("message", {}).get("content"),
        "agent_type": "tutor",
        "credential_source": result.get("credential_source"),
        "credential_fingerprint": result.get("credential_fingerprint"),
    }


@router.post("/diagnose", response_model=dict)
def diagnose_error(
    request: DiagnoseRequest,
    session_id: int | None = None,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
    current_user: User = Depends(get_current_user),
):
    """诊断错误"""
    user_id = current_user.username
    analytics = AnalyticsService(db)
    math_verification = llm.math_tools.verify_answer(request.student_answer, request.correct_answer)
    prompt = f"""题目：{request.question_content}

学生答案：{request.student_answer}
正确答案：{request.correct_answer}
标准解法：{request.standard_solution}

数学工具验证结果：{math_verification.get('result', 'unknown')}

请诊断学生的错误：
1. 具体哪里错了
2. 错误的原因（概念理解错误？计算错误？方法错误？）
3. 正确的思路应该是什么
4. 给出改进建议"""
    resolved = _resolve_provider_or_raise(db, current_user, "auto")
    result = llm.complete_chat(
        resolved=resolved,
        messages=[{"role": "user", "content": prompt}],
        prompt_profile="custom",
        system_prompt_override=llm.agent_prompts["diagnosis"],
        agent_type=f"diagnosis:{resolved.provider_id}",
        user_id=user_id,
        session_id=session_id,
        analytics=analytics,
        max_tokens=400,
        temperature=0.5,
    )

    if "error" in result:
        raise api_error(502, "llm_provider_error", "Model provider is temporarily unavailable")
    if resolved.source == "user":
        LLMCredentialService(db).record_used(resolved.credential_id)

    diagnosis = result.get("message", {}).get("content") or ""
    return {
        "diagnosis": diagnosis,
        "error_type": llm._extract_error_type(diagnosis),
        "math_verification": math_verification,
        "agent_type": "diagnosis",
        "credential_source": result.get("credential_source"),
        "credential_fingerprint": result.get("credential_fingerprint"),
    }


@router.post("/summary", response_model=dict)
def session_summary(
    request: SummaryRequest,
    session_id: int | None = None,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
    current_user: User = Depends(get_current_user),
):
    """生成 Session 总结"""
    user_id = current_user.username
    analytics = AnalyticsService(db)
    prompt = f"""本次训练 Session 统计：
- 总题数：{request.session_stats.get('total_questions', 0)}
- 正确数：{request.session_stats.get('correct_count', 0)}
- 正确率：{request.session_stats.get('correct_rate', 0):.1%}
- 平均用时：{request.session_stats.get('average_time', 0):.1f} 秒

请生成一段鼓励性的总结，包括：
1. 肯定学生的努力
2. 指出进步的地方
3. 给出下一步学习建议
4. 保持积极正面的语调"""
    resolved = _resolve_provider_or_raise(db, current_user, "auto")
    result = llm.complete_chat(
        resolved=resolved,
        messages=[{"role": "user", "content": prompt}],
        prompt_profile="custom",
        system_prompt_override=llm.agent_prompts["pomodoro_coach"],
        agent_type=f"pomodoro_coach:{resolved.provider_id}",
        user_id=user_id,
        session_id=session_id,
        analytics=analytics,
        max_tokens=300,
        temperature=0.8,
    )

    if "error" in result:
        raise api_error(502, "llm_provider_error", "Model provider is temporarily unavailable")
    if resolved.source == "user":
        LLMCredentialService(db).record_used(resolved.credential_id)

    return {
        "summary": result.get("message", {}).get("content"),
        "agent_type": "pomodoro_coach",
        "credential_source": result.get("credential_source"),
        "credential_fingerprint": result.get("credential_fingerprint"),
    }
