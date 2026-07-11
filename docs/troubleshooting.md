# FamilySafety 故障排查

> **找不到答案？** 在 GitHub Issue 搜一下类似问题，没找到再开新 Issue 并附上日志。

---

## 启动 / 部署类

### 后端起不来：`JWT_SECRET must be set to a random string >=32 chars in prod`

**原因**：生产模式下 `JWT_SECRET` 是默认值。
**修复**：
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# 把输出粘到 .env 的 JWT_SECRET=
```

### 后端起不来：`cors_origins=['*'] with credentials is forbidden in prod`

**原因**：带凭证的 CORS 不允许 `*`。
**修复**：`.env` 写具体域名：
```
CORS_ORIGINS=["https://dashboard.example.com"]
```

### Docker 容器启动后反复重启

```bash
docker compose logs backend --tail 200
```

常见：
- `Connection refused: postgres` → 数据库还没准备好，Compose 重启几次就好
- `permission denied` → 数据卷权限问题，`chown -R 10001:10001 ./data/`
- `Address already in use` → 主机 8000 端口被占用，改 `.env` 里 `WEB_PORT`

### `uvicorn` 单进程，4 核 CPU 只跑 1 核

部署环境用 `docker compose`，CMD 走的是 gunicorn 4 workers。
本地开发才是 uvicorn 单进程。生产环境别忘了：
```bash
docker compose up -d --build
```

---

## 数据库 / 迁移类

### 升级后报错 `no such column`

没用 alembic。修复：
```bash
cd backend
alembic upgrade head
```
如果是 v0.1 → v0.2 第一次升级，先跑：
```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

### `OperationalError: database is locked`

SQLite 不支持并发写。生产请换 Postgres：
```
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/familysafety
```

### 表创建失败：`UnicodeDecodeError` / `InvalidTextRepresentation`

通常是 Postgres 字符集问题。确认：
- 数据库用 `UTF8`（不是 `SQL_ASCII`）
- `LANG=en_US.UTF-8` / `LC_ALL=en_US.UTF-8`

---

## LLM / 答题类

### 出题返回 503 `Question generation failed`

LLM 不可达或配额耗尽：
```bash
curl -X POST "$LLM_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}]}'
```
- 401/403 → API key 错误，检查 `.env`
- 429 → 配额耗尽，等待或换 key
- 网络超时 → 检查 LLM_BASE_URL 是否能解析；考虑加反向代理

### 出题全部是 fallback 题（质量差）

- 查看日志 `LLM question generation failed, falling back: ...`
- 修复 LLM 连接后无需重启，下次答题自动用 LLM

### 答题提交后得分异常

数据库 `quiz_sessions.answer_key_enc` 解密失败：
- 可能是 `FERNET_KEY` 或 `JWT_SECRET` 被改了
- 解密失败 → 该 session 无法判分，只能丢弃
- **预防**：永远不要改 `FERNET_KEY`；换机器时复制旧 `.env`

---

## Windows 客户端类

### 客户端装不上：`This app can't run on your PC`

系统不是 Windows 10/11 x64，或 .NET 8 runtime 没装。
确认：
```powershell
[System.Environment]::OSVersion.Version
# Major 必须 >= 10
dotnet --list-runtimes
# 必须有 Microsoft.WindowsDesktop.App 8.x
```

### 客户端启动后秒退

```powershell
cd "C:\Program Files\FamilySafety"
.\FamilySafety.Agent.exe --debug
```

常见：
- `WinRing0 not found` → Hook DLL 没拷到，安装包漏文件，重装
- `Cannot connect to server` → 检查服务端可达、端口开放、API key 正确
- `database is locked` (来自客户端日志中转发的) → 服务端 SQLite 锁

### 客户端装上但 web 看板看不到

- 看「设备」页是否显示这台设备，状态 `online=true` 表示心跳正常
- `online=false` 表示客户端没起来或被 360 / 火绒拦截
- 客户端日志：
  ```powershell
  Get-EventLog -LogName Application -Source FamilySafety -Newest 20
  ```

### 答题弹窗不弹 / 一闪而过

- 答题 UI 进程被另一层防护误杀，看客户端日志的 `quiz start` 段
- WebView2 runtime 没装：`https://developer.microsoft.com/en-us/microsoft-edge/webview2/`

### 时长限制不起效

