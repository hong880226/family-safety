"""Schedule service: decide whether the current wall-clock time falls inside
an allowed window for a Rule, and what cap (if any) that window grants.

This is the single source of truth used by:
  * ``app.api.v1.agent.heartbeat`` — to choose between force_quiz /
    allow-and-monitor;
  * future agent-side enforcement (mirror logic on the agent for offline
    protection).

Matching rules
--------------
1. ``default_action`` ("allow" / "deny") is the verdict when no window
   covers ``now_utc``. The agent still applies the daily_limit cap
   independently.
2. A window covers the current time iff:
      * ``rule.enabled`` and ``window.enabled``
      * ``weekday_mask`` has the current weekday bit set (bit 0 = Mon ... bit 6 = Sun)
      * ``start_time <= now_time < end_time`` (normal), or
        ``now_time >= start_time`` (start < end case is the rule above; overnight
        case is ``now_time >= start_time`` OR ``now_time < end_time``).
3. Among covering windows, the highest ``priority`` wins (ties → first).
4. ``action='deny'`` ⇒ (``allowed=False``, cap ``None``)
   ``action='allow'`` ⇒ (``allowed=True``, cap ``None``)
   ``action='cap'``  ⇒ (``allowed=True``, cap ``cap_minutes``)
   ``default_action`` is treated like an implicit ``action='allow'`` row at
   priority = ``-infinity`` (so any explicit window beats it).

Returning a tuple ``(allowed, cap_minutes)`` keeps the heartbeat code small
and trivially testable.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, time

from app.models.rule import Rule
from app.models.time_window import TimeWindow


def _now_in_range(now_t: time, start: time, end: time) -> bool:
    """True if ``now_t`` is in ``[start, end)`` (handles overnight wrap)."""
    if start == end:
        # Degenerate window: treat as 24h.
        return True
    if start < end:
        return start <= now_t < end
    # Overnight: e.g. 22:00-06:00. Two disjoint intervals.
    return now_t >= start or now_t < end


def _match_weekday(window: TimeWindow, now_utc: datetime) -> bool:
    # datetime.weekday(): Mon=0 ... Sun=6 — same convention as weekday_mask.
    return bool(window.weekday_mask & (1 << now_utc.weekday()))


def now_in_window(rule: Rule, now_utc: datetime) -> tuple[bool, int | None]:
    """Decide whether usage is allowed right now, and what cap applies.

    Returns ``(allowed, cap_minutes)``. ``cap_minutes`` is ``None`` when there
    is no cap (either because the window is ``allow``, or because the default
    policy is in effect and no window matched).
    """
    default_action = (rule.default_action or "allow").lower()
    # Filter to enabled windows; sort by priority desc, then id for stability.
    windows: Iterable[TimeWindow] = sorted(
        (w for w in (rule.time_windows or []) if w.enabled),
        key=lambda w: (-w.priority, w.id),
    )

    for w in windows:
        if not _match_weekday(w, now_utc):
            continue
        if not _now_in_range(now_utc.time(), w.start_time, w.end_time):
            continue
        action = (w.action or "allow").lower()
        if action == "deny":
            return False, None
        if action == "cap":
            return True, w.cap_minutes
        # allow
        return True, None

    # No window matched → fall back to rule default.
    return default_action != "deny", None
