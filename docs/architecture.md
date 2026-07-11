# FamilySafety 架构设计文档

> 版本：v1.0  
> 最后更新：2026-07-11  
> 状态：草案，待评审

---

## 0. 文档目的

本文档回答以下问题：

1. 系统由哪些模块组成，各自职责是什么
2. 数据如何在模块之间流动
3. 关键的非功能性需求（守护强度、数据安全、性能）如何满足
4. 多孩子共用电脑场景如何解决
5. 部署、扩展、运维的基本约定

阅读对象：参与本项目开发的所有工程师。

---

## 1. 项目背景与目标

### 1.1 痛点

- 商业家长控制软件收费高，且功能陈旧，缺乏教育性
- 简单的"限时 + 锁屏"方案容易让孩子产生对抗心理
- 单孩子单电脑的方案不能覆盖多孩子共用电脑的现实场景

### 1.2 目标

打造一套**自托管、可扩展、有教育意义**的家长控制套件：

| 目标 | 衡量标准 |
|------|---------|
| 家长可自部署 | Docker 一键启动，所有数据本地 |
| 孩子愿意配合 | 用答题兑换时长，把限制转化为学习激励 |
| 难以被绕过 | 七层防御，普通孩子无法关停 |
| 适配多场景 | 多账号、多电脑、不同年龄段 |

### 1.3 非目标（v1.0 不做）

- 手机 / 平板端（架构预留扩展点，不在 v1.0 实现）
- 远程定位、GPS 追踪
- 跨家庭数据共享
- AI 行为分析（如检测"假装学习"）

---

## 2. 系统架构总览

### 2.1 部署形态

