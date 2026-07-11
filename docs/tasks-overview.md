# FamilySafety 任务计划 - 总览

配套 architecture.md 使用。颗粒度：每任务 = 1 个 PR（4-16 小时）。

## 任务总览

| Phase | 周期 | 目标 | 任务数 |
|-------|------|------|--------|
| P0 基础设施 | 第 1 周 | 仓库结构、CI、文档 | 8 |
| P1 后端 MVP  | 第 2 周 | 设备注册、心跳、规则匹配、内容规则模型 | 15 |
| P2 LLM 答题  | 第 3 周 | 出题、判题、奖励、内容分类、周报生成、推送 | 21 |
| P3 Windows 骨架 | 第 4 周 | .NET 解决方案、Service、Monitor | 15 |
| P4 守护 + UI | 第 5 周 | Hook DLL、Quiz UI、Guardian | 18 |
| P5 家长端 | 第 6 周 | Dashboard、规则、出题、LLM 建议、内容规则、周报、推送 | 14 |
| P6 打包发布 | 第 7 周 | Installer、E2E、文档 | 6 |
| P7 1.0 发布 | 第 8 周 | 测试、修复、发布 | 4 |

合计 101 任务 / 约 10 周（新增内容检测 + 周报）。

## 关键里程碑

- W1 末：仓库结构 + CI + 文档齐备
- W2 末：后端可跑通，注册/心跳/Resolver/内容规则 E2E 通
- W3 末：答题功能完整，出题配置 + 弱项分析可用
- W4 末：内容分类 + 周报生成 + 邮件推送全流程通
- W5 末：Windows 客户端骨架可启动，Service 自启
- W6 末：完整超时答题流程跑通，含 Hook 强制
- W7 末：家长可登录看板，能配置所有规则和推送
- W9 末：一键安装包可发，自动注册到后端
- W10 末：v1.0 正式发布

## 关键路径（Top 10）

1. T107 设备注册
2. T108 心跳 + T109 Resolver
3. T204 出题 + T215 集成 QuizConfig
4. T305-T307 Service 三件套
5. T312-T313 窗口查询 + 时长累加 + T216 内容分类
6. T402-T404 键盘钩子
7. T408-T410 Quiz 三个页面
8. T413-T414 Guardian 拉起
9. T509/T510 出题配置 + LLM 建议 + T511/T513 内容规则 + 周报
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
