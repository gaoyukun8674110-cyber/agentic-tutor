# Tutor 后端服务

一个智能数学教学系统，包含 6 个核心服务模块。

## 架构概览

1. **题库服务** - 题目存储、检索、标准解管理
2. **训练引擎** - Session 编排、动态出题、教学策略
3. **学生模型服务** - 掌握度维护、学习画像、推荐算法
4. **番茄钟服务** - 时间管理、间隔重复、学习节奏
5. **分析服务** - 行为日志、统计分析、A/B 测试
6. **LLM 服务** - 统一模型管理、多角色 Agent、工具集成

## 技术栈

- FastAPI - Web 框架
- SQLAlchemy - ORM
- SQLite - 数据库（可替换为 PostgreSQL）
- OpenAI API - LLM 服务
- Sympy - 数学计算工具

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
# 复制 .env.example 为 .env，然后编辑 .env 文件
# 至少需要填入 OPENAI_API_KEY（如果使用 LLM 功能）

# 3. 初始化数据库（可选，应用启动时会自动创建表）
# alembic upgrade head
# 或者直接运行应用，会自动创建表

# 4. 启动服务
python start.py
# 或者
uvicorn app.main:app --reload

# 5. 访问 API 文档
# 浏览器打开 http://localhost:8000/docs
```

## Architecture / Decision Records

- Authentication now uses `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout`, and `/api/auth/me`.
- Protected browser calls use `Authorization: Bearer <access_token>` and an HttpOnly refresh cookie scoped to `/api/auth`; the old shared `X-API-Key` application auth path is removed.
- Run `python -m alembic upgrade head` before local demo or deployment startup. The migrations seed `test-01 / 123456`, backfill legacy unowned Tutor data to that user, and verify no null-owned legacy rows remain.
- Frontend project now lives at `../frontend` inside the `H:\ai-tutor` monorepo; backend and frontend changes that depend on the API contract should be versioned together.
- SQLite is used for the portfolio/demo profile because local setup is deterministic; SQLAlchemy keeps a PostgreSQL migration path open.
- LLM calls are backend-proxied so API keys never ship to the browser and multiple OpenAI-compatible providers can be routed behind one API.
- Users can save personal OpenAI-compatible provider credentials at `/settings/model`; `/api/llm/chat`, `/hint`, `/explain`, `/diagnose`, and `/summary` resolve user credentials before optional global fallback and return `credential_source`.
- RAG v1 stores source files, chunks text, and uses OpenAI embeddings when configured; hash embeddings are explicitly surfaced as `embedding_mode="hash"` for offline development and tests.
- Upload ingestion creates a `pending` material first and fills embeddings in a background task to avoid holding the HTTP response open for long PDFs.

## RAG pgvector Runtime

RAG retrieval now requires PostgreSQL with pgvector. Start the local database from the repository root:

```bash
docker compose up -d db
python -m alembic upgrade head
```

Set `DATABASE_URL=postgresql+psycopg://tutor:tutor@localhost:55432/tutor` for local development. Embeddings use dedicated RAG settings and must not reuse chat provider routing:

```bash
RAG_EMBEDDING_API_KEY=
RAG_EMBEDDING_BASE_URL=https://api.openai.com/v1
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_VECTOR_DIM=1536
RAG_HNSW_EF_SEARCH=40
```

`RAG_EMBEDDING_API_KEY` must be an official OpenAI embedding key. Chat providers such as SSSAiCode can still be configured through `OPENAI_BASE_URL`, but that setting is not used for material embeddings.

## Tutor 行为评测雏形

项目包含一个轻量级 Tutor 行为 eval scaffold，用来证明关键教学行为可以被结构化检查。当前版本只做 JSONL schema 校验和 case 分类汇总，不执行复杂 LLM judge。

```bash
python scripts/evaluate_tutor_behavior.py --json
```

## 用户级 LLM Key 配置

Personal provider API keys are encrypted in `user_llm_credentials`; plaintext keys are accepted only on `PUT /api/llm/credentials/{provider_id}` and are never returned by API responses.

Required deployment settings:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the generated value as `LLM_CREDENTIAL_ENCRYPTION_KEY`. For key rotation, deploy the new key as `LLM_CREDENTIAL_ENCRYPTION_KEY` and move the previous active key into comma-separated `LLM_CREDENTIAL_PREVIOUS_KEYS`; old credentials remain decryptable while new writes use the new key. Set `LLM_FINGERPRINT_HMAC_KEY` to a separate random secret when possible; otherwise the app derives an HMAC secret from the encryption key.

