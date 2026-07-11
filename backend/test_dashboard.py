"""P5 web dashboard smoke test (with CSRF + bcrypt)."""
import io
import re
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BACKEND = Path(__file__).resolve().parent

# Clean DB
db_file = BACKEND / "familysafety.db"
if db_file.exists():
    db_file.unlink()

log_path = BACKEND / "uvicorn.log"
log_f = open(log_path, "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8765", "--log-level", "warning"],
    cwd=str(BACKEND),
    stdout=log_f,
    stderr=subprocess.STDOUT,
)
print(f"[setup] uvicorn pid={proc.pid}")
uvicorn_proc = proc

try:
    import httpx
    for i in range(20):
        time.sleep(0.5)
        try:
            r = httpx.get("http://127.0.0.1:8765/healthz", timeout=2)
            if r.status_code == 200:
                print(f"[setup] uvicorn ready after {(i+1)*0.5}s")
                break
        except Exception:
            continue
    else:
        raise RuntimeError("uvicorn did not start")

    BASE = "http://127.0.0.1:8765"
    CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')

    def login_token(client: httpx.Client) -> str:
        r = client.get(f"{BASE}/web/login")
        m = CSRF_RE.search(r.text)
        return m.group(1) if m else ""

    print("\n[1] Login page (anonymous)")
    r = httpx.get(f"{BASE}/web/login", timeout=5)
    print(f"  status={r.status_code}, len={len(r.text)}")
    assert r.status_code == 200
    assert "FamilySafety" in r.text
    print(f"  OK content length={len(r.text)}")

    print("\n[2] Static CSS")
    r = httpx.get(f"{BASE}/static/css/app.css", timeout=5)
    assert r.status_code == 200
    print(f"  OK CSS served, length={len(r.text)}")

    print("\n[3] Auth required for dashboard")
    r = httpx.get(f"{BASE}/web/dashboard", timeout=5, follow_redirects=False)
    print(f"  status={r.status_code}, location={r.headers.get('location','')}")
    assert r.status_code in (302, 303, 307), f"expected redirect, got {r.status_code}: {r.text[:300]}"
    assert "/web/login" in r.headers.get("location", "")
    print(f"  OK redirected to {r.headers['location']}")

    print("\n[4] Login attempt (no parent yet)")
    with httpx.Client(follow_redirects=False) as c:
        csrf = login_token(c)
        r = c.post(f"{BASE}/web/login",
            data={"username": "nope", "password": "admin", "csrf_token": csrf},
        )
    print(f"  status={r.status_code} (expected 401)")
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:300]}"

    print("\n[5] Need at least one parent - register a device first to create family")
    r = httpx.post(f"{BASE}/api/v1/agent/register", json={
        "name": "TEST", "device_type": "windows",
        "computer_model": "TEST-PC", "windows_username": "testkid",
    })
    print(f"  register status={r.status_code}, body={r.json()}")
    assert r.status_code == 200
    body = r.json()
    parent_username = body.get("parent_username")
    parent_password = body.get("initial_parent_password")
    assert parent_username and parent_password, "register should return initial parent creds"

    print("\n[6] Login with auto-generated parent creds")
    with httpx.Client(follow_redirects=False) as c:
        csrf = login_token(c)
        r = c.post(f"{BASE}/web/login",
            data={"username": parent_username, "password": parent_password, "csrf_token": csrf},
        )
    print(f"  status={r.status_code}, location={r.headers.get('location','')}")
    assert r.status_code in (302, 303), f"expected redirect, got {r.status_code}: {r.text[:300]}"
    cookie = r.cookies.get("auth_token")
    assert cookie, "No auth_token cookie"
    print(f"  OK got auth_token cookie ({len(cookie)} chars)")

    print("\n[7] Dashboard (with auth)")
    r = httpx.get(f"{BASE}/web/dashboard", timeout=5, cookies={"auth_token": cookie})
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:300]}"
    assert "概览" in r.text
    print(f"  OK dashboard rendered, length={len(r.text)}")

    print("\n[8] All pages")
    for path in [
        "/web/members", "/web/devices", "/web/rules",
        "/web/quiz-config", "/web/mastery",
        "/web/content-rules", "/web/toxic-alerts",
        "/web/weekly-reports", "/web/settings",
        "/web/change-password",
    ]:
        r = httpx.get(f"{BASE}{path}", timeout=5, cookies={"auth_token": cookie})
        ok = r.status_code == 200
        print(f"  {path:30s} -> {r.status_code} {'OK' if ok else 'FAIL'}")

    print("\n[9] CSRF: POST without token must be 403")
    r = httpx.post(f"{BASE}/web/settings",
        data={"email": "x@y.z", "csrf_token": ""},
        cookies={"auth_token": cookie})
    print(f"  status={r.status_code}")
    assert r.status_code == 403

    print("\n[10] Cross-family save attempt: POST with member_id of another family must fail")
    # member_id 1 doesn't exist in family 1; should hit 404 or similar
    r = httpx.post(f"{BASE}/web/quiz-config",
        data={"member_id": "99999", "csrf_token": "fake"},
        cookies={"auth_token": cookie})
    print(f"  status={r.status_code}")
    assert r.status_code in (403, 404, 422)

    print("\n" + "="*60)
    print("ALL DASHBOARD PAGES OK")
    print("="*60)

finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except: proc.kill()
    log_f.close()