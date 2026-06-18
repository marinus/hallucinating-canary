#!/usr/bin/env python3
"""UserPromptSubmit hook: cheap, token-free refresh of canary survival once per
user turn. Keeps health.json current between compaction events. Emits nothing."""

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
    if session and session.get("canaries"):
        a = cl.analyze_transcript(inp.get("transcript_path"), session["canaries"])
        if a["available"]:
            cl.save_health(cwd, cl.compute_health(cfg, a))


try:
    main()
except Exception:
    pass
sys.exit(0)
