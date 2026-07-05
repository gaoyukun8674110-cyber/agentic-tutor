# PRD：将向量检索从手写 VP-tree 迁移到 pgvector（方言感知）

> 交付对象：实现 AI（Codex）。本文件是唯一事实来源。所有决策已在文中拍板，**不要再自行更改设计方向**；如遇文中未覆盖的细节，按"与现有代码风格一致 + 最小改动"处理。

---

## 1. 背景与现状（必须先读懂）

当前检索实现是一棵**手写 VP-tree**，序列化成 JSON 文件，问题有三：

1. 在 1536 维 embedding 下 VP-tree 剪枝基本失效（维度灾难），复杂度≈全表扫描，**付出了树的复杂度却拿不到加速**。
2. 每次上传材料**全量重建整棵树并写 `.vector-index.json` 文件**，多 worker 并发写有竞态、无增量更新。
3. embedding 存 `TEXT` JSON，查询时全部读进 Python 计算。

**涉及的现有代码（迁移时会改到）：**

- `backend/app/services/vector_index.py` — VP-tree 全部逻辑（`build_snapshot` / `search_snapshot` / `PersistentVectorIndex` / `euclidean_distance`）。**本次删除。**
- `backend/app/services/materials.py` — `MaterialService`：
  - `search_materials()`（第 399 行起）：当前调用 `_load_or_rebuild_vector_index()` + `search_snapshot()`。
  - `_rebuild_vector_index()` / `_load_or_rebuild_vector_index()` / `_indexable_chunks()` / `_ready_chunk_stats()` / `self.vector_index`：VP-tree 相关，**本次删除或替换**。
  - `create_material_from_bytes()`（~第 311 行）和 `fill_material_embeddings()`（~第 381 行）末尾都调用了 `self._rebuild_vector_index()`。
  - `normalize_vector()` / `cosine_similarity()` / embedding provider（`HashEmbeddingProvider` / `OpenAIEmbeddingProvider` / `default_embedding_provider`）**保留**。
- `backend/app/models/materials.py` — `StudyMaterialChunk.embedding_json`（`Text`，保留）。
- `backend/app/config.py` — `RAG_TOP_K=5`、`RAG_EMBEDDING_MODEL="text-embedding-3-small"`、`RAG_HASH_EMBEDDING_DIMENSIONS=128`。
- `backend/alembic/versions/` — 迁移目录，命名规范见现有文件如 `20260514_04_user_llm_credentials.py`。
- 测试：`backend/tests/test_materials_rag.py`、`backend/tests/test_materials_api.py`（均用 `sqlite:///:memory:`）。

---

## 2. 目标 / 非目标

**目标**
- 生产（Postgres）用 pgvector + HNSW 索引 + cosine 距离做检索，删除 VP-tree 及 JSON 文件那套。
- 测试与无 Postgres 的本地开发（SQLite）继续可用，检索结果排序语义不变。
- 对外 API（`search_materials` 返回结构与 `score` 数值语义）**保持不变**。

**非目标**
- 不改 chunk 切分、embedding provider、上传流程的对外行为。
- 不引入独立向量数据库（Milvus/Qdrant 等）。
- 不做 reranking、hybrid search。

---

## 3. 关键约束与已拍板的决策

### 3.1 双数据库方言（最重要）
- 测试/默认本地 = **SQLite**（`sqlite:///:memory:`，`Base.metadata.create_all` 建表），**不能出现 `vector` 列类型**，否则建表即崩。
- 生产 = **Postgres + pgvector**。
- **决策：不把 `vector` 列放进 ORM model**。`embedding` 向量列**只通过 Alembic 迁移在 Postgres 上创建**，并**只在 `PgVectorStore` 里用原生 SQL 读写**。SQLite 上该列不存在、永不被引用。

### 3.2 canonical 存储 = `embedding_json`
- `embedding_json`（`Text`）保持为**所有环境的权威 embedding 存储**，写入路径不变。
- Postgres 上的 `embedding vector` 列是**派生副本**，写完 chunk 后由 `PgVectorStore` 同步填充。这样 SQLite 路径完全不依赖向量列。

