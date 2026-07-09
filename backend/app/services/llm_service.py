"""LLM 服务 - 统一模型管理、多角色 Agent、工具集成"""

import json
import logging
import time
from fnmatch import fnmatchcase
from threading import Lock
from typing import TYPE_CHECKING, Any

from openai import OpenAI

from app.config import settings
from app.services.analytics import AnalyticsService
from app.utils.errors import safe_llm_error
from app.utils.math_tools import MathTools

logger = logging.getLogger(__name__)
_warned_missing_stream_usage = False

if TYPE_CHECKING:
    from app.agents.base import AgentContext
    from app.agents.tools import ToolRegistry
    from app.services.llm_credential_resolver import ResolvedProvider


MATH_RENDERING_RULES = """数学公式输出规则：
- 涉及数学、概率、统计、代数、微积分时，公式必须使用 LaTeX。
- 行内公式使用 `$...$`，独立展示的公式使用 `$$...$$`。
- 不要用纯文本模拟分数、指数、根号、求和或积分；优先使用 `\\frac`、`^`、`\\sqrt`、`\\sum`、`\\int` 等 LaTeX 写法。
- 公式外的解释继续使用清晰的自然语言。"""


class LLMService:
    """LLM 服务"""

    def __init__(self, analytics: AnalyticsService | None = None):
        self.client = (
            OpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )
            if settings.OPENAI_API_KEY
            else None
        )
        self.analytics = analytics
        self.math_tools = MathTools()
        self._clients: dict[str, OpenAI] = {}
        self._client_lock = Lock()

        # Agent 角色定义
        self.agent_prompts = {
            "solver": """你是一个数学解题助手。你的任务是：
1. 使用提供的数学工具（Sympy）来验证和计算
2. 给出结构化的解题步骤
3. 确保答案的准确性""",
            "tutor": """你是一个苏格拉底式的数学导师。你的任务是：
1. 不直接给答案，而是通过提问引导学生思考
2. 给出提示（hint），而不是完整解答
3. 用通俗易懂的语言解释数学概念
4. 鼓励学生，保持耐心和友好""",
            "diagnosis": """你是一个错误诊断专家。你的任务是：
1. 对比学生的答案和标准答案
2. 找出学生错误的具体位置和原因
3. 解释为什么错了，以及正确的思路是什么
4. 给出针对性的改进建议""",
            "pomodoro_coach": """你是一个学习教练。你的任务是：
1. 在番茄钟开始和结束时给出鼓励性的话语
2. 总结学习成果，给出正面反馈
3. 提醒学生注意休息，保持学习节奏""",
        }

        self.prompt_profiles = {
            "three_stage": {
                "name": "三段式学习法",
                "description": "先用二八原则规划核心知识，再用简单比喻解释概念，最后用费曼追问检测理解。",
                "system_prompt": """你是我的学习系统，由三个模块组成：

1. 学习设计师：
当学生提出学习目标时，先根据二八原则，把目标拆成最小必要知识，只列出最关键的 20%，并说明这些知识分别解决什么问题。

2. 概念解释师：
当学生对某个概念不懂时，用生活中最简单的比喻解释。要求逻辑准确、语言简单，最好让 10 岁小学生也能理解，并给出对比例子。

3. 费曼教练：
当学生说“来费曼”时，你扮演一个完全不懂的新手，不断向学生提问，直到学生能把概念讲清楚。最后总结学生遗漏了哪些关键点。

工作规则：
- 不要一次性输出太多。
- 先判断学生当前处于哪个阶段：规划、理解、还是检测。
- 如果目标不清楚，先问 1-3 个关键问题。
- 如果学生已经给出明确主题，直接开始。
- 每次回答只推进一个小步骤，优先让学生真正理解，而不是堆信息。""",
            },
            "socratic": {
                "name": "苏格拉底引导",
                "description": "通过追问和提示引导学生自己推理，不直接给完整答案。",
                "system_prompt": """你是一位苏格拉底式 AI Tutor。
你的目标是帮助学生学会思考，而不是替学生完成所有任务。
优先使用简短问题、分层提示和下一步引导。
除非学生明确要求完整讲解，否则不要直接给最终答案。""",
            },
            "explain": {
                "name": "概念讲解",
                "description": "用清晰结构解释概念、步骤和原因。",
                "system_prompt": """你是一位善于讲解概念的 AI Tutor。
请先判断学生卡住的概念点，再用清晰、分层、通俗的方式解释。
回答应包含关键思路、必要步骤和一个小例子。""",
            },
            "diagnose": {
                "name": "错题诊断",
                "description": "定位错误原因，区分概念、计算和方法问题。",
                "system_prompt": """你是一位错题诊断 Tutor。
请帮助学生定位错误发生在哪里、为什么错、应该如何修正。
区分概念误解、计算失误、方法选择错误和审题问题。""",
            },
            "coach": {
                "name": "学习教练",
                "description": "结合番茄钟节奏提醒休息、复盘和继续学习。",
                "system_prompt": """你是一位学习节奏教练。
请结合当前番茄钟状态，帮助学生保持专注、合理休息、及时复盘。
语气应简洁、鼓励、具体。""",
            },
            "exam": {
                "name": "考试训练",
                "description": "模拟考试环境，控制提示强度并强调限时训练。",
                "system_prompt": """问题不必Q1，Q2，Q3，直接1，2，3就行；
答案你留着，不要展示出来，后面我给你答案你直接给我判就行；
题目的话要对齐雅思题目难度，在有情景的情况下出选择题，只需要有A，B选项就OK；
是关键处出A，B选项就行，不是出A,B问句;题目15个起步；
如果一个知识点下有几个小知识点的话要先针对每个对应的小知识点进行每个至少5题的小专项训练再接着对整个知识点做专项训练；
出过一次的题不要出第二次;在提交答案之后要对答案进行对错判断并进行分析薄弱项；并且要求对薄弱项的知识点讲解能"一刀切";
一刀切规则的时候要给一个简单的示例,不然我看不懂!如果发现哪里有薄弱项，那我们接下来就对薄弱项进行专项加强；
每次出题记得把答案打乱。""",
            },
            "custom": {
                "name": "自定义提示词",
                "description": "使用后端配置或请求传入的自定义系统提示词。",
                "system_prompt": "你是一位 AI Tutor。请根据当前后端配置的教学策略帮助学生学习。",
            },
        }

    def _provider_configs(self) -> dict[str, dict[str, Any]]:
        """Return backend-only provider configuration."""
        return {
            "openai": {
                "name": "OpenAI",
                "adapter": "openai-compatible",
                "api_key": settings.OPENAI_API_KEY,
                "base_url": settings.OPENAI_BASE_URL,
                "default_model": settings.OPENAI_MODEL,
                "models": [settings.OPENAI_MODEL, "gpt-4o-mini", "gpt-4o"],
                "requires_api_key": True,
                "implemented": True,
            },
            "deepseek": {
                "name": "DeepSeek",
                "adapter": "openai-compatible",
                "api_key": settings.DEEPSEEK_API_KEY,
                "base_url": settings.DEEPSEEK_BASE_URL,
                "default_model": settings.DEEPSEEK_MODEL,
                "models": [settings.DEEPSEEK_MODEL],
                "requires_api_key": True,
                "implemented": True,
            },
            "qwen": {
                "name": "Qwen",
                "adapter": "openai-compatible",
                "api_key": settings.QWEN_API_KEY,
                "base_url": settings.QWEN_BASE_URL,
                "default_model": settings.QWEN_MODEL,
                "models": [settings.QWEN_MODEL],
                "requires_api_key": True,
                "implemented": True,
            },
            "linkapi": {
                "name": "LinkAPI",
                "adapter": "openai-compatible",
                "api_key": settings.LINKAPI_API_KEY,
                "base_url": settings.LINKAPI_BASE_URL,
                "default_model": settings.LINKAPI_MODEL,
                "models": [
                    settings.LINKAPI_MODEL,
                    "claude-sonnet-4-20250514",
                    "gpt-4o-mini",
                    "deepseek-chat",
                ],
                "requires_api_key": True,
                "implemented": True,
            },
            "ollama": {
                "name": "Ollama",
                "adapter": "openai-compatible",
                "api_key": "ollama",
                "base_url": settings.OLLAMA_BASE_URL,
                "default_model": settings.OLLAMA_MODEL,
                "models": [settings.OLLAMA_MODEL],
                "requires_api_key": False,
                "implemented": True,
            },
            "anthropic": {
                "name": "Anthropic Claude",
                "adapter": "native",
                "api_key": settings.ANTHROPIC_API_KEY,
                "base_url": None,
                "default_model": settings.ANTHROPIC_MODEL,
                "models": [settings.ANTHROPIC_MODEL],
                "requires_api_key": True,
                "implemented": False,
            },
            "gemini": {
                "name": "Google Gemini",
                "adapter": "openai-compatible",
                "api_key": settings.GEMINI_API_KEY,
                "base_url": settings.GEMINI_BASE_URL,
                "default_model": settings.GEMINI_MODEL,
                "models": [settings.GEMINI_MODEL, "gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro"],
                "requires_api_key": True,
                "implemented": True,
            },
        }

    def get_provider_metadata(self) -> dict[str, Any]:
        """Expose safe provider metadata to the frontend without API keys."""
        providers = []
        for provider_id, config in self._provider_configs().items():
            has_credentials = bool(config["base_url"]) and (not config["requires_api_key"] or bool(config["api_key"]))
            enabled = has_credentials and config["implemented"]
            reason = None
            if not has_credentials:
                reason = "provider credentials are not configured"
            elif not config["implemented"]:
                reason = "provider adapter is not implemented yet"

            providers.append(
                {
                    "id": provider_id,
                    "name": config["name"],
                    "adapter": config["adapter"],
                    "enabled": enabled,
                    "implemented": config["implemented"],
                    "default_model": config["default_model"],
                    "models": config["models"],
                    "reason": reason,
                }
            )

        return {"providers": providers}

    def get_prompt_profiles(self) -> dict[str, Any]:
        """Return available Tutor teaching styles."""
        return {
            "profiles": [
                {
                    "id": profile_id,
                    "name": profile["name"],
                    "description": profile["description"],
                }
                for profile_id, profile in self.prompt_profiles.items()
            ]
        }

    def _has_provider_credentials(self, config: dict[str, Any]) -> bool:
        return bool(config["base_url"]) and (not config["requires_api_key"] or bool(config["api_key"]))

    def _resolve_provider_id(
        self, requested_provider: str | None, provider_configs: dict[str, dict[str, Any]]
    ) -> str | None:
        provider_id = requested_provider or "auto"
        if provider_id != "auto":
            return provider_id

        if settings.DEFAULT_LLM_PROVIDER != "auto":
            return settings.DEFAULT_LLM_PROVIDER

        for candidate_id, config in provider_configs.items():
            if (
                self._has_provider_credentials(config)
                and config["implemented"]
                and config["adapter"] == "openai-compatible"
            ):
                return candidate_id

        return None

    @staticmethod
    def _latest_user_content(messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user" and message.get("content", "").strip():
                return message.get("content", "").strip()
        return ""

    @staticmethod
    def detect_learning_phase(student_message: str | None) -> str:
        text = (student_message or "").strip().lower()
        if not text:
            return "general"

        if any(keyword in text for keyword in ["来费曼", "费曼", "feynman", "考考我", "测试我", "检测我"]):
            return "feynman"

        if any(
            keyword in text
            for keyword in [
                "我想学",
                "想学",
                "学习目标",
                "目标",
                "计划",
                "规划",
                "怎么学",
                "学习路线",
                "路径",
                "安排",
                "二八",
            ]
        ):
            return "planning"

        if any(
            keyword in text
            for keyword in [
                "不懂",
                "是什么",
                "什么意思",
                "解释",
                "讲一下",
                "讲讲",
                "举例",
                "例子",
                "为什么",
                "区别",
                "类比",
                "换一种",
            ]
        ):
            return "understanding"

        return "general"

    @staticmethod
    def _learning_phase_instruction(phase: str) -> str:
        instructions = {
            "planning": "当前阶段是规划：按二八原则列出最关键的 20% 知识，并说明每个知识点解决什么问题；不要展开成大段课程。",
            "understanding": "当前阶段是理解：用简单生活比喻解释概念，给一个对比例子，然后停下来确认学生是否理解。",
            "feynman": "当前阶段是检测：扮演完全不懂的新手，一次只问一个追问，最后总结学生遗漏的关键点。",
            "general": "当前阶段不明确：先根据学生问题判断阶段；如果目标不清楚，只问 1-3 个关键问题。",
        }
        return instructions.get(phase, instructions["general"])

    @staticmethod
    def _format_material_context(material_context: Any) -> list[str]:
        if not isinstance(material_context, dict):
            return []

        raw_chunks = material_context.get("chunks")
        if not isinstance(raw_chunks, list) or not raw_chunks:
            return []

        has_web_chunks = any(isinstance(chunk, dict) and chunk.get("origin") == "web" for chunk in raw_chunks)
        lines = [
            "",
            "当前检索到的学习资料片段：",
            "请优先使用这些资料片段回答；引用资料时标出对应来源。如果资料片段没有覆盖学生问题，请明确说明当前资料没有覆盖，再用通用知识做引导或追问。",
        ]
        if has_web_chunks:
            lines.append(
                "Live web search was performed for this turn. Web chunks are marked with origin=web; "
                "answer from them when relevant, cite the source URL, and do not claim that web search is unavailable."
            )
        included = 0
        for index, chunk in enumerate(raw_chunks[:5], start=1):
            if not isinstance(chunk, dict):
                continue
            content = str(chunk.get("content") or "").strip()
            if not content:
                continue
            source_label = str(chunk.get("source_label") or chunk.get("filename") or f"学习资料片段 {index}")
            if chunk.get("origin") == "web":
                url = str(chunk.get("url") or "").strip()
                source_label = f"网络来源: {source_label}" + (f" ({url})" if url else "")
            score = chunk.get("score")
            score_text = f" · score {float(score):.3f}" if isinstance(score, int | float) else ""
            lines.append(f"[{index}] {source_label}{score_text}")
            lines.append(content)
            included += 1

        return lines if included else []

    def _build_system_prompt(
        self,
        prompt_profile: str,
        tutor_context: dict[str, Any] | None = None,
        system_prompt_override: str | None = None,
    ) -> str:
        profile = self.prompt_profiles.get(prompt_profile, self.prompt_profiles["socratic"])
        if prompt_profile == "custom" and system_prompt_override:
            prompt = system_prompt_override
        else:
            prompt = profile["system_prompt"]

        prompt = f"{prompt}\n\n{MATH_RENDERING_RULES}"

        if tutor_context:
            context_lines = ["", "当前学习上下文："]
            for key, value in tutor_context.items():
                if key in {"material_context", "material_ids"}:
                    continue
                context_lines.append(f"- {key}: {value}")
            context_lines.extend(self._format_material_context(tutor_context.get("material_context")))
            prompt = f"{prompt}\n" + "\n".join(context_lines)

        return prompt

    def _should_inline_system_prompt(self, provider: str, model: str) -> bool:
        """Some OpenAI-compatible gateways route Claude models to Anthropic Messages API.

        Anthropic Messages does not allow a `system` role inside `messages`, so keep
        the Tutor instructions by merging them into the first user message.
        """
        return provider == "linkapi" and model.lower().startswith("claude")

    def _build_chat_messages(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        inline_system_prompt: bool = False,
    ) -> list[dict[str, str]]:
        user_messages = [
            {
                "role": message.get("role", "user"),
                "content": message.get("content", ""),
            }
            for message in messages
            if message.get("role") != "system"
        ]

        if not inline_system_prompt:
            return [{"role": "system", "content": system_prompt}, *user_messages]

        if not user_messages:
            return [{"role": "user", "content": system_prompt}]

        first_message = user_messages[0]
        first_message["role"] = "user"
        first_message["content"] = (
            f"请严格遵循以下 Tutor 行为规则：\n{system_prompt}\n\n" f"学生消息：\n{first_message['content']}"
        )
        return user_messages

    def _safe_log_llm_call(
        self,
        user_id: str | None,
        session_id: int | None,
        agent_type: str,
        prompt_length: int,
        response_length: int,
        duration_ms: float,
        analytics: AnalyticsService | None = None,
    ) -> None:
        analytics_service = analytics or self.analytics
        if not analytics_service:
            return

        try:
            analytics_service.log_llm_call(
                user_id=user_id,
                session_id=session_id,
                agent_type=agent_type,
                prompt_length=prompt_length,
                response_length=response_length,
                duration_ms=duration_ms,
            )
        except Exception as error:
            logger.warning("LLM analytics log failed: %s", error, exc_info=error)

    def _get_provider_client(self, provider: str, provider_config: dict[str, Any]) -> OpenAI:
        client = self._clients.get(provider)
        if client is None:
            with self._client_lock:
                client = self._clients.get(provider)
                if client is None:
                    client = OpenAI(
                        api_key=provider_config["api_key"],
                        base_url=provider_config["base_url"],
                    )
                    self._clients[provider] = client
        return client

    @staticmethod
    def _configured_unsupported_chat_params_by_model() -> list[tuple[str, set[str]]]:
        raw_config = str(getattr(settings, "LLM_UNSUPPORTED_CHAT_PARAMS_BY_MODEL", "") or "")
        rules: list[tuple[str, set[str]]] = []
        for raw_rule in raw_config.replace("\n", ";").split(";"):
            if ":" not in raw_rule:
                continue
            raw_pattern, raw_params = raw_rule.split(":", 1)
            pattern = raw_pattern.strip().lower()
            params = {param.strip() for param in raw_params.split(",") if param.strip()}
            if pattern and params:
                rules.append((pattern, params))
        return rules

    def _unsupported_chat_params_for_model(self, model: str | None) -> set[str]:
        if not model:
            return set()

        normalized_model = model.lower()
        unsupported: set[str] = set()
        for pattern, params in self._configured_unsupported_chat_params_by_model():
            if fnmatchcase(normalized_model, pattern):
                unsupported.update(params)
        return unsupported

    def _sanitize_chat_completion_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(kwargs)
        unsupported_params = self._unsupported_chat_params_for_model(str(sanitized.get("model") or "") or None)
        removed_params = sorted(param for param in unsupported_params if param in sanitized)
        for param in removed_params:
            sanitized.pop(param, None)

        if removed_params:
            logger.info(
                "Removed unsupported LLM chat parameter(s) for model %s: %s",
                sanitized.get("model"),
                ", ".join(removed_params),
            )

        return sanitized

    @staticmethod
    def _tool_name_aliases(name: str) -> set[str]:
        aliases = {
            "retrieve_materials": {"retrieve_materials", "retriever"},
            "web_search": {"web_search"},
            "calculate": {"calculate", "math"},
            "get_learner_profile": {"get_learner_profile", "learner_store"},
        }
        return aliases.get(name, {name})

    def _build_tool_schemas(self, allowed_tools: list[str] | None = None) -> list[dict[str, Any]]:
        allowed = set(allowed_tools or ["retrieve_materials", "web_search", "calculate", "get_learner_profile"])

        def is_allowed(function_name: str) -> bool:
            return bool(self._tool_name_aliases(function_name) & allowed)

        schemas = {
            "retrieve_materials": {
                "type": "function",
                "function": {
                    "name": "retrieve_materials",
                    "description": "Search the learner's selected study materials for passages relevant to the query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "material_ids": {"type": "array", "items": {"type": "integer"}},
                        },
                        "required": ["query"],
                    },
                },
            },
            "web_search": {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current or external information and source URLs.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            },
            "calculate": {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Calculate or simplify a math expression.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"},
                            "variables": {"type": "object", "additionalProperties": {"type": "number"}},
                        },
                        "required": ["expression"],
                    },
                },
            },
            "get_learner_profile": {
                "type": "function",
                "function": {
                    "name": "get_learner_profile",
                    "description": "Get the current learner profile, weak skills, and mastery snapshot.",
                    "parameters": {
                        "type": "object",
                        "properties": {"weak_limit": {"type": "integer", "minimum": 1, "maximum": 10}},
                    },
                },
            },
        }
        return [schema for name, schema in schemas.items() if is_allowed(name)]

    @staticmethod
    def _response_usage_payload(response: Any) -> dict[str, int | None]:
        usage = getattr(response, "usage", None)
        if not usage:
            return {}
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    @staticmethod
    def _message_to_openai_dict(message: Any) -> dict[str, Any]:
        if isinstance(message, dict):
            return dict(message)
        payload: dict[str, Any] = {
            "role": getattr(message, "role", "assistant"),
            "content": getattr(message, "content", None),
        }
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            payload["tool_calls"] = [
                {
                    "id": getattr(tool_call, "id", ""),
                    "type": getattr(tool_call, "type", "function"),
                    "function": {
                        "name": getattr(getattr(tool_call, "function", None), "name", ""),
                        "arguments": getattr(getattr(tool_call, "function", None), "arguments", "{}"),
                    },
                }
                for tool_call in tool_calls
            ]
        return payload

    def _create_chat_completion_message(
        self,
        client: OpenAI,
        **kwargs,
    ) -> tuple[Any, dict[str, int | None]]:
        """Call chat completions once and return the assistant message, preserving tool_calls."""
        sanitized_kwargs = self._sanitize_chat_completion_kwargs(kwargs)
        response = client.chat.completions.create(**sanitized_kwargs)
        choices = getattr(response, "choices", None) or []
        message = getattr(choices[0], "message", {"role": "assistant", "content": ""}) if choices else {}
        return message, self._response_usage_payload(response)

    @staticmethod
    def _tool_call_id(tool_call: Any) -> str:
        if isinstance(tool_call, dict):
            return str(tool_call.get("id") or "")
        return str(getattr(tool_call, "id", "") or "")

    @staticmethod
    def _tool_call_name(tool_call: Any) -> str:
        function = tool_call.get("function") if isinstance(tool_call, dict) else getattr(tool_call, "function", None)
        if isinstance(function, dict):
            return str(function.get("name") or "")
        return str(getattr(function, "name", "") or "")

    @staticmethod
    def _tool_call_arguments(tool_call: Any) -> dict[str, Any]:
        function = tool_call.get("function") if isinstance(tool_call, dict) else getattr(tool_call, "function", None)
        raw_arguments = (
            function.get("arguments") if isinstance(function, dict) else getattr(function, "arguments", "{}")
        )
        if isinstance(raw_arguments, dict):
            return raw_arguments
        try:
            parsed = json.loads(raw_arguments or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _resolve_tool(self, registry: "ToolRegistry", function_name: str) -> Any:
        registry_names = {
            "retrieve_materials": "retriever",
            "web_search": "web_search",
            "calculate": "math",
            "get_learner_profile": "learner_store",
        }
        return registry.get(registry_names.get(function_name, function_name))

    def _invoke_tool_call(
        self,
        tool_call: Any,
        *,
        tools: "ToolRegistry",
        allowed_tools: set[str],
        agent_context: "AgentContext",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started_at = time.time()
        function_name = self._tool_call_name(tool_call)
        arguments = self._tool_call_arguments(tool_call)
        trace = {"tool": function_name, "arguments": arguments}
        try:
            if not (self._tool_name_aliases(function_name) & allowed_tools):
                result = {"error": "tool_not_allowed", "tool": function_name}
            else:
                tool = self._resolve_tool(tools, function_name)
                invoke = getattr(tool, "invoke", None)
                if not callable(invoke):
                    result = {"error": "tool_not_invokable", "tool": function_name}
                else:
                    result = invoke(arguments, agent_context)
        except Exception as error:
            result = {"error": "tool_execution_failed", "detail": str(error)}

        duration_ms = (time.time() - started_at) * 1000
        trace["duration_ms"] = duration_ms
        trace["ok"] = "error" not in result
        return result, trace

    def _create_chat_completion(self, client: OpenAI, **kwargs) -> tuple[str, dict[str, int | None]]:
        """Call chat completions in streaming mode and aggregate content plus usage."""
        sanitized_kwargs = self._sanitize_chat_completion_kwargs(kwargs)
        stream_kwargs = {**sanitized_kwargs, "stream": True, "stream_options": {"include_usage": True}}
        try:
            stream = client.chat.completions.create(**stream_kwargs)
        except Exception:
            fallback_kwargs = {**sanitized_kwargs, "stream": True}
            stream = client.chat.completions.create(**fallback_kwargs)

        content_parts: list[str] = []
        usage_payload: dict[str, int | None] = {}
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage:
                usage_payload = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }

            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue

            delta = getattr(choices[0], "delta", None)
            delta_content = getattr(delta, "content", None)
            if delta_content is not None:
                content_parts.append(delta_content)

        if not usage_payload:
            global _warned_missing_stream_usage
            if not _warned_missing_stream_usage:
                logger.warning("LLM provider did not return stream usage; token analytics are unavailable")
                _warned_missing_stream_usage = True

        return "".join(content_parts), usage_payload

    def complete_chat(
        self,
        resolved: "ResolvedProvider",
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        prompt_profile: str = "three_stage",
        system_prompt_override: str | None = None,
        tutor_context: dict[str, Any] | None = None,
        agent_type: str,
        user_id: str | None,
        session_id: int | None,
        analytics: AnalyticsService | None,
        model: str | None = None,
        tools: "ToolRegistry | None" = None,
        allowed_tools: list[str] | None = None,
        agent_context: "AgentContext | None" = None,
    ) -> dict[str, Any]:
        """Generate a reply using an already resolved user/global provider."""
        selected_model = model or resolved.default_model
        detected_learning_phase = self.detect_learning_phase(self._latest_user_content(messages))
        learning_phase = detected_learning_phase
        normalized_tutor_context = dict(tutor_context or {})
        if prompt_profile == "three_stage":
            previous_learning_phase = str(normalized_tutor_context.get("learning_phase") or "")
            if detected_learning_phase == "general" and previous_learning_phase:
                learning_phase = previous_learning_phase
            normalized_tutor_context["learning_phase"] = learning_phase
            normalized_tutor_context["learning_phase_instruction"] = self._learning_phase_instruction(learning_phase)

        system_prompt = self._build_system_prompt(
            prompt_profile=prompt_profile,
            tutor_context=normalized_tutor_context,
            system_prompt_override=system_prompt_override,
        )
        chat_messages = self._build_chat_messages(
            system_prompt=system_prompt,
            messages=messages,
            inline_system_prompt=self._should_inline_system_prompt(resolved.provider_id, selected_model),
        )

        start_time = time.time()
        client = None
        try:
            client = OpenAI(api_key=resolved.api_key, base_url=resolved.base_url)
            usage_payload: dict[str, int | None] = {}
            used_tools = list(dict.fromkeys(normalized_tutor_context.get("used_tools") or []))
            tool_trace: list[dict[str, Any]] = []
            tool_schemas = self._build_tool_schemas(allowed_tools) if tools and agent_context else []
            tool_calling_enabled = bool(getattr(settings, "AGENT_TOOL_CALLING_ENABLED", True))
            common_kwargs = {
                "model": selected_model,
                "temperature": temperature if temperature is not None else settings.OPENAI_TEMPERATURE,
                "max_tokens": max_tokens if max_tokens is not None else settings.OPENAI_MAX_TOKENS,
                "timeout": 60,
            }

            if tool_calling_enabled and tool_schemas and tools and agent_context:
                tool_messages = list(chat_messages)
                allowed_tool_names = set(allowed_tools or [])
                if not allowed_tool_names:
                    allowed_tool_names = {"retrieve_materials", "web_search", "calculate", "get_learner_profile"}

                final_message: Any = {"role": "assistant", "content": ""}
                max_iterations = max(1, int(getattr(settings, "MAX_TOOL_ITERATIONS", 4)))
                for _ in range(max_iterations):
                    message, call_usage = self._create_chat_completion_message(
                        client,
                        messages=tool_messages,
                        tools=tool_schemas,
                        tool_choice="auto",
                        **common_kwargs,
                    )
                    usage_payload = call_usage or usage_payload
                    final_message = message
                    tool_calls = getattr(message, "tool_calls", None)
                    if isinstance(message, dict):
                        tool_calls = message.get("tool_calls")
                    if not tool_calls:
                        break

                    tool_messages.append(self._message_to_openai_dict(message))
                    for tool_call in tool_calls:
                        function_name = self._tool_call_name(tool_call)
                        result, trace = self._invoke_tool_call(
                            tool_call,
                            tools=tools,
                            allowed_tools=allowed_tool_names,
                            agent_context=agent_context,
                        )
                        tool_trace.append(trace)
                        if function_name and function_name not in used_tools:
                            used_tools.append(function_name)
                        tool_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": self._tool_call_id(tool_call),
                                "content": json.dumps(result, ensure_ascii=False, default=str),
                            }
                        )
                else:
                    final_message, call_usage = self._create_chat_completion_message(
                        client,
                        messages=tool_messages,
                        **common_kwargs,
                    )
                    usage_payload = call_usage or usage_payload

                content = getattr(final_message, "content", None)
                if isinstance(final_message, dict):
                    content = final_message.get("content")
                content = content or ""
                chat_messages = tool_messages
            else:
                content, usage_payload = self._create_chat_completion(
                    client,
                    messages=chat_messages,
                    **common_kwargs,
                )
            duration_ms = (time.time() - start_time) * 1000

            self._safe_log_llm_call(
                user_id=user_id,
                session_id=session_id,
                agent_type=agent_type,
                prompt_length=sum(len(str(message.get("content") or "")) for message in chat_messages),
                response_length=len(content or ""),
                duration_ms=duration_ms,
                analytics=analytics,
            )

            return {
                "message": {"role": "assistant", "content": content},
                "provider": resolved.provider_id,
                "model": selected_model,
                "prompt_profile": prompt_profile,
                "learning_phase": learning_phase,
                "usage": usage_payload,
                "latency_ms": duration_ms,
                "credential_source": resolved.source,
                "credential_fingerprint": resolved.fingerprint,
                "used_tools": used_tools,
                "tool_trace": tool_trace,
            }
        except Exception as e:
            return {"error": safe_llm_error(e)}
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def chat(
        self,
        provider: str,
        model: str | None,
        messages: list[dict[str, str]],
        prompt_profile: str = "three_stage",
        tutor_context: dict[str, Any] | None = None,
        system_prompt_override: str | None = None,
        user_id: str | None = None,
        session_id: int | None = None,
        analytics: AnalyticsService | None = None,
    ) -> dict[str, Any]:
        """Generate a Tutor chat reply through the selected provider."""
        provider_configs = self._provider_configs()
        provider = self._resolve_provider_id(provider, provider_configs)
        if not provider:
            return {"error": "No configured LLM provider is available"}
        if provider not in provider_configs:
            return {"error": f"Unknown provider: {provider}"}

        provider_config = provider_configs[provider]
        has_credentials = self._has_provider_credentials(provider_config)
        if not has_credentials:
            return {"error": f"{provider_config['name']} is not configured"}
        if not provider_config["implemented"]:
            return {"error": f"{provider_config['name']} adapter is not implemented yet"}
        if provider_config["adapter"] != "openai-compatible":
            return {"error": f"{provider_config['name']} adapter is not supported yet"}

        selected_model = model or provider_config["default_model"]
        detected_learning_phase = self.detect_learning_phase(self._latest_user_content(messages))
        learning_phase = detected_learning_phase
        normalized_tutor_context = dict(tutor_context or {})
        if prompt_profile == "three_stage":
            previous_learning_phase = str(normalized_tutor_context.get("learning_phase") or "")
            if detected_learning_phase == "general" and previous_learning_phase:
                learning_phase = previous_learning_phase
            normalized_tutor_context["learning_phase"] = learning_phase
            normalized_tutor_context["learning_phase_instruction"] = self._learning_phase_instruction(learning_phase)

        system_prompt = self._build_system_prompt(
            prompt_profile=prompt_profile,
            tutor_context=normalized_tutor_context,
            system_prompt_override=system_prompt_override,
        )
        chat_messages = self._build_chat_messages(
            system_prompt=system_prompt,
            messages=messages,
            inline_system_prompt=self._should_inline_system_prompt(provider, selected_model),
        )

        start_time = time.time()
        try:
            client = self._get_provider_client(provider, provider_config)
            content, usage_payload = self._create_chat_completion(
                client,
                model=selected_model,
                messages=chat_messages,
                temperature=settings.OPENAI_TEMPERATURE,
                max_tokens=settings.OPENAI_MAX_TOKENS,
            )
            duration_ms = (time.time() - start_time) * 1000

            self._safe_log_llm_call(
                user_id=user_id,
                session_id=session_id,
                agent_type=f"tutor_chat:{prompt_profile}:{provider}",
                prompt_length=sum(len(message["content"]) for message in chat_messages),
                response_length=len(content or ""),
                duration_ms=duration_ms,
                analytics=analytics,
            )

            return {
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "provider": provider,
                "model": selected_model,
                "prompt_profile": prompt_profile,
                "learning_phase": learning_phase,
                "usage": usage_payload,
                "latency_ms": duration_ms,
            }
        except Exception as e:
            return {"error": safe_llm_error(e)}

    def generate_hint(
        self,
        question_content: str,
        student_answer: str | None = None,
        step: int = 1,
        user_id: str | None = None,
        session_id: int | None = None,
        analytics: AnalyticsService | None = None,
    ) -> dict[str, Any]:
        """生成提示（hint）"""
        if not self.client:
            return {"error": "OpenAI API key not configured"}

        prompt = f"""题目：{question_content}

学生当前答案：{student_answer if student_answer else "尚未作答"}

请给出第 {step} 步的提示（hint），不要直接给答案。提示应该：
1. 引导学生思考下一步应该做什么
2. 用提问的方式，而不是陈述
3. 简短、精准，不超过 50 字"""

        start_time = time.time()
        try:
            hint, _ = self._create_chat_completion(
                self.client,
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": self.agent_prompts["tutor"]},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=200,
            )

            duration_ms = (time.time() - start_time) * 1000

            # 记录日志
            self._safe_log_llm_call(
                user_id=user_id,
                session_id=session_id,
                agent_type="tutor_hint",
                prompt_length=len(prompt),
                response_length=len(hint),
                duration_ms=duration_ms,
                analytics=analytics,
            )

            return {
                "hint": hint,
                "step": step,
                "agent_type": "tutor",
            }
        except Exception as e:
            return {"error": safe_llm_error(e)}

    def explain_solution(
        self,
        question_content: str,
        standard_solution: str,
        solution_steps: list[dict] | None = None,
        user_id: str | None = None,
        session_id: int | None = None,
        analytics: AnalyticsService | None = None,
    ) -> dict[str, Any]:
        """讲解标准解"""
        if not self.client:
            return {"error": "OpenAI API key not configured"}

        steps_text = ""
        if solution_steps:
            for i, step in enumerate(solution_steps, 1):
                steps_text += f"\n步骤 {i}: {step.get('description', '')}"

        prompt = f"""题目：{question_content}

标准答案：{standard_solution}
解题步骤：{steps_text}

请用通俗易懂的语言讲解这道题的解法，包括：
1. 解题思路
2. 关键步骤的解释
3. 为什么这样做"""

        start_time = time.time()
        try:
            explanation, _ = self._create_chat_completion(
                self.client,
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": self.agent_prompts["tutor"]},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )

            duration_ms = (time.time() - start_time) * 1000

            self._safe_log_llm_call(
                user_id=user_id,
                session_id=session_id,
                agent_type="tutor_explain",
                prompt_length=len(prompt),
                response_length=len(explanation),
                duration_ms=duration_ms,
                analytics=analytics,
            )

            return {
                "explanation": explanation,
                "agent_type": "tutor",
            }
        except Exception as e:
            return {"error": safe_llm_error(e)}

    def diagnose_error(
        self,
        question_content: str,
        student_answer: str,
        correct_answer: str,
        standard_solution: str,
        user_id: str | None = None,
        session_id: int | None = None,
        analytics: AnalyticsService | None = None,
    ) -> dict[str, Any]:
        """诊断错误"""
        if not self.client:
            return {"error": "OpenAI API key not configured"}

        # 使用数学工具验证答案
        math_verification = self.math_tools.verify_answer(student_answer, correct_answer)

        prompt = f"""题目：{question_content}

学生答案：{student_answer}
正确答案：{correct_answer}
标准解法：{standard_solution}

数学工具验证结果：{math_verification.get('result', 'unknown')}

请诊断学生的错误：
1. 具体哪里错了
2. 错误的原因（概念理解错误？计算错误？方法错误？）
3. 正确的思路应该是什么
4. 给出改进建议"""

        start_time = time.time()
        try:
            diagnosis, _ = self._create_chat_completion(
                self.client,
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": self.agent_prompts["diagnosis"]},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,  # 诊断需要更准确
                max_tokens=400,
            )

            duration_ms = (time.time() - start_time) * 1000

            self._safe_log_llm_call(
                user_id=user_id,
                session_id=session_id,
                agent_type="diagnosis",
                prompt_length=len(prompt),
                response_length=len(diagnosis),
                duration_ms=duration_ms,
                analytics=analytics,
            )

            return {
                "diagnosis": diagnosis,
                "error_type": self._extract_error_type(diagnosis),
                "math_verification": math_verification,
                "agent_type": "diagnosis",
            }
        except Exception as e:
            return {"error": safe_llm_error(e)}

    def session_summary(
        self,
        session_stats: dict[str, Any],
        user_id: str | None = None,
        session_id: int | None = None,
        analytics: AnalyticsService | None = None,
    ) -> dict[str, Any]:
        """生成 Session 总结"""
        if not self.client:
            return {"error": "OpenAI API key not configured"}

        prompt = f"""本次训练 Session 统计：
- 总题数：{session_stats.get('total_questions', 0)}
- 正确数：{session_stats.get('correct_count', 0)}
- 正确率：{session_stats.get('correct_rate', 0):.1%}
- 平均用时：{session_stats.get('average_time', 0):.1f} 秒

请生成一段鼓励性的总结，包括：
1. 肯定学生的努力
2. 指出进步的地方
3. 给出下一步学习建议
4. 保持积极正面的语调"""

        start_time = time.time()
        try:
            summary, _ = self._create_chat_completion(
                self.client,
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": self.agent_prompts["pomodoro_coach"]},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=300,
            )

            duration_ms = (time.time() - start_time) * 1000

            self._safe_log_llm_call(
                user_id=user_id,
                session_id=session_id,
                agent_type="pomodoro_coach",
                prompt_length=len(prompt),
                response_length=len(summary),
                duration_ms=duration_ms,
                analytics=analytics,
            )

            return {
                "summary": summary,
                "agent_type": "pomodoro_coach",
            }
        except Exception as e:
            return {"error": safe_llm_error(e)}

    def _extract_error_type(self, diagnosis: str) -> str:
        """从诊断文本中提取错误类型"""
        if "概念" in diagnosis or "理解" in diagnosis:
            return "concept_error"
        elif "计算" in diagnosis or "运算" in diagnosis:
            return "calculation_error"
        elif "方法" in diagnosis or "思路" in diagnosis:
            return "method_error"
        else:
            return "unknown"
