"""Generate all Phase task documents in one go."""
from pathlib import Path

DOCS = Path("E:/codeRepo/familysafety/docs")
DOCS.mkdir(parents=True, exist_ok=True)


OVERVIEW = """# FamilySafety 任务计划 - 总览

配套 architecture.md 使用。颗粒度：每任务 = 1 个 PR（4-16 小时）。

## 任务总览

| Phase | 周期 | 目标 | 任务数 |
|-------|------|------|--------|
| P0 基础设施 | 第 1 周 | 仓库结构、CI、文档 | 8 |
| P1 后端 MVP  | 第 2 周 | 设备注册、心跳、规则匹配 | 12 |
| P2 LLM 答题  | 第 3 周 | 出题、判题、奖励 | 10 |
| P3 Windows 骨架 | 第 4 周 | .NET 解决方案、Service、Monitor | 15 |
| P4 守护 + UI | 第 5 周 | Hook DLL、Quiz UI、Guardian | 18 |
| P5 家长端 | 第 6 周 | Web Dashboard、规则配置 | 8 |
| P6 打包发布 | 第 7 周 | Installer、E2E、文档 | 6 |
| P7 1.0 发布 | 第 8 周 | 测试、修复、发布 | 4 |

合计 81 任务 / 约 8 周。

## 关键里程碑

- W1 末：仓库结构 + CI + 文档齐备
- W2 末：后端可跑通，注册/心跳/Resolver E2E 通
- W3 末：答题功能完整，本地题库兜底可用
- W4 末：Windows 客户端骨架可启动，Service 自启
- W5 末：完整超时答题流程跑通，含 Hook 强制
- W6 末：家长可登录看板，能配置规则
- W7 末：一键安装包可发，自动注册到后端
- W8 末：v1.0 正式发布

## 关键路径（Top 10）

1. T107 设备注册
2. T108 心跳 + T109 Resolver
3. T204 generate_questions + T207 Quiz Start
4. T305-T307 Service 三件套
5. T312-T313 窗口查询 + 时长累加
6. T402-T404 键盘钩子
7. T408-T410 Quiz 三个页面
8. T413-T414 Guardian 拉起
9. T501-T503 Dashboard
10. T601-T604 Installer

## 详细任务清单

- P0 基础设施：tasks-p0.md
- P1 后端 MVP：tasks-p1.md
- P2 LLM 答题：tasks-p2.md
- P3 Windows 骨架：tasks-p3.md
- P4 守护 + UI：tasks-p4.md
- P5 家长端：tasks-p5.md
- P6 打包发布：tasks-p6.md
- P7 1.0 发布：tasks-p7.md
"""


P0 = """# FamilySafety 任务计划 - P0 基础设施

第 1 周，8 个任务。

## T001 初始化 Git 仓库与目录结构
- 范围：仓库根目录创建 backend/ agent-windows/ deploy/ docs/
- 验收：git clone 后能看到完整结构
- 依赖：无

## T002 编写 README.md
- 范围：项目总览、快速开始、技术栈、贡献指南
- 验收：陌生人能在 5 分钟内理解项目目标
- 依赖：T001

## T003 添加 LICENSE
- 范围：MIT 协议
- 依赖：T001

## T004 配置 .gitignore
- 范围：Python、.NET、IDE 通用 ignore
- 依赖：T001

## T005 添加 Issue / PR 模板
- 范围：.github/ISSUE_TEMPLATE/、PULL_REQUEST_TEMPLATE.md
- 依赖：T001

## T006 配置 GitHub Actions CI 骨架
- 范围：lint + test 工作流
- 依赖：T001

## T007 完成 ARCHITECTURE.md
- 范围：docs/architecture.md
- 验收：团队成员 review 通过
- 依赖：无

## T008 完成本任务计划
- 范围：本文档系列（tasks-p0.md ~ tasks-p7.md）
- 验收：每个任务有清晰交付物和验收标准
- 依赖：无

P0 完成标志：仓库结构完整、CI 跑通、文档齐备。
"""


P1 = """# FamilySafety 任务计划 - P1 后端 MVP

第 2 周，12 个任务。

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

P1 完成标志：完整后端跑起来，curl 测三个核心 API 全通。
"""


files = {
    "tasks-overview.md": OVERVIEW,
    "tasks-p0.md": P0,
    "tasks-p1.md": P1,
}

for name, content in files.items():
    target = DOCS / name
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {name}: {len(content)} bytes")

print(f"\nDone. Files in {DOCS}:")
for p in sorted(DOCS.glob("*.md")):
    print(f"  {p.name} ({p.stat().st_size} bytes)")