```text
┌─────────────────────────────────────────────────────────────┐
│  家庭局域网 / 公网                                            │
│                                                              │
│  ┌──────────────────────────┐   ┌──────────────────────────┐│
│  │  Debian / Docker         │   │  Windows 客户端 1-N      ││
│  │  ┌──────────────────┐   │   │  ┌─────────────────────┐ ││
│  │  │  FastAPI 后端     │   │   │  │  FamilySafety Service│ ││
│  │  │  + PostgreSQL    │◄──┼───┼──┤  (Windows Service)   │ ││
│  │  │  + Redis         │   │   │  └──────────┬──────────┘ ││
│  │  └──────────────────┘   │   │             │             ││
│  │  ┌──────────────────┐   │   │  ┌──────────▼──────────┐ ││
│  │  │  LLM 适配层       │   │   │  │  Guardian 守护       │ ││
│  │  │  (OpenAI 协议)    │   │   │  └──────────┬──────────┘ ││
│  │  └──────────────────┘   │   │             │             ││
│  │  ┌──────────────────┐   │   │  ┌──────────▼──────────┐ ││
│  │  │  家长看板 (Web)    │   │   │  │  Monitor 监控 Agent  │ ││
│  │  └──────────────────┘   │   │  └──────────┬──────────┘ ││
│  └──────────────────────────┘   │             │ 触发        ││
│                                  │  ┌──────────▼──────────┐ ││
│                                  │  │  Quiz 答题 UI (WPF)  │ ││
│                                  │  └─────────────────────┘ ││
│                                  └──────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块清单

| # | 模块 | 位置 | 技术栈 | 职责 |
|---|------|------|--------|------|
| 1 | Backend API | Debian | FastAPI + SQLAlchemy | 设备注册、心跳、数据存储、规则匹配、答题下发 |
| 2 | Database | Docker | PostgreSQL 16 | 持久化数据 |
| 3 | Cache | Docker | Redis 7 | 任务缓存、会话状态 |
| 4 | LLM Adapter | Backend | httpx | OpenAI 协议适配，本地/云端模型统一接入 |
| 5 | Parent Dashboard | Backend 内嵌 | Jinja2 + Chart.js | 家长查看报表、配置规则 |
| 6 | Windows Service | Windows | C# .NET 8 | 进程总管、协调所有子进程 |
| 7 | Hook DLL | Windows | C++/CLI | 键盘/鼠标钩子、任务管理器拦截 |
| 8 | Guardian | Windows | C# .NET 8 | 守护进程 |
| 9 | Monitor | Windows | C# .NET 8 | 窗口监控、时长统计 |
| 10 | Quiz UI | Windows | WPF .NET 8 | 答题交互、UI 强制 |
| 11 | Tray | Windows | WPF .NET 8 | 系统托盘、家长快捷入口 |
| 12 | Installer | Windows | Inno Setup | 客户端打包部署 |

---

## 3. 后端架构

### 3.1 数据模型（核心）

#### Family（家庭）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| name | str | 家庭名称 |
| created_at | datetime | 创建时间 |

#### Member（成员）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| family_id | FK | 所属家庭 |
| name | str | 显示名（"小明"） |
| role | enum | parent / child |
| grade | int | 年级（1-12），用于出题难度 |
| windows_username | str | Windows 登录账号（用于自动匹配） |
| avatar | str | 头像 URL |

#### Device（设备）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| family_id | FK | 所属家庭 |
| member_id | FK, nullable | 当前登录成员（动态） |
| name | str | 设备显示名（"客厅台式机"） |
| device_type | enum | windows / android |
| device_id | str | 客户端生成的 UUID |
| computer_model | str | 电脑型号（Agent 自动采集） |
| api_key | str | 鉴权密钥 |
| last_seen | datetime | 最后心跳时间 |
| online | bool | 是否在线 |

#### Rule（规则）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| member_id | FK | 所属成员 |
| name | str | 规则名称 |
| match_key | str | 匹配键 `<username>@<model>`，支持通配符 |
| match_priority | int | 优先级，数字越大越优先 |
| daily_limit_minutes | int | 每日总限额 |
| weekday_limit_minutes | int | 工作日限额 |
| weekend_limit_minutes | int | 周末限额 |
| bedtime_start | time | 就寝开始 |
| bedtime_end | time | 就寝结束（可跨夜） |
| monitored_apps | json | 监控应用列表 |
| blocked_websites | json | 网站黑名单 |
| questions_per_session | int | 每次答题题数 |
| reward_ratio | float | 答对率 × 此系数 = 奖励比例 |
| max_reward_minutes | int | 单次答题最多奖励时长 |
| enabled | bool | 是否启用 |

#### UsageRecord（使用记录）
| 字段 | 类型 | 说明 |
|------|------|------|
| device_id | FK | |
| member_id | FK | |
| app_name | str | |
| window_title | str | |
| start_at, end_at | datetime | |
| duration_seconds | int | |
| is_overtime | bool | 是否发生在超时阶段 |

#### QuizSession（答题会话）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | |
| member_id | FK | |
| device_id | FK | |
| token | str | 答题令牌（防作弊） |
| subject | enum | math / chinese / english / science / mix |
| grade | int | |
| questions | json | 题目内容（含答案，用于判题） |
| answers | json | 孩子提交的答案 |
| score | int | 得分（0-题数） |
| reward_minutes | int | 实际奖励时长 |
| status | enum | pending / completed / expired |
| explanations | text | LLM 生成的解析 |

### 3.2 关键 API

```
POST   /api/v1/agent/register         # 设备首次注册
POST   /api/v1/agent/heartbeat        # 心跳 + 时长上报 + 触发状态查询
POST   /api/v1/agent/usage            # 批量上报使用记录
GET    /api/v1/agent/rule             # 获取当前生效规则
POST   /api/v1/quiz/start             # 开始答题会话
POST   /api/v1/quiz/submit            # 提交答案 + 获取判分 + 奖励
GET    /api/v1/dashboard/summary      # 家长看板聚合数据
GET    /api/v1/dashboard/usage        # 详细使用数据（按天/按应用）
GET    /api/v1/dashboard/quiz         # 答题历史
GET    /api/v1/admin/members          # 成员管理
POST   /api/v1/admin/rules            # 规则管理
```

### 3.3 账号 + 型号 匹配算法

Agent 心跳时上报 `{device_id, windows_username, computer_model, timestamp}`，后端执行：

```python
def resolve_rule(db, device_id, username, model):
    # 1. 找设备
    device = db.get(Device, device_id=...)
    member_id = device.member_id  # 首次注册时绑定

    # 2. 按 username 自动切换成员
    if username != device.last_username:
        member = db.query(Member).filter_by(
            family_id=device.family_id,
            windows_username=username
        ).first()
        if member:
            device.member_id = member.id
            device.last_username = username
            db.commit()

    # 3. 按 (username, model) 匹配规则
    rules = db.query(Rule).filter_by(member_id=member.id).all()
    match_key = f"{username}@{model}"

    # 4. 优先级排序，取最高匹配
    for rule in sorted(rules, key=lambda r: -r.match_priority):
        if fnmatch(match_key, rule.match_key):
            return rule

    # 5. 兜底
    return rules[-1]  # match_key = "*@*"
