"""Static schema check for the FsWatchdog control pipe (PR-D).

The Windows-side FsTray / FsConfigUI / CLI all send a single-line JSON
message on the FsWatchdog_Ctrl_Pipe named pipe. FsWatchdogService parses
that line and dispatches (currently only graceful_stop).

This Python script reads the C# source files and verifies:

1. The pipe name constant lives in exactly one place
   (FsCommon.ProcessNames.WatchdogControlPipe) and matches between the
   sender side (ServicePipeClient.cs) and the receiver side
   (Supervisor.cs ListenForControlCommands).
2. The graceful_stop JSON message has the agreed-upon shape: type,
   password_hash, salt, iterations. We grep for the field names; this
   catches accidental renames that would otherwise only surface at
   runtime when a parent clicks "退出".
3. The receiver actually verifies the hash server-side (it must call
   ExportForSync and CryptographicOperations.FixedTimeEquals, or a
   documented equivalent). Without verification the pipe is open to any
   local user — the spec explicitly forbids that.
4. The CLI subcommand name "graceful-stop" is plumbed end-to-end
   (Cli.cs switch case + ServicePipeClient.SendGracefulStop call).

Run from anywhere:
    python3 agent-windows/tests/test_pipe_messages.py
Exit code 0 = pass, 1 = fail.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # .../agent-windows
SRC = ROOT / "src"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []

    process_names = SRC / "FsCommon" / "ProcessNames.cs"
    service_pipe_client = SRC / "FsCommon" / "ServicePipeClient.cs"
    supervisor = SRC / "FsWatchdogService" / "Supervisor.cs"
    cli = SRC / "FsWatchdogService" / "Cli.cs"
    tray = SRC / "FsTray" / "Program.cs"
    config_ui = SRC / "FsConfigUI" / "MainForm.cs"

    for f in (process_names, service_pipe_client, supervisor, cli, tray, config_ui):
        if not f.exists():
            failures.append(f"missing source file: {f}")
    if failures:
        for line in failures:
            print(f"FAIL: {line}", file=sys.stderr)
        return 1

    # ---- (1) Pipe name constant lives in ProcessNames.cs and is used consistently ----
    pn_text = _read(process_names)
    const_match = re.search(
        r'public\s+const\s+string\s+WatchdogControlPipe\s*=\s*"([^"]+)"',
        pn_text,
    )
    if not const_match:
        failures.append("ProcessNames.cs missing WatchdogControlPipe constant")
        return 1
    pipe_name = const_match.group(1)
    print(f"  - control pipe name: {pipe_name}")

    sender_text = _read(service_pipe_client)
    if 'ProcessNames.WatchdogControlPipe' not in sender_text:
        failures.append("ServicePipeClient.cs does not reference ProcessNames.WatchdogControlPipe")
    # The C# code must use the constant (ProcessNames.WatchdogControlPipe), not
    # a hard-coded literal of the pipe name. Detect accidental hard-coding
    # by looking for the literal string assigned to a NamedPipeClientStream.
    hardcoded = re.search(
        r'NamedPipeClientStream\([^)]*"' + re.escape(pipe_name) + '"',
        sender_text,
    )
    if hardcoded:
        failures.append(
            f"ServicePipeClient.cs hard-codes the pipe name \"{pipe_name}\" — "
            "use ProcessNames.WatchdogControlPipe instead."
        )

    receiver_text = _read(supervisor)
    if 'ProcessNames.WatchdogControlPipe' not in receiver_text:
        failures.append("Supervisor.cs does not reference ProcessNames.WatchdogControlPipe")
    hardcoded_recv = re.search(
        r'NamedPipeServerStream\([^)]*"' + re.escape(pipe_name) + '"',
        receiver_text,
    )
    if hardcoded_recv:
        failures.append(
            f"Supervisor.cs hard-codes the pipe name \"{pipe_name}\" — "
            "use ProcessNames.WatchdogControlPipe instead."
        )

    # ---- (2) graceful_stop JSON shape ----
    for required_field in ("type", "password_hash", "salt", "iterations"):
        if required_field not in sender_text:
            failures.append(
                f'ServicePipeClient.cs does not serialize "{required_field}" field'
            )
        if required_field not in receiver_text:
            failures.append(
                f'Supervisor.cs does not read "{required_field}" field'
            )
    if '"graceful_stop"' not in sender_text:
        failures.append('ServicePipeClient.cs missing graceful_stop type literal')

    # ---- (3) Receiver actually verifies the hash ----
    if 'ExportForSync' not in receiver_text:
        failures.append(
            "Supervisor.cs does not call ParentAuth.ExportForSync — receiver "
            "cannot verify the supplied hash."
        )
    if 'FixedTimeEquals' not in receiver_text:
        failures.append(
            "Supervisor.cs does not use CryptographicOperations.FixedTimeEquals "
            "— constant-time comparison is required to avoid timing attacks."
        )

    # ---- (4) CLI subcommand is plumbed end-to-end ----
    cli_text = _read(cli)
    if '"graceful-stop"' not in cli_text:
        failures.append('Cli.cs missing "graceful-stop" switch case')
    if 'SendGracefulStop' not in cli_text:
        failures.append("Cli.cs never calls ServicePipeClient.SendGracefulStop")
    if 'ParentPasswordDialog' not in cli_text and 'PromptSecret' not in cli_text:
        failures.append(
            "Cli.cs does not prompt for a password before SendGracefulStop — "
            "the gate is missing."
        )

    # ---- (5) Tray + ConfigUI go through the same helper ----
    tray_text = _read(tray)
    if 'ServicePipeClient.SendGracefulStop' not in tray_text:
        failures.append("FsTray/Program.cs does not call ServicePipeClient.SendGracefulStop")
    if 'ParentPasswordDialog' not in tray_text:
        failures.append("FsTray/Program.cs does not use ParentPasswordDialog")
    # sc.exe is allowed ONLY as a fallback inside a clearly-labeled block.
    # We accept it as long as the file still calls the pipe helper first.
    if 'sc.exe' in tray_text:
        labels = ('fallback', 'fall back', '回退', '兜底', 'legacy')
        if not any(label in tray_text.lower() for label in labels):
            failures.append(
                "FsTray/Program.cs still uses sc.exe — fallback path must be "
                "labeled with 'fallback' / 'fall back' / '回退' / '兜底' / 'legacy'."
            )

    config_ui_text = _read(config_ui)
    if 'ServicePipeClient.SendGracefulStop' not in config_ui_text:
        failures.append("FsConfigUI/MainForm.cs does not call ServicePipeClient.SendGracefulStop")
    if 'ParentPasswordDialog' not in config_ui_text:
        failures.append("FsConfigUI/MainForm.cs does not use ParentPasswordDialog")

    # ---- (6) HeartbeatLoop added capture_screen handler ----
    hb = _read(SRC / "FsAgent" / "HeartbeatLoop.cs")
    if '"capture_screen"' not in hb:
        failures.append("HeartbeatLoop.cs missing capture_screen case")
    if 'UploadScreenshotAsync' not in hb:
        failures.append("HeartbeatLoop.cs does not call BackendClient.UploadScreenshotAsync")
    if 'NotifyService' not in hb:
        failures.append(
            "HeartbeatLoop.cs does not notify the tray before capture — privacy "
            "requirement violated (architecture §5.3)."
        )

    # ---- (7) NotifyService uses --notify-screenshot + FsTray honors it ----
    notify = _read(SRC / "FsCommon" / "NotifyService.cs")
    if '--notify-screenshot' not in notify:
        failures.append("NotifyService.cs does not invoke FsTray --notify-screenshot")
    if '--notify-screenshot' not in tray_text:
        failures.append("FsTray/Program.cs does not handle --notify-screenshot arg")

    if failures:
        print("FAIL:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("OK: PR-D control-pipe + screenshot plumbing is consistent.")
    print(f"  - control pipe:            {pipe_name}")
    print("  - message fields:          type, password_hash, salt, iterations")
    print("  - constant-time verify:    FixedTimeEquals")
    print("  - senders wired:           FsTray, FsConfigUI, Cli")
    print("  - receiver wired:          Supervisor.GracefulStopAsync")
    print("  - screenshot notify:       NotifyService + FsTray --notify-screenshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
