"""Prompt templates for all LLM-backed features.

Keep prompts in this file so they are easy to iterate and version.
"""

from typing import Any


SUBJECT_LABELS: dict[str, str] = {
    "math": "数学",
    "chinese": "语文",
    "english": "英语",
    "science": "科学",
}


# ============ Question generation ============

QUESTION_SYSTEM = (
    "你是一位为 {grade} 年级学生编写练习题的小学老师。\n"
    "- 题目要贴近课本和生活\n"
    "- 每道题有 4 个选项 (A/B/C/D)\n"
    "- 难度等级: {difficulty} (1=基础, 2=标准, 3=进阶, 4=挑战, 5=竞赛)\n"
    "- 必须输出严格的 JSON, 不要任何额外文字"
)

QUESTION_USER_TPL = (
    "请为 {grade} 年级学生出 {count} 道「{subject_label}」题。\n"
    "难度等级: {difficulty}/5\n"
    "{weakness_hint}\n"
    "\n"
    "请严格返回如下 JSON 结构:\n"
    "{{\n"
    '  "questions": [\n'
    "    {{\n"
    '      "id": 0,\n'
    '      "subject": "{subject}",\n'
    '      "grade": {grade},\n'
    '      "difficulty": {difficulty},\n'
    '      "question": "题干",\n'
    '      "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],\n'
    '      "answer": "A",\n'
    '      "explanation": "简要解析"\n'
    "    }}\n"
    "  ]\n"
    "}}"
)


def build_question_messages(
    grade: int,
    subject: str,
    count: int,
    difficulty: int = 3,
    is_weak: bool = False,
) -> list[dict[str, str]]:
    """Build chat messages for generating questions."""
    subject_label = SUBJECT_LABELS.get(subject, subject)
    weakness_hint = ""
    if is_weak:
        weakness_hint = (
            f"⚠️ 这是该学生的弱项学科，请多出基础题和典型例题，并在解析中给出详细步骤。"
        )
    user = QUESTION_USER_TPL.format(
        grade=grade,
        count=count,
        subject=subject,
        subject_label=subject_label,
        difficulty=difficulty,
        weakness_hint=weakness_hint,
    )
    system = QUESTION_SYSTEM.format(grade=grade, difficulty=difficulty)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ============ Answer judging ============

JUDGE_SYSTEM = "你是一位善于鼓励学生的小学老师，正在批改学生的作业。"

JUDGE_USER_TPL = (
    "请批改以下 {grade} 年级学生的答题，并给出每道题的反馈。\n"
    "\n"
    "【题目】\n{questions_block}\n"
    "\n"
    "【学生答案】\n{answers_block}\n"
    "\n"
    "请严格返回如下 JSON:\n"
    "{{\n"
    '  "results": [\n'
    "    {{\n"
    '      "question_id": 0,\n'
    '      "is_correct": true,\n'
    '      "correct_answer": "A",\n'
    '      "student_answer": "B",\n'
    '      "feedback": "答对啦! ..." 或 "哎呀, 正确答案是 A, 因为 ..."'
    "    }}\n"
    "  ],\n"
    '  "overall_feedback": "整体表现 ..."\n'
    "}}"
)


def build_judge_messages(
    grade: int,
    questions: list[dict[str, Any]],
    answers: dict[int, str],
) -> list[dict[str, str]]:
    """Build chat messages for judging answers."""
    q_lines = []
    for q in questions:
        opts = "\n      ".join(q.get("options", []))
        q_lines.append(
            f"题目 {q['id'] + 1}: {q['question']}\n"
            f"      选项:\n      {opts}\n"
            f"      正确答案: {q.get('answer', '?')}"
        )
    a_lines = [
        f"题目 {qid + 1}: {choice}" for qid, choice in sorted(answers.items())
    ]

    user = JUDGE_USER_TPL.format(
        grade=grade,
        questions_block="\n\n".join(q_lines),
        answers_block="\n".join(a_lines) or "(学生未作答)",
    )
    return [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": user},
    ]


