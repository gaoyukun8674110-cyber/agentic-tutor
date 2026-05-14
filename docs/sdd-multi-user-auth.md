# SDD — AI Tutor 多用户登录与数据隔离

| 字段 | 值 |
| --- | --- |
| 文档编号 | SDD-AITUTOR-AUTH-001 |
| 版本 | v1.0 (draft) |
| 状态 | 待评审 |
| 起草日期 | 2026-05-13 |
| 适用代码库 | `H:\ai-tutor` (monorepo) |
| 影响范围 | `backend/`、`frontend/`、`backend/alembic/` |
| 关联文档 | `IMPLEMENTATION_PLAN.md`, `backend/IMPLEMENTATION_PLAN.md`, `frontend/IMPLEMENTATION_PLAN.md`, `AGENTS.md` |
| 执行者 | Codex(按本 SDD 实施) |

---

## 1. 背景与动机

当前 AI Tutor 仅以共享的 `X-API-Key` 头作为身份令牌(`backend/app/api/deps.py:get_current_user`),所有访问者被解析为同一个伪用户 `local`(`Settings.DEFAULT_AUTH_USER_ID`),前端把 `'local'` 作为常量硬编码进 `DashboardPage` 与各业务调用中。这意味着:

- 任何持有 `local-dev-key` 的客户端都拥有 `local` 用户的全部权限。
- 多人无法在同一后端实例上各自维护学习记录、错题记录、对话历史。
- 项目作为外企面试作品集时缺少基础的身份/权限层,审稿人会立即扣分。

业务诉求是:**学生注册并登录后,只能看到属于自己的学习记录、错题记录(`StudentAnswer`)、对话历史(`TutorConversation`),其它用户的数据对其完全不可见。**

## 2. 目标与非目标

### 2.1 In scope (本 SDD 必须交付)

1. 引入真正的 `users` 表,提供 `注册 / 登录 / 刷新 / 登出 / 取当前用户` 五个标准认证端点。
2. 用 JWT(access token,15 分钟)+ refresh token(httpOnly cookie,30 天,服务端可吊销并轮换)替换现有的共享 API Key 机制。
3. 把后端 `get_current_user` 依赖、所有业务端点、所有服务层调用统一改造为以登录用户为隔离边界,任何一个用户都不能读到或修改另一个用户的数据(逐行端点审计)。
4. 前端新增 `/login`、`/register` 页面与路由守卫;`apiClient` 改造为带 cookie、自动 401→refresh 重放;移除前端硬编码的 `'local'` user id 与 `VITE_API_KEY`。
5. 提供 Alembic 迁移把 `users` 表落库,把现有业务表上 `user_id` 列的可空性与索引收紧到生产可用,并对 `tutor.db` 中现存的 `local` 数据给出明确处置方案。
6. 提供后端单测 + 前端组件测试,覆盖关键认证流程与跨用户隔离回归。

### 2.2 Out of scope (本期不做,但记录为下一期 backlog)

- 邮箱验证、找回密码、双因素认证(基于第 1 节问答,选择开放自助注册,不要求邮箱验证)。
- 第三方 OAuth(Google / GitHub / 微信)登录。
- 角色与权限(RBAC):本期仅有一种角色 `student`,管理员后台不在范围。
- 单点登出(SLO)、跨设备 session 列表 UI。
- **错题本视图**(基于第 1 节问答,本期仅做数据隔离,不新增前端错题本页面)。
- 速率限制、审计日志的生产级实现(下文 §10.5 给出占位建议)。

## 3. 术语表

| 术语 | 定义 |
| --- | --- |
| **User / 用户** | `users` 表中的一行,通过 `username` + `password` 登录;`username` 同时是业务侧 `user_id` 字符串的唯一来源。 |
| **Access Token** | 短期 JWT,放在内存 + `Authorization: Bearer ...` 请求头,15 分钟过期。 |
| **Refresh Token** | 256-bit 随机串,服务端只存 SHA-256 哈希,通过 httpOnly+SameSite cookie 下发,30 天过期,使用时一次性轮换。 |
| **隔离边界** | 后端所有业务查询必须在 SQL 层用 `user_id = current_user.username` 过滤;路径参数中的 `user_id` 必须与登录用户一致,否则 403。 |
| **legacy 数据** | 当前 `backend/tutor.db` 里 `user_id IS NULL` 的所有行(经 2026-05-13 盘点:`tutor_conversations` 3 行、`tutor_conversation_messages` 78 行通过 `conversation_id` 间接挂上、`study_materials` 1 行),迁移期间统一归属 `test-01` 用户,不丢数据。 |

## 4. 现状分析

### 4.1 现有认证模型

- `backend/app/api/deps.py:10-22` — `get_current_user` 仅做白名单匹配,从 `settings.API_KEYS` 里查 `X-API-Key`,可选地用 `userid:secret` 格式切出 user_id,否则 fallback 到 `settings.DEFAULT_AUTH_USER_ID = "local"`。
- `backend/app/config.py:58-59` — `API_KEYS = ["local-dev-key"]`、`DEFAULT_AUTH_USER_ID = "local"`。
- `backend/app/api/deps.py:25-28` — `require_matching_user` 在路径参数里再校验一次 user 一致性,目前只在 `/api/student/{user_id}/...` 系列使用。
- `frontend/src/utils/apiClient.ts:1-2,124` — `VITE_API_KEY` 硬编码默认 `'local-dev-key'`,每次请求都加 `X-API-Key` 头。
- `frontend/src/pages/DashboardPage.tsx:21` — `const DASHBOARD_USER_ID = 'local'` 直接当成调用参数。

### 4.2 现有数据模型对 user_id 的覆盖情况

