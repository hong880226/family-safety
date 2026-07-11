"""pytest config for backend tests."""
import os
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

# Force a test-friendly config BEFORE any ``app.*`` import so the cached
# settings in app.db.session pick up an async-friendly URL. The shell often
# exports ``DATABASE_URL=sqlite:///...`` (sync) from a prior dev session, which
# then makes ``create_async_engine`` blow up at import time.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET"] = os.environ.get("JWT_SECRET") or "test-jwt-secret-not-for-production-32+chars"
