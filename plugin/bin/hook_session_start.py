#!/usr/bin/env python3
"""SessionStart hook.

 - fresh session  -> generate canaries, store, inject into context
 - source=compact -> measure survival across the compaction, then re-inject
Always exits 0; never disrupts the session.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import canary_lib as cl  # noqa: E402


def emit(additional_context):
    if not additional_context:
        return
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": additional_context,
        }
    }))


def main():
    inp = cl.read_stdin()
    cwd = inp.get("cwd") or os.getcwd()
    cfg = cl.load_config(cwd)
    if not cfg["enabled"]:
        return

    # First-run setup happens here (prompt-free), so no /init command is needed.
    cl.ensure_initialized(cwd, cfg)

    source = inp.get("source") or "startup"
    session = cl.load_session(cwd)

    if source == "compact" and session and session.get("canaries"):
        a = cl.analyze_transcript(inp.get("transcript_path"), session["canaries"])
        cl.save_health(cwd, cl.compute_health(cfg, a))
        cl.append_history(cwd, {
            "ts": cl.now_iso(), "event": "post_compact",
            "present": a["present"], "total": a["total"], "missing": a["missing"],
        })
        if cfg["reinjectOnCompact"]:
            emit(cl.injection_text(session["canaries"]))
        return

    same = session and session.get("sessionId") == inp.get("session_id")
    if not same:
        canaries = cl.gen_canaries(cfg["canaryCount"], cfg["canaryPrefix"])
        session = {
            "sessionId": inp.get("session_id") or "unknown",
            "createdAt": cl.now_iso(),
            "canaries": canaries,
        }
        cl.save_session(cwd, session)
        cl.save_health(cwd, cl.compute_health(cfg, {
            "present": len(canaries), "total": len(canaries),
            "compacted": False, "compactions": 0, "missing": [],
        }))
        cl.append_history(cwd, {
            "ts": session["createdAt"], "event": "session_start",
            "source": source, "canaries": canaries,
        })
    emit(cl.injection_text(session["canaries"]))


try:
    main()
except Exception:
    pass
sys.exit(0)