| 表 | 列 | 当前状态 | 改造需求 |
| --- | --- | --- | --- |
| `students` | `user_id String(100) UNIQUE NOT NULL` | ✅ 已有 | 改为引用 `users.username`,即 `ForeignKey("users.username", ondelete="CASCADE")`;`get_or_create_student` 在认证后自动建档。 |
| `student_masteries` | `student_id FK` | ✅ 通过 `students` 间接隔离 | 仅需补 `student_id` 索引(已有);服务层确保 `student_id` 始终来自当前用户的 `students.id`。 |
| `student_answers` | `student_id FK` | ✅ 同上 | 同上;**这就是“错题记录”的物理载体**,隔离即可。 |
| `training_sessions` | `student_id FK` | ✅ | 同上。 |
| `session_questions` | 经 `session_id` 间接 | ✅ | 同上。 |
| `tutor_conversations` | `user_id String NULLABLE` | ⚠️ 可空,当前 3 行全部为 NULL | 迁移为 `NOT NULL`,补 `FK users.username`,先把 NULL 行回填到 `test-01`。 |
| `tutor_conversation_messages` | 经 `conversation_id` 间接 | ✅ | — |
| `tutor_conversation_digests` | 经 `conversation_id` 间接 | ✅ | — |
| `dashboard_tasks` | `user_id String NOT NULL` | ✅ | 补 `FK users.username`。 |
| `pomodoro_logs` | `user_id String NOT NULL` | ✅ | 补 `FK users.username`。 |
| `study_materials` | `user_id String NULLABLE` | ⚠️ 可空,当前 1 行为 NULL | 迁移为 `NOT NULL`,补 `FK`,先把 NULL 行回填到 `test-01`。 |
| `study_material_chunks` | 经 `material_id` 间接 | ✅ | — |
| `behavior_logs` / `question_stats` / `skill_stats` | `user_id` 不同情况 | 待审计(§7.4) | 服务层调用点逐一确认。 |

### 4.3 现有痛点小结

1. **认证非身份化**:API Key = 用户身份,丢一把钥匙整个仓库被读完。
2. **前端 user_id 是常量**:即便后端做了隔离,前端也无法表达“另一个用户登录”。
3. **CORS 在 DEBUG 下 `allow_origins=["*"]` 且 `allow_credentials=False`**(`backend/app/main.py:22-36`)— 一旦改用 cookie,必须改成具体白名单 + `allow_credentials=True`。

## 5. 设计目标与原则

1. **最小破坏面**:`Student.user_id` 字符串仍是隔离主键,新增的 `users.username` 与之同义,业务服务层尽量不动。
2. **HTTP 边界纯净**:认证逻辑集中在 `app/auth/` + `app/api/auth.py` + `app/api/deps.py`,业务路由仅消费 `current_user`。
3. **可测性优先**:认证模块的所有纯函数(哈希、JWT 编解、cookie 拼装)与 IO 分离,单测无须启动 FastAPI。
4. **作品集质量**:遵循 OWASP ASVS L1,使用 argon2id、httpOnly cookie、token 轮换、CSRF 防御策略明示。
5. **演进路径**:本期不做的特性(邮箱验证、OAuth、RBAC)在模型与端点命名上预留空间,不需要破坏式变更。

## 6. 系统架构

### 6.1 总体视图

```
┌─────────────────────┐       (1) POST /api/auth/register|login
│  Vite + React (SPA) │ ───────────────────────────────────► ┌─────────────────────┐
│  AuthProvider       │ ◄──── Set-Cookie: refresh_token ──── │  FastAPI            │
│  ProtectedRoute     │       JSON: { access_token, user }   │  app/api/auth.py    │
│  apiClient (memo    │                                       │                     │
│   access_token,     │       (2) Bearer access_token         │  app/auth/          │
│   credentials:incl) │ ────────────────────────────────────► │   tokens / passwords│
│                     │       (3) 401 → POST /auth/refresh    │                     │
│                     │       (cookie 自动随行)               │  app/api/deps.py    │
│                     │ ◄──── 新 access_token + 轮换 cookie ── │  get_current_user   │
└─────────────────────┘                                       │                     │
                                                              │  业务路由           │
                                                              │  按 user_id 过滤    │
                                                              └─────────┬───────────┘
                                                                        │
                                                          SQLite ──────►│
                                                          (tutor.db)    │
                                                                        ▼
                                                              users / refresh_tokens
                                                              students / answers / ...
```

### 6.2 关键时序

**注册 → 登录 → 业务调用 → access 过期 → refresh → 登出**

```
SPA            FastAPI                         DB
 │  POST /auth/register {u,p}     →
 │                                argon2_hash(p), INSERT users
 │  ← 201 {user}
 │
 │  POST /auth/login {u,p}        →
 │                                verify_hash, INSERT refresh_tokens(hash, exp)
 │  ← 200 {access_token, user}
 │     Set-Cookie: refresh_token=<raw>; HttpOnly; SameSite=Lax;
 │                Path=/api/auth; Max-Age=2592000; Secure(prod)
 │
 │  GET /api/dashboard/summary    →   Bearer <access>
 │                                decode JWT, sub=username, attach User
 │  ← 200 {...}
 │
 │  (15 min 后)
 │  GET /api/... → 401 token_expired
 │  POST /auth/refresh (cookie 自动)  →
 │                                查 refresh_tokens 哈希,未吊销且未过期
 │                                UPDATE 旧 token 标记 revoked_at
 │                                INSERT 新 token
 │  ← 200 {access_token}, Set-Cookie: refresh_token=<new>...
 │  (前端透明重放原请求)
 │
 │  POST /auth/logout            →
 │                                UPDATE refresh_tokens SET revoked_at=now
 │  ← 204, Set-Cookie: refresh_token=; Max-Age=0
```

### 6.3 Token 生命周期摘要

| 项目 | Access Token | Refresh Token |
| --- | --- | --- |
| 类型 | JWT(HS256) | 32 字节随机串(`secrets.token_urlsafe(32)`) |
| 载体 | 内存(JS module 变量 + `AuthContext`) | httpOnly cookie(浏览器自动管理) |
| 有效期 | 15 分钟 | 30 天(每次使用后轮换并续期) |
| 服务端可吊销 | 否(无状态) | 是(`refresh_tokens.revoked_at`) |
| 持久化 | 否 | 仅哈希(`sha256(raw)`),不存原文 |
| 暴露面 | 仅 Authorization header | 仅 `/api/auth/*` 路径(Cookie `Path` 限定) |

