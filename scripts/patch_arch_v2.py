"""Append sections 3.10-3.12 to architecture.md about
- content detection (games, web games, toxic videos)
- weekly reports + push notifications
- (also update 3.9 API list)
"""
from pathlib import Path
import re

DOC = Path("E:/codeRepo/familysafety/docs/architecture.md")
text = DOC.read_text(encoding="utf-8")

INSERTION = """
### 3.10 内容检测架构（v1.0 增强）

孩子使用电脑的方式远比"运行游戏进程"复杂，必须有完整的内容识别体系。

#### 检测层级

```
L1 进程名匹配（毫秒级、本地）
   ↓ 命中游戏客户端
L2 窗口标题关键词（百毫秒级、本地）
   ↓ 命中浏览器 / 网页应用
L3 URL 提取（秒级、需要 Hook 浏览器）
   ↓ 命中可疑 URL
L4 内容语义分析（异步、LLM）
   ↓ 命中"疑似毒视频"等内容
```

#### ContentCategory 枚举（标准分类）

| 值 | 含义 | 示例 |
|----|------|------|
| `game_native` | 桌面游戏 | steam.exe, LoL |
| `game_web` | 网页游戏 | 4399.com, roblox.com |
| `short_video` | 短视频 | 抖音, B站, YouTube Shorts |
| `video_long` | 长视频 | B站长视频, YouTube |
| `social` | 社交 | QQ, 微信, Telegram |
| `study` | 学习 | B站学习区, 慕课网 |
| `search` | 搜索 | 百度, Google |
| `news` | 新闻 | 头条, 网易新闻 |
| `unknown` | 未分类 | 默认 |

#### ContentRule 表（家长可配置的分类规则）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | |
| family_id | FK | |
| match_type | enum | `process` / `window_title` / `url` / `domain` |
| pattern | str | 匹配模式（正则或 glob） |
| category | enum | 映射到 ContentCategory |
| sub_label | str | 细分子类（如「4399小游戏」「毒视频疑似」） |
| action | enum | `monitor` / `warn` / `block` / `flag_for_llm` |
| enabled | bool | |
| created_at | datetime | |

#### 检测流程（Agent 端）

```csharp
// C# 伪代码（在 fs_monitor 中）
CategoryResult Categorize(WindowInfo win) {
    // L1: 进程名匹配
    var rule = rules.FirstOrDefault(r =>
        r.match_type == "process" &&
        Regex.IsMatch(win.ProcessName, r.pattern) &&
        r.enabled);

    if (rule != null) {
        return new CategoryResult {
            category = rule.category,
            source = "process",
            confidence = 0.95,
            action = rule.action
        };
    }

    // L2: 窗口标题匹配
    if (IsBrowser(win.ProcessName)) {
        var titleRule = rules.FirstOrDefault(r =>
            r.match_type == "window_title" &&
            Regex.IsMatch(win.Title, r.pattern));

        if (titleRule != null) {
            return new CategoryResult {
                category = titleRule.category,
                source = "title",
                confidence = 0.75,
                action = titleRule.action
            };
        }

        // L3: 提取 URL（Hook 浏览器，v1.1 实现）
        var url = BrowserHook.GetURL(win.Hwnd);
        // v1.0 暂时用标题启发式
    }

    return new CategoryResult { category = "unknown", confidence = 0.0 };
}
```

#### LLM 二次判定（flag_for_llm）

当 rule.action == `flag_for_llm` 时，Agent 把当前窗口标题 + 最近 5 分钟活动记录打包上报后端，后端调用 LLM 判断：

```text
System: 你是一位内容审核专家，专注于识别不适宜青少年观看的内容。
User: 请判断以下内容是否属于「毒视频」（含自残/暴力/低俗/赌博引流等）。

【应用】抖音电脑版
【当前视频标题】xxx
【最近 5 分钟标题列表】
  - xxx
  - xxx
  - xxx

返回 JSON：{"is_toxic": true/false, "category": "...", "confidence": 0.0-1.0, "reason": "..."}
```

#### 默认规则集（首次部署内置）

```json
[
  {"match_type": "process", "pattern": "(?i)(steam|epicgames|minecraft|riot|wegame|valve)\\.exe$", "category": "game_native", "action": "monitor"},
  {"match_type": "process", "pattern": "(?i)(chrome|msedge|firefox)\\.exe$", "category": "browser", "action": "monitor"},
  {"match_type": "window_title", "pattern": "(4399|7k7k|3366|roblox|miniclip)", "category": "game_web", "action": "warn"},
  {"match_type": "window_title", "pattern": "(抖音|douyin|tiktok|快手|kwai)", "category": "short_video", "action": "monitor"},
  {"match_type": "window_title", "pattern": "(bilibili|b站)", "category": "video_long", "action": "monitor"},
  {"match_type": "window_title", "pattern": "(自残|自杀|血腥|暴力|色情|赌博)", "category": "toxic_content", "action": "flag_for_llm"}
]
```

家长可在 Dashboard 增删改规则。

#### 数据模型调整

| 表 | 调整 |
|----|------|
| UsageRecord | 新增 `category`、`sub_label`、`confidence` 字段 |
| ContentRule | 新增表（如上） |
| ToxicAlert | 新增表（LLM 判定为毒视频的记录） |

#### ToxicAlert 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | |
| member_id | FK | |
| device_id | FK | |
| window_title | str | 触发时的窗口标题 |
| llm_judgment | json | LLM 返回的完整判定 |
| category | str | toxic / gambling / violence / adult / etc |
| confidence | float | |
| notified | bool | 是否已通知家长 |
| created_at | datetime | |

### 3.11 周报与推送（v1.0 新增）

#### WeeklyReport 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | |
| family_id | FK | |
| member_id | FK | 哪位孩子 |
| week_start | date | 周一日期 |
| week_end | date | 周日日期 |
| summary | json | 数据汇总（时长、应用、答题） |
| ai_content | text | LLM 生成的教育建议正文 |
| push_status | enum | `pending` / `sent` / `failed` |
| push_channel | enum | `email` / `webhook` / `dashboard` |
| created_at | datetime | |
| sent_at | datetime | nullable |

#### summary 字段结构

```json
{
  "total_minutes": 480,
  "delta_vs_last_week": -30,
  "overtime_count": 2,
  "top_apps": [
    {"app": "steam.exe", "category": "game_native", "minutes": 240},
    {"app": "chrome.exe", "category": "browser", "minutes": 180}
  ],
  "category_breakdown": {
    "game_native": 240,
    "game_web": 60,
    "short_video": 90,
    "study": 50,
    "other": 40
  },
  "quiz_summary": {
    "total_sessions": 5,
    "total_questions": 15,
    "avg_accuracy": 0.73,
    "by_subject": {
      "math": {"accuracy": 0.6, "count": 5, "is_weak": true},
      "chinese": {"accuracy": 0.8, "count": 5}
    }
  },
  "weak_subjects": ["math"],
  "toxic_alerts_count": 0
}
```

#### 推送通道

| 通道 | 实现 | 适用 |
|------|------|------|
| Dashboard | 留存在 /dashboard/reports | v1.0 必做 |
| Email | SMTP（家长在配置里填邮箱） | v1.0 必做 |
| Webhook | POST JSON 到家长填写的 URL（兼容企业微信 / 钉钉 / 飞书机器人） | v1.1 |

#### 定时任务（APScheduler）

```python
# 后端启动时注册
scheduler.add_job(
    generate_weekly_reports,
    'cron',
    day_of_week='sun',
    hour=20,
    minute=0,
    id='weekly_report'
)

async def generate_weekly_reports():
    families = db.query(Family).all()
    for family in families:
        for member in family.members:
            if member.role != 'child':
                continue
            summary = await compute_weekly_summary(db, member)
            ai_content = await llm.generate_weekly_advice(summary)
            report = WeeklyReport(
                family_id=family.id,
                member_id=member.id,
                week_start=...,
                summary=summary.dict(),
                ai_content=ai_content,
                push_status='pending',
            )
            db.add(report)
            db.commit()
            await send_via_channels(report, family.config)
```

#### LLM 周报 Prompt 模板

```text
你是一位青少年家庭教育专家。请基于以下一周数据，为「{name}」（{grade} 年级）的家长撰写一份周报。

要求：
1. 开头一段总评（积极正面，但不回避问题）
2. 「使用时长」段：客观描述，必要时温和提醒
3. 「内容分布」段：游戏/学习/视频占比，给出建议
4. 「学习表现」段：答题准确率，特别提及弱项学科
5. 「下周建议」段：3 条具体可操作建议
6. 结尾给家长一段鼓励语

字数：500-800 字中文。语气：温和、专业、不焦虑。
```

### 3.12 更新后的完整 API 列表

```
# Agent 端
POST   /api/v1/agent/register
POST   /api/v1/agent/heartbeat
POST   /api/v1/agent/usage
GET    /api/v1/agent/rule
POST   /api/v1/agent/usage/categorized    # 带内容分类的上报

# 答题
POST   /api/v1/quiz/start
POST   /api/v1/quiz/submit

# 内容检测
GET    /api/v1/admin/content-rules        # 规则列表
POST   /api/v1/admin/content-rules        # 新增
PUT    /api/v1/admin/content-rules/{id}   # 修改
DELETE /api/v1/admin/content-rules/{id}   # 删除
POST   /api/v1/admin/content-rules/test   # 测试规则（输入样本，返回匹配结果）
GET    /api/v1/dashboard/toxic-alerts     # 毒视频告警列表
POST   /api/v1/admin/llm-judge            # Agent 上报触发 LLM 二次判定

# 弱项分析
GET    /api/v1/dashboard/mastery

# LLM 建议
GET    /api/v1/dashboard/suggestions
POST   /api/v1/suggestions/generate
POST   /api/v1/suggestions/{id}/apply
POST   /api/v1/suggestions/{id}/reject

# 周报
GET    /api/v1/dashboard/reports          # 历史周报列表
GET    /api/v1/dashboard/reports/{id}     # 单份周报详情
POST   /api/v1/reports/generate           # 手动触发生成
GET    /api/v1/admin/notification-config  # 推送配置
PUT    /api/v1/admin/notification-config  # 修改推送配置

# Dashboard 基础
GET    /api/v1/dashboard/summary
GET    /api/v1/dashboard/usage

# 成员/规则/设备管理
GET    /api/v1/admin/members
POST   /api/v1/admin/members
PUT    /api/v1/admin/members/{id}
DELETE /api/v1/admin/members/{id}
GET    /api/v1/admin/rules
POST   /api/v1/admin/rules
PUT    /api/v1/admin/rules/{id}
DELETE /api/v1/admin/rules/{id}
GET    /api/v1/admin/quiz-config/{rule_id}
PUT    /api/v1/admin/quiz-config/{rule_id}
GET    /api/v1/admin/devices
POST   /api/v1/admin/devices/{id}/revoke

# LLM 配置
GET    /api/v1/admin/llm-config
PUT    /api/v1/admin/llm-config
POST   /api/v1/admin/llm-config/test

# 鉴权
POST   /api/v1/auth/login
POST   /api/v1/auth/logout

# 健康检查
GET    /healthz
GET    /readyz
```

### 3.13 NotificationConfig 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | |
| family_id | FK | |
| email | str | SMTP 收件人 |
| smtp_host | str | SMTP 服务器 |
| smtp_port | int | |
| smtp_user | str | |
| smtp_password | str | 加密存储 |
| webhook_url | str | 可选，企业微信 / 钉钉 |
| enable_weekly_email | bool | 是否发周报邮件 |
| enable_toxic_alert | bool | 毒视频告警推送 |
| toxic_alert_threshold | float | 触发推送的置信度阈值 |
| updated_at | datetime | |
"""


# Find the section after 3.9 to insert 3.10-3.13 before 4.1
marker = "\n### 4.1 进程拓扑"
if marker in text:
    insert_pos = text.find(marker)
    new_text = text[:insert_pos] + INSERTION + "\n" + text[insert_pos:]
    DOC.write_text(new_text, encoding="utf-8")
    print(f"  appended {len(INSERTION)} bytes")
    print(f"  new file size: {len(new_text)} bytes")
else:
    print("ERROR: marker not found")