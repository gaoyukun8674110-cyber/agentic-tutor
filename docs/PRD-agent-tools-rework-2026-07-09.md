# PRD｜Agent 工具返工：Web Search 不可用 + RAG 无关注入

- 版本：v1
- 日期：2026-07-09
- 适用代码库：`agentic-tutor`（monorepo，后端 `backend/`）
- 目标读者：接手修复的模型/工程师
- 优先级：🔴 高（测试演示期，直接影响可演示性）

---

## 0. TL;DR（给执行者）

有**三个**独立的真实 bug，均已定位到具体代码：

1. **【P0】未勾选资料仍全库检索**：前端未勾选资料时不传 `material_ids` 键，导致 `_inject_material_context` 的提前 return 判定失效，代码继续走检索；`search_materials` 收到 `material_ids=None` 时**不加 id 过滤**，退化为「在该用户全部已上传资料里搜 top_k」。**这就是「没勾选也返回英语语法内容」的根因。**
2. **【P1】RAG 无关硬注入（勾选时）**：勾选资料后**每一轮都无条件检索并注入 top_k 个 chunk**，从不判断相关性。`RAG_MIN_SCORE` 阈值**只用于 web 搜索判定，从未用于过滤 material chunk**。导致问「AI Agent」却引用英语语法笔记的 chunk。
3. **【P1】Web Search 对 LLM 不可见**：`web_search` 工具的结果被当作「静态资料片段」拼进上下文，而**没有**作为可调用工具（function calling）暴露给 LLM。导致用户问「你能联网吗」时 LLM 诚实回答「我没有 web_search 工具」——它没撒谎，是架构没给它工具。

三个 bug 都需要修。本 PRD 给出**分层方案**：先「止血修复」（改动小、当天可演示），再可选「架构重构」（更正确、工作量大）。**建议至少完成止血修复的全部项。P0 必须最先修。**

---

## 1. 现状与根因（已核实的代码事实）

### 1.1 相关文件与调用链

- 工具定义：`backend/app/agents/tools/web_search.py`（`WebSearchTool` / `TavilyProvider`）
- 工具注册：`backend/app/api/llm.py:105-108`
  ```python
  tools.register("retriever", RetrieverTool(db))
  tools.register("math", MathTool(llm.math_tools))
  tools.register("learner_store", LearnerStoreTool(db))
  tools.register("web_search", WebSearchTool())
  ```
- RAG 检索注入：`backend/app/api/llm.py:253` `_inject_material_context`
- Web 搜索注入：`backend/app/api/llm.py:284` `_inject_web_context`
- 搜索触发判定：`backend/app/api/llm.py:224` `should_web_search`
- material 检索实现：`backend/app/services/materials.py:403` `search_materials`
- 上下文 → prompt 拼接：`backend/app/services/llm_service.py:348` `_format_material_context`
- 配置项：`backend/app/config.py` — `RAG_MIN_SCORE=0.35`(:42)、`RAG_TOP_K=5`(:110)、`WEB_SEARCH_*`(:37-41)

### 1.2 Bug 1【P0】：未勾选资料仍全库检索（「没勾选也返回语法内容」的根因）

**根因**：`_inject_material_context`（llm.py:253-281）的「跳过检索」判定有逻辑漏洞：

```python
selected_material_ids = _normalize_material_ids(next_context.get("material_ids"))
if "material_ids" in next_context and not selected_material_ids:   # ← 仅当 material_ids 键"存在但为空"才跳过
    next_context.pop("material_context", None)
    return next_context, []
chunks = material_service.search_materials(..., material_ids=selected_material_ids, ...)  # ← 否则继续检索
```

- 前端**未勾选**资料时，若**根本不传 `material_ids` 这个键**（而非传空列表 `[]`），则 `"material_ids" in next_context` 为 **False**，提前 return **不执行**，代码直接往下检索。
- `search_materials`（materials.py:425）里 `if material_ids:` —— 当 `material_ids` 为 `None`/`[]` 时**这个 id 过滤根本不加**，查询退化为「在该用户**全部**已上传资料里搜 top_k」。
- 结果：**没勾选任何资料，照样从全部资料里检索并注入语法 chunk。** 这是 P0，必须最先修。

**注意**：需先和前端确认「未勾选」时到底传的是「不传 material_ids 键」还是「传空列表」——两种情况修法不同（见 A0）。无论哪种，后端都应做到「未勾选 ⇒ 绝不检索 material」。