## 7. 后端设计

### 7.1 新增 / 修改的模块结构

```
backend/app/
├── auth/                          (NEW)
│   ├── __init__.py
│   ├── passwords.py               # hash_password / verify_password (argon2id)
│   ├── tokens.py                  # encode_access / decode_access / generate_refresh / hash_refresh
│   ├── cookies.py                 # build_refresh_cookie / clear_refresh_cookie
│   └── exceptions.py              # InvalidCredentials / TokenExpired / TokenRevoked 子类
├── models/
│   └── user.py                    # NEW: User, RefreshToken
├── api/
│   ├── auth.py                    # NEW: 注册/登录/刷新/登出/me
│   └── deps.py                    # MODIFIED: 改为 JWT-based,见 §7.3
├── config.py                      # MODIFIED: 增加 JWT_SECRET 等设置,删除 API_KEYS / DEFAULT_AUTH_USER_ID
├── main.py                        # MODIFIED: 注册 auth router; CORS allow_credentials=True 且不能 ["*"]
└── alembic/versions/
    ├── 20260514_01_users_table.py             # NEW
    ├── 20260514_02_tighten_user_id_nullable.py# NEW
    └── 20260514_03_seed_legacy_local_user.py  # NEW (可选)
```

### 7.2 数据模型(新增表)

**`users`**

| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 自增主键。 |
| `username` | String(64) | UNIQUE NOT NULL, index | 业务侧 user_id 即此列;只允许 `^[a-zA-Z0-9_-]{3,64}$`。 |
| `email` | String(255) | NULLABLE, UNIQUE (NULLs 允许重复) | 留作下一期邮箱验证,本期可选填。 |
| `password_hash` | String(255) | NOT NULL | argon2id 编码字符串。 |
| `is_active` | Boolean | NOT NULL, default True | 软封禁开关。 |
| `created_at` | String(50) | NOT NULL | ISO8601 字符串,与现有表风格一致。 |
| `updated_at` | String(50) | NOT NULL | 同上。 |
| `last_login_at` | String(50) | NULLABLE | 登录成功时刷新。 |

**`refresh_tokens`**

| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | |
| `user_id` | Integer | FK `users.id` ON DELETE CASCADE, index | |
| `token_hash` | String(64) | NOT NULL, UNIQUE | `hashlib.sha256(raw).hexdigest()`。 |
| `issued_at` | String(50) | NOT NULL | |
| `expires_at` | String(50) | NOT NULL, index | |
| `revoked_at` | String(50) | NULLABLE | 非空即视为已吊销。 |
| `user_agent` | String(255) | NULLABLE | 弱审计用,源自 `Request.headers`。 |
| `client_ip` | String(64) | NULLABLE | 同上。 |
| `created_at` | String(50) | NOT NULL | |

> 说明:`token_hash` 唯一,即便 `token_urlsafe(32)` 碰撞概率 ≈ 2⁻²⁵⁶,也避免重复入库。

### 7.3 `deps.py` 改造

```python
# 改造后语义(伪代码,实际由 codex 落地)
async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = _extract_bearer(request)        # Authorization: Bearer <jwt>
    if not token:
        raise api_error(401, "unauthorized", "Missing access token")
    try:
        claims = decode_access_token(token) # 校验 HS256 + exp + iat + sub
    except TokenExpired:
        raise api_error(401, "token_expired", "Access token expired")
    except InvalidToken:
        raise api_error(401, "invalid_token", "Invalid access token")

    user = db.query(User).filter(User.username == claims["sub"]).first()
    if not user or not user.is_active:
        raise api_error(403, "forbidden", "User not allowed")
    return user

def require_matching_user(user_id: str, current_user: User) -> None:
    if user_id != current_user.username:
        raise api_error(403, "forbidden", "User is not authorized for this resource")
```

> 返回类型从 `str` 改为 `User`。**所有调用 `Depends(get_current_user)` 的端点**(目前 25+ 处,见 §7.4 清单)需要把 `current_user: str` 改为 `current_user: User`,并把后续 `current_user` 字符串用法改为 `current_user.username`。这一改造由 codex 用 ripgrep 一次性扫描完成,见 §13 阶段 3。

### 7.4 `/api/auth` 端点契约

> 错误响应统一遵循现有 `app.utils.errors.api_error` 格式 `{"detail": {"code": ..., "user_message": ..., "trace_id": ...}}`。

#### POST `/api/auth/register`

- **请求**: `{ "username": str, "password": str, "email": str | null }`
- **校验**: username 正则 `^[a-zA-Z0-9_-]{3,64}$`;password 长度 8–128;email 若给出则 RFC 5322 简化校验。
- **201 响应**: `{ "user": { "id", "username", "email", "created_at" } }`
- **错误**: 422 `validation_error`;409 `username_taken` / `email_taken`。
- **副作用**: `INSERT users`(`password_hash = argon2id(password)`)。
- **不自动登录**(避免和登录端点行为耦合;前端注册成功后再调 `/login`)。

#### POST `/api/auth/login`

- **请求**: `{ "username": str, "password": str }`(JSON;不走 OAuth2PasswordRequestForm,避免 multipart 依赖与 i18n 冲突)
- **200 响应**: `{ "access_token": str, "token_type": "bearer", "expires_in": 900, "user": {...} }`
- **Set-Cookie**: `refresh_token=<raw>; HttpOnly; SameSite=Lax; Path=/api/auth; Max-Age=2592000; Secure(若 settings.DEBUG=False)`
- **错误**: 401 `invalid_credentials`(用户不存在 / 密码错误统一返回此码,避免账户枚举);403 `account_disabled`。
- **副作用**: `INSERT refresh_tokens`;`UPDATE users.last_login_at`。

