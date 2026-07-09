# PRD：AI Tutor「模型服务暂时不可用」二次修复（工具循环非流式回归）

- **日期**：2026-07-09
- **状态**：根因已定位（证据充分），**仓库未修复，需 codex 落库**
- **优先级**：P0（线上展示项目，面向 HR，主对话直接不可用）
- **相关服务**：`ai-tutor-backend`（FastAPI，容器 `ai-tutor-backend-1`，VPS `96.9.210.217:8001`）
- **前端**：Vercel 部署，`/api/*` 反代至 `http://96.9.210.217:8001`
- **前置背景**：见 `docs/AI-Tutor_模型服务不可用_PRD_2026-07-08.md`（temperature 老问题，已入库修复，本次**不是**它复发）

---

## 1. 现象

前端页面正常渲染，发送对话消息后弹出错误横幅：

> ⚠️ 模型服务暂时不可用 (trace `44cc5bd24fd844c896d62a8ab60e155b`)

后端 `POST /api/llm/chat` 返回 `502 Bad Gateway`。复现触发点：一条要求「联网搜索最新 AI agent 情况」的用户消息（会进入工具调用流程）。历史上更早几轮对话曾正常出字——发生在 PR #8 重建镜像**之前**。

## 2. 影响

- 全部依赖 LLM 的功能不可用：主对话、提示（hint）、讲解、错误诊断、Session 总结。
- 前端、Vercel 反代、后端进程、数据库均正常——纯粹是**后端 → 模型提供商**这一跳失败。

## 3. 根因（已定位）

**不是** 7-08 那个 `temperature` 问题。那个已正式入库并做成配置感知：
`app/config.py` → `LLM_UNSUPPORTED_CHAT_PARAMS_BY_MODEL = "gpt-5*:temperature"`，
`LLMService._sanitize_chat_completion_kwargs()` 会在发请求前剥掉 `temperature`，两条路径都调用了它。所以纯对话能正常回复。

**本次根因**：PR #8（`feat(agent): real function-calling tool loop`，commit `9587347`）引入的**工具调用循环走的是非流式请求**，而线上 `gpt-5.5` / SSSAiCode（`node-cf`）渠道**强制要求 `stream:true`**（见 7-08 PRD 第 3 节实测表：非流式 → `400 Stream must be set to true`）。

调用分叉在 `app/services/llm_service.py` → `complete_chat()`：

- **L811** `if tool_calling_enabled and tool_schemas and tools and agent_context:` → 进入工具循环，
  - **L820 / L855** 均调用 `_create_chat_completion_message(...)`。
- **L637** `_create_chat_completion_message()` 内部：`client.chat.completions.create(**sanitized_kwargs)` —— **没有传 `stream=True`**，是**非流式**调用（读取 `response.choices[0].message`）。
- 对照 **L715** `_create_chat_completion()`：强制 `stream_kwargs = {..., "stream": True, "stream_options": {"include_usage": True}}`，所以旧的纯对话路径不受影响。

触发条件为何是「每条对话」：`AGENT_TOOL_CALLING_ENABLED` 默认 `True`（`config.py:44`），且 `TutorAgent` 每次都以 `tools=ctx.tools, agent_context=ctx` 调 `complete_chat`（`app/agents/tutor.py`），`allowed_tools` 非空 → `tool_schemas` 非空 → **L811 条件恒成立** → 每条对话都进非流式工具循环 → 该渠道 400 → `complete_chat` 兜底返回 `{"error": ...}` → `/api/llm/chat` 抛 502 →「模型服务暂时不可用」。

**时间线自洽**：PR #8 之前工具循环未生效（走 L715 流式路径），故截图里更早几轮能出字；重建镜像后工具循环生效，非流式请求即被该渠道拒绝。

### 3.1 服务器侧确认命令

```bash
docker logs ai-tutor-backend-1 2>&1 | grep 44cc5bd24fd844c896d62a8ab60e155b
# 预期: LLM provider error trace_id=44cc5bd2... error=BadRequestError('... Stream must be set to true')
```

## 4. 代码定位

- `backend/app/services/llm_service.py`
  - `_create_chat_completion_message(self, client, **kwargs)` — **L637**，工具循环的单次调用，**非流式**，是本次问题的唯一咽喉点。
  - `complete_chat(...)` — **L753**；工具循环分支 **L811**，两处调用点 **L820**（带 `tools`/`tool_choice`）、**L855**（`else` 收尾调用，不带 tools）。
  - `_create_chat_completion(self, client, **kwargs)` — **L715**，已正确流式，可作为参照实现。
  - `_response_usage_payload(response)` — **L604**，非流式取 usage 的方式；流式化后需改为从流末 `usage` chunk 聚合（参考 L718 起 `_create_chat_completion` 的聚合写法）。
  - `_message_to_openai_dict(message)` — 将 assistant 消息（含 `tool_calls`）回填进对话历史；流式聚合出的 message 需与它兼容。
- `backend/app/config.py`
  - `AGENT_TOOL_CALLING_ENABLED: bool = True`（L44）、`MAX_TOOL_ITERATIONS: int = 4`（L45）。
- 现有测试：`backend/tests/test_tool_calling_loop.py`（当前用非流式 `FakeResponse` 打桩，改流式后需同步更新）。

## 5. 需要 codex 做的正式修复（落库到仓库 + 重建镜像后依然生效）

