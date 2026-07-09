"""Deterministic web-search tool with Tavily provider support."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import settings

FALLBACK_WEB_CONTENT = "当前无法联网核实，以下基于通用知识回答。"
_CACHE_TTL_SECONDS = 15 * 60
_MAX_CONTENT_CHARS = 1200


def _httpx_proxy_kwarg() -> str:
    """Return the httpx.Client single-proxy kwarg name for the installed version.

    httpx <0.26 uses ``proxies``; 0.26+ renamed it to ``proxy`` and removed
    ``proxies`` in 0.28. Pick the right one so a configured WEB_SEARCH_PROXY
    works across versions instead of silently raising and degrading.
    """
    try:
        major, minor, *_ = (int(part) for part in httpx.__version__.split(".")[:2])
    except (ValueError, AttributeError):
        return "proxy"
    return "proxy" if (major, minor) >= (0, 26) else "proxies"


class WebSearchProvider(Protocol):
    def search(self, query: str, *, max_results: int, timeout: float) -> list[dict[str, Any]]: ...


@dataclass(slots=True)
class TavilyProvider:
    api_key: str | None
    proxy: str | None = None

    def search(self, query: str, *, max_results: int, timeout: float) -> list[dict[str, Any]]:
        if not self.api_key:
            return [fallback_web_chunk()]

        request_kwargs: dict[str, Any] = {"timeout": timeout}
        if self.proxy:
            # httpx renamed the single-proxy kwarg `proxies` -> `proxy` in 0.26.
            request_kwargs[_httpx_proxy_kwarg()] = self.proxy

        with httpx.Client(**request_kwargs) as client:
            response = client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
            response.raise_for_status()
            payload = response.json()

        results = payload.get("results") if isinstance(payload, dict) else []
        normalized: list[dict[str, Any]] = []
        for result in results[:max_results]:
            if not isinstance(result, dict):
                continue
            content = str(result.get("content") or "").strip()
            url = str(result.get("url") or "").strip()
            title = str(result.get("title") or url or "Web source").strip()
            if not content:
                continue
            normalized.append(
                {
                    "content": content[:_MAX_CONTENT_CHARS],
                    "source_label": title,
                    "url": url,
                    "score": float(result.get("score") or 0.0),
                    "origin": "web",
                }
            )
        return normalized or [fallback_web_chunk()]


def fallback_web_chunk() -> dict[str, Any]:
    return {
        "content": FALLBACK_WEB_CONTENT,
        "source_label": "Web search unavailable",
        "url": "",
        "score": 0.0,
        "origin": "web",
        "error": "web_search_unavailable",
    }


class WebSearchTool:
    name = "web_search"

    def __init__(self, provider: WebSearchProvider | None = None):
        self.provider = provider or TavilyProvider(
            api_key=settings.WEB_SEARCH_API_KEY,
            proxy=settings.WEB_SEARCH_PROXY,
        )
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        now = time.time()
        cache_key = normalized_query.lower()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return [dict(item) for item in cached[1]]

        try:
            chunks = self.provider.search(
                normalized_query,
                max_results=max_results or settings.WEB_SEARCH_MAX_RESULTS,
                timeout=timeout or settings.WEB_SEARCH_TIMEOUT,
            )
        except Exception:
            chunks = [fallback_web_chunk()]

        self._cache[cache_key] = (now, [dict(item) for item in chunks])
        return chunks