#### POST `/api/auth/refresh`

- **请求**: 无 body;从 cookie 读取 `refresh_token`。
- **200 响应**: `{ "access_token": str, "expires_in": 900 }`,并 `Set-Cookie` 下发**新的** refresh token。
- **错误**: 401 `missing_refresh` / `invalid_refresh` / `expired_refresh` / `revoked_refresh`。
- **副作用**: 旧 token 标记 `revoked_at = now`;插入新 refresh 行(轮换)。
- **安全要求**: 必须使用**原始 token 计算哈希后查库**,绝不在日志或响应里出现原始 token。

#### POST `/api/auth/logout`

- **请求**: 无 body;读取 cookie 中的 refresh。
- **204 响应**,`Set-Cookie: refresh_token=; Max-Age=0; Path=/api/auth`。
- **副作用**: 若 cookie 中 token 命中且未吊销,则 `UPDATE revoked_at = now`;命中失败也返回 204(幂等)。

#### GET `/api/auth/me`

- 受 `Depends(get_current_user)` 保护,200 返回 `{ "user": {...} }`。

### 7.5 现有受保护端点审计

下表所有端点都必须在改造后:
(a) 已通过 `dependencies=[Depends(get_current_user)]` 或函数参数 `current_user: User = Depends(get_current_user)`,
(b) 任何接受 `user_id` 路径参数的,必须调用 `require_matching_user(user_id, current_user)`,
(c) 任何数据库查询都必须以 `current_user.username` 为过滤条件,绝不允许用客户端传入的 `user_id`(请求体 / query)直接查询。

| 文件 | 端点 | 当前隔离状态 | 需要的改造 |
| --- | --- | --- | --- |
| `api/questions.py` | `GET /api/questions/...` | 题库为全局只读,无 user 维度 | 仅需替换 `current_user` 类型 |
| `api/training.py` | `POST/GET /api/training/...` | 经 `student_id` 隔离 | 把 `current_user` 字符串改为 `User.username`;确认 `get_or_create_student(current_user.username)` 是唯一入口 |
| `api/student.py` | `GET /api/student/{user_id}/...` | 已用 `require_matching_user` | 仅替换参数类型 |
| `api/llm.py` | 大量 conversation 路由 | `user_id` 由各函数自行从 `current_user` 取 | 全数改为 `current_user.username`,**移除任何允许客户端通过 query 传 `user_id` 的兼容代码** |
| `api/analytics.py` | `POST /api/analytics/...` | 经 `BehaviorLog.user_id` | 强制写入 `current_user.username` |
| `api/dashboard.py` | `/api/dashboard/...` | 已迁到 `current_user`,但 `DashboardTaskCreate.user_id` 仍是请求字段 | **删除请求体里的 `user_id` 字段**,服务端只信任 `current_user` |
| `api/materials.py` | 上传 / 检索 / 列表 | 当前 `user_id` 可为 None | 全部强制为 `current_user.username`;`StudyMaterial.user_id` 列改为 NOT NULL |

> Codex 执行时,用 `rg "current_user: str"` + `rg "user_id" backend/app/api` 两次全量扫描确认无遗漏。

### 7.6 配置项变更(`config.py`)

**新增**

```
JWT_SECRET: str        # 必填,启动校验非空;默认从环境变量读取
JWT_ALGORITHM: str = "HS256"
ACCESS_TOKEN_TTL_SECONDS: int = 900           # 15 min
REFRESH_TOKEN_TTL_SECONDS: int = 60*60*24*30  # 30 days
PASSWORD_MIN_LENGTH: int = 8
PASSWORD_MAX_LENGTH: int = 128
COOKIE_REFRESH_NAME: str = "refresh_token"
COOKIE_REFRESH_PATH: str = "/api/auth"
COOKIE_SECURE: bool | None = None  # None = 跟随 not DEBUG
```

**删除**

```
API_KEYS                  # 已不再使用
DEFAULT_AUTH_USER_ID      # 不再有默认匿名身份
```

**修改**

```
DEBUG: bool = True
CORS_ORIGINS: 不变(已经是具体白名单,可保留)
# 注意:main.py 中 build_cors_options 的 debug 分支必须改成具体 origins,
# 不能再返回 ["*"] —— 与 allow_credentials=True 不兼容。
```

启动校验:`main.py` 的 `initialize_app_database` 前增加 `assert settings.JWT_SECRET, "JWT_SECRET must be set"`;DEBUG 模式下可允许进程启动时自动生成一个 ephemeral secret 但打 WARNING 日志,生产模式下必须读到非空字符串(避免冷启动 panic)。

## 8. 前端设计

### 8.1 路由与守卫

```
<AuthProvider>
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/register" element={<RegisterPage />} />
    <Route element={<ProtectedRoute />}>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/tutor" element={<TutorPage />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
</AuthProvider>
```

- `ProtectedRoute`:`useAuth().status === 'authenticated'` 时渲染 `<Outlet />`;`'unauthenticated'` 时 `<Navigate to="/login" state={{ from: location }} />`;`'loading'` 时渲染 `<PageSkeleton />`。

### 8.2 `AuthContext`

```ts
// src/auth/AuthContext.tsx
type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';
interface AuthState {
  status: AuthStatus;
  user: { id: number; username: string; email: string | null } | null;
}
interface AuthActions {
  login(username: string, password: string): Promise<void>;
  register(username: string, password: string, email?: string): Promise<void>;
  logout(): Promise<void>;
}
```

- 启动时调用 `POST /api/auth/refresh` 探测是否已登录(浏览器自动带 cookie),命中即 `setUser`、`setAccessToken`,失败则 `unauthenticated`。
- `login` / `register` / `logout` 之后,**广播 `auth-changed` 事件**,触发 `useQueryClient().clear()`,清除 React Query 缓存以避免上一个用户数据残留。

### 8.3 `apiClient.ts` 改造

主要变更:

