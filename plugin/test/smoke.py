#!/usr/bin/env python3
"""End-to-end smoke test: drives the real hook/statusline/CLI scripts via
subprocess with simulated stdin and a synthetic transcript that contains a
compaction boundary. Verifies the post-compaction live-window survival logic.

Run: python3 plugin/test/smoke.py
"""

import json
import os
import subprocess
import sys
import tempfile

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin")
BIN = os.path.abspath(BIN)
PY = sys.executable

failures = []


def check(name, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + name + (("  -- " + detail) if detail and not cond else ""))
    if not cond:
        failures.append(name)


def run(script, stdin_obj, cwd):
    p = subprocess.run(
        [PY, os.path.join(BIN, script)],
        input=json.dumps(stdin_obj),
        cwd=cwd, capture_output=True, text=True,
    )
    return p.stdout, p.stderr, p.returncode


def main():
    proj = tempfile.mkdtemp(prefix="cc-smoke-")
    tpath = os.path.join(proj, "transcript.jsonl")
    print("project:", proj)

    # 1. SessionStart (fresh)
    out, err, rc = run("hook_session_start.py", {
        "cwd": proj, "session_id": "s1", "source": "startup",
        "hook_event_name": "SessionStart",
    }, proj)
    check("session-start exits 0", rc == 0, err)
    payload = json.loads(out) if out.strip() else {}
    ac = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
    check("session-start injects additionalContext", "[hallucinating-canary]" in ac, out)

    session = json.load(open(os.path.join(proj, ".claude/hallucinating-canary/session.json")))
    canaries = session["canaries"]
    check("3 canaries generated", len(canaries) == 3, str(canaries))
    check("canaries appear in injection", all(c in ac for c in canaries))

    # Auto-init: the hook (not a command) created config, gitignore, statusLine.
    check("hook auto-created config file", os.path.exists(os.path.join(proj, ".hallucinating-canary.json")))
    gi = open(os.path.join(proj, ".gitignore")).read() if os.path.exists(os.path.join(proj, ".gitignore")) else ""
    check("hook auto-added gitignore entry", ".claude/hallucinating-canary/" in gi)
    slp = os.path.join(proj, ".claude", "settings.local.json")
    sl0 = json.load(open(slp)) if os.path.exists(slp) else {}
    check("hook auto-wired statusLine", sl0.get("statusLine", {}).get("type") == "command", json.dumps(sl0))

    # 2. Idempotency: same session_id -> no regeneration
    run("hook_session_start.py", {"cwd": proj, "session_id": "s1", "source": "resume"}, proj)
    session2 = json.load(open(os.path.join(proj, ".claude/hallucinating-canary/session.json")))
    check("same session_id keeps canaries", session2["canaries"] == canaries)

    # 3. Build a synthetic transcript with a compaction boundary.
    #    Pre-compaction: all 3 canaries present (the methodological trap).
    #    Summary entry: only canaries[0].  Post: canaries[1].  -> canaries[2] LOST.
    lines = [
        {"type": "user", "content": "hello " + " ".join(canaries)},
        {"type": "assistant", "content": "noted anchors " + " ".join(canaries)},
        {"type": "summary", "isCompactSummary": True,
         "content": "Summary so far. Retained anchor: " + canaries[0]},
        {"type": "assistant", "content": "continuing; still have " + canaries[1]},
    ]
    with open(tpath, "w") as f:
        for ln in lines:
            f.write(json.dumps(ln) + "\n")

    # 4. UserPromptSubmit refresh -> recompute health over live window
    out, err, rc = run("hook_user_prompt.py", {"cwd": proj, "transcript_path": tpath}, proj)
    check("user-prompt exits 0", rc == 0, err)
    check("user-prompt emits nothing", out.strip() == "", repr(out))
    health = json.load(open(os.path.join(proj, ".claude/hallucinating-canary/health.json")))

    check("survival counts live window only (2/3)",
          health["canariesPresent"] == 2 and health["canariesTotal"] == 3,
          json.dumps(health))
    check("lost canary identified", health["missing"] == [canaries[2]], str(health["missing"]))
    check("compaction detected (count=1)", health["compactions"] == 1, str(health["compactions"]))
    check("survival score 67%", health["survivalScore"] == 67, str(health["survivalScore"]))
    check("level is warning", health["level"] == "warning", health["level"])

    # 5. Statusline render
    out, err, rc = run("statusline.py", {
        "cwd": proj, "transcript_path": tpath,
        "context_window": {"used_percentage": 50},
    }, proj)
    check("statusline exits 0", rc == 0, err)
    check("statusline shows warning emoji + note", out.startswith("🟡") and "lost after compaction" in out, repr(out))
    print("    statusline ->", out)

    # 6. PreCompact + SessionEnd
    _, err, rc = run("hook_pre_compact.py", {"cwd": proj, "transcript_path": tpath, "trigger": "auto"}, proj)
    check("pre-compact exits 0", rc == 0, err)
    _, err, rc = run("hook_session_end.py", {"cwd": proj, "reason": "exit"}, proj)
    check("session-end exits 0", rc == 0, err)

    hist = [json.loads(l) for l in open(os.path.join(proj, ".claude/hallucinating-canary/history.json")) if l.strip()]
    events = [h["event"] for h in hist]
    check("history records all events",
          {"session_start", "pre_compact", "session_end"}.issubset(set(events)), str(events))

    # 7. CLI status
    p = subprocess.run([PY, os.path.join(BIN, "cli.py"), "status"], cwd=proj, capture_output=True, text=True)
    check("cli status exits 0", p.returncode == 0, p.stderr)
    check("cli status reports 2/3", "2 / 3" in p.stdout, p.stdout)
    print("    --- cli status ---")
    for ln in p.stdout.splitlines():
        print("    " + ln)

    # 7b. init wires statusLine into .claude/settings.local.json (fresh dir)
    proj2 = tempfile.mkdtemp(prefix="cc-smoke-init-")
    p = subprocess.run([PY, os.path.join(BIN, "cli.py"), "init"], cwd=proj2, capture_output=True, text=True)
    check("cli init exits 0", p.returncode == 0, p.stderr)
    sl_path = os.path.join(proj2, ".claude", "settings.local.json")
    sl = json.load(open(sl_path)) if os.path.exists(sl_path) else {}
    cmd = sl.get("statusLine", {}).get("command", "")
    check("init installs statusLine", sl.get("statusLine", {}).get("type") == "command", json.dumps(sl))
    check("statusLine uses absolute path to statusline.py",
          "statusline.py" in cmd and os.path.isabs(cmd.split('"')[1] if '"' in cmd else ""), cmd)

    # non-clobber: a pre-existing different statusLine is preserved
    proj3 = tempfile.mkdtemp(prefix="cc-smoke-clob-")
    os.makedirs(os.path.join(proj3, ".claude"))
    pre = {"statusLine": {"type": "command", "command": "echo mine"}}
    json.dump(pre, open(os.path.join(proj3, ".claude", "settings.local.json"), "w"))
    p = subprocess.run([PY, os.path.join(BIN, "cli.py"), "init"], cwd=proj3, capture_output=True, text=True)
    after = json.load(open(os.path.join(proj3, ".claude", "settings.local.json")))
    check("existing statusLine NOT clobbered", after["statusLine"]["command"] == "echo mine", json.dumps(after))
    check("init reports manual-merge guidance", "manually" in p.stdout, p.stdout)

    # 8. Disabled => statusline silent
    cfgp = os.path.join(proj, ".hallucinating-canary.json")
    json.dump({"enabled": False}, open(cfgp, "w"))
    out, _, _ = run("statusline.py", {"cwd": proj, "context_window": {"used_percentage": 10}}, proj)
    check("disabled statusline is silent", out.strip() == "", repr(out))

    print()
    if failures:
        print("RESULT: {} FAILURE(S): {}".format(len(failures), ", ".join(failures)))
        sys.exit(1)
    print("RESULT: ALL PASS")


main()