### 3.3 维度统一（消除 128 vs 1536 冲突）
- 新增配置 `RAG_EMBEDDING_DIM: int = 1536`。
- **列固定为 `vector(1536)`**（迁移里写死 1536）。
- `HashEmbeddingProvider` 的默认维度改为 `settings.RAG_EMBEDDING_DIM`（即 1536），使 hash fallback 也能进同一向量列。
- `RAG_HASH_EMBEDDING_DIMENSIONS` 默认值改为 `1536`（或直接改用 `RAG_EMBEDDING_DIM`，二选一，保持单一来源）。
- 若将来换 embedding 模型改维度：需要新建迁移，本 PRD 不覆盖。

### 3.4 距离度量 = cosine，score 语义不变
- 向量入库前已 `normalize_vector` 归一化为单位向量，**保持**。
- Postgres 用 pgvector cosine 距离操作符 `<=>`，配 `vector_cosine_ops`。
- **score 计算必须保持与当前一致**：当前 `score = round(max(0.0, 1 - dist²/2), 6)`，对单位向量恰等于 cosine 相似度。
  - Postgres：`similarity = 1 - (embedding <=> query)`，即 `score = round(max(0.0, 1 - cosine_distance), 6)`。
  - SQLite 暴力路径：`score = round(max(0.0, cosine_similarity(q, v)), 6)`（`cosine_similarity` 已存在）。
  - 两条路径对同一数据必须给出**相同排序**和**数值一致**的 score。

### 3.5 过滤语义必须保持
`search_materials` 现有行为需原样保留：
- 只检索 `StudyMaterial.status == "ready"` 的 chunk。
- 传入 `user_id` 时，只在该用户的材料内检索（当前用 per-user 树实现；SQL 用 `WHERE study_materials.user_id = :user_id`）。`user_id` 为 None 时全局检索。
- 传入 `material_ids` 时，限定在这些材料内。
- `top_k` 取值：`max(1, min(top_k or RAG_TOP_K, 10))`（保持现逻辑）。
- 当前 `allowed_user_ids` 实参恒为 `None`，可忽略该维度。

---

## 4. 详细改动清单

### 4.1 依赖
- `backend/requirements.txt` 增加：`pgvector`（SQLAlchemy/psycopg 集成库）。确认 `psycopg`/`psycopg2` 生产依赖已存在（Postgres 连接用）；若无则一并加上与现有连接方式匹配的驱动。

### 4.2 配置 `backend/app/config.py`
- 新增 `RAG_EMBEDDING_DIM: int = 1536`。
- 将 `RAG_HASH_EMBEDDING_DIMENSIONS` 默认改为 `1536`（与 `RAG_EMBEDDING_DIM` 一致）。
- 可选：新增 `RAG_HNSW_EF_SEARCH: int = 40`（查询时召回/速度平衡，见 4.6）。

### 4.3 Embedding provider `backend/app/services/materials.py`
- `HashEmbeddingProvider.__init__` 默认维度取 `settings.RAG_EMBEDDING_DIM`。
- `default_embedding_provider()`：`HashEmbeddingProvider(dimensions=settings.RAG_EMBEDDING_DIM)`。
- `OpenAIEmbeddingProvider`：保持默认（`text-embedding-3-small` 原生 1536）。**不改**。

### 4.4 新增向量存储抽象 `backend/app/services/vector_store.py`（新建文件）

定义方言感知的检索后端：

```python
class VectorStore(Protocol):
    def sync_chunks(self, db, chunk_ids: list[int]) -> None: ...   # 写完 chunk 后同步向量列（SQLite 为 no-op）
    def search(self, db, *, query_vector, top_k, user_id, material_ids) -> list[tuple[int, float]]: ...
        # 返回 [(chunk_id, score), ...]，score = cosine 相似度，按 score 降序
```

