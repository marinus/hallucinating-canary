#!/usr/bin/env python3
"""PreCompact hook: snapshot canary presence immediately before Claude Code
summarizes the conversation, so the before/after pair is recorded."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import canary_lib as cl  # noqa: E402


def main():
    inp = cl.read_stdin()
    cwd = inp.get("cwd") or os.getcwd()
    cfg = cl.load_config(cwd)
    if not cfg["enabled"]:
        return

    session = cl.load_session(cwd)
    canaries = session["canaries"] if session and session.get("canaries") else []
    a = cl.analyze_transcript(inp.get("transcript_path"), canaries)
    cl.append_history(cwd, {
        "ts": cl.now_iso(), "event": "pre_compact",
        "trigger": inp.get("trigger") or inp.get("matcher") or "unknown",
        "present": a["present"], "total": a["total"],
    })


try:
    main()
except Exception:
    pass
sys.exit(0)