**目标**：让工具调用循环也用流式请求，既满足 `gpt-5.5`/SSSAiCode 渠道的「强制 stream」约束，又保留 function-calling / 工具式联网搜索能力；重建镜像后不回归。

1. **主修复**：把 `_create_chat_completion_message` 改为**流式**调用并聚合结果。
   - 请求侧对齐 `_create_chat_completion`：传 `stream=True` + `stream_options={"include_usage": True}`；沿用 `_sanitize_chat_completion_kwargs`（继续剥 `temperature` 等）。保留对 `stream_options` 不被支持时的降级（参照 L718 起的 try/except fallback）。
   - 响应侧需从流的 delta 聚合三样东西：
     - **content**：拼接 `choices[0].delta.content`；
     - **tool_calls**：按 `delta.tool_calls[*].index` 聚合——`id`/`function.name` 在首个分片出现，`function.arguments` 需**跨多个分片按 index 累加字符串**；
     - **usage**：取流末携带 `usage` 的 chunk（该渠道可能不回传，需容忍缺失，见第 2 点）。
   - 聚合出的 assistant message 必须能被 `_message_to_openai_dict` 正确序列化（含 `tool_calls` 的 `id`/`type`/`function.name`/`function.arguments`），保证下一轮 `role:"tool"` 消息能正确回填。
   - **多轮循环不变量**：`complete_chat` 的 `for _ in range(max_iterations)` 逻辑、`tool_choice="auto"`、以及 L855 的 `else` 收尾调用（不带 tools）都改用流式实现，行为与现在一致（有 tool_calls 则继续、无则收尾）。

2. **usage 缺失降级**：该渠道 `stream_options.include_usage` 可能不回传 usage，导致 token 统计为 `None`。保持**非致命降级**（现状即如此），必要时记一条 warning，不要因缺 usage 而失败。非阻塞。

3. **配置化/一致性**：确保工具循环与纯对话两条路径的采样参数处理、stream 处理**共用同一套逻辑**，避免以后再出现「一条路径流式、一条非流式」的偏差。可考虑抽出统一的 `_stream_and_aggregate(client, **kwargs, want_tools: bool)`，两处复用。

4. **测试**（`backend/tests/test_tool_calling_loop.py` + 可加 `test_llm_chat.py`）：
   - 把打桩从「返回 `FakeResponse`」改为「返回可迭代的**流式 chunk**」，模拟 tool_call 分片（`id`+`name` 在首片、`arguments` 分多片累加）。
   - 断言：**发给 provider 的每次 payload 都含 `stream=True`**（工具循环路径也不例外）。
   - 断言：多分片 `arguments` 能正确拼回完整 JSON，工具被正确调用，最终 content 正确聚合。
   - 保留原有断言：`tool_choice="auto"`、第二次调用 `messages[-1].role == "tool"`、`used_tools`/`tool_trace` 正确。
   - 回归：`gpt-5*` 模型下 payload 不含 `temperature`（沿用现有 sanitize 覆盖）。

## 6. 验收标准

- [ ] 仓库代码重建镜像后，`POST /api/llm/chat`（含触发工具调用的消息）返回 200 且正常出字，不再 502。
- [ ] 提示 / 讲解 / 诊断 / 总结四个辅助功能均可用。
- [ ] 工具式联网搜索（web_search）在 `gpt-5.5` 渠道下端到端可用。
- [ ] 存在覆盖「工具循环路径也是 `stream=True`」+「tool_call arguments 跨分片聚合」的自动化测试。
- [ ] 切回一个支持非流式 / 支持 temperature 的模型时功能不回归。

## 7. 临时缓解（线上顶包，未入库，codex 修好后回滚此项）

在 VPS `/root/ai-tutor/.env` 关闭工具循环，回退到可用的流式纯对话路径：

```bash
echo 'AGENT_TOOL_CALLING_ENABLED=false' >> /root/ai-tutor/.env
cd /root/ai-tutor && docker compose up -d backend
```

- 代价：暂时失去 function-calling / 工具式联网搜索，主对话及四个辅助功能恢复。
- ⚠️ 正式修复入库后，删掉这行 `.env` 覆盖再重新部署，恢复工具调用能力。

## 8. 附录：环境与部署

**关键环境（VPS 容器内，与 7-08 PRD 一致）**
```
OPENAI_BASE_URL = https://node-cf.sssaicodeapi.com/api/v1
OPENAI_MODEL    = gpt-5.5
DEFAULT_LLM_PROVIDER = openai
ALLOW_GLOBAL_LLM_FALLBACK = true
AGENT_TOOL_CALLING_ENABLED = true   # 默认值，问题在此路径触发
```

**部署（正式修复入库后）**
```bash
cd /root/ai-tutor && git pull && docker compose up -d --build backend
```

**端到端验证（service 层，绕过 HTTP 鉴权；应能在 gpt-5.5 上带工具跑通）**
```bash
docker exec ai-tutor-backend-1 python - <<'PY'
import os
from openai import OpenAI
from app.services.llm_service import LLMService
svc = LLMService.__new__(LLMService)
c = OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ["OPENAI_BASE_URL"])
# 期望：流式聚合后正常返回 content，不再 400 "Stream must be set to true"
content, usage = svc._create_chat_completion_message(
    c, model=os.environ["OPENAI_MODEL"],
    messages=[{"role": "user", "content": "用一句话说你好"}],
    temperature=0.7, max_tokens=60,
)
print("CONTENT=", repr(content), "USAGE=", usage)
PY
```
