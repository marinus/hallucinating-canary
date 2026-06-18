"""Shared helpers for HallucinatingCanary. Python 3 stdlib only.

Every consumer (hooks, statusline, CLI) imports from here so the
post-compaction "live window" logic lives in exactly one place.
"""

import json
import os
import secrets
import sys
from datetime import datetime, timezone

DEFAULT_CONFIG = {
    "enabled": True,
    "canaryCount": 3,
    "canaryPrefix": "HC-",
    "warningThreshold": 70,
    "criticalThreshold": 40,
    "reinjectOnCompact": True,
    "instructionCheck": False,
    "autoWireStatusline": True,
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# --- stdin -----------------------------------------------------------------

def read_stdin():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


# --- paths & config --------------------------------------------------------

def paths(cwd):
    d = os.path.join(cwd, ".claude", "hallucinating-canary")
    return {
        "dir": d,
        "session": os.path.join(d, "session.json"),
        "health": os.path.join(d, "health.json"),
        "history": os.path.join(d, "history.json"),
        "config": os.path.join(cwd, ".hallucinating-canary.json"),
    }


def _read_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def load_config(cwd):
    cfg = dict(DEFAULT_CONFIG)
    user = _read_json(paths(cwd)["config"], None)
    if isinstance(user, dict):
        cfg.update(user)
    return cfg


def save_config(cwd, cfg):
    _write_json(paths(cwd)["config"], cfg)


def load_session(cwd):
    return _read_json(paths(cwd)["session"], None)


def save_session(cwd, s):
    _write_json(paths(cwd)["session"], s)


def load_health(cwd):
    return _read_json(paths(cwd)["health"], None)


def save_health(cwd, h):
    _write_json(paths(cwd)["health"], h)


def append_history(cwd, event):
    p = paths(cwd)
    os.makedirs(p["dir"], exist_ok=True)
    with open(p["history"], "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


# --- canaries --------------------------------------------------------------

def gen_canaries(count, prefix):
    return [prefix + secrets.token_hex(2).upper() for _ in range(count)]


def injection_text(canaries):
    return (
        "[hallucinating-canary] Retain these session anchors verbatim and do not "
        "summarize them away. If asked to list session anchors, reproduce them "
        "exactly: " + ", ".join(canaries) + "."
    )


# --- transcript analysis (the live-window logic) ---------------------------

# IMPORTANT: the transcript file retains the FULL history, including
# pre-compaction messages that are no longer in the model's context. Survival
# must be measured only over the post-last-compaction "live window".
#
# The boundary predicate below is a schema-agnostic heuristic. Confirm and
# tighten it against a real transcript (see experiments/canary-survival.md
# Step 0) before trusting survival numbers in production.
def is_compaction_summary(entry):
    if not isinstance(entry, dict):
        return False
    if entry.get("isCompactSummary") is True or entry.get("isSummary") is True:
        return True
    if entry.get("type") == "summary":
        return True
    if entry.get("type") == "system":
        import re
        if re.search(r"compact|summary", json.dumps(entry), re.IGNORECASE):
            return True
    return False


def analyze_transcript(transcript_path, canaries):
    result = {
        "available": False,
        "compacted": False,
        "compactions": 0,
        "present": 0,
        "total": len(canaries),
        "missing": [],
    }
    if not transcript_path or not os.path.exists(transcript_path):
        return result

    entries = []
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return result
    result["available"] = True

    last_boundary = -1
    for i, e in enumerate(entries):
        if is_compaction_summary(e):
            last_boundary = i
            result["compactions"] += 1
    result["compacted"] = last_boundary != -1

    live = entries if last_boundary == -1 else entries[last_boundary:]
    live_text = "\n".join(json.dumps(e) for e in live)

    result["missing"] = [c for c in canaries if c not in live_text]
    result["present"] = len(canaries) - len(result["missing"])
    return result


# --- health ----------------------------------------------------------------

def compute_health(cfg, a):
    present = a.get("present", 0)
    total = a.get("total", 0)
    compacted = a.get("compacted", False)
    survival = round((present / total) * 100) if total > 0 else 100

    score = survival
    level = "healthy"
    if score < cfg["warningThreshold"]:
        level = "warning"
    if score < cfg["criticalThreshold"]:
        level = "critical"
    if compacted and present < total and level == "healthy":
        level = "warning"

    return {
        "survivalScore": survival,
        "level": level,
        "canariesPresent": present,
        "canariesTotal": total,
        "missing": a.get("missing", []),
        "compactions": a.get("compactions", 0),
        "lastCheck": now_iso(),
    }


def level_emoji(level):
    return {"critical": "🔴", "warning": "🟡"}.get(level, "🟢")


# --- auto-setup (prompt-free; runs inside the SessionStart hook) -----------

def ensure_gitignore(cwd):
    gi = os.path.join(cwd, ".gitignore")
    line = ".claude/hallucinating-canary/"
    body = ""
    if os.path.exists(gi):
        try:
            with open(gi, "r", encoding="utf-8") as f:
                body = f.read()
        except Exception:
            return False
    if line in body.split("\n"):
        return False
    if body and not body.endswith("\n"):
        body += "\n"
    body += line + "\n"
    with open(gi, "w", encoding="utf-8") as f:
        f.write(body)
    return True


def statusline_script_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline.py")


def wire_statusline(cwd):
    """Install the statusLine into project .claude/settings.local.json (local,
    gitignored). Non-clobbering. Uses an absolute path because plugins cannot
    ship statusLine and ${CLAUDE_PLUGIN_ROOT} is not expanded in settings.json.
    Returns (state, script_path) where state is installed|present|skipped."""
    settings_path = os.path.join(cwd, ".claude", "settings.local.json")
    script = statusline_script_path()
    desired = {"type": "command", "command": 'python3 "{}"'.format(script)}
    data = _read_json(settings_path, {})
    if not isinstance(data, dict):
        data = {}
    existing = data.get("statusLine")
    if existing == desired:
        return ("present", script)
    if existing:
        return ("skipped", script)
    data["statusLine"] = desired
    _write_json(settings_path, data)
    return ("installed", script)


def ensure_initialized(cwd, cfg):
    """Idempotent first-run setup, done by the SessionStart hook so the user
    never has to invoke a command (and thus never sees a permission prompt).
    Creates the editable config file, state dir, .gitignore entry, and (unless
    disabled) wires the statusline."""
    cfg_path = paths(cwd)["config"]
    if not os.path.exists(cfg_path):
        save_config(cwd, dict(DEFAULT_CONFIG))
    os.makedirs(paths(cwd)["dir"], exist_ok=True)
    ensure_gitignore(cwd)
    if cfg.get("autoWireStatusline", True):
        wire_statusline(cwd)
