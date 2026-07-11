"""P2 Module 1: LLM client + prompts + fallback bank + question generator."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend")


def write(rel: str, content: str) -> None:
    target = BACKEND / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {rel} ({len(content)} bytes)")


# ============ LLM client ============
write("app/llm/__init__.py", "")
write("app/llm/client.py", """"""Unified LLM client supporting any OpenAI-compatible endpoint.

Used for:
  - generate_questions (lesson quizzes)
  - judge_answers (scoring + explanations)
  - generate_weekly_report (parent digest)
  - generate_suggestions (parent advice)
  - judge_toxic_content (content safety check)
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
from loguru import logger

from app.core.config import get_settings

settings = get_settings()


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout_seconds

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        response_format_json: bool = False,
        max_retries: int = 2,
    ) -> str:
        """Send chat completion request. Returns raw text content.

        Raises LLMError on persistent failure.
        """
        if not self.api_key:
            raise LLMError("LLM_API_KEY is not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.base_url}/chat/completions"
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return content.strip() if content else ""
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                last_exc = e
                logger.warning(f"LLM call attempt {attempt} failed: {e}")
                await asyncio.sleep(2 ** (attempt - 1))

        raise LLMError(f"LLM call failed after {max_retries} retries: {last_exc}")

    @staticmethod
    def parse_json_response(text: str) -> Any:
        """Robustly extract JSON from an LLM response."""
        text = text.strip()
        # Try direct
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try fenced code block
        m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # Try last { ... } block
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        raise LLMError(f"Could not parse JSON from LLM response: {text[:200]}")


# ============ Prompts ============
write("app/llm/prompts.py', '"""Prompt templates for all LLM-backed features.

Keep all prompts in this file so it's easy to iterate and version them.
"""

QUESTION_SYSTEM = """你是一位为 {grade} 年级学生编写练习题的小学老师。
- 题目要贴近课本和生活
- 每道题有 4 个选项（A/B/C/D）
- 难度等级：{difficulty}（1=基础，2=标准，3=进阶，4=挑战，5=竞赛）
- 必须输出严格的 JSON，不要任何额外文字"""

QUESTION_USER = """请为 {grade} 年级学生出 {count} 道「{subject_label}」题。
难度等级：{difficulty}/5
{weakness_hint}

请严格返回如下 JSON 结构（不要 markdown 包裹）：
{{
  "questions": [
    {{
      "id": 0,
      "subject": "{subject}",
      "grade": {grade},
      "difficulty": {difficulty},
      "question": "题干",
      "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
      "answer": "A",
      "explanation": "简要解析"
    }}
  ]
}}"""


JUDGE_SYSTEM = """你是一位善于鼓励学生的小学老师，正在批改学生的作业。"""

JUDGE_USER = """请批改以下 {grade} 年级学生的答题，并给出每道题的反馈。

题目：
{questions_block}

学生答案：
{answers_block}

请严格返回如下 JSON（不要 markdown 包裹）：
{{
  "results": [
    {{
      "question_id": 0,
      "is_correct": true,
      "correct_answer": "A",
      "student_answer": "B",
      "feedback": "答对啦！这道题考察了 ..."/哎呀，正确答案是 A，因为 ..."
    }}
  ],
  "overall_feedback": "整体表现非常棒！你掌握得最棒的是 X，要继续加油的是 Y ..."
}}"""


WEEKLY_REPORT_SYSTEM = """你是一位温暖、专业的青少年家庭教育顾问。
- 客观但不冷漠，避免制造焦虑
- 用数据说话，不要泛泛而谈
- 给出可执行的下周建议
- 适当鼓励家长和孩子"""

WEEKLY_REPORT_USER = """请基于「{name}」（{grade} 年级）本周的数据撰写一份家长周报。

【使用时长】
- 本周总时长：{total_minutes} 分钟
- 较上周变化：{delta_minutes:+d} 分钟
- 超时次数：{overtime_count}
- 最常用应用 Top 5：{top_apps}

【内容分类占比】
{category_breakdown}

【答题表现】
- 本周答题：{quiz_count} 次，共 {quiz_questions} 道题
- 总正确率：{overall_accuracy:.0%}
- 各学科正确率：{by_subject}

【弱项学科】
{weak_subjects}

【毒视频告警】
{toxic_alerts}

请输出严格的 HTML 邮件正文（约 500-800 字中文），结构如下：

<h2>本周总评</h2>
<p>...</p>

<h3>使用时长</h3>
<p>...</p>

<h3>内容分布</h3>
<p>...</p>

<h3>学习表现</h3>
<p>...</p>

<h3>下周建议</h3>
<ol>
  <li>...</li>
  <li>...</li>
  <li>...</li>
</ol>

<p>家长加油语：...</p>

要求：
- 只输出 HTML，不要 markdown
- 不要编造数据，所有数字必须与上文一致
"""


SUGGESTION_SYSTEM = """你是一位青少年家庭教育顾问。基于真实数据给出可操作的建议，不要泛泛而谈。"""

SUGGESTION_USER = """请为「{name}」（{grade} 年级）生成 3-5 条家庭教育建议，每条建议必须是数据驱动的。

【使用数据（最近 {lookback_days} 天）】
- 每日平均时长：{daily_avg_minutes} 分钟
- 超时次数：{overtime_count}
- 最常用应用 Top 3：{top_apps}

【答题数据（最近 30 天）】
各学科准确率：
{mastery_table}

【当前规则】
- 每日限额：{daily_limit} 分钟
- 出题配置：{quiz_config_str}

【历史建议（避免重复）】
{previous_suggestions}

请严格返回如下 JSON（不要 markdown 包裹）：
{{
  "suggestions": [
    {{
      "type": "limit|subjects|difficulty|encouragement|schedule",
      "title": "一句话标题",
      "content": "详细说明（含具体数字）",
      "evidence": {{}},
      "confidence": 0.85
    }}
  ]
}}"""


TOXIC_JUDGE_SYSTEM = """你是一位青少年内容审核专家，专注于识别不适宜的内容。
需要识别的类型：
- 自残、自杀
- 血腥、暴力
- 色情、低俗
- 赌博引流
- 炫富、价值观扭曲"""

TOXIC_JUDGE_USER = """请判断以下内容是否属于「青少年不宜」内容。

【当前应用】{app_name}
【当前窗口标题】{window_title}
【最近 5 分钟浏览历史】
{history_block}

请严格返回如下 JSON（不要 markdown 包裹）：
{{
  "is_toxic": true,
  "category": "self_harm|violence|adult|gambling|other",
  "confidence": 0.85,
  "reason": "为什么这样判断"
}}

仅当置信度 ≥ 0.6 时返回 is_toxic=true。"""
""",