```

### 3.4 LLM 适配层

支持任意 OpenAI 兼容协议服务：

```python
class LLMClient:
    def __init__(self, base_url, api_key, model):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    async def generate_questions(grade, subject, count):
        # System: 你是友善的小学老师
        # User: 请为 X 年级出 Y 道 Z 学科题...
        # 强制 JSON 输出
        ...

    async def judge_answers(questions, user_answers):
        # 让 LLM 生成鼓励式解析
        ...
```

**降级策略**：LLM 调用失败时，回退到本地题库（每学科预置 50+ 道），保证服务可用。

---

## 4. Windows 客户端架构


### 3.5 出题配置模型（v1.0 增强）

家长对「出什么题」有精细化诉求，必须把出题配置从 Rule 中拆出，独立建模。

#### QuizConfig（出题配置表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| rule_id | FK | 关联的 Rule（一对一） |
| total_questions | int | 总题数，默认 3 |
| difficulty | int | 难度 1-5，默认 3 |
| subjects | json | 学科列表，如 `["math", "chinese"]` |
| distribution | json | 学科分布，如 `{"math": 2, "chinese": 1}` |
| distribution_mode | enum | `manual` / `auto` / `weakness_first` |
| auto_weak_threshold | float | 弱项阈值，准确率 < 此值视为弱项，默认 0.6 |
| weak_subjects | json | 手动指定的弱项学科，覆盖自动计算 |
| updated_at | datetime | |

#### distribution_mode 详解

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| `manual` | 按 distribution 字段精确出题 | 家长想精准控制每次出题 |
| `auto` | 在 subjects 中等概率随机 | 默认，平衡各学科 |
| `weakness_first` | 弱项学科优先出题，剩余随机 | 家长想帮孩子补短板 |

#### 配置示例

```json
{
  "total_questions": 5,
  "difficulty": 3,
  "subjects": ["math", "chinese", "english", "science"],
  "distribution": {"math": 2, "chinese": 1, "english": 1, "science": 1},
  "distribution_mode": "weakness_first",
  "auto_weak_threshold": 0.6
}
```

#### 出题流程调整

```
原流程：Quiz Start → LLM.generate(grade, subject, count)
新流程：Quiz Start → 加载 QuizConfig → 计算实际 distribution →
        按学科分批调 LLM.generate(grade, subject, count) →
        合并题目
