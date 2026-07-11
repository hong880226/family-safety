"""Lightweight DTO-name consistency check for agent-windows HeartbeatLoop.

The agent-windows code is C#/net8.0-windows (cannot build on Linux CI without
the Windows SDK), so this Python script parses the C# source files and checks
that every JSON snake_case field name referenced in HeartbeatRequest /
HeartbeatResponse DTOs (via [JsonPropertyName("...")]) and in HeartbeatLoop /
HandleCommand matches the field names the backend actually emits.

Fixtures under ./fixtures/ are exact snapshots of what the backend
``/api/v1/agent/heartbeat`` response looks like for each command type, taken
from backend/app/api/v1/agent.py + backend/app/web/routes.py + backend tests.

Run from anywhere:
    python3 agent-windows/tests/test_commands_parse.py
Exit code 0 = pass, 1 = fail.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # .../agent-windows
SRC = ROOT / "src"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BACKEND_ROUTES = ROOT.parent / "backend" / "app" / "api" / "v1" / "agent.py"

# ---- The field names the agent must round-trip ----
# Anything the agent sets / expects on a heartbeat, and the snake_case names
# the four command payloads ship with (per backend/app/web/routes.py).
EXPECTED_HEARTBEAT_FIELDS = {
    # Agent -> backend (HeartbeatRequest, BackendClient.cs)
    "timestamp",
    "windows_username",
    "computer_model",
    "current_app",
    "window_title",
    "used_seconds_today",
    "used_seconds_this_week",
    "uptime_seconds",
}

EXPECTED_HEARTBEAT_RESPONSE_FIELDS = {
    # Backend -> agent (HeartbeatResponse)
    "matched_rule",
    "matched_member_id",
    "commands",
    "server_time",
}

# Each command type can carry these extra payload keys (from backend routes + tests).
EXPECTED_COMMAND_PAYLOAD_FIELDS = {
    "lock_screen": set(),
    "shutdown": {"delay_seconds", "message"},
    "reboot": {"delay_seconds", "message"},
    "force_quiz": {"reason"},
    "show_warning": {"message"},
    # PR-D: agent-side capture command. Backend never issues this; it's the
    # contract we expect when PR-E wires the parent-side trigger.
    "capture_screen": {"trigger_type"},
}

ALL_KNOWN_COMMAND_TYPES = set(EXPECTED_COMMAND_PAYLOAD_FIELDS.keys())


def extract_json_property_names(cs_file: Path) -> set[str]:
    """Pull every [JsonPropertyName("xxx")] value out of a C# file."""
    text = cs_file.read_text(encoding="utf-8")
    return {m for m in re.findall(r'\[JsonPropertyName\("([^"]+)"\)\]', text)}


def extract_csharp_string_literals(cs_file: Path) -> set[str]:
    """Pull every quoted string literal out of a C# file. Used to verify
    that HandleCommand switch cases match the JSON ``type`` field values.
    """
    text = cs_file.read_text(encoding="utf-8")
    return set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"', text))


def main() -> int:
    failures: list[str] = []

    backend_client = SRC / "FsCommon" / "BackendClient.cs"
    heartbeat_loop = SRC / "FsAgent" / "HeartbeatLoop.cs"
    ipc_server = SRC / "FsAgent" / "IpcServer.cs"
    for f in (backend_client, heartbeat_loop, ipc_server):
        if not f.exists():
            failures.append(f"missing source file: {f}")

    if failures:
        for line in failures:
            print(f"FAIL: {line}", file=sys.stderr)
        return 1

    dto_fields = extract_json_property_names(backend_client)
    missing_req = EXPECTED_HEARTBEAT_FIELDS - dto_fields
    missing_resp = EXPECTED_HEARTBEAT_RESPONSE_FIELDS - dto_fields
    if missing_req:
        failures.append(
            "HeartbeatRequest DTO missing JsonPropertyName for: "
            + ", ".join(sorted(missing_req))
        )
    if missing_resp:
        failures.append(
            "HeartbeatResponse DTO missing JsonPropertyName for: "
            + ", ".join(sorted(missing_resp))
        )

    # HandleCommand must have a case branch for every command type.
    hb_literals = extract_csharp_string_literals(heartbeat_loop)
    for cmd_type in ALL_KNOWN_COMMAND_TYPES:
        # We check the DTO doesn't accidentally rename it; HandleCommand uses
        # it as a case literal so the string must appear at least once in the
        # file. ``lock_screen``, ``show_warning`` etc. show up both as case
        # values and possibly in comments — that's fine.
        if cmd_type not in hb_literals:
            failures.append(
                f"HeartbeatLoop.cs never references command type \"{cmd_type}\""
            )

    # Fixtures sanity check: every command payload key in a fixture must be in
    # the EXPECTED_COMMAND_PAYLOAD_FIELDS for that command type. This catches
    # accidental field renames on the backend that the agent wouldn't notice
    # until a live test.
    for fx in sorted(FIXTURES.glob("*.json")):
        body = json.loads(fx.read_text(encoding="utf-8"))
        for cmd in body.get("commands", []):
            cmd_type = cmd["type"]
            if cmd_type not in EXPECTED_COMMAND_PAYLOAD_FIELDS:
                failures.append(
                    f"{fx.name}: unknown command type {cmd_type!r}"
                )
                continue
            allowed = EXPECTED_COMMAND_PAYLOAD_FIELDS[cmd_type]
            extra = set(cmd.keys()) - {"type"} - allowed
            if extra:
                failures.append(
                    f"{fx.name}: command {cmd_type!r} has unexpected keys "
                    f"{sorted(extra)} (agent won't read them)"
                )

    # Cross-check the agent DTO names against what backend actually emits —
    # grep the backend heartbeat handler for the snake_case fields it serializes.
    if BACKEND_ROUTES.exists():
        backend_text = BACKEND_ROUTES.read_text(encoding="utf-8")
        for fname in EXPECTED_HEARTBEAT_FIELDS:
            if fname not in backend_text:
                # Not all fields are necessarily touched in agent.py — some
                # come from the Pydantic schema. Warn rather than fail.
                print(f"warn: field {fname!r} not referenced in {BACKEND_ROUTES.name}")
    else:
        print(f"warn: backend handler {BACKEND_ROUTES} not present, skipping cross-check")

    if failures:
        print("FAIL:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("OK: PR-B command-channel DTO names are consistent.")
    print(f"  - HeartbeatRequest fields: {len(EXPECTED_HEARTBEAT_FIELDS)} checked")
    print(f"  - HeartbeatResponse fields: {len(EXPECTED_HEARTBEAT_RESPONSE_FIELDS)} checked")
    print(f"  - command types with cases: {len(ALL_KNOWN_COMMAND_TYPES)} checked")
    print(f"  - fixtures: {len(list(FIXTURES.glob('*.json')))} parsed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
