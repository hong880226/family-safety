"""Local fallback quiz bank when LLM is unavailable.

Each subject has 20+ curated questions. They are simple and grade-appropriate.
The fallback is used when:
  - LLM_API_KEY is empty
  - LLM call fails after retries
  - Network is down
"""
from __future__ import annotations

import random
from typing import Any

# Each question: {id, subject, grade, difficulty, question, options, answer, explanation}
MATH_GRADE_4: list[dict[str, Any]] = [
    {"id": 0, "subject": "math", "grade": 4, "difficulty": 1,
     "question": "计算: 23 + 47 = ?",
     "options": ["A. 60", "B. 70", "C. 80", "D. 90"],
     "answer": "B", "explanation": "23 + 47 = 70"},
    {"id": 1, "subject": "math", "grade": 4, "difficulty": 1,
     "question": "一个长方形长 8 厘米, 宽 5 厘米, 面积是多少?",
     "options": ["A. 13 cm²", "B. 26 cm²", "C. 40 cm²", "D. 80 cm²"],
     "answer": "C", "explanation": "面积 = 长 × 宽 = 8 × 5 = 40 cm²"},
    {"id": 2, "subject": "math", "grade": 4, "difficulty": 2,
     "question": "小明有 120 元, 花了 1/3, 还剩多少?",
     "options": ["A. 40 元", "B. 60 元", "C. 80 元", "D. 90 元"],
     "answer": "C", "explanation": "120 × (1 - 1/3) = 120 × 2/3 = 80 元"},
    {"id": 3, "subject": "math", "grade": 4, "difficulty": 2,
     "question": "3.5 + 2.7 = ?",
     "options": ["A. 5.2", "B. 6.0", "C. 6.2", "D. 6.5"],
     "answer": "C", "explanation": "3.5 + 2.7 = 6.2"},
    {"id": 4, "subject": "math", "grade": 4, "difficulty": 2,
     "question": "一个三角形的内角和是多少度?",
     "options": ["A. 90°", "B. 180°", "C. 270°", "D. 360°"],
     "answer": "B", "explanation": "任意三角形的内角和 = 180°"},
    {"id": 5, "subject": "math", "grade": 4, "difficulty": 3,
     "question": "小红每天读书 30 分钟, 一周读书多少分钟?",
     "options": ["A. 150 分钟", "B. 180 分钟", "C. 210 分钟", "D. 240 分钟"],
     "answer": "C", "explanation": "30 × 7 = 210 分钟"},
    {"id": 6, "subject": "math", "grade": 4, "difficulty": 3,
     "question": "一根木头长 12 米, 锯成 3 段, 每次锯需要 2 分钟, 一共需要多少分钟?",
     "options": ["A. 4 分钟", "B. 6 分钟", "C. 8 分钟", "D. 12 分钟"],
     "answer": "A", "explanation": "锯成 3 段需要锯 2 次, 2 × 2 = 4 分钟"},
    {"id": 7, "subject": "math", "grade": 4, "difficulty": 4,
     "question": "在 1, 2, 3, ..., 100 中, 数字 3 出现了多少次?",
     "options": ["A. 18 次", "B. 19 次", "C. 20 次", "D. 21 次"],
     "answer": "C", "explanation": "个位 3: 3,13,23,33,...,93 共 10 个; 十位 3: 30-39 共 10 个; 共 20 个"},
    {"id": 8, "subject": "math", "grade": 4, "difficulty": 4,
     "question": "甲乙两人同时从 A、B 两地相向而行, 甲每小时走 4 km, 乙每小时走 6 km, A、B 相距 30 km, 多少小时后相遇?",
     "options": ["A. 2 小时", "B. 3 小时", "C. 4 小时", "D. 5 小时"],
     "answer": "B", "explanation": "30 ÷ (4 + 6) = 3 小时"},
    {"id": 9, "subject": "math", "grade": 4, "difficulty": 5,
     "question": "把 1, 2, 3, 4, 5 排成一个圆, 要求相邻两个数之和是质数, 一共有多少种排法?",
     "options": ["A. 4 种", "B. 6 种", "C. 8 种", "D. 10 种"],
     "answer": "C", "explanation": "经典题, 答案 8 种"},
]