### 1.3 Bug 2【P1】：RAG 无关硬注入（勾选时）

**根因**：`_inject_material_context`（llm.py:253-281）在有 `material_ids` 或勾选资料时，**每一轮无条件**调用 `search_materials` 并把结果塞进 `material_context`。

- `search_materials`（materials.py:403-439）**只按 `(1 - 余弦距离)` 排序返回 top_k，不做任何 min_score 过滤**。哪怕最高分只有 0.2（完全不相关），也照样返回并注入。
- `RAG_MIN_SCORE=0.35` 这个阈值**只在 `should_web_search`（llm.py:246）里被用来判断「RAG 太弱→触发 web 搜索」**，从未用于**丢弃低分 material chunk**。
- 结果：问「AI Agent」→ 在语法笔记里检索 → 返回相似度最高但完全不相关的 chunk 18/13/17 → 原样注入 prompt → LLM 引用英语语法回答 AI Agent 问题。

### 1.4 Bug 3【P1】：Web Search 对 LLM 不可见

**根因**：`_inject_web_context`（llm.py:284-318）在 `should_web_search` 命中后调用 `WebSearchTool.search()`，但把结果**拼进 `material_context["chunks"]`**（llm.py:309-311），和 RAG 资料混在一起，作为「检索片段」注入 prompt。

- LLM 收到的是**文本片段**，不是一个名为 `web_search` 的**可调用工具**。因此 LLM 的工具列表里永远没有 web_search，被直接问到时只能回答「我没有联网工具」。
- 触发完全依赖 `should_web_search` 的**关键词匹配**（llm.py:235-236：`联网/搜一下/最新/2026/latest...`）。未命中关键词就不搜；即使命中，搜索也是**静默**发生，LLM 不会声明「我搜过了」，用户无感知。
- 结论：**配不配 Tavily key 都改变不了「LLM 没有可调用工具」这个事实**。这是设计缺陷，不是配置问题。

---

## 2. 期望行为

### 2.1 Web Search
- 当用户问需要联网/时效性的问题（或明确要求联网），系统能真正联网检索、**在回答中标注来源**，并让 LLM **知道自己刚做了联网搜索**（不再否认有工具）。
- 当用户直接问「你能不能联网」时，LLM 的回答应与真实能力一致（能就说能、演示时可现场搜一条给对方看）。

### 2.2 RAG
- 只有当检索到的资料**与当前问题真正相关**（分数 ≥ 阈值）时才注入 chunk。
- 当资料不相关（全部低于阈值）时，**不注入任何 material chunk**，让 LLM 用通用知识回答，且不再出现「问 A 引用无关 B」。

---

## 3. 方案 A：止血修复（推荐，当天可演示，风险小）

> 改动集中在 `llm.py` / `materials.py` / `config.py`，不动 LLM 调用循环，向后兼容。**建议全部做，A0 必须最先做。**

### A0. 未勾选资料 ⇒ 绝不检索（修 Bug 1 / P0，最优先）

**目标**：用户没勾选任何资料时，后端**完全不做 material 检索**，`material_context` 一定为空。

**第一步（必须）**：和前端确认「未勾选」时请求里 `tutor_context.material_ids` 到底是什么：
- 情况甲：**不带 `material_ids` 键** → 当前 bug 就是这个（提前 return 判不到）。
- 情况乙：**带 `material_ids: []`** → 当前提前 return 能命中，则 P0 可能表现为别的路径，仍需按下方加固。
- 建议**前端统一**：勾选了就传 `material_ids: [1,2]`；没勾就传 `material_ids: []`（显式空列表），语义最清晰。

**第二步（后端加固，不依赖前端）**：改 `_inject_material_context`（llm.py:260-269），把判定改成「**只有在明确选了资料时才检索**」，而不是「只有在键存在且为空时才跳过」：

```python
next_context = dict(tutor_context)
cleaned_message = (last_user_message or "").strip()
if not cleaned_message:
    next_context.pop("material_context", None)
    return next_context, []

selected_material_ids = _normalize_material_ids(next_context.get("material_ids"))
# 未选择任何资料 ⇒ 绝不检索（不管前端传的是空列表还是根本没传该键）
if not selected_material_ids:
    next_context.pop("material_context", None)
    return next_context, []

chunks = material_service.search_materials(
    query=cleaned_message,
    user_id=user_id,
    material_ids=selected_material_ids,
    top_k=top_k,
)
```

