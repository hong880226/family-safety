"""Form / request schemas for the rule-edit dashboard endpoint.

Kept in a separate module to avoid mutating ``web_inputs.py`` (baseline file
with shared form schemas). The web edit endpoint parses form fields directly
and constructs a list of ``TimeWindowIn`` to apply.
"""
from __future__ import annotations

import json
from datetime import time
from typing import Annotated

from fastapi import Form
from pydantic import BaseModel, Field, field_validator, model_validator

# Bit indices for ``weekday_mask`` (Mon = 0, Sun = 6).
_WEEKDAY_BITNAMES = (
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
)


def _form_to_bitmask(mon: str, tue: str, wed: str, thu: str, fri: str,
                     sat: str, sun: str) -> int:
    bits = 0
    for i, v in enumerate((mon, tue, wed, thu, fri, sat, sun)):
        if v and v not in ("", "0", "false", "False"):
            bits |= 1 << i
    return bits or 0x7F


class RuleEditForm(BaseModel):
    """Top-level rule fields editable from the dashboard.

    Time windows come in as a separate form-encoded ``windows_json`` field
    (one POST per row would balloon the request body and break CSRF-friendly
    form parsing). The web route validates the JSON before constructing
    ``TimeWindowIn`` rows.
    """

    default_action: Annotated[str, Field(default="allow", max_length=8)] = "allow"
    daily_limit_minutes: Annotated[int, Field(ge=0, le=24 * 60)] = 120
    enabled: bool = True
    # JSON-encoded list of windows. Each item: {weekday_mask, start_time,
    # end_time, action, cap_minutes?, enabled?, priority?}.
    windows_json: Annotated[str, Field(default="[]", max_length=20_000)] = "[]"

    @field_validator("default_action")
    @classmethod
    def _validate_default_action(cls, v: str) -> str:
        if v not in {"allow", "deny"}:
            raise ValueError("default_action must be allow or deny")
        return v

    @model_validator(mode="after")
    def _validate_windows(self) -> RuleEditForm:
        try:
            rows = json.loads(self.windows_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"windows_json is not valid JSON: {e}") from e
        if not isinstance(rows, list):
            raise ValueError("windows_json must be a JSON array")
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"window[{i}] must be an object")
            # Validate time strings parse as HH:MM[:SS]; pydantic handles this
            # when we later build TimeWindowIn, but doing it here surfaces
            # errors with a useful index.
            for k in ("start_time", "end_time"):
                v = row.get(k)
                if not isinstance(v, str):
                    raise ValueError(f"window[{i}].{k} must be a string")
                time.fromisoformat(v)  # raises ValueError on bad format
            action = row.get("action", "allow")
            if action not in {"allow", "deny", "cap"}:
                raise ValueError(f"window[{i}].action must be allow/deny/cap")
            if action == "cap":
                cap = row.get("cap_minutes")
                if not isinstance(cap, int) or cap <= 0:
                    raise ValueError(f"window[{i}].cap_minutes required for action=cap")
        return self

    @classmethod
    def as_form(
        cls,
        default_action: str = Form("allow"),
        daily_limit_minutes: int = Form(120),
        enabled: str = Form("true"),
        windows_json: str = Form("[]"),
        mon: str = Form(""),
        tue: str = Form(""),
        wed: str = Form(""),
        thu: str = Form(""),
        fri: str = Form(""),
        sat: str = Form(""),
        sun: str = Form(""),
    ) -> RuleEditForm:
        # If the form sent the default-weekday checkboxes (the empty-rule
        # case where there are no rows yet) we fold them into the implicit
        # 0x7F default — explicit windows override.
        del mon, tue, wed, thu, fri, sat, sun  # currently unused; reserved for a future per-row UI
        return cls(
            default_action=default_action,
            daily_limit_minutes=daily_limit_minutes,
            enabled=enabled not in ("", "0", "false", "False"),
            windows_json=windows_json,
        )