# ============ Weekly report ============

WEEKLY_REPORT_SYSTEM = (
    "你是一位温暖、专业的青少年家庭教育顾问。\n"
    "- 客观但不冷漠，避免制造焦虑\n"
    "- 用数据说话，不要泛泛而谈\n"
    "- 给出可执行的下周建议\n"
    "- 适当鼓励家长和孩子"
)

WEEKLY_REPORT_USER_TPL = (
    "请基于「{name}」({grade} 年级)本周的数据撰写一份家长周报。\n"
    "\n"
    "【使用时长】\n"
    "- 本周总时长: {total_minutes} 分钟\n"
    "- 较上周变化: {delta_minutes:+d} 分钟\n"
    "- 超时次数: {overtime_count}\n"
    "- 最常用应用 Top 5: {top_apps}\n"
    "\n"
    "【内容分类占比】\n{category_breakdown}\n"
    "\n"
    "【答题表现】\n"
    "- 本周答题: {quiz_count} 次, 共 {quiz_questions} 道\n"
    "- 总正确率: {overall_accuracy:.0%}\n"
    "- 各学科: {by_subject}\n"
    "\n"
    "【弱项学科】 {weak_subjects}\n"
    "【毒视频告警】 {toxic_alerts}\n"
    "\n"
    "请输出 HTML 邮件正文 (500-800 字中文)，结构:\n"
    "<h2>本周总评</h2>\n"
    "<h3>使用时长</h3>\n"
    "<h3>内容分布</h3>\n"
    "<h3>学习表现</h3>\n"
    "<h3>下周建议</h3>\n"
    "<p>家长加油语</p>\n"
    "\n"
    "要求: 只输出 HTML, 不要 markdown, 不要编造数据。"
)


def build_weekly_report_messages(
    name: str,
    grade: int,
    total_minutes: int,
    delta_minutes: int,
    overtime_count: int,
    top_apps: list[dict[str, Any]],
    category_breakdown: dict[str, int],
    quiz_count: int,
    quiz_questions: int,
    overall_accuracy: float,
    by_subject: dict[str, float],
    weak_subjects: list[str],
    toxic_alerts: int,
) -> list[dict[str, str]]:
    """Build chat messages for generating weekly report."""
    cb = "\n".join(f"- {k}: {v} 分钟" for k, v in category_breakdown.items())
    apps = ", ".join(f"{a['app']} ({a['minutes']}分)" for a in top_apps[:5])
    bs = ", ".join(f"{k} ({v:.0%})" for k, v in by_subject.items()) or "无数据"
    weak = ", ".join(weak_subjects) or "无"

    user = WEEKLY_REPORT_USER_TPL.format(
        name=name,
        grade=grade,
        total_minutes=total_minutes,
        delta_minutes=delta_minutes,
        overtime_count=overtime_count,
        top_apps=apps or "无",
        category_breakdown=cb or "无数据",
        quiz_count=quiz_count,
        quiz_questions=quiz_questions,
        overall_accuracy=overall_accuracy,
        by_subject=bs,
        weak_subjects=weak,
        toxic_alerts=toxic_alerts,
    )
    return [
        {"role": "system", "content": WEEKLY_REPORT_SYSTEM},
        {"role": "user", "content": user},
    ]


# ============ Suggestions ============

SUGGESTION_SYSTEM = (
    "你是一位青少年家庭教育顾问。基于真实数据给出可操作的建议，不要泛泛而谈。"
)

