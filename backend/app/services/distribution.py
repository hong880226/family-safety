"""Compute quiz distribution based on QuizConfig and SubjectMastery."""
from __future__ import annotations

from app.models.quiz_config import DistributionMode


def compute_distribution(
    mode: str,
    subjects: list[str],
    distribution: dict[str, int],
    total: int,
    weak_subjects: list[str] | None = None,
    mastery: dict[str, dict] | None = None,
) -> dict[str, int]:
    """Return a dict {subject: count} summing to `total`.

    Modes:
      - manual:        use distribution dict literally (clipped to total)
      - auto:          round-robin among subjects
      - weakness_first: prioritize weak_subjects, fill rest round-robin
    """
    if mode == DistributionMode.MANUAL.value:
        # Clamp to total
        s = sum(distribution.values())
        if s != total:
            scale = total / s if s > 0 else 1
            out = {k: max(0, round(v * scale)) for k, v in distribution.items()}
            # Adjust to exact total
            diff = total - sum(out.values())
            if out:
                first = next(iter(out))
                out[first] = max(0, out[first] + diff)
            return {k: v for k, v in out.items() if v > 0}
        return {k: v for k, v in distribution.items() if v > 0}

    if not subjects:
        return {}

    if mode == DistributionMode.WEAKNESS_FIRST.value:
        weak = [s for s in (weak_subjects or []) if s in subjects]
        non_weak = [s for s in subjects if s not in weak]
        out: dict[str, int] = {}
        # Reserve at least 1 per weak subject, capped
        per_weak = max(1, total // (2 * max(1, len(weak)))) if weak else 0
        # First pass: assign each weak subject `per_weak`
        used = 0
        for s in weak:
            give = min(per_weak, total - used)
            if give > 0:
                out[s] = give
                used += give
        # Remaining: round-robin among non_weak + remaining weak
        pool = non_weak + weak
        if not pool:
            pool = subjects
        idx = 0
        while used < total and pool:
            s = pool[idx % len(pool)]
            out[s] = out.get(s, 0) + 1
            used += 1
            idx += 1
        return out

    # auto: round-robin
    out = {}
    for i in range(total):
        s = subjects[i % len(subjects)]
        out[s] = out.get(s, 0) + 1
    return out
