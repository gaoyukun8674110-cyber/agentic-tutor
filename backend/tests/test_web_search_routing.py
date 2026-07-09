import unittest

from app.agents.tools import ToolRegistry
from app.agents.tools.web_search import FALLBACK_WEB_CONTENT, TavilyProvider, WebSearchTool
from app.api.llm import _inject_web_context, should_web_search


class FakeWebProvider:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def search(self, query, *, max_results, timeout):
        self.calls.append({"query": query, "max_results": max_results, "timeout": timeout})
        if self.fail:
            raise TimeoutError("offline")
        return [
            {
                "content": "fresh answer",
                "source_label": "Source",
                "url": "https://example.com",
                "score": 0.8,
                "origin": "web",
            }
        ]


class WebSearchRoutingTests(unittest.TestCase):
    def test_should_web_search_trigger_cases(self):
        self.assertTrue(should_web_search("请联网查一下", [{"score": 0.9}]))
        self.assertTrue(should_web_search("今年最新版本是什么", [{"score": 0.9}]))
        self.assertTrue(should_web_search("需要核实", [{"score": 0.9}], fact_check_required=True))
        self.assertTrue(should_web_search("普通问题", []))
        self.assertTrue(should_web_search("普通问题", [{"score": 0.1}], rag_min_score=0.35))

    def test_should_web_search_skips_when_rag_score_is_high(self):
        self.assertFalse(should_web_search("普通问题", [{"score": 0.8}], rag_min_score=0.35))

    def test_inject_web_context_adds_chunks_and_used_tool(self):
        provider = FakeWebProvider()
        tools = ToolRegistry({"web_search": WebSearchTool(provider=provider)})

        context, chunks = _inject_web_context({}, "请联网查一下", [{"score": 0.9}], tools)

        self.assertTrue(context["web_search_used"])
        self.assertIn("web_search", context["used_tools"])
        self.assertEqual(chunks[0]["origin"], "web")
        self.assertEqual(provider.calls[0]["query"], "请联网查一下")

    def test_web_search_failure_degrades_to_fallback_chunk(self):
        tool = WebSearchTool(provider=FakeWebProvider(fail=True))

        chunks = tool.search("latest")

        self.assertEqual(chunks[0]["content"], FALLBACK_WEB_CONTENT)
        self.assertEqual(chunks[0]["origin"], "web")

    def test_tavily_provider_without_key_returns_fallback_with_or_without_proxy(self):
        self.assertEqual(
            TavilyProvider(api_key=None).search("q", max_results=1, timeout=1)[0]["content"], FALLBACK_WEB_CONTENT
        )
        self.assertEqual(
            TavilyProvider(api_key=None, proxy="socks5://127.0.0.1:10808").search("q", max_results=1, timeout=1)[0][
                "content"
            ],
            FALLBACK_WEB_CONTENT,
        )


if __name__ == "__main__":
    unittest.main()