- **`PgVectorStore`**：
  - `sync_chunks`：对给定 chunk_id，用原生 SQL 从各行 `embedding_json` 读向量并写入 `embedding` 列。示例：
    `UPDATE study_material_chunks SET embedding = :vec WHERE id = :id`（`:vec` 用 pgvector 参数绑定，list[float] → vector）。
  - `search`：一条 SQL 完成过滤 + 排序 + 取 top_k：
    ```sql
    SELECT c.id, 1 - (c.embedding <=> :qvec) AS score
    FROM study_material_chunks c
    JOIN study_materials m ON m.id = c.material_id
    WHERE m.status = 'ready'
      AND (:user_id IS NULL OR m.user_id = :user_id)
      AND (:no_material_filter OR c.material_id = ANY(:material_ids))
      AND c.embedding IS NOT NULL
    ORDER BY c.embedding <=> :qvec
    LIMIT :top_k
    ```
    score 做 `round(max(0.0, score), 6)`。
- **`BruteForceVectorStore`**（SQLite/其他方言，取代 VP-tree）：
  - `sync_chunks`：no-op。
  - `search`：用 ORM 查出候选（`status=='ready'` + user/material 过滤），逐行 `json.loads(embedding_json)`，用现有 `cosine_similarity(query_vector, v)` 打分，降序取 top_k。数据量小（测试/小库），全量计算即可。
- **工厂**：`def make_vector_store(db_or_engine) -> VectorStore`，按 `bind.dialect.name == "postgresql"` 选择 `PgVectorStore`，否则 `BruteForceVectorStore`。

### 4.5 改造 `MaterialService`（`backend/app/services/materials.py`）
- 删除：`self.vector_index`、`_rebuild_vector_index`、`_load_or_rebuild_vector_index`、`_indexable_chunks`。`_ready_chunk_stats` 若无其他引用可一并删。
- `__init__`：用 `self.vector_store = make_vector_store(self.db)` 替换 `PersistentVectorIndex(...)`。
- `create_material_from_bytes` / `fill_material_embeddings`：把结尾的 `self._rebuild_vector_index()` 替换为 `self.vector_store.sync_chunks(self.db, <本次写入的 chunk_id 列表>)`（需在 commit 后拿到 chunk id；可在插入时收集）。
- `search_materials`：删除 snapshot 加载与 `search_snapshot` 调用，改为：
  ```python
  chunk_scores = self.vector_store.search(
      self.db, query_vector=query_vector, top_k=top_k,
      user_id=user_id, material_ids=set(material_ids) if material_ids else None,
  )
  ```
  后续用 `chunk_scores`（已是 `(chunk_id, score)`，score 即相似度）组装返回结构，**保持返回字段与顺序不变**（`chunk_id/material_id/filename/source_label/content/score/embedding_mode`）。
  注意：不再需要 `1 - dist²/2` 的换算——`PgVectorStore`/`BruteForceVectorStore` 已直接返回 cosine 相似度作为 score。

### 4.6 删除文件
- 删除 `backend/app/services/vector_index.py`。
- 删除对 `.vector-index.json` 的一切引用（`self.upload_dir / ".vector-index.json"`）。
- 若磁盘存在旧的 `.vector-index.json`，无需代码清理（可在部署步骤手动删）。

### 4.7 Alembic 迁移（新建，命名遵循现有 `YYYYMMDD_0N_*.py` 规范）
迁移必须**方言感知**，SQLite 上整体 no-op：

```python
def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE study_material_chunks ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    # 回填现有数据（把 embedding_json 灌进向量列）——见下方回填说明
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw
        ON study_material_chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute("ALTER TABLE study_material_chunks DROP COLUMN IF EXISTS embedding")
```