```

#### 题目难度说明

- 1：基础（小学低年级 / 课内基础）
- 2：标准（小学中年级 / 课内练习）
- 3：进阶（小学高年级 / 课内拔高）
- 4：挑战（初中衔接 / 奥数基础）
- 5：竞赛（奥数中级 / 学科竞赛）

LLM prompt 中显式要求「难度等级 X，匹配 X 年级平均水平」。

### 3.6 弱项分析服务（v1.0 新增）

#### SubjectMastery 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| member_id | FK | |
| subject | str | math / chinese / ... |
| total_answered | int | 历史答题总数 |
| total_correct | int | 历史答对总数 |
| accuracy | float | 0-1 准确率 |
| last_quiz_at | datetime | 最后答题时间 |
| is_weak | bool | 是否弱项（accuracy < 阈值） |
| updated_at | datetime | |

#### 计算逻辑

```python
def update_mastery(db, member_id, subject):
    # 1. 聚合该成员该学科最近 30 天答题数据
    sessions = db.query(QuizSession).filter(
        QuizSession.member_id == member_id,
        QuizSession.created_at >= now - timedelta(days=30),
        QuizSession.status == 'completed',
    ).all()
    
    total = 0
    correct = 0
    for s in sessions:
        # questions: [{subject, is_correct}]
        for q in s.questions:
            if q.subject == subject:
                total += 1
                if q.is_correct:
                    correct += 1
    
    accuracy = correct / total if total > 0 else 1.0
    is_weak = accuracy < 0.6 and total >= 10
    
    mastery = db.get(SubjectMastery, member_id=member_id, subject=subject)
    mastery.accuracy = accuracy
    mastery.total_answered = total
    mastery.total_correct = correct
    mastery.is_weak = is_weak
    mastery.updated_at = now
    db.commit()
```

#### 触发时机

- 每次 `quiz/submit` API 完成后，异步触发对应学科的 mastery 更新
- Dashboard 加载时，如果数据超过 1 小时未更新则触发一次

### 3.7 LLM 智能建议（v1.0 新增）

家长希望「让 LLM 基于孩子的真实数据给建议」，降低手动调参成本。

#### Suggestion 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| member_id | FK | |
| type | enum | `limit` / `subjects` / `difficulty` / `encouragement` / `schedule` |
| title | str | 建议标题，如「建议提高数学题比例」 |
| content | text | 建议详细说明 |
| evidence | json | 触发该建议的数据依据 |
| confidence | float | LLM 自评置信度 0-1 |
| status | enum | `pending` / `accepted` / `rejected` / `applied` |
| generated_at | datetime | 生成时间 |
| resolved_at | datetime | 处理时间 |

#### 建议类型详解

| type | 示例 | 触发条件 |
|------|------|----------|
| `limit` | 「小明本周 3 次超时，建议将每日限额从 90 → 75 分钟」 | 7 天内超额 ≥ 3 次 |
| `subjects` | 「数学准确率仅 35%，建议提高数学题比例」 | 弱项自动检测 |
| `difficulty` | 「最近答题正确率持续 > 85%，建议难度从 3 → 4」 | 简单题正确率过高 |
| `encouragement` | 「小明本周答题 5 次全对，可以给他发一段鼓励语」 | 表现优秀 |
| `schedule` | 「小明晚上 8-9 点最专注，建议允许这个时段延长 20 分钟」 | 使用时段分析 |

#### 生成 API

```http
POST /api/v1/suggestions/generate
Body: {"member_id": 1, "lookback_days": 7}
Response: {
  "suggestions": [
    {
      "type": "subjects",
      "title": "数学准确率较低，建议专项练习",
      "content": "近 7 天数学答题 12 道，答对 4 道，正确率 33%。建议在 QuizConfig 中将数学题比例从 25% 提升至 50%。",
      "evidence": {
        "subject": "math",
        "accuracy": 0.33,
        "sample_size": 12
      },
      "confidence": 0.85
    }
  ]
}
```

#### LLM Prompt 模板（建议生成）

```text
你是一位家庭教育顾问。请基于以下数据，为孩子「{name}」（{grade} 年级）生成 3-5 条可操作的建议。