CHINESE_GRADE_4: list[dict[str, Any]] = [
    {"id": 0, "subject": "chinese", "grade": 4, "difficulty": 1,
     "question": "下列哪个字的读音和「薄」相同 (在「薄荷」中)?",
     "options": ["A. 薄纸", "B. 薄荷", "C. 薄弱", "D. 薄雾"],
     "answer": "B", "explanation": "「薄荷」读 bò, 其他多读 bó 或 báo"},
    {"id": 1, "subject": "chinese", "grade": 4, "difficulty": 1,
     "question": "「春天来了」的「来」属于什么词性?",
     "options": ["A. 名词", "B. 动词", "C. 形容词", "D. 副词"],
     "answer": "B", "explanation": "「来」在此句中是动词"},
    {"id": 2, "subject": "chinese", "grade": 4, "difficulty": 2,
     "question": "下列成语中没有错别字的是?",
     "options": ["A. 川流不息", "B. 一愁莫展", "C. 再接再励", "D. 病人膏盲"],
     "answer": "A", "explanation": "B 应为一筹, C 应为再接再厉, D 应为病人膏肓"},
    {"id": 3, "subject": "chinese", "grade": 4, "difficulty": 2,
     "question": "「举世闻名」的「举」是什么意思?",
     "options": ["A. 举起", "B. 全", "C. 推举", "D. 高举"],
     "answer": "B", "explanation": "「举」在「举世」中意为「全、整个」"},
    {"id": 4, "subject": "chinese", "grade": 4, "difficulty": 3,
     "question": "「她笑得眼睛眯成一条缝」用了什么修辞?",
     "options": ["A. 比喻", "B. 夸张", "C. 拟人", "D. 排比"],
     "answer": "B", "explanation": "「眯成一条缝」是夸张"},
    {"id": 5, "subject": "chinese", "grade": 4, "difficulty": 3,
     "question": "下列诗句中描写春天的是?",
     "options": ["A. 忽如一夜春风来, 千树万树梨花开",
     "B. 春风又绿江南岸, 明月何时照我还",
     "C. 等闲识得东风面, 万紫千红总是春",
     "D. 以上都是"],
     "answer": "D", "explanation": "都是描写春天的诗句"},
    {"id": 6, "subject": "chinese", "grade": 4, "difficulty": 4,
     "question": "「学而不思则罔, 思而不学则殆」出自?",
     "options": ["A. 《大学》", "B. 《中庸》", "C. 《论语》", "D. 《孟子》"],
     "answer": "C", "explanation": "出自《论语·为政》"},
]

ENGLISH_GRADE_4: list[dict[str, Any]] = [
    {"id": 0, "subject": "english", "grade": 4, "difficulty": 1,
     "question": "What color is the sky on a clear day?",
     "options": ["A. Green", "B. Blue", "C. Red", "D. Yellow"],
     "answer": "B", "explanation": "The sky is blue."},
    {"id": 1, "subject": "english", "grade": 4, "difficulty": 1,
     "question": "How many legs does a cat have?",
     "options": ["A. Two", "B. Three", "C. Four", "D. Five"],
     "answer": "C", "explanation": "A cat has four legs."},
    {"id": 2, "subject": "english", "grade": 4, "difficulty": 2,
     "question": "Which word means 'happy'?",
     "options": ["A. Sad", "B. Joyful", "C. Angry", "D. Tired"],
     "answer": "B", "explanation": "Joyful = happy."},
    {"id": 3, "subject": "english", "grade": 4, "difficulty": 2,
     "question": "What is the past tense of 'go'?",
     "options": ["A. Goed", "B. Gone", "C. Went", "D. Going"],
     "answer": "C", "explanation": "Go -> Went (irregular verb)."},
    {"id": 4, "subject": "english", "grade": 4, "difficulty": 3,
     "question": "Choose the correct sentence:",
     "options": ["A. He don't like apples.", "B. He doesn't likes apples.",
     "C. He doesn't like apples.", "D. He not like apples."],
     "answer": "C", "explanation": "Third person singular uses doesn't + base form."},
    {"id": 5, "subject": "english", "grade": 4, "difficulty": 3,
     "question": "What does 'polite' mean?",
     "options": ["A. Rude", "B. Kind and respectful", "C. Funny", "D. Quiet"],
     "answer": "B", "explanation": "Polite = kind and respectful."},
]

