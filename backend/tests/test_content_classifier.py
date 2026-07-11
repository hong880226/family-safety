"""Unit tests for content_classifier ReDoS guards."""
import re

from app.services.content_classifier import (
    _is_unsafe_pattern,
    _match,
    _safe_search,
)


def test_safe_pattern_passes():
    assert _is_unsafe_pattern(r"(毒视频|色情|赌博)") is False
    assert _is_unsafe_pattern(r"^steam\.exe$") is False
    assert _is_unsafe_pattern(r"(?i)(steam|epicgames)\.exe$") is False


def test_nested_quantifier_rejected():
    assert _is_unsafe_pattern(r"(a+)+") is True
    assert _is_unsafe_pattern(r"(a*)*") is True


def test_quantified_alternation_rejected():
    """(a|b)+ / (a|b)* — overlap-prone alternation is also catastrophic.

    Regression for the (a|a)+ bypass that took ~76s on 'a'*28+'!'.
    """
    assert _is_unsafe_pattern(r"^(a|a)+$") is True
    assert _is_unsafe_pattern(r"(a|bc)+") is True
    assert _is_unsafe_pattern(r"(ab|cd)*") is True


def test_adjacent_quantifier_rejected():
    assert _is_unsafe_pattern(r"a++") is True
    assert _is_unsafe_pattern(r"a**") is True


def test_dot_star_chains_rejected():
    assert _is_unsafe_pattern(r".*.*") is True
    assert _is_unsafe_pattern(r".+.+") is True


def test_too_long_pattern_rejected():
    assert _is_unsafe_pattern("a" * 500) is True


def test_empty_pattern_rejected():
    assert _is_unsafe_pattern("") is True


def test_safe_search_returns_false_on_unsafe():
    """Unsafe patterns short-circuit to False."""
    assert _safe_search(r"(a+)+$", "aaaaaa") is False


def test_safe_search_returns_fast_on_alternation_bypass():
    """Regression: (a|a)+ on 'a'*28+'!' previously took ~76s.

    Even if heuristic somehow misses, the call must return within a few
    ms so a single bad rule can't pin a worker.
    """
    import time
    t0 = time.monotonic()
    result = _safe_search(r"^(a|a)+$", "a" * 28 + "!")
    elapsed = time.monotonic() - t0
    assert elapsed < 0.1, f"_safe_search took {elapsed:.3f}s on canonical bypass"
    assert result is False


def test_safe_search_matches_normal_patterns():
    assert _safe_search(r"毒视频", "这是个毒视频标题") is True
    assert _safe_search(r"^steam\.exe$", "STEAM.EXE", re.IGNORECASE) is True


def test_safe_search_caps_input_length():
    """Long inputs are truncated so regex can't blow up on length."""
    pattern = r"needle"
    text = "needle" + "x" * 10000
    assert _safe_search(pattern, text) is True  # matches before truncation


def test_classify_skips_unsafe_db_rule():
    """An unsafe DB rule must not cause a match."""
    unsafe_rule = {
        "match_type": "window_title",
        "pattern": r"(a+)+$",
        "category": "toxic_content",
        "sub_label": None,
        "action": "monitor",
    }
    assert _match(unsafe_rule, "chrome.exe", "any-title") is False