【使用时长数据】
本周每日平均使用时长：{daily_avg} 分钟
本周超时次数：{overtime_count}
最常用应用 Top 3：{top_apps}

【答题表现】
各学科准确率（近 30 天）：
{mastery_table}

【当前规则】
每日限额：{daily_limit} 分钟
出题配置：{quiz_config}

【历史建议】（避免重复）
{previous_suggestions}

要求：
1. 建议必须基于数据，不要泛泛而谈
2. 给出可执行的修改（如「建议将数学题数从 1 增加到 3」）
3. 包含积极正面的鼓励
4. 返回严格 JSON，结构按 Suggestion schema
```

#### 建议应用流程

```
家长在 Dashboard 看到建议（带证据数据）
  ↓
家长可操作：
  - 一键应用 → 后端自动修改 Rule / QuizConfig
  - 修改后应用 → 弹出表单让家长微调
  - 拒绝 → 标记 rejected，记录原因
  - 稍后提醒 → 7 天后再推送
```

### 3.8 更新后的出题 API（v1.0）

#### POST /api/v1/quiz/start

```http
Request:
{
  "device_id": "uuid",
  "subject": null  // 可选：null 表示按 QuizConfig 自动分布
}

Response:
{
  "token": "...",
  "questions": [
    {"id": 0, "subject": "math", "grade": 4, "question": "...", "options": [...], "difficulty": 3},
    ...
  ],
  "config_used": {  // 实际使用的配置（家长可见）
    "distribution": {"math": 2, "chinese": 1},
    "difficulty": 3,
    "mode": "weakness_first"
  },
  "expires_in": 600
}
```

### 3.9 Dashboard 新增 API

```
GET    /api/v1/dashboard/mastery           # 学科掌握度雷达图数据
GET    /api/v1/dashboard/suggestions       # 当前活跃建议列表
POST   /api/v1/suggestions/generate        # 手动触发 LLM 建议生成
POST   /api/v1/suggestions/{id}/apply      # 应用建议
POST   /api/v1/suggestions/{id}/reject     # 拒绝建议
GET    /api/v1/admin/quiz-config/{rule_id} # 获取出题配置
PUT    /api/v1/admin/quiz-config/{rule_id} # 更新出题配置
```



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
  {"match_type": "process", "pattern": "(?i)(steam|epicgames|minecraft|riot|wegame|valve)\.exe$", "category": "game_native", "action": "monitor"},
  {"match_type": "process", "pattern": "(?i)(chrome|msedge|firefox)\.exe$", "category": "browser", "action": "monitor"},
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


### 4.1 进程拓扑

```text
                    ┌──────────────────────────┐
                    │  SCM (Service Control    │
                    │   Manager) 系统级托管     │
                    └────────────┬─────────────┘
                                 │ 启动/监控/恢复
                                 ▼
                    ┌──────────────────────────┐
                    │ FamilySafetyService      │
                    │  (Windows Service)       │
                    │  - 最高权限 SYSTEM       │
                    │  - 协调所有子进程        │
                    │  - 上报心跳              │
                    │  - 失败自动重启          │
                    └─────┬────┬────┬─────────┘
                          │    │    │
              启动并互守   │    │    │  启动
                          ▼    ▼    ▼
                ┌─────┐  ┌─────┐  ┌─────┐
                │Tray │  │Guard│  │Mon  │
                │     │  │ian  │  │itor │
                └─────┘  └──┬──┘  └──┬──┘
                          ▲ │      │
                          │ │      │ 检测到超时
                          │ ▼      ▼
                          │   ┌─────┐
                          │   │Quiz │
                          │   │ UI  │
                          │   └─────┘
                          │
                  反 taskkill 互相拉起