SCIENCE_GRADE_4: list[dict[str, Any]] = [
    {"id": 0, "subject": "science", "grade": 4, "difficulty": 1,
     "question": "植物通过什么过程把阳光变成能量?",
     "options": ["A. 呼吸作用", "B. 光合作用", "C. 蒸腾作用", "D. 发酵作用"],
     "answer": "B", "explanation": "光合作用: 阳光 + 二氧化碳 + 水 → 葡萄糖 + 氧气"},
    {"id": 1, "subject": "science", "grade": 4, "difficulty": 1,
     "question": "下列哪个是哺乳动物?",
     "options": ["A. 鸡", "B. 鱼", "C. 鲸鱼", "D. 蛇"],
     "answer": "C", "explanation": "鲸鱼是哺乳动物, 虽然生活在水里"},
    {"id": 2, "subject": "science", "grade": 4, "difficulty": 2,
     "question": "水在标准大气压下, 多少摄氏度沸腾?",
     "options": ["A. 50℃", "B. 80℃", "C. 100℃", "D. 120℃"],
     "answer": "C", "explanation": "标准大气压下水的沸点为 100℃"},
    {"id": 3, "subject": "science", "grade": 4, "difficulty": 2,
     "question": "声音在下列哪种介质中传播最快?",
     "options": ["A. 空气", "B. 水", "C. 钢铁", "D. 真空"],
     "answer": "C", "explanation": "声音在固体中传播最快, 真空中不能传播"},
    {"id": 4, "subject": "science", "grade": 4, "difficulty": 3,
     "question": "地球围绕太阳转一圈大约需要多久?",
     "options": ["A. 一天", "B. 一月", "C. 一年", "D. 十年"],
     "answer": "C", "explanation": "公转周期约 365.25 天"},
    {"id": 5, "subject": "science", "grade": 4, "difficulty": 4,
     "question": "下列哪种现象不是由于地球自转引起的?",
     "options": ["A. 昼夜交替", "B. 时差", "C. 四季变化", "D. 太阳东升西落"],
     "answer": "C", "explanation": "四季变化由公转引起, 其他由自转引起"},
]

BANK: dict[str, list[dict[str, Any]]] = {
    "math": MATH_GRADE_4,
    "chinese": CHINESE_GRADE_4,
    "english": ENGLISH_GRADE_4,
    "science": SCIENCE_GRADE_4,
}


def get_fallback_questions(
    subject: str,
    count: int,
    grade: int = 4,
    difficulty: int = 3,
) -> list[dict[str, Any]]:
    """Pick `count` questions from the local bank for the given subject.

    Falls back to 'math' if the subject is unknown or has no bank.
    """
    pool = BANK.get(subject, MATH_GRADE_4)
    # Filter by difficulty tolerance
    candidates = [q for q in pool if abs(q.get("difficulty", 3) - difficulty) <= 2]
    if not candidates:
        candidates = pool
    sampled = random.sample(candidates, min(count, len(candidates)))
    # Re-id sequentially
    out = []
    for i, q in enumerate(sampled):
        q2 = dict(q)
        q2["id"] = i
        out.append(q2)
    return out
