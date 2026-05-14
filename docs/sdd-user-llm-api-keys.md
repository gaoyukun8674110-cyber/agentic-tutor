# SDD - AI Tutor 用户级大模型 API Key 配置

| 字段 | 值 |
| --- | --- |
| 文档编号 | SDD-AITUTOR-USER-LLM-KEYS-001 |
| 版本 | v2.0 draft |
| 状态 | 待评审 |
| 起草日期 | 2026-05-14 |
| 修订日期 | 2026-05-14 |
| 适用代码库 | `H:\ai-tutor` |
| 影响范围 | `backend/`, `backend/alembic/`, `frontend/`, `docs/` |
| 关联文档 | `docs/sdd-multi-user-auth.md`, `AGENTS.md`, `backend/README.md` |
| 执行原则 | 先确认本 SDD，再进入实现计划与代码修改 |

**v2.0 主要变更**：拆分 PUT/PATCH、加固 `base_url` SSRF 防护、引入密钥轮换与 AAD 绑定、修正 `is_default` 并发竞争、`/api/llm/chat` 回显 `credential_source`、显式给出 Pydantic / 模块层面的实现强约束（§19）。

---

## 1. 背景

当前项目已经具备多用户登录能力：`users` 表中已有 `test-01`，业务 API 通过 `Authorization: Bearer <access_token>` 解析 `current_user`，并用 `current_user.username` 隔离对话、资料、Dashboard 等用户数据。

但大模型 API Key 仍是后端全局配置：

- `backend/app/config.py` 通过 `.env` 读取 `OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`QWEN_API_KEY`、`LINKAPI_API_KEY` 等。
- `backend/app/services/llm_service.py` 的 provider 配置只来自 `settings`，并按 `provider_id` 单层缓存 `OpenAI` client，无法按用户隔离。
- `frontend/src/features/tutor/useTutorChat.ts` 发起聊天时传 `provider: 'auto'`，没有用户级 API Key 输入或选择流程。
- 当前本地 `backend/.env` 不存在，运行时外部 provider API Key 均未配置；只有不需要 API Key 的 `ollama` 在 metadata 中显示 enabled，但是否可用取决于本机 Ollama 服务是否运行。

业务目标是：**新用户登录后，可以填写自己的大模型 API Key；之后该用户的 Tutor 对话和其他 LLM 功能优先使用该用户自己的 Key，而不是所有用户共享一个后端 Key；并且用户在前端能够清晰看到当前 LLM 请求究竟用的是谁的 Key。**

## 2. 目标

1. 登录用户可以在前端配置自己的大模型 provider 凭证。
2. API Key 只提交给后端保存，保存后不再明文返回给浏览器。
3. 每个用户只能读取、更新、删除自己的模型凭证。
4. `/api/llm/chat`、`/api/llm/hint`、`/api/llm/explain`、`/api/llm/diagnose`、`/api/llm/summary` 都按当前用户解析 provider，**并且复用同一套 provider resolution 代码路径**。
5. Provider metadata 要能告诉前端"当前用户是否已配置可用 provider"，但不能泄露 Key。
6. `/api/llm/chat` 响应必须显式回显 `credential_source`（`user` / `global` / `local`），让用户能够确认本次对话用的是不是自己的 Key。
7. 保留后端全局 `.env` provider 作为可选 fallback（`ALLOW_GLOBAL_LLM_FALLBACK`），便于本地 demo、管理员托管模式和无个人 Key 的用户试用。
8. 用户更新或删除 Key 后，后续请求必须立即使用新配置，不得继续复用旧 Key 客户端。
9. 相关错误必须安全脱敏，不能把 `sk-...`、`Bearer ...` 或完整 provider 异常原样暴露到前端或日志。
10. 加密密钥要支持轮换：泄露或合规要求换密钥时不必清空用户 Key。

## 3. 非目标

- 本期不实现计费、余额查询、用量配额、充值、账单归因。
- 本期不实现 OpenAI OAuth、Claude Console OAuth 或第三方授权登录。
- 本期不实现原生 Anthropic/Gemini SDK adapter；继续保持当前状态：OpenAI-compatible provider 可用，native provider 标记为未实现。
- 本期不把 API Key 存到 localStorage、sessionStorage、IndexedDB 或前端源码。
- 本期不做多 workspace、多组织、多角色权限；隔离边界仍是当前登录用户。
- 本期不做复杂模型市场；provider 列表仍由后端代码定义，但**允许用户在 default_model 字段填写自由文本**（前端给 dropdown + "其他"）。
- 本期不做"保存前先测试"的预校验流程（v2 再加）。

## 4. 设计选择

### 4.1 方案 A：后端加密保存用户级凭证（推荐）

新增 `user_llm_credentials` 表。用户在设置页提交 API Key，后端用服务端加密密钥加密后入库。LLM 调用时，后端按当前用户解密并构建 provider client。

优点：

- 用户只需配置一次。
- API Key 不进入前端持久化存储。
- 可以复用当前后端代理架构。
- 后续可以扩展验证、禁用、轮换、审计、配额。

代价：

- 后端必须管理加密密钥。
- 数据库备份和加密密钥要分开保护。
- 需要处理 client 缓存失效，避免旧 Key 被继续使用。

### 4.2 方案 B：每次聊天请求都由前端携带 API Key

前端不保存或只临时保存 Key，每次 `/api/llm/chat` 把 Key 带给后端。

优点：

- 后端不用存储用户 Key。

问题：

- 很容易被误放进浏览器持久化、日志、错误上报或请求重放。
- 每个 LLM endpoint 都要扩展请求体，污染业务 API。
- 刷新页面后用户需要重新输入，体验差。

结论：不采用。

### 4.3 方案 C：只使用后端全局 `.env` Key

继续由部署者统一配置 Key，所有用户共享。

优点：

- 当前代码改动最少。

问题：

- 不满足"新用户使用自己的 API"这一核心需求。
- 无法按用户隔离成本和 provider。

结论：只作为 fallback，不作为目标方案。

## 5. 总体架构

采用方案 A，并保留全局 fallback。

```text
React settings page
  -> POST/PATCH /api/llm/credentials/{provider_id}
      -> validate provider id, ownership, base_url whitelist
      -> encrypt(api_key, AAD = f"{user_id}:{provider_id}")
      -> upsert user_llm_credentials