```

### 4.2 七层进程守护

| 层 | 防御对象 | 实现技术 |
|----|---------|---------|
| L1 UI 强制 | 用户直接操作 | WPF 全屏窗口 + 钩子禁用 Win/Alt+Tab |
| L2 双进程互守 | taskkill / 任务管理器结束 | Guardian ↔ Monitor 互相拉起 |
| L3 服务化 | 普通杀进程 | 注册为 Windows Service（SCM 托管） |
| L4 任务计划 | 禁用服务 | Task Scheduler 兜底，每分钟检查服务 |
| L5 注册表 | 禁用自启 | Run 键 + WMI 事件订阅 |
| L6 文件保护 | 删除 exe | NTFS ACL + 安装目录完整性校验 |
| L7 权限隔离 | 进安全模式删文件 | 孩子账号设为 Standard User，无管理员权限 |

### 4.3 进程互守协议

```csharp
// 互守通过共享内存 + 命名事件 实现
class ProcessSupervisor
{
    void StartWatched(string exePath)
    {
        var proc = Process.Start(exePath);
        proc.EnableRaisingEvents = true;
        proc.Exited += (s, e) =>
        {
            if (!_shuttingDown)
            {
                Log.Warn($"{proc.ProcessName} 意外退出，重启");
                Thread.Sleep(2000);
                StartWatched(exePath);
            }
        };
    }
}
```

### 4.4 UI 强制实现

#### 4.4.1 键盘钩子（FamilySafety.Hooks DLL）

```cpp
// 答题窗口激活时拦截：
//   Win 键、Ctrl+Esc、Alt+F4、Alt+Tab、F11
HHOOK _keyboardHook;

LRESULT CALLBACK LowLevelKeyboardProc(int nCode, WPARAM wParam, LPARAM lParam)
{
    if (nCode == HC_ACTION && IsQuizWindowActive())
    {
        KBDLLHOOKSTRUCT* kb = (KBDLLHOOKSTRUCT*)lParam;
        if (ShouldBlock(kb)) return 1;  // 吞掉事件
    }
    return CallNextHookEx(_keyboardHook, nCode, wParam, lParam);
}
```

#### 4.4.2 任务管理器拦截

```cpp
// 通过 WH_CALLWNDPROC 全局钩子 + 定时检查 taskmgr.exe
// 思路：自家进程被 taskmgr 选中时，定时切换到前台夺回焦点
// 配合 SetForegroundWindow + FlashWindow
```

#### 4.4.3 家长密码解锁

```csharp
// 所有"退出 / 暂停 / 修改设置"操作必须输入家长密码
// 密码 PBKDF2 哈希存储在 config.json
// 服务端不存家长密码（隐私考虑）
bool VerifyParentPassword(string input)
{
    var hash = PBKDF2(input, salt);
    return hash == _config.ParentPasswordHash;
}
```

### 4.5 数据流（孩子视角）

```text
1. 孩子开机 → Windows 启动 → Service 自动启动 → Monitor 启动
2. Monitor 每 5 秒查询前台窗口 → 命中游戏 → 累加时长
3. 心跳每 15 秒发往后端 → 后端返回最新规则、是否超额
4. 累计超过限额 → Monitor 触发 Quiz 进程 → Quiz 全屏弹出
5. Quiz 显示题目 → 孩子作答 → 提交答案 → 后端判分 + LLM 解析
6. 得分 → 兑换奖励时长 → 后端下发"剩余 X 分钟"指令
7. 时间到 → Quiz 自动关闭 / 显示"再玩 X 分钟即将超时"
```

### 4.6 配置下发

后端 → Agent 通过心跳响应下发增量配置：

```json
{
  "rule": {
    "daily_limit_minutes": 90,
    "monitored_apps": ["steam.exe", "..."],
    "questions_per_session": 3,
    "max_reward_minutes": 20
  },
  "commands": [
    { "type": "force_quiz", "reason": "overtime" },
    { "type": "lock_screen" },
    { "type": "show_warning", "message": "..." }
  ]
}
```

---

## 5. 安全与隐私

### 5.1 数据存储

| 数据 | 存储位置 | 加密 |
|------|---------|------|
| 使用记录 | 本地 + 后端 | TLS 传输，不加密存储（v1.0） |
| 答题内容 | 后端 | TLS |
| 家长密码 | Agent 本地 | PBKDF2 哈希 |
| API Key | Agent + 后端 | 明文（设备级，不暴露用户密码） |

### 5.2 通信

- 后端启用 HTTPS（生产）
- Agent 与后端使用 Bearer Token（api_key）
- 所有 API 走 POST，参数最小化

### 5.3 隐私原则

- **不上传家长密码**到后端
- **不上传截屏**（v1.0 不做）
- **不上传应用内容**，仅上报窗口标题（可配置脱敏）

---

## 6. 部署架构

### 6.1 后端（Debian + Docker）

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
  backend:
    build: ./backend
    depends_on: [postgres, redis]
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://...
      LLM_BASE_URL: ${LLM_BASE_URL}
      LLM_API_KEY: ${LLM_API_KEY}
```

