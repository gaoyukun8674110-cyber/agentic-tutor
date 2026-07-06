# PRD · RAG 检索层迁移：手写 VP-tree + SQLite → PostgreSQL + pgvector

> 状态：**已定稿 · 可执行**（下方所有决策已拍板，无待定项）
> 作者：AI Tutor 团队
> 目标分支：新开 `feat/rag-pgvector`（便于回滚）
> 目的：把当前"内存 VP-tree + SQLite 里 JSON 存向量"的玩具级检索，替换为工业标准的 **PostgreSQL + pgvector（HNSW 索引 + cosine 算子）**，消除"没有工程意识"的印象，并获得真实的可扩展性。

---

## 0. 已拍板的执行参数（Codex 直接照此执行，勿自行猜测）

| 项 | 已定值 | 说明 |
|---|---|---|
| 向量维度 N | **1536** | 已用真实 key 验证 OpenAI `/v1/embeddings` 返回 1536 维 |
| Embedding 模型 | **OpenAI 官方 `text-embedding-3-small`** | 走 `https://api.openai.com/v1`，独立 key（`sk-proj-...`），已充值可用 |
| Chat 模型（不动） | SSSAiCode `gpt-5.4`，`base_url=https://sssaicode.com/api/v1` | **该厂商不代理 embedding（实测 405），所以 embedding 必须直连官方，二者分离** |
| pgvector 距离算子 | `<=>`（cosine）+ HNSW 索引 `vector_cosine_ops` | 向量已归一化 |
| top_k | 默认 5 / 上限 10（**不变**） | 保持现有行为 |
| 历史数据 | **重嵌入，不搬运** | 旧向量是无 key 时期的 128 维 hash 垃圾，与 1536 不兼容，必须用真模型重新生成 |
| 建表方式 | **Alembic 迁移**（非 create_all） | 见 §5 |
| 测试基座 | 依赖真实 pgvector 容器 | 见 §7 |
| 分支 | `feat/rag-pgvector` | 独立分支，未合主干可弃 |

> ✅ **部署环境已确认**：VPS 位于**新加坡**，可直连 `api.openai.com`，**无需配置出站代理**，嵌入请求不会超时。原 R1 前置项已消除。

> 🔐 **密钥安全**：OpenAI 官方 key 只经环境变量 `OPENAI_API_KEY` 注入，**禁止**写进代码 / `.env.example` / 提交历史。对话中曾明文出现的 key 请 revoke 后重建。

---

## 1. 背景与目标

### 1.1 为什么改（Why）
- **可信度**：当前实现 = SQLite 的 `Text` 列里 `json.dumps` 存向量 + 应用内存里跑手写 VP-tree，每次写入全量重建索引。这在面试/评审里会被判为"能跑但无工程意识"。
- **技术短板（真实存在，非借口）**：
  1. **VP-tree 高维退化**：VP-tree 是度量空间精确最近邻结构，只在低维有优势；1536 维下剪枝失效，退化到近似全表线性扫描。
  2. **全量重建**：`_rebuild_vector_index()` 在每次上传后重建整棵树（`services/materials.py:311,381`），资料一多写入就卡。
  3. **全量载入内存**：检索前把所有向量 load 进内存（`search_snapshot`），不具备规模扩展性。
- **结论**：正确做法是把最近邻检索下沉到数据库，用 pgvector 的 ANN 索引（HNSW）+ cosine 算子。

### 1.2 目标（What / 可验收）
- 全应用数据库从 SQLite 迁移到 **PostgreSQL**。
- `study_material_chunks` 的向量从 `embedding_json TEXT` 迁移为 pgvector 的 **`vector(N)`** 列，建 **HNSW（cosine）** 索引。
- 检索路径 `search_materials()` 改为**一条 SQL**（`ORDER BY embedding <=> :q LIMIT k`），删除 VP-tree 相关代码。
- **对外行为不变**：API 签名、返回结构、`score` 语义、用户隔离、`material_ids` 过滤、`top_k` 默认 5 / 上限 10 全部保持。
- 现有已入库的 embedding 数据**无损迁移**（backfill）。

### 1.3 非目标（Out of scope，明确不做，保持诚实）
- ❌ rerank / cross-encoder
- ❌ hybrid search（向量 + 关键词）/ RRF 融合
- ❌ 检索路由（本项目**从来没有** grep/关键词检索路，见 §2）
- ❌ 量化评估体系（Recall@k / MRR 离线评测）——可另立 PRD

> 面试话术对齐：迁移后你可以诚实地说"我把检索从自研 VP-tree 换成了 pgvector + HNSW，cosine 算子；rerank / hybrid 我知道解决什么问题，但这个数据量还没上"。

---

## 2. 现状基线（Ground Truth，带出处）

