# FamilySafety 任务计划 - P1 后端 MVP

第 2 周，15 个任务。

## T101 Python 项目骨架（FastAPI）
- 范围：backend/ 初始化、pyproject.toml、目录结构
- 验收：uvicorn app.main:app --reload 启动成功
- 依赖：T001

## T102 配置模块（pydantic-settings）
- 范围：app/core/config.py
- 验收：启动时打印所有配置项
- 依赖：T101

## T103 数据库连接（SQLAlchemy Async）
- 范围：app/db/session.py
- 验收：能连上 PostgreSQL
- 依赖：T102

## T104 定义 ORM 模型（完整版）
- 范围：Family / Member / Device / Rule / UsageRecord / QuizSession
- 验收：init_db() 执行后表全部存在
- 依赖：T103

## T105 Pydantic Schemas
- 范围：app/schemas/ 完整定义
- 验收：OpenAPI 文档完整
- 依赖：T104

## T106 Alembic 迁移初始化
- 范围：alembic init、alembic.ini、env.py
- 验收：alembic revision --autogenerate 成功
- 依赖：T104

## T107 设备注册 API
- 范围：POST /api/v1/agent/register
- 验收：curl 测试可成功注册并拿到 api_key
- 依赖：T105, T106

## T108 心跳 API
- 范围：POST /api/v1/agent/heartbeat
- 验收：不同账号返回不同规则
- 依赖：T107

## T109 账号 + 型号匹配 Resolver
- 范围：app/services/resolver.py
- 验收：单测覆盖 5 种匹配场景
- 依赖：T104

## T110 使用记录上报 API
- 范围：POST /api/v1/agent/usage
- 验收：批量插入 100 条 < 1s
- 依赖：T107

## T111 健康检查端点
- 范围：GET /healthz、GET /readyz
- 验收：返回 200/503 正确
- 依赖：T103

## T112 Dockerfile + docker-compose
- 范围：backend/Dockerfile、deploy/docker-compose.yml
- 验收：docker compose up 启动全套，访问 /docs 看到 API
- 依赖：T111

## T113 ContentRule / ToxicAlert 模型
- 范围：ContentRule / ToxicAlert 表 schema
- 验收：Alembic 迁移成功
- 依赖：T104

## T114 内容规则种子数据
- 范围：首次部署时插入默认规则集（进程/标题）
- 验收：数据库初始化后规则可用
- 依赖：T113

## T115 NotificationConfig 模型
- 范围：NotificationConfig 表 + 加密字段
- 验收：能写入 SMTP 配置（密码加密）
- 依赖：T104

P1 完成标志：完整后端跑起来，注册/心跳/Resolver/内容规则 E2E 通。