1. 删除 `API_KEY` 常量与 `headers.set('X-API-Key', API_KEY)`。
2. 所有 `fetch` 调用增加 `credentials: 'include'`。
3. 从模块作用域读 `accessToken` 内存变量(`getAccessToken()` / `setAccessToken()` 暴露给 `AuthContext`),拼到 `Authorization: Bearer ${accessToken}`。
4. **401 自动 refresh**(关键代码骨架):

```ts
let refreshInFlight: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) throw new ApiError('refresh_failed', res.status, 'unauthorized');
      const body = await res.json();
      setAccessToken(body.access_token);
      return body.access_token;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

// apiFetch 内部:第一次 401 且非 /api/auth/* 时,尝试 refresh 再重放一次;
// 第二次仍 401,清空 access token,广播 auth:logout,redirect /login。
```

> **要求**:`refreshInFlight` 必须是单飞(single-flight)的,避免一次性并发请求各自触发 5 个 `/auth/refresh`。

### 8.4 `LoginPage` / `RegisterPage` UI 草案

- 使用现有 `components/ui/*` 风格(`button`, glass surface)保持一致。
- 表单字段:登录 `[用户名, 密码]`;注册 `[用户名, 密码, 邮箱(可选), 重复密码]`。
- 客户端校验:与后端同步的正则与长度;错误以 toast / 内联文案展示,优先使用现有 `utils/toast.ts`。
- i18n:在 `englishToChineseMessages` 加入新键 `'invalid_credentials'`, `'username_taken'`, `'token_expired'`, `'password_too_short'` 等;不要新增独立 i18n 框架。
- **顶部导航(`TopNavbar`)** 增加用户菜单(头像首字母 + 下拉:用户名展示 + 登出),登出按钮调用 `useAuth().logout()`。

### 8.5 移除硬编码 user_id

- `frontend/src/pages/DashboardPage.tsx:21` 与所有 `DASHBOARD_USER_ID` 引用替换为 `useAuth().user.username`。
- `frontend/src/utils/dashboardApi.ts`、`chatApi.ts` 等若有 `user_id` 入参,改为从 hook/路径读出当前用户名,**而不是任由调用方传**。
- 测试桩(`apiClient.test.ts` 已有)需要更新使用新的 `Auth` 错误码与 401 重试路径。

## 9. 安全设计

| 项 | 设计 | 备注 |
| --- | --- | --- |
| 密码哈希 | argon2id(`passlib[argon2]`),time_cost=3、memory_cost=64MiB、parallelism=2 | argon2-cffi 已是 OWASP 推荐;参数偏弱但兼顾本地 dev 体验。 |
| 密码策略 | 8–128 字符,不强制复杂度(NIST SP 800-63B) | 不做密码字典黑名单,留作 backlog。 |
| Access token 签名 | HS256 + `JWT_SECRET`(≥ 32 字节) | 单服务足够;切多实例时 secret 走 K/V 共享。 |
| Refresh token | 32 字节 urlsafe 随机串,SHA-256 哈希入库 | 仅返回原文一次,后续靠 cookie 自动回传。 |
| Cookie 属性 | `HttpOnly; SameSite=Lax; Path=/api/auth; Secure(prod); Max-Age=2592000` | `Lax` 足以挡常规 CSRF;`Path` 限制只在 auth 路由发送。 |
| CSRF | 因为业务 API 不读 cookie(只读 `Authorization` header),不存在跨站伪造业务请求;`/api/auth/refresh` 读 cookie 但仅返回新 access token,无副作用风险面 | 若后续把 cookie 用作业务身份,必须改为 double-submit token 或 SameSite=Strict |
| CORS | `allow_origins = settings.CORS_ORIGINS`(具体域),`allow_credentials = True` 始终为真;DEBUG 也不放 `*` | 与 cookie 共存的硬约束。 |
| 错误信息 | 登录失败统一返回 `invalid_credentials`,不区分“用户不存在”与“密码错” | 防账户枚举。 |
| 速率限制 | 本期**不强制**实现;在 `api/auth.py` 处用 `# TODO: rate-limit (slowapi)` 标注 | backlog。 |
| 日志 | `auth.tokens` 与 `auth.passwords` 模块禁止 `logger.info(token)` / `logger.info(password)`;统一 mask | 单测覆盖 mask 行为。 |
| Secret 管理 | `JWT_SECRET` 通过 `.env` 注入,`.gitignore` 已含 `.env` | DEBUG 兜底自动生成不可跨进程持久,符合开发体验 |

## 10. 数据迁移与兼容

### 10.1 Alembic 迁移脚本

按编号依次写三份迁移:

1. `20260514_01_users_table.py`
   - `create_table('users')`(§7.2 schema)
   - `create_table('refresh_tokens')`(§7.2 schema)
   - 索引:`ix_users_username`, `ix_refresh_tokens_user_id`, `ix_refresh_tokens_expires_at`。

2. `20260514_02_tighten_user_id_nullable.py`
   - `op.alter_column('tutor_conversations', 'user_id', nullable=False)`
   - `op.alter_column('study_materials', 'user_id', nullable=False)`
   - 在 SQLite 上 `op.batch_alter_table` 包一层(SQLite 不支持原地 alter)。
   - 同时给 `tutor_conversations.user_id` 与 `study_materials.user_id` 加 `ForeignKey('users.username')`。

