# FamilySafety 任务计划 - P0 基础设施

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
