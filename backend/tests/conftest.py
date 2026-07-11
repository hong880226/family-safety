"""pytest config for backend tests."""
import sys
from pathlib import Path

# Force UTF-8 I/O on Windows so pytest reads source files as UTF-8
# (the codebase uses Chinese comments/strings).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Ensure `app.*` imports resolve when running `pytest` from backend/.
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))