| 环节 | 现状 | 出处 |
|---|---|---|
| 数据库 | SQLite，`DATABASE_URL=sqlite:///...tutor.db` | `config.py:10,20` `database.py:9-11` |
| 建表方式 | `Base.metadata.create_all`（**无真实 Alembic 迁移**，`alembic/versions` 为空） | `bootstrap.py:17` `alembic.ini:61` |
| 向量存储 | `embedding_json = Column(Text)`，`json.dumps(embedding)` | `models/materials.py:45` `services/materials.py:304,370` |
| 检索结构 | 手写 **VP-tree + 欧氏距离**，快照落 `.vector-index.json`，**每次写入全量重建** | `services/vector_index.py` 全文；`services/materials.py:311,381,485-506` |
| 距离→分数 | `score = max(0, 1 - d²/2)`（归一化下等价 cosine 相似度） | `services/materials.py:424` |
| top_k | 默认 `RAG_TOP_K=5`，上限截断到 10 | `config.py:96` `services/materials.py:409` |
| embedding | 默认 `text-embedding-3-small`；**无 OPENAI_API_KEY 时静默回退 128 维 hash 假向量** | `services/materials.py:212-219` |
| 检索入口 | `MaterialService.search_materials()` | `services/materials.py:399` |
| 调用方 | `api/materials.py:75`、`api/llm.py:222`（签名不变即可无痛） | — |
| **grep/关键词/hybrid/rerank/路由** | **不存在**，检索只有纯向量单路 | 全仓 grep 零命中 |

---

## 3. 关键设计决策（含取舍）

### D1. 数据库：整库迁移到 PostgreSQL（不是只迁 RAG 表）
`DATABASE_URL` 是全局的，改了它，`users / chat_history / training / llm_credentials` 等所有表都会跑在 Postgres 上。**决定整库迁移**（一个应用连两个库很丑，也不专业）。所有模型当前只用通用类型（`Integer/String/Text`），Postgres 全兼容，无需改其它模型。

### D2. 向量列维度 N：**已定 = 1536**（见 §0）
pgvector `vector(N)` 维度写死为 **1536**（OpenAI `text-embedding-3-small`），做成 `RAG_VECTOR_DIM=1536` 可配置。
- **维度冲突处理**：hash 兜底 provider 现在是 128 维，与 `vector(1536)` 不兼容。
  - **生产**：`fill_material_embeddings` 写入前校验 `len(vector)==RAG_VECTOR_DIM`，不符 **fail-fast**（不再静默 hash 兜底污染索引）。
  - **测试**：让 `HashEmbeddingProvider` 产出 `RAG_VECTOR_DIM` 维（可把测试的 `RAG_VECTOR_DIM` 设小，如 64，列维度随配置建），保证列维度与 provider 一致。

### D2b. ⚠️ Embedding 必须独立于 Chat 走官方 OpenAI（关键，别接错）
当前 embedding 复用 `OPENAI_API_KEY / OPENAI_BASE_URL`（`services/materials.py:212-219`）。但 **chat 走的是 SSSAiCode（`https://sssaicode.com/api/v1`），该厂商实测不代理 `/embeddings`（返回 405）**。因此：
- **必须为 embedding 引入独立配置**，不要让它跟随 chat 的 base_url。新增：
  - `RAG_EMBEDDING_API_KEY`（= OpenAI 官方 `sk-proj-...`）
  - `RAG_EMBEDDING_BASE_URL`（= `https://api.openai.com/v1`，默认值即此）
  - `RAG_EMBEDDING_MODEL`（= `text-embedding-3-small`，已存在）
- `OpenAIEmbeddingProvider` / `default_embedding_provider()` 改为读上述**专用**变量；找不到 embedding key 时 **fail-fast 报错**，禁止静默回退 hash（生产环境）。
- **反例（禁止发生）**：把 embedding 的 base_url 指到 `sssaicode.com` → 必然 405。

### D3. 距离算子：cosine（`<=>`）+ HNSW 索引（`vector_cosine_ops`）
- 算子用 `<=>`（cosine 距离）。embedding 已在 `normalize_vector` 归一化，cosine 是防坑默认。
- 索引选 **HNSW**（vs IVFFlat）：小数据量下 HNSW 建图查询快、召回高、无需预聚类；IVFFlat 需先有数据才能建、召回略低。**HNSW 是本项目合理默认**。
- **score 语义保持不变**：SQL 取 `1 - (embedding <=> :q)` 作为相似度（等价现有 `1 - d²/2`，因为归一化下 `d²=2-2cos`）。