- 检查「规则」页 daily_limit_minutes 是否被设置
- 默认 120 分钟；如果改过没生效，看 `rules` 表是否 `enabled=true`
- 「用量」是否真的到时间了？客户端 `used_seconds_today` 字段从哪上报的

---

## 通知 / 邮件类

### 收不到周报

1. 推送设置里勾选了「每周邮件推送」吗？
2. SMTP 设置正确吗？端口 587 通常要 STARTTLS（默认开启）
3. 测试发送按钮能用吗？
4. 看垃圾邮件箱
5. 很多云邮箱需要**应用专用密码**：
   - Gmail：Google 账号 → 安全性 → 两步验证 → 应用专用密码
   - QQ：设置 → 账户 → POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务 → 开启 SMTP → 生成授权码

### 报错 `SMTP password decryption failed family=N`

- `FERNET_KEY` 改了，或
- 数据从备份还原但 `.env` 用了新密钥

修复：在推送设置页**重新输入** SMTP 密码（覆盖加密存储）。

### 毒视频告警过多（误报）

- 内容规则的 `pattern` 太宽
- 把 `action` 从 `flag_for_llm` 改成 `block` / `monitor`
- 或在 `pattern` 里增加更精确的关键词

---

## 安全 / 登录类

### 忘记密码

服务端不支持邮件找回（v0.1 范围）。重置方式：
```sql
-- SQLite
sqlite3 familysafety.db "UPDATE members SET password_hash = NULL WHERE name = 'parent_1';"
```
然后 web 登录时会显示「密码未设置」错误（这是设计：拒绝默认密码后门）。
**正解**：在服务端 host 上：
```python
from app.core.security import hash_password
# 通过 python -c 跑：
python -c "from app.core.security import hash_password; print(hash_password('新密码'))"
# 把输出粘到 password_hash 列。
```

### 403 CSRF token missing

- 浏览器禁用 JS 或用了某些隐私插件 → 关闭后重试
- 浏览器缓存了过期的 token → 硬刷新（Ctrl+Shift+R）
- 服务端重启导致 `jwt_secret` 改了 → 重新登录

### 401 not authenticated

- Cookie 被清理或过期（默认 24h）
- 重新登录即可

### 后台日志里看到 SQL 错误但前端 500

检查 `X-Request-ID`，全局日志应能看到对应 stacktrace。
如果有 stacktrace 暴露给前端，说明没开全局异常 handler（请确认 main.py 已更新到最新版本）。

---

## 性能 / 资源类

### 数据库大 / 查询慢

- `usage_records` 表增长最快，每月可清理 90 天前数据：
  ```sql
  DELETE FROM usage_records WHERE start_at < now() - interval '90 days';
  ```
- 给 `usage_records(member_id, start_at)` 加索引
- 周报数据可保留 2 年；老数据可归档到冷表

### LLM 调用慢 / 经常超时

- 默认超时 30s。提高 `LLM_TIMEOUT_SECONDS=60`
- 切换到本地 Ollama（不推荐生产，模型质量差）
- 或换更快的 API：DeepSeek 比 OpenAI 便宜且支持中文好

### 后端吃内存

每个 gunicorn worker ~150MB。4 worker = 600MB + Postgres + Redis。
小机器（1GB）改：
```
WEB_CONCURRENCY=2
```

---

## 调试技巧

### 看实时日志
```bash
docker compose logs -f backend
```

### 进容器排查
```bash
docker compose exec backend bash
python -c "from app.db.session import engine; from sqlalchemy import text; import asyncio; asyncio.run(engine.connect().__aenter__())"
```

### 重置所有数据（**会删家长账号**）
```bash
docker compose down -v
docker compose up -d
# 客户端重新注册即可（家庭 1，家长 parent_1）
```

### 用 SQLite 看数据
```bash
sqlite3 backend/familysafety.db
.tables
SELECT id, name, role, family_id FROM members;
```

---

## 仍未解决？

1. 收集信息：
   - 部署环境（OS、Docker 版本、内存）
   - 完整日志（`docker compose logs > bundle.log`）
   - 复现步骤
2. 在 GitHub 开 issue：
   https://github.com/<your-org>/familysafety/issues/new
   标题格式：`[bug] <简短描述>`
3. 附上：日志 + 配置（**移除 JWT_SECRET / LLM_API_KEY / SMTP 密码**）

---

## 下一步

- 用法：[`user-guide.md`](./user-guide.md)
- 架构：[`architecture.md`](./architecture.md)