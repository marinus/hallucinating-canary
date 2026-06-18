#!/usr/bin/env python3
"""Inspect live HallucinatingCanary state for a project, and re-run the survival
analysis against the real transcript on disk. Use it before/after a /compact.

Usage:  python3 plugin/test/inspect.py [PROJECT_DIR]   (default: ~/cc-canary-test)
"""

import glob
import json
import os
import sys

BIN = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"))
sys.path.insert(0, BIN)
import canary_lib as cl  # noqa: E402


def find_transcript(project_dir):
    base = os.path.basename(os.path.normpath(project_dir))
    pats = [
        os.path.expanduser("~/.claude/projects/*{}*/**/*.jsonl".format(base)),
        os.path.expanduser("~/.claude/projects/*{}*/*.jsonl".format(base)),
    ]
    hits = []
    for p in pats:
        hits += glob.glob(p, recursive=True)
    hits = sorted(set(hits), key=lambda f: os.path.getmtime(f), reverse=True)
    return hits[0] if hits else None


def main():
    project = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/cc-canary-test")
    print("project:", project)
    session = cl.load_session(project)
    health = cl.load_health(project)

    if not session:
        print("  no session.json yet — run /hallucinating-canary:init and start a session")
        return
    canaries = session.get("canaries", [])
    print("  stored canaries:", ", ".join(canaries))
    print("  health.json    :", json.dumps(health) if health else "(none)")

    t = find_transcript(project)
    print("  transcript     :", t or "(not found under ~/.claude/projects)")
    if not t:
        return

    a = cl.analyze_transcript(t, canaries)
    print("  --- live transcript analysis ---")
    print("    compaction detected :", a["compacted"], "(count={})".format(a["compactions"]))
    print("    canaries present    : {}/{}  (live window only)".format(a["present"], a["total"]))
    if a["missing"]:
        print("    missing             :", ", ".join(a["missing"]))

    # Diagnostic: does ANY entry look like a compaction boundary? If /compact
    # ran but count==0, the is_compaction_summary() heuristic needs adjusting.
    try:
        raw = [json.loads(x) for x in open(t) if x.strip()]
        types = {}
        for e in raw:
            if isinstance(e, dict):
                k = e.get("type", "?")
                types[k] = types.get(k, 0) + 1
        print("    transcript entry types:", json.dumps(types))
        if a["compactions"] == 0:
            print("    NOTE: no boundary matched. If you ran /compact, the heuristic")
            print("          is wrong — paste the entry-type list so we can fix it.")
    except Exception as e:
        print("    (could not summarize entry types:", e, ")")


main()
