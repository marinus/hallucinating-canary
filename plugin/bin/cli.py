#!/usr/bin/env python3
"""OPTIONAL manual tool. The plugin self-initializes inside the SessionStart
hook, so you normally never run this. It exists for users who want to drive
setup or toggling explicitly from their own terminal:

    python3 .../bin/cli.py <init|enable|disable|status>

No Claude Code skill invokes this, so it never causes a permission prompt during
normal use. Config can also just be edited directly in .hallucinating-canary.json.
"""

import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import canary_lib as cl  # noqa: E402


def fmt_ago(iso):
    if not iso:
        return "never"
    try:
        then = datetime.fromisoformat(iso)
        m = round((datetime.now(timezone.utc) - then).total_seconds() / 60)
    except Exception:
        return iso
    if m < 1:
        return "just now"
    if m == 1:
        return "1 minute ago"
    if m < 60:
        return "{} minutes ago".format(m)
    return "{} h ago".format(round(m / 60))


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    cwd = os.getcwd()
    p = cl.paths(cwd)

    if cmd == "init":
        cfg = cl.load_config(cwd)
        added = cl.ensure_gitignore(cwd)
        os.makedirs(p["dir"], exist_ok=True)
        if not os.path.exists(p["config"]):
            cl.save_config(cwd, dict(cl.DEFAULT_CONFIG))
        sl_state, script = cl.wire_statusline(cwd)
        print("HallucinatingCanary initialized (note: this also happens automatically on session start).")
        print("  config:    {}".format(p["config"]))
        print("  state:     {}".format(p["dir"]))
        print("  gitignore: {}".format("entry added" if added else "already present"))
        if sl_state == "installed":
            print("  statusLine: installed in .claude/settings.local.json (restart session to see it)")
        elif sl_state == "present":
            print("  statusLine: already configured")
        else:
            print("  statusLine: a different one exists; add this segment manually:")
            print('             python3 "{}"'.format(script))

    elif cmd in ("enable", "disable"):
        cfg = cl.load_config(cwd)
        cfg["enabled"] = cmd == "enable"
        cl.save_config(cwd, cfg)
        print("HallucinatingCanary {}.".format("enabled" if cfg["enabled"] else "disabled"))

    elif cmd == "status":
        cfg = cl.load_config(cwd)
        health = cl.load_health(cwd)
        session = cl.load_session(cwd)
        if not cfg["enabled"]:
            print("HallucinatingCanary is disabled (set \"enabled\": true in .hallucinating-canary.json).")
            return
        if not health or not session:
            print("No active session state yet — start a session so the SessionStart hook runs.")
            return
        missing = health.get("missing", [])
        miss = "  (missing: {})".format(", ".join(missing)) if missing else ""
        print("HallucinatingCanary — survival {}% ({}) {}".format(
            health["survivalScore"], health["level"], cl.level_emoji(health["level"])))
        print("")
        print("Canaries present : {} / {}{}".format(
            health["canariesPresent"], health["canariesTotal"], miss))
        print("Compactions      : {}".format(health["compactions"]))
        print("Last check       : {}".format(fmt_ago(health.get("lastCheck"))))
        print("")
        print("Note: the statusline % also factors in live context-window pressure.")

    else:
        print("Usage: hallucinating-canary <init|enable|disable|status>")


main()
