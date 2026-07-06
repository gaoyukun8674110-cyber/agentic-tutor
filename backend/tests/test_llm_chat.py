import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def load_llm_module():
    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = lambda **kwargs: None

    fake_config = types.ModuleType("app.config")
    fake_config.settings = SimpleNamespace(
        OPENAI_API_KEY=None,
        OPENAI_BASE_URL="https://api.openai.com/v1",
        OPENAI_MODEL="gpt-4o-mini",
        OPENAI_TEMPERATURE=0.7,
        OPENAI_MAX_TOKENS=2000,
        DEEPSEEK_API_KEY=None,
        DEEPSEEK_BASE_URL="https://api.deepseek.com/v1",
        DEEPSEEK_MODEL="deepseek-chat",
        QWEN_API_KEY=None,
        QWEN_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1",
        QWEN_MODEL="qwen-plus",
        OLLAMA_BASE_URL="http://localhost:11434/v1",
        OLLAMA_MODEL="llama3.1",
        ANTHROPIC_API_KEY=None,
        ANTHROPIC_MODEL="claude-3-5-sonnet-latest",
        GEMINI_API_KEY=None,
        GEMINI_MODEL="gemini-1.5-pro",
        LINKAPI_API_KEY=None,
        LINKAPI_BASE_URL="https://api.linkapi.ai/v1",
        LINKAPI_MODEL="claude-haiku-4-5-20251001",
        DEFAULT_LLM_PROVIDER="auto",
    )

    fake_analytics = types.ModuleType("app.services.analytics")
    fake_analytics.AnalyticsService = object

    fake_math_tools = types.ModuleType("app.utils.math_tools")

    class FakeMathTools:
        def verify_answer(self, student_answer, correct_answer):
            return {"result": "unknown"}

    fake_math_tools.MathTools = FakeMathTools
    fake_errors = types.ModuleType("app.utils.errors")
    fake_errors.safe_llm_error = lambda error: {
        "code": "llm_provider_error",
        "user_message": "Model provider is temporarily unavailable",
        "trace_id": "test-trace",
    }

    fake_services = types.ModuleType("app.services")
    fake_services.__path__ = []
    fake_utils = types.ModuleType("app.utils")
    fake_utils.__path__ = []

    module_overrides = {
        "openai": fake_openai,
        "app.config": fake_config,
        "app.services": fake_services,
        "app.services.analytics": fake_analytics,
        "app.utils": fake_utils,
        "app.utils.math_tools": fake_math_tools,
        "app.utils.errors": fake_errors,
    }
    previous_modules = {name: sys.modules.get(name) for name in module_overrides}
    sys.modules.update(module_overrides)

    module_path = Path(__file__).resolve().parents[1] / "app" / "services" / "llm_service.py"
    spec = importlib.util.spec_from_file_location("llm_service_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    try:
        spec.loader.exec_module(module)
    finally:
        for name, previous_module in previous_modules.items():
            if previous_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module
    return module


llm_module = load_llm_module()
LLMService = llm_module.LLMService


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeUsage:
    prompt_tokens = 12
    completion_tokens = 8
    total_tokens = 20


class FakeCompletion:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]
        self.usage = FakeUsage()


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeCompletion("先观察题目中的已知条件。")


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FailingCompletions:
    def create(self, **kwargs):
        raise RuntimeError("Invalid api key sk-secret")


class FakeOpenAIClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = FakeChat()
        FakeOpenAIClient.instances.append(self)


class FailingOpenAIClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = FakeChat()
        self.chat.completions = FailingCompletions()
        FailingOpenAIClient.instances.append(self)


class NoneContentCompletions(FakeCompletions):
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeCompletion(None)


class NoneContentOpenAIClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = FakeChat()
        self.chat.completions = NoneContentCompletions()
        NoneContentOpenAIClient.instances.append(self)


