#!/usr/bin/env python3
"""Dashboard Publisher - generates dashboard_status.json and pushes to GitHub Pages."""

import json
import hashlib
import subprocess
import time
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
DOCS_DIR = PROJECT_DIR / "docs"
STATUS_FILE = DOCS_DIR / "dashboard_status.json"
AGENTS_CONFIG = PROJECT_DIR / "config" / "agents.json"
SCHEDULER_STATE = PROJECT_DIR / "data" / "scheduler_state.json"
SESSIONS_FILE = PROJECT_DIR / "data" / "sessions.json"
TRANSCRIPT_DIR = Path.home() / ".claude" / "projects" / "-home-aroc-projects-chat-agent"
RETOUREN_FILE = Path.home() / "gdrive" / "5_Privat" / "retouren_tracking.json"
REQUEST_LOG_FILE = PROJECT_DIR / "data" / "request_log.json"
CURRENT_JOBS_FILE = PROJECT_DIR / "data" / "current_jobs.json"
HASH_FILE = PROJECT_DIR / "data" / "dashboard_hash.txt"
MIN_PUSH_INTERVAL = 300  # 5 minutes


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _build_agents(config, state):
    """Merge agent config with scheduler state into dashboard format."""
    agents = []
    for agent_id, agent_cfg in config.get("agents", {}).items():
        tasks_cfg = agent_cfg.get("scheduled_tasks", [])
        enabled_tasks = [t for t in tasks_cfg if t.get("enabled", False)]
        if not enabled_tasks:
            continue

        tasks = []
        for t in enabled_tasks:
            task_state = state.get(t["id"], {})
            tasks.append({
                "id": t["id"],
                "description": t.get("description", t["id"]),
                "cron": t.get("cron", ""),
                "enabled": True,
                "last_run": task_state.get("last_run"),
                "last_status": task_state.get("last_status"),
                "last_error": task_state.get("last_error"),
                "last_duration_seconds": task_state.get("last_duration_seconds"),
                "run_count": task_state.get("run_count", 0),
            })

        # Overall agent status
        statuses = [t["last_status"] for t in tasks if t["last_status"]]
        if "error" in statuses:
            agent_status = "error"
        elif "timeout" in statuses:
            agent_status = "timeout"
        elif statuses:
            agent_status = "success"
        else:
            agent_status = None

        agents.append({
            "id": agent_id,
            "name": agent_cfg.get("name", agent_id),
            "emoji": agent_cfg.get("emoji", ""),
            "status": agent_status,
            "tasks": tasks,
        })

    return agents


def _build_retouren(retouren_data):
    """Build retouren section (anonymized for public dashboard)."""
    returns = retouren_data.get("returns", [])
    pending = [r for r in returns if r.get("status") == "pending"]
    total = sum(r.get("amount", 0) or 0 for r in pending)

    items = []
    for r in returns:
        items.append({
            "shop": r.get("shop", ""),
            "product": r.get("product", ""),
            "amount": r.get("amount"),
            "payment_method": r.get("payment_method", ""),
            "return_date": r.get("return_date", ""),
            "refund_deadline": r.get("refund_deadline", ""),
            "status": r.get("status", "pending"),
            "refund_date": r.get("refund_date"),
        })

    return {
        "pending_count": len(pending),
        "total_amount": total,
        "last_scan": retouren_data.get("last_scan"),
        "items": items,
    }


def _build_sessions(config):
    """Build sessions section with transcript info per agent."""
    sessions_data = _load_json(SESSIONS_FILE)
    if not sessions_data:
        return []

    agents_cfg = config.get("agents", {})
    sessions = []
    for agent_id, session_id in sessions_data.items():
        agent_cfg = agents_cfg.get(agent_id, {})
        transcript = TRANSCRIPT_DIR / f"{session_id}.jsonl"

        size_mb = 0
        last_modified = None
        if transcript.exists():
            stat = transcript.stat()
            size_mb = stat.st_size / (1024 * 1024)
            last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()

        sessions.append({
            "agent_id": agent_id,
            "name": agent_cfg.get("name", agent_id),
            "emoji": agent_cfg.get("emoji", ""),
            "session_id": session_id[:8],
            "transcript_mb": round(size_mb, 1),
            "last_activity": last_modified,
        })

    # Sort by last_activity desc (most recent first), None last
    sessions.sort(key=lambda s: s["last_activity"] or "", reverse=True)
    return sessions


def _build_activity_log(state):
    """Build activity log from scheduler state (sorted by last_run desc)."""
    entries = []
    for task_id, task_state in state.items():
        if "last_run" in task_state and task_state["last_run"]:
            entries.append({
                "timestamp": task_state["last_run"],
                "agent": task_id,
                "task": task_id,
                "status": task_state.get("last_status", ""),
                "message": task_state.get("last_error", "OK") if task_state.get("last_status") != "success" else f"OK ({task_state.get('last_duration_seconds', 0):.1f}s)",
            })

    entries.sort(key=lambda x: x["timestamp"], reverse=True)
    return entries[:50]


def _build_request_log():
    """Build request log from persistent request_log.json."""
    data = _load_json(REQUEST_LOG_FILE)
    if isinstance(data, list):
        # Sort by timestamp desc, return last 100
        data.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return data[:100]
    return []


def generate_status():
    """Generate the dashboard status JSON."""
    config = _load_json(AGENTS_CONFIG)
    state = _load_json(SCHEDULER_STATE)
    retouren = _load_json(RETOUREN_FILE)

    current_jobs = _load_json(CURRENT_JOBS_FILE)
    if not isinstance(current_jobs, list):
        current_jobs = []

    return {
        "last_updated": datetime.now().isoformat(),
        "agents": _build_agents(config, state),
        "sessions": _build_sessions(config),
        "retouren": _build_retouren(retouren),
        "activity_log": _build_activity_log(state),
        "request_log": _build_request_log(),
        "current_jobs": current_jobs,
    }


def publish_dashboard(force=False):
    """Generate status JSON, commit and push if changed."""
    status = generate_status()
    content = json.dumps(status, indent=2, ensure_ascii=False)

    # Check if content changed
    content_hash = hashlib.md5(content.encode()).hexdigest()
    old_hash = ""
    try:
        old_hash = HASH_FILE.read_text().strip()
    except FileNotFoundError:
        pass

    if content_hash == old_hash and not force:
        return False  # No changes

    # Write status file
    DOCS_DIR.mkdir(exist_ok=True)
    STATUS_FILE.write_text(content)
    HASH_FILE.write_text(content_hash)

    # Git commit and push
    try:
        subprocess.run(
            ["git", "add", "docs/dashboard_status.json"],
            cwd=PROJECT_DIR, capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "commit", "-m", "dashboard: update status"],
            cwd=PROJECT_DIR, capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "push"],
            cwd=PROJECT_DIR, capture_output=True, timeout=30
        )
        return True
    except Exception as e:
        print(f"Dashboard push failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    print("Generating dashboard status...")
    result = publish_dashboard(force=True)
    status = _load_json(STATUS_FILE)
    agents = status.get("agents", [])
    print(f"  {len(agents)} agents, {sum(len(a.get('tasks',[])) for a in agents)} tasks")
    print(f"  {status.get('retouren', {}).get('pending_count', 0)} pending retouren")
    print(f"  {len(status.get('activity_log', []))} log entries")
    print(f"  Pushed: {result}")
