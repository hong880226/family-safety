"""Unit tests for input-validation (Pydantic form models)."""
import pytest
from pydantic import ValidationError

from app.schemas.web_inputs import (
    ContentRuleForm,
    MemberForm,
    QuizConfigForm,
    SettingsForm,
)


# ---- MemberForm ----

def test_member_form_valid():
    m = MemberForm(name="小明", grade=4, windows_username="xiaoming")
    assert m.grade == 4


def test_member_form_grade_out_of_range():
    with pytest.raises(ValidationError):
        MemberForm(name="小明", grade=13)
    with pytest.raises(ValidationError):
        MemberForm(name="小明", grade=0)


def test_member_form_name_too_long():
    with pytest.raises(ValidationError):
        MemberForm(name="x" * 100)


def test_member_form_name_bad_chars():
    """SQL-injection / script-tag attempts are blocked by the regex."""
    with pytest.raises(ValidationError):
        MemberForm(name="'; DROP TABLE members;--")
    with pytest.raises(ValidationError):
        MemberForm(name="<script>alert(1)</script>")


# ---- QuizConfigForm ----

def test_quiz_config_default_total_questions_is_3():
    q = QuizConfigForm(member_id=1)
    assert q.total_questions == 3


def test_quiz_config_total_questions_out_of_range():
    with pytest.raises(ValidationError):
        QuizConfigForm(member_id=1, total_questions=0)
    with pytest.raises(ValidationError):
        QuizConfigForm(member_id=1, total_questions=21)


def test_quiz_config_difficulty_out_of_range():
    with pytest.raises(ValidationError):
        QuizConfigForm(member_id=1, difficulty=6)
    with pytest.raises(ValidationError):
        QuizConfigForm(member_id=1, difficulty=0)


def test_quiz_config_distribution_mode_must_be_enum():
    with pytest.raises(ValidationError):
        QuizConfigForm(member_id=1, distribution_mode="malicious_mode")


# ---- ContentRuleForm ----

def test_content_rule_normal_pattern_passes():
    # We don't need to instantiate via as_form for unit test; build directly.
    from app.models.content_rule import ContentAction, ContentCategory, MatchType
    r = ContentRuleForm(
        match_type=MatchType.WINDOW_TITLE,
        pattern=r"毒视频|色情",
        category=ContentCategory.TOXIC_CONTENT,
        action=ContentAction.BLOCK,
    )
    assert r.pattern == r"毒视频|色情"


def test_content_rule_redos_pattern_rejected():
    """(a+)+ and similar nested quantifiers must be rejected."""
    from app.models.content_rule import ContentAction, ContentCategory, MatchType
    with pytest.raises(ValidationError):
        ContentRuleForm(
            match_type=MatchType.WINDOW_TITLE,
            pattern=r"(a+)+",
            category=ContentCategory.TOXIC_CONTENT,
            action=ContentAction.MONITOR,
        )


def test_content_rule_too_long_pattern_rejected():
    from app.models.content_rule import ContentAction, ContentCategory, MatchType
    with pytest.raises(ValidationError):
        ContentRuleForm(
            match_type=MatchType.WINDOW_TITLE,
            pattern="a" * 500,
            category=ContentCategory.TOXIC_CONTENT,
            action=ContentAction.MONITOR,
        )


# ---- SettingsForm ----

def test_settings_form_smtp_port_must_be_valid():
    with pytest.raises(ValidationError):
        SettingsForm(smtp_port=0)
    with pytest.raises(ValidationError):
        SettingsForm(smtp_port=70000)


def test_settings_form_threshold_must_be_0_to_1():
    with pytest.raises(ValidationError):
        SettingsForm(toxic_threshold=-0.1)
    with pytest.raises(ValidationError):
        SettingsForm(toxic_threshold=1.5)