class LLMChatTests(unittest.TestCase):
    def setUp(self):
        FakeOpenAIClient.instances = []
        FailingOpenAIClient.instances = []

    def test_provider_metadata_hides_api_keys_and_marks_configured_providers(self):
        service = LLMService()

        with patch.object(llm_module, "settings") as fake_settings:
            fake_settings.OPENAI_API_KEY = "secret-openai"
            fake_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
            fake_settings.OPENAI_MODEL = "gpt-4o-mini"
            fake_settings.DEEPSEEK_API_KEY = None
            fake_settings.DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
            fake_settings.DEEPSEEK_MODEL = "deepseek-chat"
            fake_settings.QWEN_API_KEY = "secret-qwen"
            fake_settings.QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            fake_settings.QWEN_MODEL = "qwen-plus"
            fake_settings.OLLAMA_BASE_URL = "http://localhost:11434/v1"
            fake_settings.OLLAMA_MODEL = "llama3.1"
            fake_settings.ANTHROPIC_API_KEY = None
            fake_settings.ANTHROPIC_MODEL = "claude-3-5-sonnet-latest"
            fake_settings.GEMINI_API_KEY = None
            fake_settings.GEMINI_MODEL = "gemini-1.5-pro"
            fake_settings.LINKAPI_API_KEY = None
            fake_settings.LINKAPI_BASE_URL = "https://api.linkapi.ai/v1"
            fake_settings.LINKAPI_MODEL = "claude-haiku-4-5-20251001"
            fake_settings.DEFAULT_LLM_PROVIDER = "auto"

            metadata = service.get_provider_metadata()

        providers = {provider["id"]: provider for provider in metadata["providers"]}
        self.assertTrue(providers["openai"]["enabled"])
        self.assertTrue(providers["qwen"]["enabled"])
        self.assertTrue(providers["ollama"]["enabled"])
        self.assertFalse(providers["deepseek"]["enabled"])
        self.assertNotIn("api_key", providers["openai"])
        self.assertNotIn("secret-openai", str(metadata))

    def test_prompt_profiles_include_multiple_tutoring_methods_and_custom_entry(self):
        service = LLMService()

        profiles = service.get_prompt_profiles()

        profile_ids = {profile["id"] for profile in profiles["profiles"]}
        self.assertIn("three_stage", profile_ids)
        self.assertIn("socratic", profile_ids)
        self.assertIn("explain", profile_ids)
        self.assertIn("diagnose", profile_ids)
        self.assertIn("coach", profile_ids)
        self.assertIn("exam", profile_ids)
        self.assertIn("custom", profile_ids)

    def test_three_stage_profile_contains_learning_method_rules(self):
        service = LLMService()

        prompt = service._build_system_prompt(
            prompt_profile="three_stage",
            tutor_context={"learning_phase": "planning"},
        )

        self.assertIn("学习设计师", prompt)
        self.assertIn("二八原则", prompt)
        self.assertIn("概念解释师", prompt)
        self.assertIn("费曼教练", prompt)
        self.assertIn("learning_phase", prompt)

    def test_system_prompt_requires_latex_math_output(self):
        service = LLMService()

        prompt = service._build_system_prompt(
            prompt_profile="three_stage",
            tutor_context={"learning_phase": "understanding"},
        )

        self.assertIn("LaTeX", prompt)
        self.assertIn("$...$", prompt)
        self.assertIn("$$...$$", prompt)
        self.assertIn("\\frac", prompt)
        self.assertIn("\\sqrt", prompt)

    def test_exam_prompt_matches_built_in_training_rules(self):
        service = LLMService()

        expected_prompt = """问题不必Q1，Q2，Q3，直接1，2，3就行；
答案你留着，不要展示出来，后面我给你答案你直接给我判就行；
题目的话要对齐雅思题目难度，在有情景的情况下出选择题，只需要有A，B选项就OK；
是关键处出A，B选项就行，不是出A,B问句;题目15个起步；
如果一个知识点下有几个小知识点的话要先针对每个对应的小知识点进行每个至少5题的小专项训练再接着对整个知识点做专项训练；
出过一次的题不要出第二次;在提交答案之后要对答案进行对错判断并进行分析薄弱项；并且要求对薄弱项的知识点讲解能"一刀切";
一刀切规则的时候要给一个简单的示例,不然我看不懂!如果发现哪里有薄弱项，那我们接下来就对薄弱项进行专项加强；
每次出题记得把答案打乱。"""
        self.assertEqual(service.prompt_profiles["exam"]["system_prompt"], expected_prompt)
        self.assertTrue(service._build_system_prompt(prompt_profile="exam").startswith(expected_prompt))

    def test_detect_learning_phase_from_student_message(self):
        service = LLMService()

        self.assertEqual(service.detect_learning_phase("我想学机器学习，帮我做个计划"), "planning")
        self.assertEqual(service.detect_learning_phase("这个概念我不懂，能不能解释一下"), "understanding")
        self.assertEqual(service.detect_learning_phase("来费曼，我讲给你听"), "feynman")
        self.assertEqual(service.detect_learning_phase("今天继续"), "general")

    def test_chat_composes_prompt_profile_and_calls_selected_openai_compatible_provider(self):
        service = LLMService()

        with (
            patch.object(llm_module, "OpenAI", FakeOpenAIClient),
            patch.object(llm_module, "settings") as fake_settings,
        ):
            fake_settings.OPENAI_API_KEY = "secret-openai"
            fake_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
            fake_settings.OPENAI_MODEL = "gpt-4o-mini"
            fake_settings.OPENAI_TEMPERATURE = 0.7
            fake_settings.OPENAI_MAX_TOKENS = 2000
            fake_settings.DEEPSEEK_API_KEY = "secret-deepseek"
            fake_settings.DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
            fake_settings.DEEPSEEK_MODEL = "deepseek-chat"
            fake_settings.QWEN_API_KEY = None
            fake_settings.QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            fake_settings.QWEN_MODEL = "qwen-plus"
            fake_settings.OLLAMA_BASE_URL = "http://localhost:11434/v1"
            fake_settings.OLLAMA_MODEL = "llama3.1"
            fake_settings.ANTHROPIC_API_KEY = None
            fake_settings.ANTHROPIC_MODEL = "claude-3-5-sonnet-latest"
            fake_settings.GEMINI_API_KEY = None
            fake_settings.GEMINI_MODEL = "gemini-1.5-pro"
            fake_settings.LINKAPI_API_KEY = None
            fake_settings.LINKAPI_BASE_URL = "https://api.linkapi.ai/v1"
            fake_settings.LINKAPI_MODEL = "claude-haiku-4-5-20251001"
            fake_settings.DEFAULT_LLM_PROVIDER = "auto"

            result = service.chat(
                provider="deepseek",
                model="deepseek-chat",
                messages=[{"role": "user", "content": "我不会移项"}],
                prompt_profile="socratic",
                tutor_context={"goal": "一次方程训练", "timer_state": "focus"},
            )

        self.assertEqual(result["message"]["content"], "先观察题目中的已知条件。")
        self.assertEqual(result["provider"], "deepseek")
        self.assertEqual(result["model"], "deepseek-chat")
        created_client = FakeOpenAIClient.instances[0]
        self.assertEqual(created_client.kwargs["api_key"], "secret-deepseek")
        self.assertEqual(created_client.kwargs["base_url"], "https://api.deepseek.com/v1")
        call = created_client.chat.completions.calls[0]
        self.assertEqual(call["model"], "deepseek-chat")
        self.assertEqual(call["messages"][0]["role"], "system")
        self.assertIn("苏格拉底", call["messages"][0]["content"])
        self.assertIn("一次方程训练", call["messages"][0]["content"])

    def _configure_fake_settings(self, fake_settings):
        fake_settings.OPENAI_API_KEY = "secret-openai"
        fake_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
        fake_settings.OPENAI_MODEL = "gpt-4o-mini"
        fake_settings.OPENAI_TEMPERATURE = 0.7
        fake_settings.OPENAI_MAX_TOKENS = 2000
        fake_settings.DEEPSEEK_API_KEY = "secret-deepseek"
        fake_settings.DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
        fake_settings.DEEPSEEK_MODEL = "deepseek-chat"
        fake_settings.QWEN_API_KEY = None
        fake_settings.QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        fake_settings.QWEN_MODEL = "qwen-plus"
        fake_settings.OLLAMA_BASE_URL = "http://localhost:11434/v1"
        fake_settings.OLLAMA_MODEL = "llama3.1"
        fake_settings.ANTHROPIC_API_KEY = None
        fake_settings.ANTHROPIC_MODEL = "claude-3-5-sonnet-latest"
        fake_settings.GEMINI_API_KEY = None
        fake_settings.GEMINI_MODEL = "gemini-1.5-pro"
        fake_settings.LINKAPI_API_KEY = None
        fake_settings.LINKAPI_BASE_URL = "https://api.linkapi.ai/v1"
        fake_settings.LINKAPI_MODEL = "claude-haiku-4-5-20251001"
        fake_settings.DEFAULT_LLM_PROVIDER = "auto"

    def test_chat_reuses_provider_client_for_same_provider(self):
        service = LLMService()

        with (
            patch.object(llm_module, "OpenAI", FakeOpenAIClient),
            patch.object(llm_module, "settings") as fake_settings,
        ):
            self._configure_fake_settings(fake_settings)
            for _ in range(2):
                service.chat(
                    provider="deepseek",
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": "hello"}],
                    prompt_profile="socratic",
                )

        self.assertEqual(len(FakeOpenAIClient.instances), 1)

    def test_chat_sanitizes_provider_exception(self):
        service = LLMService()

        with (
            patch.object(llm_module, "OpenAI", FailingOpenAIClient),
            patch.object(llm_module, "settings") as fake_settings,
        ):
            self._configure_fake_settings(fake_settings)
            result = service.chat(
                provider="deepseek",
                model="deepseek-chat",
                messages=[{"role": "user", "content": "hello"}],
                prompt_profile="socratic",
            )

        self.assertEqual(result["error"]["code"], "llm_provider_error")
        self.assertNotIn("sk-secret", str(result))

    def test_complete_chat_sets_timeout_and_normalizes_empty_provider_content(self):
        service = LLMService()
        resolved = SimpleNamespace(
            provider_id="deepseek",
            api_key="secret-deepseek",
            base_url="https://api.deepseek.com/v1",
            default_model="deepseek-chat",
            source="user",
            fingerprint="fingerprint",
        )

        with (
            patch.object(llm_module, "OpenAI", NoneContentOpenAIClient),
            patch.object(llm_module, "settings") as fake_settings,
        ):
            self._configure_fake_settings(fake_settings)
            result = service.complete_chat(
                resolved=resolved,
                model=None,
                messages=[{"role": "user", "content": "hello"}],
                prompt_profile="socratic",
                agent_type="tutor_chat:socratic:deepseek",
                user_id="alice",
                session_id=None,
                analytics=None,
            )

        self.assertEqual(result["message"]["content"], "")
        call = NoneContentOpenAIClient.instances[0].chat.completions.calls[0]
        self.assertEqual(call["timeout"], 60)

    def test_safe_log_llm_call_uses_warning_logger_when_analytics_fails(self):
        analytics = SimpleNamespace(
            log_llm_call=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("analytics unavailable"))
        )
        service = LLMService(analytics=analytics)

        with patch.object(llm_module, "logger") as fake_logger:
            service._safe_log_llm_call(
                user_id="learner-1",
                session_id=1,
                agent_type="tutor_chat:socratic:openai",
                prompt_length=10,
                response_length=20,
                duration_ms=12.5,
            )

        fake_logger.warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