### D4. 检索从"内存树"改为"一条 SQL"
```sql
SELECT c.id, c.material_id, 1 - (c.embedding <=> :query_vec) AS score
FROM study_material_chunks c
JOIN study_materials m ON m.id = c.material_id
WHERE m.status = 'ready'
  AND (:user_id IS NULL OR m.user_id = :user_id)          -- 用户隔离
  AND (:material_ids IS NULL OR c.material_id = ANY(:mids))-- 可选过滤
ORDER BY c.embedding <=> :query_vec
LIMIT :top_k;
```
删除 `vector_index.py` 全套（VP-tree / snapshot / 全量重建），删除 `MaterialService` 里 `_rebuild_vector_index / _load_or_rebuild_vector_index / _indexable_chunks / build_snapshot / search_snapshot` 依赖。写入路径只需把向量直接写进 `embedding` 列，**不再重建任何索引**（HNSW 增量维护由 pgvector 负责）。

### D5. 迁移用真实 Alembic 迁移（而非 create_all）
新增一支 Alembic 迁移做：`CREATE EXTENSION IF NOT EXISTS vector;` → 加 `embedding vector(N)` 列 → backfill（把旧 `embedding_json` 解析写入新列）→ 建 HNSW 索引 → 删旧 `embedding_json` 列。这本身就是"工程意识"的证据。

---

## 4. 详细改动清单（按文件）

| 文件 | 改动 | 类型 |
|---|---|---|
| `requirements.txt` | `+ pgvector==0.3.6`、`+ "psycopg[binary]==3.2.x"`；`numpy` 保留（不再必需可留） | 依赖 |
| `app/config.py` | `DATABASE_URL` 默认改 Postgres（或保持可配置，部署注入）；新增 `RAG_VECTOR_DIM:int=1536`；把 `.env` 里幽灵配置 `RAG_HNSW_EF_SEARCH` 变成**真读取**并用于会话级 `SET hnsw.ef_search` | 配置 |
| `app/database.py` | `create_engine` 保留 sqlite 分支判断即可（Postgres 不传 `check_same_thread`）；可加连接池参数 | 连接 |
| `app/models/materials.py` | `embedding_json = Column(Text)` → `embedding = Column(Vector(RAG_VECTOR_DIM))`（`from pgvector.sqlalchemy import Vector`）；在 `__table_args__` 声明 HNSW 索引（`postgresql_using="hnsw"`, `vector_cosine_ops`, `ef_construction/m` 参数） | 模型 |
| `app/services/vector_index.py` | **整文件删除**（VP-tree / snapshot / 全量重建全部废弃） | 删除 |
| `app/services/materials.py` | 重写 `search_materials()` 为 §D4 的 SQL；写入路径 `embedding=vector`（不再 `json.dumps`）；删除 `_rebuild/_load/_indexable`、`PersistentVectorIndex` 引用、`build_snapshot/search_snapshot` import；`default_embedding_provider` 增加维度校验/ fail-fast | 服务 |
| `app/api/materials.py` / `app/api/llm.py` | **无需改**（`search_materials` 签名与返回结构保持一致）→ 回归验证即可 | 验证 |
| `alembic/versions/xxxx_pgvector.py` | 新增迁移：建扩展 → 加列 → backfill → 建 HNSW 索引 → 删旧列（见 §5） | 迁移 |
| `alembic.ini` / `alembic/env.py` | `sqlalchemy.url` 改由 `settings.DATABASE_URL` 注入（当前硬编码 sqlite） | 迁移 |
| `Dockerfile` / `docker-compose`（新增） | 新增 `db` 服务用 `pgvector/pgvector:pg16` 镜像；backend 依赖 db + healthcheck；`DATABASE_URL` 注入 | 部署 |
| `.env.example` | `DATABASE_URL` 换 Postgres 示例；`RAG_HNSW_EF_SEARCH` 从"幽灵"变真配置；新增 `RAG_VECTOR_DIM` | 配置 |
| `tests/test_materials_rag.py`、`test_materials_api.py`、`test_llm_material_context.py` | 改为连真实 Postgres（见 §7 测试策略）；断言逻辑基本不变（仍验召回顺序、用户隔离、material_ids 过滤） | 测试 |

---

## 5. 数据迁移（Backfill）

Alembic 迁移步骤（单向 upgrade）：
1. `CREATE EXTENSION IF NOT EXISTS vector;`
2. `ALTER TABLE study_material_chunks ADD COLUMN embedding vector(:N);`
3. **Backfill**：遍历现有行，`json.loads(embedding_json)` → 校验维度 == N → 写入 `embedding`；维度不符的行标记/跳过并记录（大概率是历史 hash 128 维脏数据，需重嵌入）。
4. `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);`
5. `ALTER TABLE study_material_chunks DROP COLUMN embedding_json;`
6. `embedding` 设 `NOT NULL`（backfill 完成后）。

> 若线上历史向量是 128 维 hash（无真 key 时期产生的），这些数据**语义无效**，迁移时应重新用真 embedding 生成，而非搬运垃圾。→ 见 §9-Q1。

