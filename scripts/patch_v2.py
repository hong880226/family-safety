"""Patch P1, P2, P5 with new content detection + weekly report tasks.
Also update overview counts.
"""
from pathlib import Path

DOCS = Path("E:/codeRepo/familysafety/docs")


# === P1: add ContentRule/ToxicAlert models + content rule seeding ===
p1 = DOCS / "tasks-p1.md"
p1_text = p1.read_text(encoding="utf-8")

P1_NEW_TASKS = """
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
"""

marker = "P1 完成标志：完整后端跑起来，curl 测三个核心 API 全通。"
p1_text = p1_text.replace(marker, P1_NEW_TASKS.strip().split("\n", 1)[1] + "\n\n" + marker)
# Actually easier: replace marker with new tasks + marker
p1_text_new = p1_text.replace(marker, P1_NEW_TASKS.strip() + "\n")
p1.write_text(p1_text_new, encoding="utf-8")
print(f"  patched tasks-p1.md ({len(p1_text_new)} bytes)")


# === P2: add content classification + LLM toxic judge + weekly report generation ===
p2 = DOCS / "tasks-p2.md"
p2_text = p2.read_text(encoding="utf-8")

P2_NEW_TASKS = """
## T216 内容分类服务（Agent 端）
- 范围：app/services/classifier.py（后端），C# 端 L1+L2 实现
- 验收：能识别游戏/浏览器/短视频
- 依赖：T113

## T217 LLM 毒视频判定
- 范围：app/services/toxic_judge.py
- 验收：100 个样本准确率 > 85%
- 依赖：T205, T113

## T218 周报数据汇总服务
- 范围：app/services/weekly_report.py
- 验收：周报 summary 字段完整正确
- 依赖：T110, T214

## T219 周报 LLM 内容生成
- 范围：基于 summary 生成教育建议正文
- 验收：人工 review 5 份周报，4 份以上可用
- 依赖：T218, T205

## T220 邮件推送
- 范围：SMTP 客户端 + 模板渲染
- 验收：测试邮件能收到
- 依赖：T115, T219

## T221 定时任务（APScheduler）
- 范围：每周日晚 8 点生成周报
- 验收：手动调整时间能触发
- 依赖：T219, T220

P2 完成标志：内容分类可用；LLM 毒视频判定准确；周报生成 + 邮件推送全流程跑通。
"""

p2_text_new = p2_text.replace(
    "P2 完成标志：家长可配置学科/难度/分布；弱项学科自动多出题；答题数据回流更新 mastery。",
    P2_NEW_TASKS.strip() + "\n"
)
p2.write_text(p2_text_new, encoding="utf-8")
print(f"  patched tasks-p2.md ({len(p2_text_new)} bytes)")


# === P5: add content rules editor + weekly report pages + notification config ===
p5 = DOCS / "tasks-p5.md"
P5_NEW = """# FamilySafety 任务计划 - P5 家长端

第 6 周，14 个任务（原 10 个 + 新增 4 个）。

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

## T511 内容分类规则编辑器（v1.0 增强）
- 范围：CRUD ContentRule、规则测试器、可视化规则预览
- 验收：家长可自定义哪些应用/网站被识别为游戏/毒视频
- 依赖：T113, T216

## T512 毒视频告警页（v1.0 增强）
- 范围：ToxicAlert 列表、LLM 判定详情、家长确认/误报标记
- 验收：家长能看到 LLM 判定的可疑内容
- 依赖：T217

## T513 周报查看页（v1.0 增强）
- 范围：历史周报列表、周报详情（数据可视化 + AI 建议正文）、对比上周
- 验收：家长能查看完整周报
- 依赖：T218, T219

## T514 推送配置页（v1.0 增强）
- 范围：SMTP 配置、Webhook 配置、通知开关、测试发送
- 验收：家长能配置周报和告警的接收方式
- 依赖：T115, T220

P5 完成标志：家长可登录看板，能配置成员/规则/设备/LLM/出题规则/内容规则，能查看弱项/LLM 建议/毒视频告警/周报，能配置推送通道。
"""

p5.write_text(P5_NEW, encoding="utf-8")
print(f"  rewrote tasks-p5.md ({len(P5_NEW)} bytes)")


# === Update overview ===
overview = DOCS / "tasks-overview.md"
ov_text = overview.read_text(encoding="utf-8")

# New counts: P1 12+3=15, P2 15+6=21, P5 10+4=14, total = 8+15+21+15+18+14+6+4 = 101
ov_text = ov_text.replace("合计 85 任务 / 约 8 周。", "合计 101 任务 / 约 10 周（新增内容检测 + 周报）。")
ov_text = ov_text.replace("| P1 后端 MVP  | 第 2 周 | 设备注册、心跳、规则匹配 | 12 |",
                          "| P1 后端 MVP  | 第 2 周 | 设备注册、心跳、规则匹配、内容规则模型 | 15 |")
ov_text = ov_text.replace("| P2 LLM 答题  | 第 3 周 | 出题、判题、奖励 | 10 |",
                          "| P2 LLM 答题  | 第 3 周 | 出题、判题、奖励、内容分类、周报生成、推送 | 21 |")
ov_text = ov_text.replace("| P5 家长端 | 第 6 周 | Web Dashboard、规则配置、出题配置、LLM 建议 | 10 |",
                          "| P5 家长端 | 第 6 周 | Dashboard、规则、出题、LLM 建议、内容规则、周报、推送 | 14 |")
overview.write_text(ov_text, encoding="utf-8")
print(f"  updated tasks-overview.md")

# W2/W3/W5 milestones update
ov_text = ov_text.replace(
    "- W2 末：后端可跑通，注册/心跳/Resolver E2E 通",
    "- W2 末：后端可跑通，注册/心跳/Resolver/内容规则 E2E 通"
)
ov_text = ov_text.replace(
    "- W3 末：答题功能完整，出题配置 + 弱项分析可用",
    "- W4 末：答题 + 内容分类 + 周报生成 + 邮件推送全流程通"
)
ov_text = ov_text.replace(
    "- W4 末：Windows 客户端骨架可启动，Service 自启",
    "- W5 末：Windows 客户端骨架可启动，Service 自启"
)
ov_text = ov_text.replace(
    "- W5 末：完整超时答题流程跑通，含 Hook 强制",
    "- W6 末：完整超时答题流程跑通，含 Hook 强制"
)
ov_text = ov_text.replace(
    "- W6 末：家长可登录看板，能配置规则",
    "- W7 末：家长可登录看板，能配置所有规则和推送"
)
ov_text = ov_text.replace(
    "- W7 末：一键安装包可发，自动注册到后端",
    "- W9 末：一键安装包可发，自动注册到后端"
)
ov_text = ov_text.replace(
    "- W8 末：v1.0 正式发布",
    "- W10 末：v1.0 正式发布"
)
overview.write_text(ov_text, encoding="utf-8")

print("\nDone.")
for p in sorted(DOCS.glob("tasks-*.md")):
    print(f"  {p.name} ({p.stat().st_size} bytes)")
print(f"  architecture.md ({ (DOCS / 'architecture.md').stat().st_size } bytes)")