### 6.2 客户端（Windows）

- Inno Setup 打包为 `FamilySafety-Setup-1.0.0.exe`
- 默认安装到 `C:\Program Files\FamilySafety\`
- 安装时自动：
  - 创建 Windows Service
  - 设置开机自启
  - 创建家长账号（首次启动要求设置密码）
  - 调用后端 `/agent/register` 注册

---

## 7. 扩展性预留

### 7.1 Android Agent（v2.0）

- 数据模型已包含 `device_type: android`
- Rule 模型已包含 `match_key`，可直接复用
- 需要开发 Kotlin Agent + AccessibilityService
- 通信协议与 Windows Agent 一致

### 7.2 多家长协同（v1.1）

- Family 模型可关联多个 Member(role=parent)
- 规则修改需要任一家长确认

### 7.3 AI 行为分析（v2.0）

- LLM 适配层已就绪
- 数据基础（UsageRecord）已就绪
- 未来可加：
  - 检测异常使用模式
  - 生成周报给家长
  - 推送教育建议

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| 国产杀软误杀 Service | 服务被拦截 | 申请数字签名证书（v1.1） |
| 孩子进 PE 系统绕过 | 物理级绕过 | L7 权限隔离 + BIOS 密码（家庭协商） |
| 后端宕机 | 时长统计丢失 | Agent 本地缓存 + 重传队列 |
| LLM API 限流 | 答题失败 | 本地题库兜底 + 多 Key 轮换 |
| 多孩子切换账号漏洞 | 切换到无规则账号 | 强制要求未匹配账号使用默认规则（最严格） |

---

## 9. 开发规范

- **Git Flow**：main / feature / hotfix
- **版本号**：Semantic Versioning
- **API 文档**：FastAPI 自动 OpenAPI + 手动维护 `docs/api.md`
- **日志**：后端用 loguru 写 JSON，Agent 用 Serilog 写结构化日志
- **测试**：后端 pytest，Agent xUnit + 集成测试

---

## 10. 里程碑

| 版本 | 时间 | 范围 |
|------|------|------|
| v0.1 | 第 1 周 | 后端 FastAPI 骨架 + 设备注册 + 心跳 |
| v0.2 | 第 2 周 | LLM 出题 + 答题 API + 本地题库兜底 |
| v0.3 | 第 3 周 | Windows Service + Monitor + 基础守护 |
| v0.4 | 第 4 周 | Guardian + Quiz UI（基础版，无强制） |
| v0.5 | 第 5 周 | Hook DLL（键盘钩子 + 任务管理器拦截） |
| v0.6 | 第 6 周 | 家长看板 + 规则管理 |
| v0.7 | 第 7 周 | Installer 打包 + 部署文档 |
| v1.0 | 第 8 周 | 全功能 E2E 测试 + 发布 |

---

**附录**：本文档随实现进展持续更新，关键决策变更需在团队内 review。