**downgrade**：加回 `embedding_json`、从 `embedding` 反序列化回 JSON、删列与索引（保证可回滚）。

---

## 6. 部署改动（Docker on VPS）

- 新增 Postgres 服务，镜像 `pgvector/pgvector:pg16`（自带扩展，`CREATE EXTENSION` 即可用）。
- backend 容器 `depends_on: db(healthcheck)`；`DATABASE_URL=postgresql+psycopg://user:pass@db:5432/tutor`。
- 首次启动跑 `alembic upgrade head`（替代/补充现有 `create_all` bootstrap；两者取舍见 §9-Q3）。
- 数据卷持久化 Postgres data；备份策略沿用现有运维。

---

## 7. 测试策略（最大改造点）

现状：测试用**内存 SQLite + `create_all`**（`tests/*.py` 大量 `Base.metadata.create_all`）。pgvector 无法在 SQLite 上跑，必须调整：
- **方案（推荐）**：CI 与本地都用 docker 起一个 `pgvector/pgvector` 实例，测试连它；用小维度（`RAG_VECTOR_DIM=64`）+ 确定性假 embedding 加速。
- 备选：`testcontainers-python` 按需拉起 pg（更干净但增依赖）。
- `test_llm_material_context.py` 里的 `FakeMaterialService.search_materials` 签名不变，无需动。
- 断言迁移：召回顺序、`score` 单调、用户隔离、`material_ids` 过滤、`top_k` 边界（5 默认 / 10 上限）逐条保留。

> ⚠️ 这是本次工作量的大头——不是改检索本身，而是让整个测试套件在 Postgres 上跑起来。

---

## 8. 验收标准（Definition of Done）

- [ ] `docker compose up` 起 backend + pgvector，`alembic upgrade head` 成功，`\d study_material_chunks` 能看到 `embedding vector(N)` + HNSW 索引。
- [ ] 上传一份 PDF → 检索命中，返回结构 / `score` / 排序与迁移前一致（同一 query 结果集等价）。
- [ ] `EXPLAIN` 显示检索走 **HNSW 索引扫描**，不是 Seq Scan。
- [ ] 用户隔离、`material_ids` 过滤、`top_k` 边界测试全绿。
- [ ] 代码库 grep `vector_index / VP-tree / build_snapshot / _rebuild_vector_index` **零命中**（旧代码彻底删净）。
- [ ] 现有 embedding 数据 backfill 完成，无维度不符的残留（或已重嵌入）。
- [ ] README / `.env.example` 更新，`RAG_HNSW_EF_SEARCH` 不再是幽灵配置。

---

## 9. 风险与已决事项（原开放问题已全部拍板，见 §0）

- **Q1 · 向量维度 N** → **已定 = 1536**（OpenAI `text-embedding-3-small`，实测验证通过）。
- **Q2 · 历史数据** → **重嵌入**。旧向量为无 key 时期 128 维 hash，语义无效，backfill 阶段跳过并对相关 material 触发重新嵌入（走 `fill_material_embeddings` 逻辑），不搬运垃圾。
- **Q3 · 建表方式** → 新结构走 **Alembic 迁移**；`bootstrap.create_all` 仅保留给测试/首启兜底。
- **Q4 · 测试基础设施** → **接受**依赖真实 pgvector 容器（CI + 本地）。
- **R1 · VPS 出站到 openai.com** → **已确认可直连**（VPS 在新加坡），无需代理。前置项消除。
- **R2 · 密钥** → 仅经 `OPENAI_API_KEY` 环境变量注入，禁止入库。

---

## 10. 实施顺序（"今天一杆子到底"的执行 checklist）

1. 定 N（Q1）→ 加依赖 `pgvector` + `psycopg` → 起本地 `pgvector/pgvector` 容器。
2. 改 `config/database/models`（vector 列 + 索引声明）。
3. 写 Alembic 迁移（扩展→列→backfill→索引→删旧列）。
4. 重写 `services/materials.py` 检索为 SQL；删 `vector_index.py` 及所有引用。
5. 改测试基座连 Postgres，跑绿 `test_materials_rag / test_materials_api`。
6. 更新 Docker / compose / `.env.example` / README。
7. 全量回归 + `EXPLAIN` 验证走索引 → 按 §8 逐条打勾。
8. 提交（建议独立分支 `feat/rag-pgvector`，便于回滚）。

---

## 11. 回滚方案
- 代码层：独立分支，未合主干可直接弃。
- 数据层：Alembic `downgrade`（恢复 `embedding_json`、删 vector 列/索引）。
- 部署层：`DATABASE_URL` 切回 SQLite + 上一个镜像 tag，即恢复旧行为（旧向量 JSON 仍在 downgrade 后可用）。
