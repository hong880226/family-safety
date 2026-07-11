"""Patch P2 and P5 task documents to include new features."""
from pathlib import Path

DOCS = Path("E:/codeRepo/familysafety/docs")

# P2 append: new tasks after T210
p2 = DOCS / "tasks-p2.md"
p2_text = p2.read_text(encoding="utf-8")

P2_NEW = """

## T211 QuizConfig 模型与 API
- 范围：QuizConfig 表、CRUD API、关联 Rule
- 验收：能配置学科、难度、分布；更新后立即生效
- 依赖：T104, T108

## T212 出题分布计算服务
- 范围：app/services/distribution.py
- 验收：支持 manual / auto / weakness_first 三种模式
- 依赖：T211, T214

## T213 多学科批量出题
- 范围：generate_questions 支持批量多学科
- 验收：5 道题跨 3 学科，生成 < 15s
- 依赖：T204, T212

## T214 SubjectMastery 模型与计算
- 范围：SubjectMastery 表、update_mastery 服务
- 验收：30 天数据准确率正确，弱项标记正确
- 依赖：T104

## T215 Quiz Start 集成 QuizConfig
- 范围：/quiz/start 改用 QuizConfig 生成题目
- 验收：响应中含 config_used 字段
- 依赖：T213, T214

P2 完成标志：家长可配置学科/难度/分布；弱项学科自动多出题；答题数据回流更新 mastery。
"""

# Insert before "P2 完成标志" (the original one)
marker_old = "P2 完成标志：手动跑一遍答题流程"
if marker_old in p2_text:
    # Remove old P2 completion marker, append new tasks + new marker
    p2_text = p2_text.replace(marker_old, "")
    p2_text += P2_NEW
    p2.write_text(p2_text, encoding="utf-8")
    print(f"  patched tasks-p2.md ({len(p2_text)} bytes)")
else:
    print("WARN: old P2 marker not found, appending at end")
    p2_text += P2_NEW
    p2.write_text(p2_text, encoding="utf-8")


# P5 replace with expanded version including new pages
P5_NEW = """# FamilySafety 任务计划 - P5 家长端

第 6 周，10 个任务（原 8 个 + 新增 2 个）。

## T501 Dashboard 基础框架
- 范围：Jinja2 + 简单 HTML + 深色简约风
- 验收：访问 /dashboard 看到导航
- 依赖：T105

## T502 家长登录
- 范围：JWT 登录、家长账号
- 验收：错误密码拒绝
- 依赖：T501

## T503 Dashboard 概览页
- 范围：今日 / 本周时长、Top 应用、最近答题
- 验收：Chart.js 数据准确
- 依赖：T502

## T504 Dashboard 详细数据页
- 范围：按天 / 按应用聚合查询
- 验收：查询性能 OK
- 依赖：T503

## T505 成员管理 CRUD
- 范围：增删改查成员
- 验收：能添加孩子并设置 grade
- 依赖：T502

## T506 规则配置页
- 范围：可视化编辑规则、匹配键预览
- 验收：配置后 Agent 心跳能拿到新规则
- 依赖：T505

## T507 设备管理页
- 范围：查看在线设备、撤销 API Key
- 验收：撤销后 Agent 鉴权失败
- 依赖：T502

## T508 LLM 配置页
- 范围：家长可配置 LLM base_url / api_key / model
- 验收：配置后立即生效
- 依赖：T502

## T509 QuizConfig 配置页（v1.0 增强）
- 范围：学科多选、难度滑块、学科分布拖拽、自动/手动/弱项优先模式切换
- 验收：家长可可视化配置出题规则
- 依赖：T506, T211

## T510 弱项雷达图 + LLM 建议页（v1.0 增强）
- 范围：学科掌握度雷达图、智能建议列表、一键应用建议
- 验收：家长能看到弱项 + LLM 生成的建议
- 依赖：T214, T215

P5 完成标志：家长可登录看板，能配置成员、规则、设备、LLM、出题配置，能查看弱项和应用 LLM 建议。
"""

(DOCS / "tasks-p5.md").write_text(P5_NEW, encoding="utf-8")
print(f"  rewrote tasks-p5.md ({len(P5_NEW)} bytes)")


# Update overview count
overview = DOCS / "tasks-overview.md"
ov_text = overview.read_text(encoding="utf-8")
ov_text = ov_text.replace("合计 81 任务 / 约 8 周。", "合计 85 任务 / 约 8 周。")
ov_text = ov_text.replace("| P5 家长端 | 第 6 周 | Web Dashboard、规则配置 | 8 |",
                          "| P5 家长端 | 第 6 周 | Web Dashboard、规则配置、出题配置、LLM 建议 | 10 |")
overview.write_text(ov_text, encoding="utf-8")
print(f"  updated tasks-overview.md")

print("\nDone.")
for p in sorted(DOCS.glob("tasks-*.md")):
    print(f"  {p.name} ({p.stat().st_size} bytes)")