Tutor / LLM API (chat | hint | explain | diagnose | summary)
  -> current_user from JWT (Authorization header only, no cookie auth)
  -> LLMCredentialResolver.resolve(current_user, requested_provider)
       -> returns ResolvedProvider(api_key, base_url, model, source, fingerprint)
  -> LLMService.complete_chat(resolved, messages, ...)
  -> response includes credential_source + credential_fingerprint
  -> errors sanitized through safe_llm_error()
```

模块边界（与 §10 对应）：

| 模块 | 文件（建议） | 职责 |
| --- | --- | --- |
| Auth | `api/auth.py` | 登录态，不参与 credential 流程 |
| LLM API | `api/llm.py` | provider metadata、credential CRUD、chat/hint/explain/diagnose/summary、限速 |
| Provider Registry | `services/llm_provider_registry.py` | **纯数据**：provider 默认值（name/adapter/default base_url/models/requires_api_key/implemented），不读 settings、无副作用 |
| Credential Service | `services/llm_credential_service.py` | DB CRUD、加解密、AAD 校验、fingerprint、safe metadata |
| Credential Resolver | `services/llm_credential_resolver.py` | 组合 registry + DB credential + settings fallback，输出 `ResolvedProvider` |
| LLM Service | `services/llm_service.py` | prompt 构建、调用 provider client、analytics 日志；只接受 `ResolvedProvider`，不再读 `settings.*_API_KEY` |

## 6. 数据模型

新增模型文件：`backend/app/models/llm_credentials.py`，在 `backend/app/models/__init__.py` 导出。

### 6.1 `user_llm_credentials`

| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 自增主键 |
| `user_id` | Integer | FK `users.id` ON DELETE CASCADE, index | 归属用户 |
| `provider_id` | String(50) | NOT NULL | `openai`、`deepseek`、`qwen`、`linkapi` 等，必须存在于 registry |
| `encrypted_api_key` | Text | NULLABLE | 加密后的密文；`ollama` 可为空 |
| `api_key_fingerprint` | String(32) | NULLABLE, index | HMAC-SHA256(server_secret, api_key) 前 16 hex；不可反推出 Key，仅用于 UI 标识与缓存 key |
| `base_url` | String(500) | NULLABLE | 用户覆盖 provider base URL；为空表示用 registry 默认值；写入前必须过 §8.6 白名单校验 |
| `default_model` | String(120) | NULLABLE | 用户默认模型；自由文本；后端不校验是否在 registry models 列表内 |
| `is_default` | Boolean | NOT NULL, default False | 当前用户 `provider='auto'` 的优先选择 |
| `is_enabled` | Boolean | NOT NULL, default True | 用户可临时禁用该 provider |
| `last_validated_at` | String(50) | NULLABLE | 最近一次测试成功时间，ISO8601 |
| `last_validation_error_code` | String(32) | NULLABLE | 枚举码（见 §6.3），不存自由文本 |
| `last_used_at` | String(50) | NULLABLE | 最近一次被 chat/hint 等使用的时间，便于用户核实 |
| `created_at` | String(50) | NOT NULL | ISO8601 |
| `updated_at` | String(50) | NOT NULL | ISO8601 |

> **时间字段类型说明**：与现有表（`tutor_conversations` 等）风格一致，时间用 ISO8601 字符串。下一次大改造时统一迁移到 `DateTime(timezone=True)`，本期不动。

索引和约束：

- `UNIQUE(user_id, provider_id)`：每个用户每个 provider 一条配置。
- `is_default` 唯一性约束（同一用户最多一条 `is_default=True`）见 §6.4。
- `provider_id` 必须在后端 provider registry 中存在，否则在应用层拒绝写入。

### 6.2 API Key 指纹

`api_key_fingerprint` 用于：

1. UI 显示"已配置"标识（非必须展示给用户，详见 §11.2）。
2. provider client 缓存 key 的一部分。
3. 日志/analytics 中标识用了哪一份凭证，**不能用作认证**。

实现：

```python
fingerprint = hmac.new(
    key=settings.LLM_FINGERPRINT_HMAC_KEY.encode(),
    msg=api_key.encode("utf-8"),
    digestmod=hashlib.sha256,
).hexdigest()[:16]
```

- `LLM_FINGERPRINT_HMAC_KEY` 可与 `LLM_CREDENTIAL_ENCRYPTION_KEY` 同源（如取后者的 SHA-256）但不能直接复用。
- 用 HMAC 而非裸 SHA-256：防止跨系统 fingerprint 相关性攻击。
- 字段长度预留 `String(32)`，方便未来切到 32 hex 不再迁移。

### 6.3 验证错误码枚举

`last_validation_error_code` 只能取以下值之一，**绝对不存自由文本**（避免 provider 原始异常被持久化）：

| 码 | 含义 |
| --- | --- |
| `auth_error` | 认证失败（401/403） |
| `rate_limit` | 限速（429） |
| `network_error` | 连接超时 / DNS 失败 / 其他网络异常 |
| `model_not_found` | 模型不存在（404、unsupported model） |
| `bad_request` | 请求参数被 provider 拒绝 |
| `unknown` | 其他 |

完整错误文本只在当次响应里返回 + 进入后端日志（log 也要经过 `safe_llm_error()`）。

### 6.4 `is_default` 并发约束

应用层不变量："同一用户最多一条 `is_default=True`"必须由数据库或事务保证：

- **Postgres**（生产）：`CREATE UNIQUE INDEX uq_user_llm_credentials_default ON user_llm_credentials(user_id) WHERE is_default = TRUE;`
- **SQLite**（当前 `tutor.db`）：不支持谓词唯一索引。改为在同一事务中：

  ```python
  with db.begin():  # BEGIN IMMEDIATE on SQLite
      if payload.is_default:
          db.execute(
              update(UserLLMCredential)
              .where(UserLLMCredential.user_id == user.id,
                     UserLLMCredential.id != target.id)
              .values(is_default=False)
          )
      target.is_default = payload.is_default
  ```

  迁移文件要给 SQLite 和 Postgres 各生成对应的索引（用 `op.execute(...)` + 方言判断）。

### 6.5 删除当前 default 后的回退

如果用户删除了当前 `is_default=True` 的 credential：

1. 后端在同一事务中把"该用户最近 `updated_at` 的 enabled credential"提升为 `is_default=True`。
2. 如果没有任何剩余 enabled credential，则 `auto` 解析回到 §9 的全局 fallback / failure 路径。

## 7. 加密设计

新增配置：

```env
LLM_CREDENTIAL_ENCRYPTION_KEY=
LLM_CREDENTIAL_PREVIOUS_KEYS=
LLM_FINGERPRINT_HMAC_KEY=
ALLOW_GLOBAL_LLM_FALLBACK=True
```

### 7.1 加密方案

使用 `cryptography` 的 Fernet + MultiFernet：

- 新增依赖：`cryptography`。
- `LLM_CREDENTIAL_ENCRYPTION_KEY` 是当前**写入**用的 Fernet key。
- `LLM_CREDENTIAL_PREVIOUS_KEYS` 是逗号分隔的历史 key 列表，仅用于**解密**旧密文。MultiFernet 按 `[current, *previous]` 顺序尝试解密。
- 生成命令：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`。
- 未配置加密密钥时，保存用户 API Key 返回 `500 llm_credentials_encryption_unavailable`；读取 provider metadata 仍可工作。
- 生产环境不得从 `JWT_SECRET` 派生加密密钥。

