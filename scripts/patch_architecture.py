"""Append new sections (3.5 - 3.8) to architecture.md about
quiz config, weakness analysis, LLM suggestions, updated data model.
"""
from pathlib import Path

DOC = Path("E:/codeRepo/familysafety/docs/architecture.md")
text = DOC.read_text(encoding="utf-8")

# Find the section after 3.4 LLM Adapter to insert new sections before 3.5/4
marker = "### 3.4 LLM 适配层"
end_marker = "---"  # the --- separator after LLM section

insertion = """

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

"""

# Insert after "### 3.4 LLM 适配层" section, before the next "###" header
# Strategy: find "### 4. Windows" and insert before it
import re

# Find the next "### 4." section
m = re.search(r"\n### 4\.", text)
if m:
    insert_pos = m.start()
    new_text = text[:insert_pos] + insertion + "\n" + text[insert_pos:]
    DOC.write_text(new_text, encoding="utf-8")
    print(f"  appended {len(insertion)} bytes to architecture.md")
    print(f"  new size: {len(new_text)} bytes (was {len(text)})")
else:
    print("ERROR: Could not find '### 4.' marker")