SUGGESTION_USER_TPL = (
    "请为「{name}」({grade} 年级)生成 3-5 条家庭教育建议。\n"
    "\n"
    "【使用数据 (最近 {lookback_days} 天)】\n"
    "- 每日平均: {daily_avg_minutes} 分钟\n"
    "- 超时次数: {overtime_count}\n"
    "- Top 3 应用: {top_apps}\n"
    "\n"
    "【答题 (最近 30 天)】\n"
    "{mastery_table}\n"
    "\n"
    "【当前规则】\n"
    "- 限额: {daily_limit} 分钟\n"
    "- 出题配置: {quiz_config_str}\n"
    "\n"
    "【历史建议 (避免重复)】\n{previous_suggestions}\n"
    "\n"
    "请返回 JSON:\n"
    "{{\n"
    '  "suggestions": [\n'
    "    {{\n"
    '      "type": "limit|subjects|difficulty|encouragement|schedule",\n'
    '      "title": "一句话标题",\n'
    '      "content": "详细说明 (含具体数字)",\n'
    '      "evidence": {{}},\n'
    '      "confidence": 0.85\n'
    "    }}\n"
    "  ]\n"
    "}}"
)


def build_suggestion_messages(
    name: str,
    grade: int,
    lookback_days: int,
    daily_avg_minutes: float,
    overtime_count: int,
    top_apps: list[dict[str, Any]],
    mastery: dict[str, dict[str, Any]],
    daily_limit: int,
    quiz_config: dict[str, Any],
    previous_suggestions: list[str],
) -> list[dict[str, str]]:
    table_lines = [
        f"- {subj}: 正确率 {m.get('accuracy', 0):.0%} (样本 {m.get('total', 0)})"
        for subj, m in mastery.items()
    ]
    apps = ", ".join(f"{a['app']} ({a['minutes']}分)" for a in top_apps[:3])
    cfg_str = (
        f"学科: {quiz_config.get('subjects')}, "
        f"分布: {quiz_config.get('distribution')}, "
        f"模式: {quiz_config.get('distribution_mode')}"
    )
    prev = "\n".join(f"- {s}" for s in previous_suggestions[-5:]) or "无"

    user = SUGGESTION_USER_TPL.format(
        name=name,
        grade=grade,
        lookback_days=lookback_days,
        daily_avg_minutes=daily_avg_minutes,
        overtime_count=overtime_count,
        top_apps=apps or "无",
        mastery_table="\n".join(table_lines) or "无数据",
        daily_limit=daily_limit,
        quiz_config_str=cfg_str,
        previous_suggestions=prev,
    )
    return [
        {"role": "system", "content": SUGGESTION_SYSTEM},
        {"role": "user", "content": user},
    ]


# ============ Toxic content judging ============

TOXIC_JUDGE_SYSTEM = (
    "你是一位青少年内容审核专家，专注于识别不适宜内容。\n"
    "需要识别: 自残/自杀, 血腥/暴力, 色情/低俗, 赌博引流, 炫富, 价值观扭曲。"
)

TOXIC_JUDGE_USER_TPL = (
    "请判断以下内容是否属于「青少年不宜」。\n"
    "\n"
    "【当前应用】 {app_name}\n"
    "【当前窗口标题】 {window_title}\n"
    "【最近 5 分钟浏览历史】\n{history_block}\n"
    "\n"
    "请返回 JSON:\n"
    "{{\n"
    '  "is_toxic": true,\n'
    '  "category": "self_harm|violence|adult|gambling|other",\n'
    '  "confidence": 0.85,\n'
    '  "reason": "为什么这样判断"\n'
    "}}\n"
    "仅当置信度 >= 0.6 时返回 is_toxic=true。"
)


def build_toxic_judge_messages(
    app_name: str,
    window_title: str,
    recent_history: list[str],
) -> list[dict[str, str]]:
    hist = "\n".join(f"  - {t}" for t in recent_history[-5:]) or "  - (无)"
    user = TOXIC_JUDGE_USER_TPL.format(
        app_name=app_name,
        window_title=window_title,
        history_block=hist,
    )
    return [
        {"role": "system", "content": TOXIC_JUDGE_SYSTEM},
        {"role": "user", "content": user},
    ]
