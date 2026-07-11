# FamilySafety 开发者指南

面向**修改代码**的贡献者。包含 dev/prod 配置、迁移、常见任务。

> **部署/使用**请看 [`user-guide.md`](./user-guide.md) 和 [`troubleshooting.md`](./troubleshooting.md)。

---

## 1. 开发环境

```bash
# 后端
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# 启动 dev server
set ENVIRONMENT=dev             # Windows PowerShell: $env:ENVIRONMENT='dev'
uvicorn app.main:app --reload --port 8000
```

打开 http://localhost:8000/docs 看 API 文档。

### 必须的环境变量（dev）

dev 模式下，`JWT_SECRET` 可以为空（自动生成 ephemeral 密钥）；
`LLM_API_KEY` 必须填，否则所有 AI 功能 fallback 到题库。

最小 `.env`：
```
ENVIRONMENT=dev
LLM_API_KEY=sk-your-key-here
```

### 必须的环境变量（prod）

见 `backend/.env.example`。**不要把任何 `change-me` 字面量粘到生产 .env**。

```bash
# 生成 JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 生成 FERNET_KEY（at-rest 加密 SMTP 密码、Quiz 答案）
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 2. 数据库迁移

模型变更后：

```bash
cd backend
alembic revision --autogenerate -m "add column foo"
alembic upgrade head             # 应用到本地 DB

# 检查迁移文件
cat alembic/versions/<新文件>.py
# 提交
git add alembic/versions/
git commit -m "schema: add foo"
```

> ⚠️ autogenerate 不会捕获：列重命名、enum 变更、约束条件变更 — 都要手工 review。

部署环境：

```bash
# 部署前：备份
docker exec familysafety-db pg_dump -U familysafety familysafety > backup.sql

# 部署
docker compose pull backend
docker compose up -d backend       # entrypoint 自动跑 alembic upgrade head
```

---

## 3. 测试

```bash
cd backend
pytest                              # 全部 unit + integration 测试
pytest tests/test_security.py -v    # 单个文件
python test_dashboard.py            # E2E smoke（需要先清 DB）
```

测试覆盖：
- `test_security.py` — bcrypt/JWT/Fernet 工具
- `test_csrf.py` — CSRF token 签发与校验
- `test_web_inputs.py` — 表单 Pydantic 验证
- `test_config_safety.py` — prod 启动 fail-closed 校验
- `test_resolver.py` — 规则匹配（5+ 场景）
- `test_family_isolation.py` — 跨家庭越权防护

### 写新测试的约定

1. 纯函数 → 写到 `tests/test_<module>.py`，无 fixture
2. DB 交互 → 用 `pytest_asyncio.fixture` 内存 SQLite
3. 端到端 → `test_dashboard.py`（启动真实 uvicorn）

---

## 4. 写新 API 端点

模板：

```python
# backend/app/api/v1/foo.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, require_parent
from app.models.member import Member

router = APIRouter(prefix="/foo", tags=["foo"])

@router.get("")
async def list_foo(
    db: AsyncSession = Depends(get_db),
    member: Member = Depends(require_parent),  # 总是校验
):
    stmt = select(Foo).where(Foo.family_id == member.family_id)  # 总是按 family 过滤
    return (await db.execute(stmt)).scalars().all()
```

**红线**：
- ❌ 任何 `Foo` 端点都不允许不带 `member.family_id` 过滤
- ❌ 任何 POST/PUT/DELETE 都不允许不调用 `validate_csrf_or_raise`
- ❌ 任何 endpoint 不允许在源码里写 `try: ... except Exception: pass`
- ✅ 写单元测试 + 至少一个越权测试

注册路由：

```python
# backend/app/main.py
from app.api.v1 import foo
app.include_router(foo.router, prefix=settings.api_v1_prefix)
```

---

## 5. 写新 dashboard 页面

1. 在 `app/web/templates/` 创建 `my_page.html`，继承 `_layout.html`
2. 在 `app/web/routes.py` 添加 handler：
   ```python
   @router.get("/my-page", response_class=HTMLResponse)
   async def my_page(
       request: Request,
       member: Member = Depends(require_parent_or_redirect),
       db: AsyncSession = Depends(get_db),
   ):
       return templates.TemplateResponse(
           request,
           "my_page.html",
           {
               "request": request,
               "csrf_token": issue_csrf_token(request),
               "active": "my-page",  # 高亮侧栏
               "data": ...,
           },
       )
   ```
3. 在 `_layout.html` 的侧栏加链接（如果新页面）
4. 所有 form 加 `<form method="post">` — JS 自动注入 CSRF token

---

## 6. 调试技巧

### 查看结构化日志

```bash
# prod 模式（JSON）
ENVIRONMENT=prod uvicorn app.main:app 2>&1 | jq