### 7.2 AAD（关联数据）绑定

Fernet 本身不支持 AAD，存在风险：拿到 DB dump 的攻击者可以把用户 A 的 `encrypted_api_key` 复制到用户 B 的行（cross-row substitution），让 B 不知情地用 A 的 quota。

本期采用**前缀绑定**作为轻量缓解：

```python
AAD_PREFIX_FORMAT = "v1|{user_id}|{provider_id}|"

def encrypt(api_key, user_id, provider_id) -> bytes:
    payload = AAD_PREFIX_FORMAT.format(user_id=user_id, provider_id=provider_id) + api_key
    return fernet.encrypt(payload.encode())

def decrypt(token, user_id, provider_id) -> str:
    plaintext = fernet.decrypt(token).decode()
    expected = AAD_PREFIX_FORMAT.format(user_id=user_id, provider_id=provider_id)
    if not plaintext.startswith(expected):
        raise CredentialAADMismatch()
    return plaintext[len(expected):]
```

行为：

- 跨行篡改解密后前缀不匹配 → 抛 `CredentialAADMismatch` → API 返回 `500 llm_credentials_corrupted`，**不**自动当作"Key 不可用"静默 fallback 到全局。
- 重命名 / 改 `provider_id` 也会失败，所以这两个字段事实上不可变；UI 上 provider 切换 = 删除旧的 + 新建。

> **未来方向**（非本期）：切换到 AES-GCM 并把 AAD 显式传给底层 cipher（同时去掉 prefix 字符串的额外开销）；密文 metadata 中再带 `key_id`，配合 KMS 管理。

### 7.3 安全规则

- 明文 API Key 只存在于请求处理内存中，使用完丢弃。
- 不在日志、异常、响应、analytics 中记录明文。
- 数据库只存 `encrypted_api_key` 和 `api_key_fingerprint`。
- `.env.example` 只提供变量名，不提供真实 Key。
- 加密密钥与数据库备份必须分开保存（不同存储位置、不同访问权限）。

## 8. 后端 API 设计

所有 credential endpoint：

- 必须使用 `Depends(get_current_user)`。
- 必须从 `Authorization: Bearer` 头读取 JWT，不接受 cookie 认证（避免 CSRF），见 §13。
- 必须按 `current_user.id` 过滤，不接受请求体或 path 里的 `user_id`。

### 8.1 获取当前用户的安全凭证状态

`GET /api/llm/credentials`

响应示例：