`ALLOW_GLOBAL_LLM_FALLBACK=False` is the default so user traffic does not silently fall back to shared backend provider keys. Only set it to `True` for an intentional local demo/admin fallback.

Seed cases 位于 `evals/tutor_cases.jsonl`，覆盖：

- 不直接给答案
- 费曼追问
- 概念解释
- 上下文压缩/新会话承接
- 错题诊断

## 学习资料 RAG v1

项目现在支持上传学习资料，并在 `/api/llm/chat` 里根据学生最后一条问题检索相关片段，注入 Tutor system prompt。第一版目标是证明资料接入、chunk、embedding、检索、引用展示这条工程链路可跑通。

支持格式：

- `.txt` / `.md`
- `.docx`
- `.pdf`（使用 `pypdf` 提取文本，不做 OCR）
- `.epub`

核心端点：

- `POST /api/materials/upload` - 上传资料并生成 chunk embedding
- `GET /api/materials` - 查看已上传资料
- `POST /api/materials/search` - 按 query 检索相关资料片段
- `POST /api/llm/chat` - 可在 `tutor_context.material_ids` 里传入资料 ID，后端会自动检索并返回 `material_context.chunks`

当前边界：

- 默认有 OpenAI key 时使用 `text-embedding-3-small`；无 key 时使用本地 hash embedding fallback，适合开发和测试，不代表真实语义检索效果。
- PDF v1 只支持可复制文本的 PDF；扫描版 PDF 需要后续接 OCR。
- 还没有复杂权限、去重、重排、LLM judge 和检索质量评测；下一步应该补 retrieval eval、rerank、资料删除/重建索引、以及答案引用一致性检查。

## API 端点概览

### 题目服务 (`/api/questions`)
- `POST /api/questions/` - 创建题目
- `GET /api/questions/{question_id}` - 获取题目
- `GET /api/questions/{question_id}/solution` - 获取标准解
- `POST /api/questions/search` - 搜索题目

### 训练服务 (`/api/training`)
- `POST /api/training/sessions` - 创建训练 Session
- `POST /api/training/sessions/{session_id}/start` - 开始 Session
- `GET /api/training/sessions/{session_id}/next` - 获取下一题
- `POST /api/training/sessions/{session_id}/answer` - 提交答案
- `POST /api/training/sessions/{session_id}/complete` - 完成 Session

### 学生服务 (`/api/student`)
- `GET /api/student/{user_id}/mastery` - 获取掌握度
- `GET /api/student/{user_id}/recommendations` - 获取推荐
- `GET /api/student/{user_id}/report` - 获取学习报告
- `GET /api/student/{user_id}/review-plan` - 获取复习计划

### LLM 服务 (`/api/llm`)
- `POST /api/llm/hint` - 生成提示
- `POST /api/llm/explain` - 讲解标准解
- `POST /api/llm/diagnose` - 诊断错误
- `POST /api/llm/summary` - 生成 Session 总结

### 学习资料服务 (`/api/materials`)
- `POST /api/materials/upload` - 上传并索引学习资料
- `GET /api/materials` - 获取学习资料列表
- `POST /api/materials/search` - 检索资料片段

### 分析服务 (`/api/analytics`)
- `GET /api/analytics/question/{question_id}/stats` - 题目统计
- `GET /api/analytics/skill/{skill_id}/stats` - 知识点统计
- `GET /api/analytics/system/stats` - 系统统计
- `GET /api/analytics/problematic-questions` - 问题题目

## 项目结构

```
app/
├── main.py                 # 应用入口
├── config.py              # 配置管理
├── database.py            # 数据库连接
├── models/                # 数据模型
│   ├── __init__.py
│   ├── question.py        # 题目模型
│   ├── student.py         # 学生模型
│   ├── session.py         # Session 模型
│   ├── analytics.py       # 日志模型
│   └── materials.py       # 学习资料与 RAG chunk 模型
├── services/              # 核心服务
│   ├── __init__.py
│   ├── question_bank.py   # 题库服务
│   ├── training_engine.py # 训练引擎
│   ├── student_model.py   # 学生模型服务
│   ├── pomodoro.py        # 番茄钟服务
│   ├── analytics.py       # 分析服务
│   ├── materials.py       # 资料提取、chunk、embedding、检索
│   └── llm_service.py     # LLM 服务
├── api/                   # API 路由
│   ├── __init__.py
│   ├── questions.py
│   ├── training.py
│   ├── student.py
│   ├── materials.py
│   └── llm.py
└── utils/                 # 工具函数
    ├── __init__.py
    └── math_tools.py      # 数学工具集成
```

