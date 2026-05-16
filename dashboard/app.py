#!/usr/bin/env python3
"""
Job Bot Dashboard — Flask web UI
Run: python dashboard/app.py   (or python main.py --dashboard)
Open: http://localhost:5000
"""

import json
import os
import sys
import threading
import subprocess
from datetime import datetime
from flask import Flask, jsonify, request, render_template

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from config import JOBS_FILE, APPLICATIONS_FILE, COVER_LETTERS_DIR, GEMINI_API_KEY, OUTPUT_DIR
except ImportError:
    from config_production import JOBS_FILE, APPLICATIONS_FILE, COVER_LETTERS_DIR, GEMINI_API_KEY, OUTPUT_DIR

app = Flask(__name__)

# Ensure output directories exist (important on fresh Render disk mounts)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(COVER_LETTERS_DIR, exist_ok=True)

_scrape_state = {"running": False, "last_run": None, "last_count": 0, "error": None}
_state_lock = threading.Lock()


def _load(path, default=None):
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _get_applied_ids():
    apps = _load(APPLICATIONS_FILE)
    return {a["job_id"] for a in apps if a.get("status") == "applied" or a.get("applied_at")}


def _get_saved_ids():
    apps = _load(APPLICATIONS_FILE)
    applied = _get_applied_ids()
    return {a["job_id"] for a in apps if a["job_id"] not in applied}


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/jobs")
def api_jobs():
    jobs = _load(JOBS_FILE)
    applied_ids = _get_applied_ids()
    saved_ids = _get_saved_ids()

    for job in jobs:
        jid = job.get("id", "")
        if jid in applied_ids:
            job["_status"] = "applied"
        elif jid in saved_ids:
            job["_status"] = "saved"
        else:
            job["_status"] = "new"

    return jsonify(jobs)


@app.route("/api/stats")
def api_stats():
    jobs = _load(JOBS_FILE)
    apps = _load(APPLICATIONS_FILE)
    applied = [a for a in apps if a.get("status") == "applied" or a.get("applied_at")]
    avg_score = round(sum(j.get("match_score", 0) for j in jobs) / len(jobs), 1) if jobs else 0

    sources = {}
    for j in jobs:
        s = j.get("source", "Unknown")
        sources[s] = sources.get(s, 0) + 1

    return jsonify({
        "total_jobs": len(jobs),
        "applications": len(apps),
        "applied": len(applied),
        "pending": len(apps) - len(applied),
        "avg_score": avg_score,
        "sources": sources,
        "scrape": _scrape_state,
    })


@app.route("/api/jobs/<job_id>/cover-letter", methods=["POST"])
def api_cover_letter(job_id):
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not set in config.py"}), 400

    jobs = _load(JOBS_FILE)
    job = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    try:
        from utils.ai_generator import ApplicationGenerator
        gen = ApplicationGenerator()
        letter = gen.generate_cover_letter(job)

        os.makedirs(COVER_LETTERS_DIR, exist_ok=True)
        safe_co = job["company"].replace(" ", "_").replace("/", "-")
        path = os.path.join(COVER_LETTERS_DIR, f"{job_id}_{safe_co}.txt")
        with open(path, "w") as f:
            f.write(f"Role: {job['title']}\nCompany: {job['company']}\n")
            f.write(f"Date: {datetime.now().strftime('%d %b %Y')}\n")
            f.write(f"URL: {job.get('url', '')}\n")
            f.write("=" * 40 + "\n\n")
            f.write(letter)

        return jsonify({"cover_letter": letter, "saved_to": path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/<job_id>/apply", methods=["POST"])
def api_mark_applied(job_id):
    jobs = _load(JOBS_FILE)
    job = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    apps = _load(APPLICATIONS_FILE)
    existing = next((a for a in apps if a.get("job_id") == job_id), None)
    now = datetime.now().isoformat()

    if existing:
        existing["status"] = "applied"
        existing["applied_at"] = now
    else:
        apps.append({
            "job_id": job_id,
            "title": job["title"],
            "company": job["company"],
            "location": job.get("location"),
            "salary_text": job.get("salary_text"),
            "url": job.get("url"),
            "source": job.get("source"),
            "match_score": job.get("match_score"),
            "cover_letter": None,
            "form_answers": None,
            "status": "applied",
            "applied_at": now,
            "created_at": now,
        })

    _save(APPLICATIONS_FILE, apps)
    return jsonify({"ok": True})


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    with _state_lock:
        if _scrape_state["running"]:
            return jsonify({"error": "Scrape already in progress"}), 409
        _scrape_state["running"] = True
        _scrape_state["error"] = None

    def do_scrape():
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(ROOT, "main.py"), "--scrape-only"],
                capture_output=True, text=True, timeout=300, cwd=ROOT,
            )
            jobs = _load(JOBS_FILE)
            with _state_lock:
                _scrape_state["last_count"] = len(jobs)
                _scrape_state["last_run"] = datetime.now().isoformat()
                if result.returncode != 0:
                    _scrape_state["error"] = (result.stderr or "")[-300:] or None
        except subprocess.TimeoutExpired:
            with _state_lock:
                _scrape_state["error"] = "Scrape timed out after 5 minutes"
        except Exception as e:
            with _state_lock:
                _scrape_state["error"] = str(e)
        finally:
            with _state_lock:
                _scrape_state["running"] = False

    threading.Thread(target=do_scrape, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/scrape/status")
def api_scrape_status():
    return jsonify(_scrape_state)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  Job Bot Dashboard  →  http://localhost:{port}\n")
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", port=port, host="0.0.0.0")