```json
{
  "credentials": [
    {
      "provider_id": "linkapi",
      "configured": true,
      "enabled": true,
      "is_default": true,
      "base_url": "https://api.linkapi.ai/v1",
      "default_model": "claude-sonnet-4-20250514",
      "api_key_fingerprint": "6ab12f90d334aa10",
      "last_validated_at": null,
      "last_validation_error_code": null,
      "last_used_at": "2026-05-14T07:55:11+00:00",
      "updated_at": "2026-05-14T08:00:00+00:00"
    }
  ]
}
```

响应模型由 Pydantic `UserLLMCredentialOut` 描述，**不声明 `api_key` 字段**（见 §19）。

### 8.2 首次保存或整体替换 provider 凭证

`PUT /api/llm/credentials/{provider_id}`

请求：

```json
{
  "api_key": "sk-...",
  "base_url": "https://api.linkapi.ai/v1",
  "default_model": "claude-sonnet-4-20250514",
  "is_default": true,
  "is_enabled": true
}
```

规则：

- `provider_id` 必须在 registry 中存在且 `implemented=True`。
- OpenAI-compatible 且 `requires_api_key=True` 的 provider 必须提交非空 `api_key`。
- `api_key` 至少 8 字符；只做最小校验，不做 provider 特定格式检查（不同 gateway 格式差异大）。
- `base_url` 必须通过 §8.6 白名单。
- `is_default=True` 时，按 §6.4 原子地把当前用户其他 credential 的 `is_default` 置为 False。
- 保存成功后异步触发 `invalidate_provider_client(user_id, provider_id)`（实现上由于用户级 client 不缓存，本调用是 no-op 占位，方便日后切换）。
- 响应只返回安全 metadata，**不回显 `api_key`**。

### 8.3 仅修改 metadata（不重新输入 Key）

`PATCH /api/llm/credentials/{provider_id}`

请求（所有字段都是可选）：

```json
{
  "base_url": "https://api.linkapi.ai/v1",
  "default_model": "claude-sonnet-4-20250514",
  "is_default": true,
  "is_enabled": false
}
```

规则：

- 请求体中**禁止包含 `api_key`**（出现即 422 `api_key_must_use_put`）。这是为了减少用户在表单里贴 Key 的次数，降低明文落 React state、剪贴板、HTTP 调试工具的概率。
- 必须先有现存 credential，否则 404。
- 其他规则同 PUT。

### 8.4 删除 provider 凭证

`DELETE /api/llm/credentials/{provider_id}`

- 只删除当前用户自己的记录。
- 返回 `204 No Content`，无 body。
- 不存在的记录返回 `404`。
- 如果删除的是当前 default，按 §6.5 自动提升新的 default。
- 删除后立即 `invalidate_provider_client(user_id, provider_id)`。

### 8.5 测试 provider 凭证

`POST /api/llm/credentials/{provider_id}/test`

行为：

- **只测当前用户保存的凭证**，绝对不走全局 fallback。
- 未保存就返回 `404`。
- prompt 固定为 `"Reply with OK."`，`max_tokens=8`。
- 成功时更新 `last_validated_at` 并清空 `last_validation_error_code`。
- 失败时映射到 §6.3 枚举码并持久化；当次响应包含安全错误摘要 + `trace_id`，**不包含 provider 原始异常**。
- 限速：**每用户每分钟最多 5 次，每用户每 provider 每 10 秒最多 1 次**（中间件或装饰器实现，见 §13）。

成功响应：

```json
{ "ok": true, "provider_id": "linkapi", "model": "claude-sonnet-4-20250514" }
```

失败响应：

```json
{
  "detail": {
    "code": "llm_provider_validation_failed",
    "error_code": "auth_error",
    "user_message": "Provider rejected the credential",
    "trace_id": "..."
  }
}
```

### 8.6 `base_url` 白名单（SSRF 防护）

保存或更新 credential 时，`base_url` 必须经过以下流程之一通过：

**Path A — 使用 registry 默认值**：用户不填 `base_url`，后端使用 `LLMProviderRegistry[provider_id].default_base_url`。这是推荐路径。

**Path B — 用户自定义 base_url**，必须全部满足：

1. URL scheme 为 `https`（开发模式 `ENV=development` 下允许 `http://localhost`、`http://127.0.0.1`）。
2. host 解析后的所有 A/AAAA 记录都**不**落在：
   - `10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`（RFC1918）
   - `127.0.0.0/8`、`::1`（loopback，除非开发模式）
   - `169.254.0.0/16`、`fe80::/10`（link-local，覆盖云元数据 `169.254.169.254`）
   - `0.0.0.0/8`
3. host 不在硬编码黑名单（如 `metadata.google.internal`、`metadata.aws.internal` 等元数据 hostname）。
4. URL 不含 `@`、不含 fragment、不含查询参数。

**Path C — 内部白名单短路**：如果 host ∈ `{api.openai.com, api.deepseek.com, dashscope.aliyuncs.com, api.linkapi.ai, ...}`，跳过 IP 检查直接通过。该列表与 registry 默认 base_url 同源维护。

校验失败统一返回 `400 invalid_provider_base_url`，user_message 用通用文案，不暴露解析后的 IP。

> **DNS rebinding 限制**：上述校验在保存时执行；如果攻击者控制 DNS 把 host 在保存后切到内网 IP，下次 chat 时仍会被打到。本期接受这个残余风险（前提：用户自定义 base_url 的入口本身已经登录态保护）。彻底缓解需要在每次 chat 出口加同样的 IP 校验，纳入 v2 backlog。

### 8.7 Provider metadata 调整

现有 `GET /api/llm/providers` 继续存在，但改为当前用户视角：