**关键差异**：删掉 `if "material_ids" in next_context and not selected_material_ids` 这种「依赖键是否存在」的脆弱判断，改为「`selected_material_ids` 为空就直接不检索」。这样无论前端传空列表还是不传键，行为都一致。

> ⚠️ 若产品预期是「不勾选=在全部资料里搜」，那本条改法会改变该语义。但根据用户反馈（问 AI Agent 却返回语法），**期望明确是「不勾选=不使用任何资料」**。执行前如有疑义与产品确认，默认按「不勾选=不检索」。

**验收**：不勾选任何资料，问任意问题 → 前端「引用资料」区**为空**，回答不含任何上传资料内容。

### A1. RAG 相关性过滤（修 Bug 2 / P1）

**目标**：低于阈值的 material chunk 不注入。

**改动点**：`backend/app/api/llm.py` 的 `_inject_material_context`（约 llm.py:271-281）。在拿到 `chunks` 后、写入 `next_context["material_context"]` 之前，按分数过滤：

```python
chunks = material_service.search_materials(
    query=cleaned_message,
    user_id=user_id,
    material_ids=selected_material_ids,
    top_k=top_k,
)
# 新增：丢弃与问题不相关（低于阈值）的 chunk，避免无关资料污染回答
min_score = settings.RAG_MIN_SCORE
relevant_chunks = [
    c for c in chunks
    if isinstance(c.get("score"), (int, float)) and float(c["score"]) >= min_score
]
if relevant_chunks:
    next_context["material_context"] = {"chunks": relevant_chunks}
else:
    next_context.pop("material_context", None)
return next_context, relevant_chunks
```

**注意**：
- 返回值 `chunks` 也应改为过滤后的 `relevant_chunks`，因为它会传给 `_inject_web_context` 用于 `should_web_search` 判定——过滤后若无相关资料，正好应触发 web 搜索兜底，逻辑自洽。
- 阈值建议先用 `RAG_MIN_SCORE=0.35`；若演示中发现「本该命中的资料被误杀」，把该值下调（如 0.25）再验。可考虑新增独立配置 `RAG_MATERIAL_MIN_SCORE` 与 web 判定阈值解耦（见 A3）。

**验收**：勾选「语法笔记.txt」后，问「什么是 AI Agent」→ 前端「引用资料」区**不再出现语法 chunk**；问「put off 什么意思」→ 仍能正确引用到语法 chunk。

### A2. Web Search 结果显式化（修 Bug 3 的「LLM 否认」部分）

**目标**：搜索命中时，让 LLM **明确知道**这些片段来自实时联网搜索，并要求它标注来源、不得否认联网能力。

**改动点**：`backend/app/services/llm_service.py` 的 `_format_material_context`（约 llm_service.py:348-374）。当前已对 `origin == "web"` 的 chunk 加了「网络来源:」前缀（llm_service.py:369-371），但**缺少一句系统级声明**让 LLM 知道「你确实执行了联网搜索」。

在拼接 material context 的引导语（llm_service.py:359 附近）中，检测到存在 `origin=="web"` 的 chunk 时，追加一句系统提示，例如：

```
本轮已通过实时联网搜索获取了以下网络来源片段（origin=web）。
请基于这些片段回答，并在结论中标注来源链接。不要声称自己没有联网/搜索能力。
```

**改动点 2（可选但强烈建议）**：调整 `should_web_search`（llm.py:224-250）——把「用户直接询问是否能联网/要求联网」这类 intent 稳定识别为触发。当前 `explicit_keywords` 已含「联网/搜一下/查一下最新」，但「帮我查一下最新的X情况」这类自然表达可能漏。建议补充关键词或在演示话术中固定使用触发词（见「演示话术」）。

**验收**：勾掉资料、问「搜一下 2026 年 AI agent 最新进展」→ 回答中出现带链接的网络来源，且 LLM 不再说「我没有联网工具」。

### A3.（可选）阈值解耦与配置

- 在 `config.py` 新增 `RAG_MATERIAL_MIN_SCORE: float = 0.35`，A1 用它做 material 过滤；`should_web_search` 继续用 `RAG_MIN_SCORE`。避免调一个影响另一个。
- 更新 `backend/.env.example` 补充说明。

---

## 4. 方案 B：架构重构（更正确，工作量大，不适合演示前动）

