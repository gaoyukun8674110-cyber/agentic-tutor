import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agents.base import AgentContext
from app.agents.tools import ToolRegistry
from app.services import llm_service as llm_module
from app.services.llm_service import LLMService


class FakeStreamChoice:
    def __init__(self, delta):
        self.delta = delta


class FakeUsage:
    prompt_tokens = 10
    completion_tokens = 5
    total_tokens = 15


class FakeStreamChunk:
    def __init__(self, delta=None, usage=None):
        self.choices = [] if delta is None else [FakeStreamChoice(delta)]
        self.usage = usage


class ToolCallingCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return [
                FakeStreamChunk(
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "web_search", "arguments": '{"query": '},
                            }
                        ]
                    }
                ),
                FakeStreamChunk({"tool_calls": [{"index": 0, "function": {"arguments": '"2026 AI agent news"}'}}]}),
                FakeStreamChunk(usage=FakeUsage()),
            ]
        return [
            FakeStreamChunk({"content": "Final answer "}),
            FakeStreamChunk({"content": "with cited source."}),
            FakeStreamChunk(usage=FakeUsage()),
        ]


class FakeOpenAIClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = SimpleNamespace(completions=ToolCallingCompletions())
        FakeOpenAIClient.instances.append(self)

    def close(self):
        pass


class FakeWebSearchTool:
    def __init__(self):
        self.calls = []

    def invoke(self, args, ctx):
        self.calls.append({"args": args, "ctx": ctx})
        return {
            "chunks": [
                {
                    "content": "Fresh source text",
                    "source_label": "Example",
                    "url": "https://example.com",
                    "origin": "web",
                }
            ],
            "count": 1,
        }


class ToolCallingLoopTests(unittest.TestCase):
    def setUp(self):
        FakeOpenAIClient.instances = []

    def _resolved(self):
        return SimpleNamespace(
            provider_id="linkapi",
            api_key="secret",
            base_url="https://gateway.test/v1",
            default_model="gpt-test",
            source="user",
            fingerprint="fp",
        )

    def test_complete_chat_executes_tool_call_and_returns_final_answer(self):
        service = LLMService()
        web_tool = FakeWebSearchTool()
        registry = ToolRegistry({"web_search": web_tool})
        ctx = AgentContext(user_id="alice", student_id=7, tools=registry)

        with patch.object(llm_module, "OpenAI", FakeOpenAIClient):
            result = service.complete_chat(
                resolved=self._resolved(),
                model=None,
                messages=[{"role": "user", "content": "Search the web"}],
                prompt_profile="socratic",
                agent_type="tutor",
                user_id="alice",
                session_id=None,
                analytics=None,
                tools=registry,
                allowed_tools=["web_search"],
                agent_context=ctx,
            )

        self.assertEqual(result["message"]["content"], "Final answer with cited source.")
        self.assertEqual(result["used_tools"], ["web_search"])
        self.assertEqual(result["tool_trace"][0]["tool"], "web_search")
        self.assertTrue(result["tool_trace"][0]["ok"])
        self.assertEqual(web_tool.calls[0]["args"]["query"], "2026 AI agent news")

        completion_calls = FakeOpenAIClient.instances[0].chat.completions.calls
        self.assertEqual(len(completion_calls), 2)
        self.assertIn("tools", completion_calls[0])
        self.assertEqual(completion_calls[0]["tool_choice"], "auto")
        self.assertEqual(completion_calls[1]["messages"][-1]["role"], "tool")
        self.assertEqual(json.loads(completion_calls[1]["messages"][-1]["content"])["count"], 1)
        self.assertTrue(all(call["stream"] is True for call in completion_calls))

    def test_complete_chat_rejects_disallowed_tool_call_without_crashing(self):
        service = LLMService()
        registry = ToolRegistry({})
        ctx = AgentContext(user_id="alice", student_id=7, tools=registry)

        with patch.object(llm_module, "OpenAI", FakeOpenAIClient):
            result = service.complete_chat(
                resolved=self._resolved(),
                model=None,
                messages=[{"role": "user", "content": "Search the web"}],
                prompt_profile="socratic",
                agent_type="tutor",
                user_id="alice",
                session_id=None,
                analytics=None,
                tools=registry,
                allowed_tools=["calculate"],
                agent_context=ctx,
            )

        self.assertEqual(result["message"]["content"], "Final answer with cited source.")
        tool_message = FakeOpenAIClient.instances[0].chat.completions.calls[1]["messages"][-1]
        self.assertIn("tool_not_allowed", tool_message["content"])
        self.assertTrue(all(call["stream"] is True for call in FakeOpenAIClient.instances[0].chat.completions.calls))

    def test_complete_chat_sanitizes_gpt5_tool_loop_payloads(self):
        service = LLMService()
        web_tool = FakeWebSearchTool()
        registry = ToolRegistry({"web_search": web_tool})
        ctx = AgentContext(user_id="alice", student_id=7, tools=registry)
        resolved = self._resolved()
        resolved.default_model = "gpt-5.5"

        with patch.object(llm_module, "OpenAI", FakeOpenAIClient):
            result = service.complete_chat(
                resolved=resolved,
                model=None,
                messages=[{"role": "user", "content": "Search the web"}],
                prompt_profile="socratic",
                agent_type="tutor",
                user_id="alice",
                session_id=None,
                analytics=None,
                temperature=0.7,
                tools=registry,
                allowed_tools=["web_search"],
                agent_context=ctx,
            )

        self.assertEqual(result["message"]["content"], "Final answer with cited source.")
        completion_calls = FakeOpenAIClient.instances[0].chat.completions.calls
        self.assertTrue(all(call["stream"] is True for call in completion_calls))
        self.assertTrue(all("temperature" not in call for call in completion_calls))


if __name__ == "__main__":
    unittest.main()