```json
{
  "providers": [
    {
      "id": "linkapi",
      "name": "LinkAPI",
      "adapter": "openai-compatible",
      "implemented": true,
      "enabled": true,
      "source": "user",
      "configured": true,
      "default_model": "claude-sonnet-4-20250514",
      "models": ["claude-sonnet-4-20250514", "gpt-4o-mini", "deepseek-chat"],
      "reason": null
    }
  ]
}
```

`source` 取值：

- `user`：当前用户已配置。
- `global`：后端 `.env` 已配置，并且 `ALLOW_GLOBAL_LLM_FALLBACK=True`。
- `local`：如 `ollama`，不需要 API Key。
- `none`：不可用。

## 9. Provider 解析策略

当前 `provider='auto'` 的解析逻辑需要从"全局 settings"升级为"当前用户有效配置"。

完整顺序：

1. 如果请求指定具体 provider：
   - 先尝试当前用户该 provider 的 enabled credential。
   - 否则，如 `ALLOW_GLOBAL_LLM_FALLBACK=True` 且全局有该 provider 的 Key，则用全局。
   - 否则失败 `llm_provider_not_configured`。
2. 如果请求是 `provider='auto'`：
   - 用户的 enabled `is_default=True` credential。
   - 否则该用户**最近 `updated_at`** 的 enabled credential。
   - 否则，如允许 fallback，使用 `settings.DEFAULT_LLM_PROVIDER` 或第一个全局可用 provider。
   - 否则 `ollama`（如 registry 中 implemented 且 base_url 存在）。
   - 否则失败 `llm_provider_not_configured`。

返回的 `ResolvedProvider` 数据结构：

```python
@dataclass(frozen=True)
class ResolvedProvider:
    provider_id: str
    api_key: str                # plaintext, only lives in memory
    base_url: str
    model: str
    source: Literal["user", "global", "local"]
    fingerprint: str | None     # None for `local` providers like ollama
```

## 10. `LLMService` 改造

### 10.1 模块拆分

按 §5 的边界拆开，避免现状中 `_provider_configs()` 把 registry / settings / credential 三层信息混在一个 dict 里：

- `llm_provider_registry.py` 只输出 dataclass `LLMProviderDescriptor`，字段：`id, name, adapter, default_base_url, default_model, models, requires_api_key, implemented`。
- `llm_credential_service.py` 提供 CRUD、加解密、safe metadata、`get_credential(user, provider_id)`、`record_used(credential_id)`。
- `llm_credential_resolver.py` 单一公开方法 `resolve(user, requested_provider) -> ResolvedProvider | None`。
- `llm_service.py` 完全不再 import `settings.OPENAI_API_KEY` 之类的全局 Key 字段；只接受 `ResolvedProvider`。

### 10.2 Chat client 缓存

当前 `_clients: Dict[str, OpenAI]` 只按 provider 缓存，在用户级 Key 下会**跨用户串 Key**。必须改。

第一版采用**简化方案**：

- 全局 provider client 继续按 `(provider_id, fingerprint)` 缓存（仅 1 个 fingerprint per provider）。
- 用户 provider client **不缓存**，每次请求 `OpenAI(api_key=..., base_url=...)` 重新构造。`OpenAI` 客户端初始化只是 `httpx.Client()`，开销很小，对当前项目规模可忽略。

理由：

- 任何缓存策略只要带 `user_id`、`fingerprint`、`base_url`，调试都比"不缓存"难。
- 更新或删除 credential 不必显式 invalidate。
- §17 验收 #5 自动满足。

如果后续观测到性能问题，再切到 `(source, user_id_or_global, provider_id, fingerprint, base_url, default_model)` 的 LRU + TTL，并由 `LLMCredentialService` 在写入路径主动 `invalidate`。

### 10.3 统一旧 LLM endpoint

`generate_hint`、`explain_solution`、`diagnose_error`、`session_summary` 当前依赖 `self.client`（OpenAI 全局 Key）。本期一次性改造：

新增内部方法：

```python
def complete_chat(
    resolved: ResolvedProvider,
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    agent_type: str,
    user_id: str | None,
    session_id: int | None,
    analytics: AnalyticsService | None,
) -> dict[str, Any]:
    ...
```

- `chat()`、`generate_hint()`、`explain_solution()`、`diagnose_error()`、`session_summary()` 都改为先调用 `LLMCredentialResolver.resolve(...)` 拿到 `ResolvedProvider`，再调 `complete_chat(...)`。
- `complete_chat` 内部统一构造 `OpenAI(api_key=resolved.api_key, base_url=resolved.base_url)`，并在 analytics 日志里附带 `provider`、`fingerprint`、`source` 三项。
- 调用成功后 `LLMCredentialService.record_used(credential_id)` 更新 `last_used_at`（如果 source == "user"）。

## 11. 前端设计

### 11.1 新增页面和入口

新增 protected route：

- `/settings/model`

入口：

- `TopNavbar` 增加设置/钥匙图标按钮，**仅登录用户可见**，未登录直接跳 `/login`。
- Tutor 页面在没有可用 provider 时展示错误 banner 和"配置模型"按钮，错误 banner 文案对应 §12 错误码。
- Tutor 气泡角落显示 `credential_source` 徽章（"Your LinkAPI key" / "Demo key" / "Ollama (local)"），让用户能直观核实本次回复用的是不是自己的 Key。

### 11.2 设置页能力

页面提供：

