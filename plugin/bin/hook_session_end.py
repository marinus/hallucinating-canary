#!/usr/bin/env python3
"""SessionEnd hook: record final state to the history log."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import canary_lib as cl  # noqa: E402


def main():
    inp = cl.read_stdin()
    cwd = inp.get("cwd") or os.getcwd()
    if not cl.load_config(cwd)["enabled"]:
        return
    cl.append_history(cwd, {
        "ts": cl.now_iso(), "event": "session_end",
        "reason": inp.get("reason") or "unknown",
        "finalHealth": cl.load_health(cwd),
    })


try:
    main()
except Exception:
    pass
sys.exit(0)