# dev 模式（彩色 plain text）
ENVIRONMENT=dev uvicorn app.main:app --reload
```

所有日志带 `request_id` 和 `path`。grep 一个请求的全部日志：

```bash
journalctl -u familysafety | jq "select(.record.extra.request_id == \"abc123\")"
```

### 模拟 LLM 失败（测 fallback）

```bash
LLM_API_KEY=invalid-key ENVIRONMENT=dev python -c "
import asyncio
from app.llm.client import LLMClient
async def t():
    c = LLMClient()
    try:
        r = await c.chat([{'role':'user','content':'hi'}])
        print('OK:', r)
    except Exception as e:
        print('Failed:', e)
asyncio.run(t())
"
```

### 触发 circuit breaker

连续 5 次失败即可触发：
```bash
for i in {1..10}; do
  curl -X POST localhost:8000/api/v1/quiz/start \
    -H "Authorization: Bearer invalid-key" \
    -d '{}' | jq .detail
done
# 第 6 次起会看到 "circuit breaker is OPEN"
```

---

## 7. 部署检查清单

部署前对照检查：

- [ ] `JWT_SECRET` 已设为随机 ≥ 32 字符
- [ ] `FERNET_KEY` 已设为独立随机 Fernet key
- [ ] `DATABASE_URL` 指向 Postgres（不是 SQLite）
- [ ] `CORS_ORIGINS` 列出具体域名，无 `*`
- [ ] `ENVIRONMENT=prod`
- [ ] `DEBUG=false`
- [ ] SMTP 密码**未**出现在 .env（用户填在 web UI，Fernet 加密落库）
- [ ] `alembic upgrade head` 已跑
- [ ] 防火墙放行 8000 端口（仅 443 + 反代后）
- [ ] 反代（Nginx / Caddy）配置 HTTPS + HSTS
- [ ] `docker compose logs backend` 无 ERROR

---

## 8. 常见任务

### 添加新的内容类别

1. `app/models/content_rule.py` — 加 `ContentCategory.MY_NEW = "my_new"`
2. `app/schemas/web_inputs.py` — ContentRuleForm 自动接受（已经是枚举）
3. `app/services/content_classifier.py` — 加默认规则
4. 迁移：`alembic revision --autogenerate -m "add content category"`

### 添加新 dashboard 页面

见上节「写新 dashboard 页面」。

### 添加新 API 端点

见上节「写新 API 端点」。

### 升级 LLM 模型

```
LLM_MODEL=deepseek-coder
```

或代码里修改 `app/core/config.py` 的默认值。

---

## 9. 仓库结构

```
backend/
  app/
    api/v1/         # JSON API（agent + quiz）
    api/deps.py     # auth dependencies
    core/           # config + security + DB session
    db/             # SQLAlchemy session
    llm/            # LLM client + prompts + fallback bank
    models/         # ORM 模型
    schemas/        # Pydantic 请求/响应模型
    services/       # 业务逻辑（content_classifier, scheduler, weekly_report...）
    web/            # 服务端渲染 dashboard
      routes.py     # /web/* 路由
      templates/    # Jinja2 模板
  alembic/          # 迁移
  tests/            # pytest 单元 + 集成测试
  deploy/           # Docker Compose / Nginx
docs/               # 用户文档 + 架构
scripts/            # 历史 codegen 脚本
```

---

## 10. 提 PR 流程

1. Fork + branch：`git checkout -b feat/my-change`
2. 改完跑 `pytest` 全过
3. 跑 `python test_dashboard.py` E2E 通过
4. 如有 schema 变更，**同时提交** alembic 迁移
5. PR 标题格式：`feat: 添加弱项学科下钻分析` / `fix: 修复越权访问...`
6. 描述：动机 + 改动点 + 测试覆盖 + 截图（如有 UI 变更）

---

## 下一步

- 部署：`deploy/README.md`
- 使用：`user-guide.md`
- 排错：`troubleshooting.md`