- Provider 列表：OpenAI、DeepSeek、Qwen、LinkAPI、Ollama。
- 每个 provider 显示状态：未配置、已配置、使用后端默认（global）、仅本地（local）。
- 表单字段：API Key、Base URL（默认占位用 registry 默认）、Default Model（dropdown + 其他）、设为默认、启用/禁用。
- 操作：保存（PUT）、仅改设置（PATCH）、测试、删除。

交互规则：

- API Key 输入框成功保存后**立即清空**且 React state 重置，不显示旧 Key。
- 已配置 provider 默认不显示 fingerprint，仅显示 `updated_at` 和 `last_used_at`；高级展开里才显示 fingerprint，避免用户误以为是可复制的凭证。
- "仅改设置" 操作走 PATCH，不需要 API Key 输入框；toggle `is_default` / `is_enabled` 都走 PATCH。
- 测试失败只显示安全错误文案 + `trace_id`。
- `ollama` 不显示 API Key 必填；允许用户覆盖 base URL 和 model。

### 11.3 前端 API 模块

新增 `frontend/src/utils/llmCredentialsApi.ts`：

- `fetchLlmCredentials()`
- `saveLlmCredential(providerId, payload)` → PUT
- `patchLlmCredential(providerId, payload)` → PATCH
- `deleteLlmCredential(providerId)`
- `testLlmCredential(providerId)`

现有 `fetchChatProviders()` 保持，但响应类型增加：

- `source`
- `configured`
- `credential_updated_at?`

Chat 调用返回类型增加：

- `credential_source: 'user' | 'global' | 'local'`
- `credential_fingerprint?: string`

## 12. 错误处理和 UX 状态

后端错误码：

| code | HTTP | 场景 |
| --- | --- | --- |
| `llm_provider_not_configured` | 422 | 当前用户没有可用 provider，且无 fallback |
| `llm_credentials_encryption_unavailable` | 500 | 后端未配置加密密钥，无法保存 Key |
| `llm_credentials_corrupted` | 500 | 解密成功但 AAD 前缀不匹配（疑似 DB 篡改） |
| `llm_provider_validation_failed` | 502 | 测试 provider 失败 |
| `unsupported_provider` | 400 | provider id 不存在或 adapter 未实现 |
| `invalid_provider_base_url` | 400 | base URL 不符合白名单 |
| `api_key_must_use_put` | 422 | PATCH 请求体出现 `api_key` 字段 |
| `rate_limited` | 429 | 触发 §13 测试端点限速 |

前端映射：

- `llm_provider_not_configured`：banner + 跳转 `/settings/model`。
- `llm_credentials_encryption_unavailable`：提示"服务器暂未开启个人 API Key 保存功能"，部署侧问题。
- `llm_credentials_corrupted`：提示"该凭证已失效，请重新输入"，并引导删除重建。
- `llm_provider_validation_failed`：提示"模型服务暂时不可用"，保留 trace id。
- `rate_limited`：提示"操作过于频繁，请稍候"。

## 13. 安全要求

1. API Key 不得出现在任何 response body、`repr(error)`、日志、测试快照、analytics payload。
2. Credential endpoint 必须使用 `current_user`，不得接受客户端传 `user_id`。
3. Delete/update/test 都必须按当前用户过滤。
4. Credential endpoint 必须使用 `Authorization: Bearer` 头读取 JWT，**禁止接受任何 cookie 认证路径**。这是防 CSRF 的关键。若未来引入 cookie-based access token，必须同步上 CSRF token 中间件。
5. `base_url` 写入路径必须过 §8.6 白名单。
6. `/api/llm/credentials/{provider_id}/test` 必须限速（per-user + per-provider）。最朴素做法：内存 `dict[(user_id, provider_id), deque[float]]`，本期可不上 Redis。
7. 生产部署必须设置 `LLM_CREDENTIAL_ENCRYPTION_KEY`，并将其与数据库备份分开保存。
8. 如果加密密钥丢失（且无 previous keys 可解），旧 API Key 无法恢复；恢复方式是用户重新填写。
9. `LLM_CREDENTIAL_PREVIOUS_KEYS` 必须支持多 key 解密，方便密钥轮换；轮换步骤记录在 `backend/README.md`。
10. `.env.example` 必须明确真实 API Key 不要提交到 git。

## 14. 数据迁移

新增 Alembic revision：

```text
20260514_04_user_llm_credentials.py
```

迁移内容：

- 创建 `user_llm_credentials` 表（含 §6.1 所有列）。
- 添加 `UNIQUE(user_id, provider_id)`。
- 添加 `idx_user_llm_credentials_user` on `user_id`。
- 添加 `idx_user_llm_credentials_fingerprint` on `api_key_fingerprint`。
- `is_default` 唯一约束：
  - Postgres：`op.execute("CREATE UNIQUE INDEX uq_user_llm_credentials_default ON user_llm_credentials(user_id) WHERE is_default = TRUE")`
  - SQLite：跳过谓词索引，靠 §6.4 事务保证。
- 用方言判断：

  ```python
  bind = op.get_bind()
  if bind.dialect.name == "postgresql":
      op.execute("CREATE UNIQUE INDEX ...")
  ```

不自动为 `test-01` 写入任何 API Key。`test-01` 第一次使用 LLM 功能时，按 §9 解析：有 fallback 走 fallback，否则得到 `llm_provider_not_configured` 提示去配置。

## 15. 测试计划

### 15.1 后端单元测试

加密 / 凭证服务：

