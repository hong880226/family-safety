"""Full E2E smoke test: agent register + heartbeat + usage + quiz start/submit."""
import io
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BACKEND = Path(__file__).resolve().parent
print(f"Backend dir: {BACKEND}\n")

# 1. Clean DB
db_file = BACKEND / "familysafety.db"
if db_file.exists():
    db_file.unlink()
    print("[setup] removed old db")

# 2. Start uvicorn
log_path = BACKEND / "uvicorn.log"
log_f = open(log_path, "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app",
     "--port", "8765", "--log-level", "warning"],
    cwd=str(BACKEND),
    stdout=log_f,
    stderr=subprocess.STDOUT,
)
print(f"[setup] started uvicorn (pid={proc.pid})")

try:
    import httpx

    # Wait for ready
    for i in range(20):
        time.sleep(0.5)
        try:
            r = httpx.get("http://127.0.0.1:8765/healthz", timeout=2)
            if r.status_code == 200:
                print(f"[setup] uvicorn ready in {(i+1)*0.5}s\n")
                break
        except Exception:
            continue
    else:
        raise RuntimeError("uvicorn did not come up")

    BASE = "http://127.0.0.1:8765"

    # === Health ===
    print("[1] Health")
    r = httpx.get(f"{BASE}/healthz")
    assert r.status_code == 200, r.text
    print(f"  OK healthz -> {r.json()}")

    r = httpx.get(f"{BASE}/readyz")
    assert r.status_code == 200
    print(f"  OK readyz -> {r.json()}")

    # === Register device ===
    print("\n[2] Register device kid01")
    r = httpx.post(f"{BASE}/api/v1/agent/register", json={
        "name": "客厅台式机", "device_type": "windows",
        "computer_model": "LENOVO-XIAOXIN-15IAU7", "windows_username": "kid01",
    })
    assert r.status_code == 200, r.text
    d1 = r.json()
    api_key1 = d1["api_key"]
    family_id = d1["family_id"]
    member_id1 = d1["member_id"]
    print(f"  OK device1: family_id={family_id}, member_id={member_id1}")

    # === Heartbeat ===
    print("\n[3] Heartbeat (within limit)")
    r = httpx.post(
        f"{BASE}/api/v1/agent/heartbeat",
        headers={"Authorization": f"Bearer {api_key1}"},
        json={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "windows_username": "kid01",
            "used_seconds_today": 600,
        },
    )
    assert r.status_code == 200
    hb = r.json()
    assert hb["matched_member_id"] == member_id1
    assert hb["commands"] == []
    print(f"  OK heartbeat, matched_rule={hb['matched_rule']['name']}")

    # === Usage batch ===
    print("\n[4] Usage batch")
    now = datetime.now(timezone.utc)
    r = httpx.post(
        f"{BASE}/api/v1/agent/usage",
        headers={"Authorization": f"Bearer {api_key1}"},
        json={"records": [
            {"app_name": "steam.exe", "window_title": "Counter-Strike 2",
             "start_at": (now - timedelta(minutes=10)).isoformat(),
             "end_at": (now - timedelta(minutes=5)).isoformat(),
             "duration_seconds": 300, "category": "game_native"},
            {"app_name": "chrome.exe", "window_title": "B站 - 三年级数学课",
             "start_at": (now - timedelta(minutes=5)).isoformat(),
             "end_at": now.isoformat(),
             "duration_seconds": 300, "category": "study"},
        ]},
    )
    assert r.status_code == 201, r.text
    print(f"  OK usage inserted {r.json()['inserted']} records")

    # === Quiz: start ===
    print("\n[5] Quiz start (math, 3 questions)")
    r = httpx.post(
        f"{BASE}/api/v1/quiz/start",
        headers={"Authorization": f"Bearer {api_key1}"},
        json={"subject": "math"},
    )
    assert r.status_code == 200, r.text
    quiz = r.json()
    token = quiz["token"]
    questions = quiz["questions"]
    print(f"  OK token={token[:16]}...")
    print(f"  Got {len(questions)} questions, subjects={quiz['config_used']['distribution']}")
    assert len(questions) == 3
    # Verify no 'answer' field leaked to client
    for q in questions:
        assert "answer" not in q, f"Answer leaked: {q}"
    print("  OK answer key not in client response")

    # === Quiz: submit all correct ===
    print("\n[6] Quiz submit (perfect score)")
    # We don't know the actual answers from LLM/fallback. Try to grab them via DB debug:
    # Get from the database directly using a separate sqlite inspection.
    import sqlite3
    db = sqlite3.connect(str(BACKEND / "familysafety.db"))
    cur = db.execute(
        "SELECT questions FROM quiz_sessions WHERE token = ?", (token,)
    )
    row = cur.fetchone()
    import json as _json
    full_questions = _json.loads(row[0])
    answers = {q["id"]: q["answer"] for q in full_questions}
    print(f"  Sending answers: {answers}")

    r = httpx.post(
        f"{BASE}/api/v1/quiz/submit",
        headers={"Authorization": f"Bearer {api_key1}"},
        json={"token": token, "answers": answers},
    )
    assert r.status_code == 200, r.text
    sub = r.json()
    print(f"  OK score={sub['score']}/{sub['total']}, correct_rate={sub['correct_rate']:.0%}")
    print(f"  OK reward_minutes={sub['reward_minutes']}")
    assert sub["score"] == sub["total"] == 3
    assert sub["reward_minutes"] >= 1

    # === Quiz: detail ===
    print("\n[7] Quiz session detail")
    r = httpx.get(
        f"{BASE}/api/v1/quiz/session/{token}",
        headers={"Authorization": f"Bearer {api_key1}"},
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    print(f"  OK status={detail['status']}, score={detail['score']}/{detail['total']}")
    assert detail["status"] == "completed"

    # === Quiz start with subject='mix' ===
    print("\n[8] Quiz start (mix)")
    r = httpx.post(
        f"{BASE}/api/v1/quiz/start",
        headers={"Authorization": f"Bearer {api_key1}"},
        json={"subject": "mix"},
    )
    assert r.status_code == 200, r.text
    q2 = r.json()
    print(f"  OK mix quiz: distribution={q2['config_used']['distribution']}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_f.close()