> 仅在方案 A 稳定后、有充裕测试窗口时再做。**演示前不要动。**

### B1. 把 web_search 变成真正的 LLM function-calling 工具
- 在 `llm_service.py` 的 chat 调用中，向模型传入 `tools=[{...web_search 的 JSON schema...}]`，让**模型自主决定**何时调用。
- 实现 tool-call 循环：模型返回 `tool_calls` → 后端执行 `WebSearchTool.search()` → 把结果作为 `role=tool` 消息回传 → 模型据此作答。
- 这样 LLM 的工具列表里**真实存在** web_search，被问到时会如实回答、并能主动调用。
- 影响面：`llm_service.py` 的 `complete_chat` / 流式路径、`agents/tutor.py` 编排。需要新增大量测试。

### B2. RAG 检索相关性门控
- 把「是否注入资料」从「勾选即注入」改为「相关才注入」，并可加一个轻量意图判断（问题是否属于资料覆盖领域）。
- A1 已是其最小实现；B2 是更完整版（可加 rerank、覆盖度判断）。

---

## 5. 验收标准（Definition of Done）

方案 A 完成后，逐条验证：

| # | 场景 | 期望 |
|---|---|---|
| 0 | **不勾选任何资料**，问「什么是 AI Agent」 | 引用资料区**为空**；回答**完全不含**任何上传资料内容（P0 核心验收）|
| 1 | 勾选语法笔记，问「什么是 AI Agent」 | 引用资料区**无**语法 chunk；回答不套用语法内容 |
| 2 | 勾选语法笔记，问「put off 的用法」 | 正常引用到相关语法 chunk |
| 3 | 不勾资料，问「搜一下 2026 AI agent 最新进展」 | 触发联网，回答带网络来源链接 |
| 4 | 直接问「你能联网搜索吗」 | LLM 回答与真实能力一致，不否认（方案 A 下：能触发搜索即视为通过；方案 B 下：工具列表真实可见）|
| 5 | 关闭/未配置 Tavily key | 优雅降级，不报错崩溃（现有 `fallback_web_chunk` 已保证）|
| 6 | 回归 | `python -m pytest tests`（需先起 pgvector：`docker compose up -d db`，DB 在 `localhost:55432`）全绿；`ruff` / `black --check` / `mypy app` 通过 |

**相关既有测试**：`tests/test_web_search_routing.py`、`tests/test_agent_tools_and_orchestrator.py`、`tests/test_materials_rag.py`。修改 `should_web_search` / material 过滤后需同步更新这些用例，并**新增**「低分 material 被过滤」的用例。

---

## 6. 约束与注意事项

- **CI 门禁**：改完必须过 ruff / black / mypy / pytest（`.github/workflows/ci.yml`）。mypy 对 `app/` 生效（`app/api/*` 在排除列表，但逻辑正确性仍需保证）。
- **不要改数据库 schema**：本次纯业务逻辑修复，不需要 alembic 迁移。
- **Tavily key 安全**：`WEB_SEARCH_API_KEY` 走服务器 `.env`，勿硬编码、勿提交。（注：现有线上 key 曾在协作中明文出现，应轮换。）
- **配置阈值可调**：`RAG_MIN_SCORE` / 新增的 `RAG_MATERIAL_MIN_SCORE` 是演示调参的主要旋钮。

---

## 7. 演示话术（临时兜底，修复前也能用）

在方案 A 落地前，如需临时演示 web 搜索，**使用能命中 `explicit_keywords` 的触发词**：
- ✅「**搜一下** 2026 年 AI agent 最新进展」
- ✅「帮我**联网查一下最新**的 X」
- ❌「你能不能联网」（这只会让 LLM 自述能力→可能否认）

且演示 RAG 时，**问的问题要和已上传资料同领域**（如上传的是英语语法，就问语法题），避免触发 Bug 2。

---

## 8. 建议执行顺序

1. **A0**（未勾选⇒不检索）——**P0，最丢人的 bug（没勾选也返回无关内容），改动最小，第一个修。**
2. **A1**（勾选时 RAG 相关性过滤）——问 A 引用无关 B，第二修。
3. **A2**（web 结果显式化 + 触发词）——解决「LLM 否认联网」。
4. 跑验收表 1-N，全绿后提 PR。
5. （有窗口再做）方案 B 重构。
3. 跑验收表 1-6，全绿后提 PR。
4. （有窗口再做）方案 B 重构。