- 保存后密文不包含明文（grep 检查）。
- 解密能还原；previous keys 加密的密文也能用 current key 解密。
- AAD 前缀篡改时抛 `CredentialAADMismatch`。
- 缺少 `LLM_CREDENTIAL_ENCRYPTION_KEY` 时返回明确错误。
- HMAC fingerprint 稳定性：同一 Key 多次计算结果一致；不同 server_secret 结果不同。

Credential API：

- 未登录 401。
- 用户 A 不能读写 / test 用户 B 的 credential。
- PATCH 请求体包含 `api_key` → 422 `api_key_must_use_put`。
- PUT 缺 `api_key` 时 provider 需要 Key → 422。
- `base_url` 白名单：
  - `http://attacker.com/v1` → 400
  - `https://169.254.169.254/v1` → 400（IP 解析检查）
  - `https://api.linkapi.ai/v1` → 200
  - 开发模式 `http://localhost:11434/v1` → 200，生产模式 → 400
- `/test` 限速：第 6 次返回 429。
- 并发两个 PUT 都设 `is_default=True` → 最终库里只有一条 `is_default=True`。
- 删除当前 default 后，剩余 enabled credential 中最新一条被升级为 default。

Provider metadata / resolver：

- 用户 credential 优先于全局配置；无 Key 时 source 为 `none`。
- `auto` 选择用户默认 provider。
- **fallback 关闭回归测试**：把 `settings.OPENAI_API_KEY` 设成 sentinel `"GLOBAL-MUST-NOT-LEAK"`，关掉 `ALLOW_GLOBAL_LLM_FALLBACK`，用户无 credential 触发 `/chat`；断言响应是 `llm_provider_not_configured` 且 `OpenAI(...)` 构造 mock 从未收到该 sentinel。

LLM 调用：

- OpenAI client 收到的是用户 Key，不是全局 Key。
- 更新 Key 后立即调用 chat，构造 `OpenAI(...)` 收到的是新 Key 而非旧 Key。
- Provider 异常脱敏，不泄露 `sk-secret`。
- chat 响应包含 `credential_source` 和 `credential_fingerprint`。

### 15.2 后端集成测试

- 注册新用户 → 登录 → PUT LinkAPI Key → `/api/llm/providers` 显示 `source=user`。
- 同一用户 PATCH `is_default=true` 不需要重输 Key，PATCH 请求体禁含 `api_key`。
- 删除 Key → `/api/llm/chat` 在无 fallback 时返回 `llm_provider_not_configured`。
- 有全局 fallback 时，新用户不配置 Key 也能使用全局 provider，且 chat 响应 `credential_source=global`。
- `/test` 限速：连续触发 6 次返回 429。

### 15.3 前端测试

- 设置页能加载 provider 和 credential 状态。
- 保存成功后 API Key 输入框清空，相关 React state 也清空（用 `screen.queryByDisplayValue` 断言）。
- PATCH 只改 `is_default` 不需要打开 API Key 输入框。
- 测试失败展示安全错误 + trace_id，不展示原始 provider 异常。
- Tutor 页面在无可用 provider 时显示配置入口。
- Tutor 气泡显示正确的 `credential_source` 徽章。
- `apiClient` 不把 API Key 放入 localStorage / sessionStorage。
- 用户切换登录态后，settings 页 credential 列表必须重新拉取，不复用上一个用户的缓存。

## 16. 实施分解建议

1. 后端模型与迁移：`UserLLMCredential`、Alembic（含方言分支）、model export。
2. 加密 / fingerprint 工具：`encrypt/decrypt with AAD prefix`、`hmac_fingerprint`、单元测试。
3. Provider registry 抽离：`llm_provider_registry.py`，与 settings 解耦。
4. Credential service & resolver：CRUD、safe metadata、`resolve()`、base_url 白名单。
5. Credential API：PUT / PATCH / DELETE / test / list、错误码、限速。
6. Provider metadata 改造：加入当前用户视角和 fallback source。
7. `LLMService` 重写：统一 `complete_chat`、删 `self.client`、hint / explain / diagnose / summary 全走 resolver。
8. Chat 响应增加 `credential_source` / `credential_fingerprint`。
9. 前端 API 模块和设置页：`/settings/model`，PUT + PATCH 区分。
10. Tutor 页面 banner + credential_source 徽章。
11. 测试与文档：补 backend/frontend 测试，更新 README、`.env.example`、密钥轮换 runbook。

## 17. 验收标准

1. 新注册用户登录后，能在 `/settings/model` 保存自己的 provider API Key。
2. 保存成功后，前端无法再获取明文 API Key（API 响应、网络面板、localStorage 都看不到）。
3. 该用户发起 Tutor 对话时，后端实际使用该用户保存的 Key，且 chat 响应 `credential_source=user`、`credential_fingerprint` 与 settings 页一致。
4. 另一个用户不能看到、测试、删除这个 Key（接口层 + UI 切换登录验证）。
5. 用户删除 Key 后，**新发起**的 LLM 请求不再使用旧 Key；in-flight 请求允许跑完。
6. 没有用户 Key 且没有全局 fallback 时，Tutor 给出可理解的配置提示（错误码 `llm_provider_not_configured`）。
7. 有全局 fallback 时，未配置个人 Key 的用户仍能使用后端默认 provider，且 chat 响应 `credential_source=global`。
8. PATCH 仅改 metadata 时无需重输 Key；PATCH 请求体含 `api_key` 返回 422。
9. 设置 `base_url=https://169.254.169.254/...` 或私网 IP 时被拒绝。
10. 后端 `LLM_CREDENTIAL_ENCRYPTION_KEY` 轮换：旧密钥放入 `LLM_CREDENTIAL_PREVIOUS_KEYS` 后，老用户 Key 仍可解密；管理员可手动触发"重新加密"脚本（v2 任务，本期至少要保证解密不挂）。
11. 后端和前端测试通过。
12. 日志和错误响应中不出现明文 API Key。

