"""API error helpers."""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("ai_tutor")

ENGLISH_TO_CHINESE_MESSAGES = {
    "Missing access token": "缺少访问令牌",
    "Invalid access token": "访问令牌无效",
    "Access token expired": "访问令牌已过期",
    "User not allowed": "当前用户不可用",
    "Invalid credentials": "用户名或密码错误",
    "User is not authorized for this resource": "当前用户无权访问该资源",
    "Model provider is temporarily unavailable": "模型服务暂时不可用",
    "Task not found": "任务不存在",
    "Conversation not found": "会话不存在",
    "Question not found": "题目不存在",
    "No more questions or session ended": "没有更多题目，或训练已结束",
    "Request failed": "请求失败",
    "Internal error": "内部错误",
}
CHINESE_TO_ENGLISH_MESSAGES = {value: key for key, value in ENGLISH_TO_CHINESE_MESSAGES.items()}
UPLOAD_TOO_LARGE_PATTERN = re.compile(r"^Upload exceeds (?P<limit>\d+) MB limit$")
UNSUPPORTED_TYPE_PATTERN = re.compile(r"^Unsupported material file type: (?P<suffix>.+)$")
INVALID_ZIP_PATTERN = re.compile(r"^(?P<suffix>\.[a-z0-9]+) upload does not look like a valid ZIP-based document$")
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*=\s*)[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"(Authorization\s*:\s*)[^\s,\)'\"]+", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b"),
]


def preferred_language(accept_language: str | None) -> str:
    if not accept_language:
        return "en"

    primary_tag = accept_language.split(",", 1)[0].strip().lower()
    return "zh" if primary_tag.startswith("zh") else "en"


def localize_user_message(message: str, accept_language: str | None) -> str:
    language = preferred_language(accept_language)
    if not message:
        return ENGLISH_TO_CHINESE_MESSAGES["Request failed"] if language == "zh" else "Request failed"

    if language == "zh":
        if message in ENGLISH_TO_CHINESE_MESSAGES:
            return ENGLISH_TO_CHINESE_MESSAGES[message]

        if match := UPLOAD_TOO_LARGE_PATTERN.match(message):
            return f"上传内容超过 {match.group('limit')} MB 限制"
        if match := UNSUPPORTED_TYPE_PATTERN.match(message):
            return f"不支持的资料文件类型：{match.group('suffix')}"
        if match := INVALID_ZIP_PATTERN.match(message):
            return f"{match.group('suffix')} 文件看起来不是有效的 ZIP 文档"
        if message == "PDF upload does not start with a PDF signature":
            return "PDF 文件不是有效的 PDF 格式"
        if message == "Text uploads must be valid UTF-8":
            return "文本文件必须是有效的 UTF-8 编码"

        return message

    if message in CHINESE_TO_ENGLISH_MESSAGES:
        return CHINESE_TO_ENGLISH_MESSAGES[message]

    return message


def new_trace_id() -> str:
    return uuid.uuid4().hex


def public_error(code: str, user_message: str, trace_id: str | None = None) -> dict[str, str]:
    return {
        "code": code,
        "user_message": user_message,
        "trace_id": trace_id or new_trace_id(),
    }


def api_error(status_code: int, code: str, user_message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=public_error(code, user_message))


def redact_secrets(value: Any) -> str:
    text = repr(value) if not isinstance(value, str) else value
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]", text)
    return text


def code_for_status(status_code: int) -> str:
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "not_found"
    if status_code >= 500:
        return "internal_error"
    return "request_error"


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    trace_id = new_trace_id()
    detail = exc.detail
    if isinstance(detail, dict) and {"code", "user_message", "trace_id"}.issubset(detail):
        payload = {
            **detail,
            "user_message": localize_user_message(str(detail.get("user_message", "")), request.headers.get("accept-language")),
        }
    else:
        user_message = str(detail) if detail else "Request failed"
        payload = public_error(
            code_for_status(exc.status_code),
            localize_user_message(user_message, request.headers.get("accept-language")),
            trace_id,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": payload},
        headers={"X-Trace-Id": payload["trace_id"]},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = new_trace_id()
    logger.exception("Unhandled API error trace_id=%s path=%s", trace_id, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": public_error(
                "internal_error",
                localize_user_message("Internal error", request.headers.get("accept-language")),
                trace_id,
            )
        },
        headers={"X-Trace-Id": trace_id},
    )


def safe_llm_error(error: Any, accept_language: str | None = None) -> dict[str, str]:
    trace_id = new_trace_id()
    logger.error("LLM provider error trace_id=%s error=%s", trace_id, redact_secrets(error))
    return public_error(
        "llm_provider_error",
        localize_user_message("Model provider is temporarily unavailable", accept_language),
        trace_id,
    )
