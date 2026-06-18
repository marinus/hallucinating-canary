#!/usr/bin/env python3
"""statusLine command: the only persistent UI surface. Blends the stored
(token-free) canary-survival score with live context pressure from stdin, and
prints a single line. Prints nothing when disabled or unconfigured."""

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

    health = cl.load_health(cwd)
    try:
        used = float((inp.get("context_window") or {}).get("used_percentage") or 0)
    except Exception:
        used = 0.0
    pressure = max(0.0, 100.0 - used)
    survival = health["survivalScore"] if health else 100
    score = round(0.5 * pressure + 0.5 * survival)

    level = "healthy"
    if score < cfg["warningThreshold"]:
        level = "warning"
    if score < cfg["criticalThreshold"]:
        level = "critical"

    note = ""
    if health and health["canariesPresent"] < health["canariesTotal"]:
        if level == "healthy":
            level = "warning"
        lost = health["canariesTotal"] - health["canariesPresent"]
        note = "  ({} anchor{} lost after compaction)".format(lost, "s" if lost > 1 else "")

    sys.stdout.write("{} Context {}%{}".format(cl.level_emoji(level), score, note))


try:
    main()
except Exception:
    pass
sys.exit(0)