3. `20260514_03_seed_test01_user.py`(**强制执行,不再可选**)
   - **创建 `test-01` 用户行**:
     - `username = 'test-01'`
     - `password_hash = argon2id('123456')`(在迁移脚本里**直接调用** `app.auth.passwords.hash_password` 生成,**不要**把明文写进 SQL;若迁移阶段还不能 import 业务模块,则在脚本顶部内联一份 `passlib.hash.argon2.hash('123456')` 调用)
     - `email = NULL`,`is_active = True`,`created_at` / `updated_at` = 迁移执行时刻 ISO8601。
   - **回填 legacy 数据**(2026-05-13 盘点结果):
     - `UPDATE tutor_conversations SET user_id='test-01' WHERE user_id IS NULL;`(预期 3 行)
     - `UPDATE study_materials SET user_id='test-01' WHERE user_id IS NULL;`(预期 1 行)
     - `tutor_conversation_messages` 不需要直接 UPDATE,它通过 `conversation_id` 自动挂上。
     - 执行前后各 `SELECT COUNT(*) WHERE user_id IS NULL` 一次,写入 Alembic logger,以便回滚审计。
   - **断言**:迁移末尾 `assert` 没有 `user_id IS NULL` 残留;若有,raise 让升级失败,避免后续 `ALTER COLUMN NOT NULL` 崩在中途。
   - **downgrade()**:把 `test-01` 拥有的 legacy 行回写为 NULL,然后删除 `users` 表中 `username='test-01'` 行;`refresh_tokens` 走 FK CASCADE 自动清理。

> ⚠️ 不再提供 reset(DELETE)分支 —— 用户明确要求保留这 3 条对话 + 1 个材料。若 codex 在实施时发现 `tutor.db` 内容已和盘点不符(例如新增了对话),迁移脚本应按"全部 `user_id IS NULL` 的行都归到 `test-01`"的规则执行,不要写死行数。

### 10.2 启动行为

- `bootstrap.initialize_database` 已在 DEBUG 下做 `Base.metadata.create_all`;迁移期间保留,但 README/AGENTS.md 标注**生产部署必须执行 `alembic upgrade head`**。
- 启动时不再单独播种 `local/localdev` 演示账号 —— `test-01/123456` 已经由迁移 `20260514_03` 创建,既保留历史数据又能直接登录演示,职责合并。
- 启动 banner 在 DEBUG 模式下打印一行提示:`"Demo account: test-01 / 123456 (please change after first login)"`,便于本地 dev、面试 demo 不卡在登录页。

### 10.3 生产部署注意

- `test-01 / 123456` 是面向**本地开发与作品集 demo** 的有意识弱口令。生产环境(`DEBUG=False`)启动时:
  - `app/bootstrap.py` 增加一段校验:若检测到 `users.username='test-01'` 且其 `password_hash` 与默认 `123456` 哈希一致(用一次 `verify_password('123456', user.password_hash)` 探测),且 `settings.DEBUG=False`,则启动日志打 ERROR 并 `sys.exit(1)`,强制运维改密。
  - 若运维希望在生产保留 `test-01` 用户但用强密码,登录一次改密即可绕过启动校验。
  - 若运维不希望存在 `test-01` 用户,可以在生产首次部署前在该环境单独跑 `DELETE FROM users WHERE username='test-01';`,迁移 `20260514_03` 自身保持幂等(检测到已存在则跳过)。
- 因此 ADR-005 提到的"生产部署必须把这条迁移替换为不带默认密码的版本"的实际落地是:**迁移脚本不变,启动检查兜底**,避免运维忘记替换迁移文件。

## 11. 测试计划

### 11.1 后端单元测试(`backend/tests/`)

新增文件:

- `tests/test_auth_passwords.py` — argon2 round-trip、错误密码不通过。
- `tests/test_auth_tokens.py` — encode/decode access、过期检测、refresh 哈希生成 + 比对。
- `tests/test_auth_api.py`(**最重要**) — 用 `TestClient` 覆盖:
  - 注册成功 / 用户名重复 409 / 校验失败 422。
  - 登录成功并返回 cookie / 密码错 401 / 账号未激活 403。
  - 刷新轮换(旧 cookie 一次性失效)、刷新过期、刷新被吊销。
  - 登出后旧 refresh 失效,新登录得到新 cookie。
  - access token 解析失败时受保护路由返回 401。
- `tests/test_isolation.py`(**新建,关键回归**) — 对以下端点用两个用户 `alice` / `bob` 各跑一遍,确认互不可见:
  - `/api/dashboard/summary`、`/api/dashboard/tasks`(创建+列出+读取+删除)。
  - `/api/student/{user_id}/mastery|recommendations|report|review-plan`(`user_id` 不匹配返回 403)。
  - `/api/llm/conversations`(列表、读取详情、导出 markdown、删除)。
  - `/api/materials`(上传后列表只含本人)。
  - `/api/training/...` 提交答题后 mastery 只更新本人。

### 11.2 前端测试(`frontend/src/**/*.test.{ts,tsx}`)

- `auth/AuthContext.test.tsx` — login/register/logout 状态机、refresh 启动探测。
- `components/ProtectedRoute.test.tsx` — 未登录跳 `/login` 并保留 `state.from`。
- `utils/apiClient.test.ts` — 401 触发一次刷新并重放;两连 401 不无限循环;single-flight 并发只发一次 `/refresh`。

### 11.3 手工验收脚本(`scripts/manual-auth-smoke.md` 或写进 AGENTS)

1. `python backend/start.py` 启动后端;
2. 浏览器 `http://localhost:5173` 应被路由守卫推到 `/login`;
3. 走注册→自动跳登录→输入凭据→进入 dashboard;
4. F12 → Application → Cookies,确认 `refresh_token` 是 HttpOnly + Secure(prod) + Path=/api/auth;
5. 把内存 access token 手动清空(`window.__authDebug.clear()` 调试钩子)再发请求,应触发一次 refresh 后业务请求成功;
6. 同浏览器开两个 incognito 注册 alice/bob,各自有独立 dashboard、错题记录、对话历史;
7. 在 alice 会话里手工 `GET /api/student/bob/mastery`,预期 403。

## 12. 验收标准(Definition of Done)