## 18. 评审确认点

请重点确认以下设计选择：

1. 是否接受"后端加密保存用户 API Key"为第一版方案。
2. 是否保留 `ALLOW_GLOBAL_LLM_FALLBACK=True`，让无个人 Key 的用户仍可使用后端默认 provider。
3. 第一版是否只支持当前已实现的 OpenAI-compatible provider：OpenAI、DeepSeek、Qwen、LinkAPI、Ollama。
4. 设置入口是否采用 protected route `/settings/model`，从顶部导航进入。
5. 是否接受第一版**用户级 provider client 不缓存**的简化实现（§10.2 的取舍）。
6. 是否接受用 Fernet + 前缀 AAD 作为本期加密方案，AES-GCM 推迟到 v2。
7. 是否接受 `base_url` 自定义需要走 §8.6 的多重白名单（包括运行时 DNS 解析检查）。
8. 是否在 Tutor 气泡上显示 `credential_source` 徽章——这是核心 UX 决策，决定用户能否核实"是不是我的 Key"。

确认后再进入实现计划和代码修改。

## 19. 实现强约束（合并自原 §13 / §11 / §10 散落条款）

下列约束是实现时**不可妥协**的，超出常规 code review 评分项：

### 19.1 Pydantic 层级

- `UserLLMCredentialOut` / `UserLLMCredentialListOut` 等响应模型**不声明 `api_key` 字段**，从类型上保证序列化时不可能带出明文。
- `UserLLMCredentialPutIn` 包含 `api_key`；`UserLLMCredentialPatchIn` 不包含 `api_key` 字段，并通过 `model_config = ConfigDict(extra='forbid')` 拒绝任何 `api_key` 键，触发 422。
- DB 模型 `UserLLMCredential` 不实现 `__repr__` 输出任何 key 字段；如必须重写 `__repr__`，只展示 `id`、`user_id`、`provider_id`、`fingerprint`。

### 19.2 解密接口

- 全局只暴露一个解密函数 `decrypt_for_provider_call(credential, user_id, provider_id) -> str`，返回值只允许作为 `OpenAI(api_key=...)` 构造参数使用。
- 严禁把解密结果存入任何 dataclass / dict / log / analytics payload；`ResolvedProvider.api_key` 是唯一例外，且 `ResolvedProvider` 不可序列化（`frozen=True` 且 `__repr__` 屏蔽 `api_key`）。

### 19.3 日志与 Analytics

- `safe_llm_error()` 必须覆盖：`sk-...`、`Bearer ...`、`api_key=...`、`Authorization:`、base64-looking 长串。新增 unit test 用 sentinel 字符串验证。
- Analytics `log_llm_call()` 入参不包含 api_key。`credential_fingerprint` 可入库，因为它无法反推。

### 19.4 缓存与并发

- 第一版用户级 client 不缓存；全局 client 缓存按 `(provider_id, fingerprint)`。
- `is_default` 写入路径必须在事务内执行（§6.4），SQLite 用 `BEGIN IMMEDIATE`。

### 19.5 限速

- 测试端点限速实现可以是进程内 `deque`，但必须有 unit test 覆盖速率窗口边界。
- 限速 key = `(user_id, provider_id)`，不要混入 IP（IP 在反代后不可靠）。

### 19.6 CSRF

- Credential API 必须只接受 `Authorization: Bearer`。如果上一份 auth SDD 的实现把 access token 同时放进 cookie，本期实现必须**显式拒绝**通过 cookie 读到的 user 解析 credential 端点。

---

附录 A — 关键文件清单

| 路径 | 状态 | 说明 |
| --- | --- | --- |
| `backend/app/models/llm_credentials.py` | 新增 | `UserLLMCredential` |
| `backend/app/models/__init__.py` | 改 | 导出新模型 |
| `backend/alembic/versions/20260514_04_user_llm_credentials.py` | 新增 | 迁移，含方言分支 |
| `backend/app/services/llm_provider_registry.py` | 新增 | 纯数据 registry |
| `backend/app/services/llm_credential_service.py` | 新增 | CRUD + 加解密 + fingerprint |
| `backend/app/services/llm_credential_resolver.py` | 新增 | 解析 ResolvedProvider |
| `backend/app/services/llm_service.py` | 重构 | 删 `self.client`，统一 `complete_chat` |
| `backend/app/api/llm.py` | 改 | 新增 credential CRUD / test，chat 响应增字段，限速 |
| `backend/app/config.py` | 改 | 新增加密 / fingerprint / fallback 开关变量 |
| `backend/.env.example` | 改 | 新增变量名 |
| `frontend/src/utils/llmCredentialsApi.ts` | 新增 | 前端 API 模块 |
| `frontend/src/pages/SettingsModelPage.tsx` | 新增 | 设置页 |
| `frontend/src/features/tutor/...` | 改 | banner、credential_source 徽章 |
| `frontend/src/components/TopNavbar.tsx` | 改 | 新增设置入口 |
| `docs/sdd-user-llm-api-keys.md` | 本文档 | v2.0 |
| `backend/README.md` | 改 | 密钥生成 + 轮换 runbook |
