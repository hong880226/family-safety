# FamilySafety

> 自托管的家庭儿童电脑使用管理套件。用答题兑换时长，把限制转化为学习激励。

---

## 项目状态

v1.0 开发中。当前已完成架构设计与任务规划，正在按 Phase 实施。

详细进度与任务清单：[`docs/tasks-overview.md`](./docs/tasks-overview.md)
架构设计：[`docs/architecture.md`](./docs/architecture.md)
用户指南：[`docs/user-guide.md`](./docs/user-guide.md)
开发者指南：[`docs/dev-guide.md`](./docs/dev-guide.md)
故障排查：[`docs/troubleshooting.md`](./docs/troubleshooting.md)
CI/CD 流程：[`docs/ci-cd.md`](./docs/ci-cd.md)

---

## CI / CD

- 后端 PR / push：自动跑 ruff、mypy、pytest（Postgres + Redis 服务）。
- 推送到 `main` 且 `backend/**` 有变更：自动构建后端 Docker 镜像并推送至 **阿里云容器镜像服务**。
  镜像地址：`registry.cn-hangzhou.aliyuncs.com/<namespace>/familysafety-backend:<short-sha>` 和 `:latest`。
- 推送到 `main` 且 `agent-windows/**` 有变更：在 Windows runner 上编译 WPF 客户端，产物以 zip 形式上传到 Actions artifacts。

所需 GitHub Secrets：`ALIYUN_REGISTRY_USER`、`ALIYUN_REGISTRY_PASSWORD`、`ALIYUN_REGISTRY_NAMESPACE`（详见 `docs/ci-cd.md`）。

---

## 这是什么

一个完全自托管的家长控制软件，包含：

- **Debian 后端**（FastAPI + PostgreSQL + Redis）
  - 设备管理、规则匹配、LLM 出题、数据聚合
  - 家长 Web 看板
- **Windows 客户端**（C# .NET 8 + WPF）
  - 进程监控、时长统计、答题 UI
  - 七层进程守护 + 键盘钩子 UI 强制
- **LLM 答题系统**
  - 家长配置学科、难度、分布
  - 自动识别孩子弱项学科，重点突破
  - 每周自动生成教育周报，邮件推送

## 核心特性

- 账号 + 电脑型号联合判定，支持多孩子共用一台电脑
- LLM 出题（兼容 OpenAI 协议，可接入 DeepSeek / OpenAI / Ollama）
- 七层进程守护，普通孩子无法关停
- 键盘钩子禁用 Alt+F4/Win 键，答题时强制专注
- 内容检测：识别游戏 / 短视频 / 网页游戏 / 毒视频（LLM 二次判定）
- 周报推送：每周自动汇总 + 教育建议邮件

---

## 快速开始（开发中）

### 后端（Docker Compose）

```bash
cd deploy
cp .env.example .env
docker compose up -d
# 浏览器访问 http://localhost:8000/docs
```

### 客户端（Windows）

```bash
# 待 P3-P6 完成
# 编译 agent-windows/FamilySafety.sln
# 运行 Inno Setup 打包脚本
```

---

## 技术栈

| 模块 | 技术 |
|------|------|
| 后端 API | Python 3.11 + FastAPI + SQLAlchemy 2 (async) |
| 数据库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| LLM | 任意 OpenAI 兼容协议（DeepSeek / OpenAI / Ollama） |
| 前端 | .NET 8 + WPF + C++/CLI Hook DLL |
| 部署 | Docker Compose（后端）、Inno Setup（客户端） |

---

## 目录结构

```
familysafety/
├── backend/                    # Python FastAPI 后端
├── agent-windows/              # C# .NET 8 Windows 客户端
├── deploy/                     # Docker Compose + Nginx
├── docs/                       # 架构与任务文档
└── scripts/                    # 构建与辅助脚本
```

---

## 贡献

欢迎贡献！开始前请先阅读 `docs/architecture.md` 了解整体设计。

---

## 许可证

MIT License — 详见 [LICENSE](./LICENSE)