- [ ] `python -m unittest discover -s backend/tests -v` 全部通过,包含 `test_auth_*` 与 `test_isolation`。
- [ ] `cd frontend; npm run type-check && npm run lint && npm test -- --run` 全部通过。
- [ ] 后端任何受保护端点在缺失 `Authorization` 头时返回 401(用 `pytest -q` 跑一个参数化清单)。
- [ ] 任意现存路由中无 `'local'` 字面值;`rg "'local'" backend/app frontend/src` 必须只剩下 README / 注释 / 历史迁移文件。
- [ ] `rg "VITE_API_KEY|X-API-Key"` 不再出现在 `frontend/src`(允许在文档里)。
- [ ] `rg "API_KEYS|DEFAULT_AUTH_USER_ID"` 不再出现在 `backend/app`。
- [ ] CORS 在 DEBUG 模式下不再返回 `Access-Control-Allow-Origin: *`(用 curl 验证)。
- [ ] AGENTS.md / README.md / 两个 IMPLEMENTATION_PLAN.md 更新到反映认证流程与本期变更。
- [ ] **legacy 数据迁移验收**:`alembic upgrade head` 后,用 `test-01 / 123456` 登录,能在前端看到原有的 3 条 Tutor 对话与 1 个学习材料;`SELECT COUNT(*) FROM tutor_conversations WHERE user_id IS NULL` 与 `... study_materials WHERE user_id IS NULL` 均为 0。

## 13. 实施分阶段(给 codex 的执行顺序)

> 每个阶段以**独立提交**结束,并在阶段末跑一次 §13.x 的 quick check。

### 阶段 1 — 后端认证基础设施(无业务影响)

- 新增 `app/auth/{passwords,tokens,cookies,exceptions}.py`、`app/models/user.py`、`app/api/auth.py`。
- 新增 Alembic 迁移 `20260514_01_users_table.py`。
- `config.py` 增加 `JWT_SECRET` 等设置;**保留**旧的 `API_KEYS` / `DEFAULT_AUTH_USER_ID` 字段不删,确保业务路由暂时无须修改。
- `main.py` 注册 auth router、修复 CORS(`allow_credentials=True` + 具体 origins)。
- 单测:`test_auth_passwords.py`, `test_auth_tokens.py`, `test_auth_api.py`(只测新端点本身)。
- **Quick check**: `python -m compileall app tests`, `python -m unittest discover -s tests -v`,新测试全绿。

### 阶段 2 — 切换 `get_current_user` 实现

- 改写 `app/api/deps.py:get_current_user` 为 JWT 版本(签名仍是 `() -> User` 之外的所有现有签名兼容性由 codex 用全仓搜索一次性改完)。
- 全仓替换:`current_user: str = Depends(get_current_user)` → `current_user: User = Depends(get_current_user)`;
  下游所有 `current_user` 字符串引用改为 `current_user.username`。
- 删除 `config.API_KEYS` 与 `DEFAULT_AUTH_USER_ID`;
  删除 `apiClient.test.ts` 中关于 `Missing X-API-Key header` 的字面断言(改为 `Missing access token`),并相应更新 `englishToChineseMessages`。
- 单测:`test_isolation.py`。
- **Quick check**: `python -m unittest`, 全绿。

### 阶段 3 — 现有端点 user_id 收紧

- 审计 §7.5 表中“需要的改造”一列,逐一改完。
- 重点:`api/dashboard.py` 删除 `DashboardTaskCreate.user_id` / `DashboardTaskUpdate.user_id` 字段;`api/materials.py` 强制 `user_id = current_user.username`。
- Alembic 迁移 `20260514_02_tighten_user_id_nullable.py` 与 `20260514_03_seed_test01_user.py`。
- **Quick check**: 先 `cp backend/tutor.db backend/tutor.db.bak`,跑 `alembic upgrade head` 在备份上验证迁移幂等(`alembic downgrade -1 && alembic upgrade head` 两次走通);手工 SQL 验证 `users(username='test-01').is_active=1`、`tutor_conversations.user_id='test-01'` 共 3 行、`study_materials.user_id='test-01'` 共 1 行;`test_isolation.py` 跑一遍。

### 阶段 4 — 前端认证 UX

- 新增 `src/auth/AuthContext.tsx`、`src/auth/ProtectedRoute.tsx`、`src/pages/LoginPage.tsx`、`src/pages/RegisterPage.tsx`。
- 改造 `App.tsx` 路由树;改造 `apiClient.ts`(`credentials: 'include'`、删 `X-API-Key`、加 Bearer、加 401 single-flight refresh)。
- 替换所有硬编码 `'local'` 字面值;`TopNavbar` 加用户菜单 + 登出。
- 前端单测 + i18n 字典更新。
- **Quick check**: `npm run type-check`, `npm run lint`, `npm test -- --run`, `npm run build`。

### 阶段 5 — 文档与作品集润色

- 更新 `AGENTS.md`(操作命令、环境变量 `JWT_SECRET`)。
- 更新 `IMPLEMENTATION_PLAN.md`(根、backend、frontend 三处),把多用户登录列入“已完成里程碑”。
- 更新 `README.md`:首屏体验从“配置 API Key” 变为“注册 → 登录”。
- 截图 / GIF demo(可选,作品集亮点)。

### 决策项(交给 codex 在实施时落实)

- **D-1**:~~legacy 数据保留 vs reset~~ —— **已锁定**:保留并归属新建的 `test-01 / 123456` 用户(active),不丢现有的 3 条对话与 1 个材料。见 §10.1。
- **D-2**:~~DEBUG 自动播种 demo 账号~~ —— **已锁定**:不再单独播种,`test-01` 已经由迁移 `20260514_03` 创建并保持 active,启动 banner 打印一行提示即可。
- **D-3**:是否启用 `slowapi` 速率限制(SDD 倾向于“否,本期 TODO”)。

## 14. 风险与对策