- **回填**：迁移中无法用 Python 逐行解析 JSON 转 vector 的话，提供独立脚本 `backend/scripts/backfill_embeddings.py`：读取所有 `embedding_json` 非空的 chunk，`UPDATE ... SET embedding = :vec`。迁移里也可用 SQL `embedding = embedding_json::vector`（pgvector 支持文本 `[...]` 转 vector，前提 JSON 是 `[...]` 数组字面量——现状 `json.dumps(list)` 正是该格式）。**优先在迁移里直接 `UPDATE study_material_chunks SET embedding = embedding_json::vector WHERE embedding_json IS NOT NULL AND embedding_json <> ''`**，最省事。
- 查询时可选设置 `SET hnsw.ef_search = :RAG_HNSW_EF_SEARCH`（在 `PgVectorStore.search` 里按会话设置），默认 40，用于召回/延迟平衡。

### 4.8 查询时的向量绑定
- `PgVectorStore` 绑定 `:qvec` 时用 pgvector 的 SQLAlchemy 类型或将 list 转成 `[..]` 文本再 `::vector`。任选其一，保证参数化、防注入。

---

## 5. 部署前置（写进交付说明，供人工执行）

1. Postgres 必须带 pgvector：生产镜像改用 `pgvector/pgvector:pg16`（或在现有 PG 上 `CREATE EXTENSION vector`，需超级用户权限）。见 `backend/Dockerfile` / 部署脚本 `backend/push.sh`。
2. 跑迁移：`alembic upgrade head`（会建 extension、列、HNSW 索引并回填）。
3. 迁移后可删除旧的 `storage/materials/.vector-index.json`。
4. 生产确保用 OpenAI embedding（1536 维），`RAG_EMBEDDING_DIM=1536`。

---

## 6. 验收标准（Definition of Done）

- [ ] `backend/app/services/vector_index.py` 已删除，无任何 import 残留。
- [ ] `grep -rn "vector-index.json\|search_snapshot\|build_snapshot\|_rebuild_vector_index" backend/` 无结果。
- [ ] SQLite 下全部现有测试通过：`cd backend && pytest`（重点 `test_materials_rag.py`、`test_materials_api.py`）。检索结果排序与旧实现一致，`score` 字段仍为 [0,1] 的 cosine 相似度、6 位小数。
- [ ] 新增测试 `test_materials_rag.py`：验证 `BruteForceVectorStore` 的 top_k 排序、user_id 隔离、material_ids 过滤、只返回 `status=='ready'`。
- [ ] 若 CI 可起 Postgres service：新增一个 pgvector 冒烟测试（建 extension → 建列 → 插入 → `<=>` 查询）；否则在 PR 描述里说明 Postgres 路径为手动验证并附验证步骤。
- [ ] 维度：hash provider 与 OpenAI provider 都产出 1536 维；无 128 维残留导致的插入失败。
- [ ] `search_materials` 返回结构、字段名、顺序与迁移前完全一致。
- [ ] Alembic：`upgrade` 在 SQLite 上 no-op、在 Postgres 上建 extension/列/索引并完成回填；`downgrade` 可回滚。

---

## 7. 回滚方案

- 代码层面：本次改动集中在 `materials.py` + 新增 `vector_store.py` + 删除 `vector_index.py`。回滚即 revert PR。
- 数据层面：`alembic downgrade` 删除 `embedding` 列与索引；`embedding_json` 始终是权威数据，无数据丢失风险。

---

## 8. 给实现者的注意点（易错）

1. **绝不**把 `vector` 类型列加进 `backend/app/models/materials.py` 的 ORM model —— 会让 SQLite `create_all` 崩溃。向量列只活在 Postgres + 原生 SQL 里。
2. score 必须是 cosine 相似度、`round(max(0.0, x), 6)`，两条后端路径数值语义一致。不要保留旧的 `1 - dist²/2` 换算。
3. 归一化（`normalize_vector`）保留，pgvector 才能用 cosine 得到正确结果。
4. 过滤（ready / user_id / material_ids）不能丢，SQL 与暴力路径行为一致。
5. `sync_chunks` 在 Postgres 上要在 chunk **已 commit / flush 拿到 id** 之后执行。