| 风险 | 等级 | 对策 |
| --- | --- | --- |
| `current_user` 改类型导致大面积破坏 | 高 | 在阶段 2 第一个 commit 前,先用 `rg -l "current_user: str"` 列全清单并写入 task list,逐文件改;每文件改完跑 `python -m compileall` 即时反馈。 |
| Refresh 单飞失误造成请求风暴 | 中 | apiClient 单测显式构造并发场景断言只调用一次 `/refresh`。 |
| Cookie 配置在 dev 与 prod 行为漂移(`Secure`、`SameSite`) | 中 | `app/auth/cookies.py` 集中所有 cookie 拼装,DEBUG / 非 DEBUG 走同一个函数,由 `settings.COOKIE_SECURE` 显式驱动。 |
| SQLite `alter_column nullable=False` 失败 | 中 | 用 `op.batch_alter_table` 包裹;迁移先 `UPDATE ... SET user_id='local' WHERE user_id IS NULL`,确保无 NULL 再改约束。 |
| 用户在两个 tab 同时操作,refresh 互相吊销 | 低 | 接受 single-flight + 旧 token 1 次轮换;若极端并发,前端在第二次 401 后才登出。 |
| `JWT_SECRET` 漏配上线 | 高 | `main.py` 启动断言 + CI 在 prod profile 下显式校验。 |
| 隔离回归覆盖不全 | 高 | `test_isolation.py` 作为强制集成测试;每新增带 `user_id` 的路由都必须在该文件加一条用例。 |

## 15. 附录

### A. 待变更 / 新增文件清单

**新增**

```
backend/app/auth/__init__.py
backend/app/auth/passwords.py
backend/app/auth/tokens.py
backend/app/auth/cookies.py
backend/app/auth/exceptions.py
backend/app/models/user.py
backend/app/api/auth.py
backend/alembic/versions/20260514_01_users_table.py
backend/alembic/versions/20260514_02_tighten_user_id_nullable.py
backend/alembic/versions/20260514_03_seed_legacy_local_user.py
backend/tests/test_auth_passwords.py
backend/tests/test_auth_tokens.py
backend/tests/test_auth_api.py
backend/tests/test_isolation.py
frontend/src/auth/AuthContext.tsx
frontend/src/auth/ProtectedRoute.tsx
frontend/src/auth/types.ts
frontend/src/pages/LoginPage.tsx
frontend/src/pages/RegisterPage.tsx
frontend/src/auth/AuthContext.test.tsx
frontend/src/auth/ProtectedRoute.test.tsx
```

**修改**

```
backend/app/api/deps.py
backend/app/api/dashboard.py
backend/app/api/llm.py
backend/app/api/materials.py
backend/app/api/training.py
backend/app/api/analytics.py
backend/app/api/student.py
backend/app/config.py
backend/app/main.py
backend/app/models/__init__.py
backend/app/models/chat_history.py        # user_id NOT NULL + FK
backend/app/models/materials.py           # user_id NOT NULL + FK
backend/app/models/dashboard.py           # 加 FK
backend/app/models/student.py             # 加 FK(可选)
backend/app/services/chat_history.py      # 删除 Optional[user_id] 路径
backend/app/services/materials.py         # 同上
backend/app/services/dashboard.py         # 同上
backend/app/services/analytics.py         # 同上
backend/requirements.txt                  # +passlib[argon2], +python-jose 或 +PyJWT
backend/AGENTS.md
backend/README.md
backend/IMPLEMENTATION_PLAN.md
frontend/src/App.tsx
frontend/src/components/TopNavbar.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/pages/TutorPage.tsx          # 若引用 'local' 也需要清理
frontend/src/utils/apiClient.ts
frontend/src/utils/apiClient.test.ts
frontend/src/utils/dashboardApi.ts
frontend/src/utils/chatApi.ts
frontend/package.json                     # 若需要新增 jwt-decode(可选)
frontend/IMPLEMENTATION_PLAN.md
AGENTS.md
IMPLEMENTATION_PLAN.md
README.md
```

### B. 决策记录(ADR)

- **ADR-001**:认证方案选用 JWT (access + refresh httpOnly cookie)。
  - 备选:服务端 session、纯 localStorage JWT。
  - 决策理由:作品集面向外企面试官,JWT + httpOnly cookie 是当前主流答案;refresh 在 cookie 里既抗 XSS 又便于服务端吊销;比纯 localStorage 方案更专业。
- **ADR-002**:注册采用开放自助注册。
  - 备选:邀请制、邮箱验证。
  - 决策理由:简化 demo 链路;邮箱验证留作下一期。
- **ADR-003**:错题本仅做数据隔离,不新增 UI。
  - 备选:新增错题本视图、新增视图 + 推荐复习。
  - 决策理由:`StudentAnswer` 已经记录答题历史并按 `student_id` 隔离,本期目标是认证 + 隔离基线,不扩展功能面。
- **ADR-004**:`Student.user_id` 字符串仍然是业务隔离主键,与 `users.username` 同义。
  - 备选:新增 `auth_user_id` 整数 FK,逐步淘汰字符串列。
  - 决策理由:最小破坏面;现有服务层、Alembic、测试代码大量基于字符串 `user_id`,改为整数 FK 不属于本期目标。
- **ADR-005**:legacy 数据(2026-05-13 盘点为 `user_id IS NULL` 的 3 条对话与 1 个材料)归属新建的 `test-01 / 123456` 用户(`is_active=True`,可直接登录)。
  - 备选 1:迁移时清空(`DELETE`)—— 被用户明确否决,会丢历史对话。
  - 备选 2:沿用 `local` 用户名 + `is_active=False` —— 不符合“能登录直接看到旧数据”的目标。
  - 决策理由:作品集 demo 时面试官输入 `test-01 / 123456` 即可立刻看到带历史会话的 dashboard,链路完整;`123456` 是有意识的弱口令,用于本地/demo,README 与启动 banner 都明确提示"首次登录后立即修改"。生产部署必须把这条迁移替换为不带默认密码的版本(详见下方"生产部署注意")。

### C. 评审与签收

- [ ] 设计评审:开发者通读本文档并在本节签字 / 评注。
- [ ] 实施授权:开发者明确把本 SDD 交付 codex,本 SDD 即作为开发契约。
- [ ] 后续修订:任何阶段中发现的偏差,以"在此 SDD 上加补丁(PATCH-001 等)"方式而非口头沟通完成。
