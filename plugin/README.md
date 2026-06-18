# HallucinatingCanary (Claude Code plugin)

An **early-warning signal for response degradation** in long Claude Code
sessions. It plants unique canary anchors at session start, detects the context
loss that drives drift and hallucination, deterministically verifies whether the
anchors survived (by inspecting the transcript — **zero model tokens**), and
shows a health indicator in the statusline.

See `../spec.md` for the full design and `../experiments/canary-survival.md` for
the validation experiment that the proxy depends on.

## What it detects (and what it doesn't)

The canary is a **proxy**. You can't cheaply measure "is Claude hallucinating?",
but you *can* measure the conditions that cause it — chiefly **context loss when
the conversation is compacted/summarized**. A vanished anchor is an early signal
that you've entered the regime where degradation and hallucination become likely.

- ✅ Early warning of **response degradation** (drift / forgotten instructions /
  hallucination), via its leading cause.
- ✅ Context **compaction** (auto-summarization) and whether your anchors
  survived it; plus live context-window **pressure**.
- ⚠️ A **smoke alarm, not a fact-checker** — anchor survival flags the
  *conditions* for degradation, not the correctness of any individual answer.

## Runtime

Hooks and the statusline are **Python 3 (stdlib only)** and invoked as
`python3 …`. Python 3 is present by default on macOS and most Linux; the
verification machine has no Node runtime, which is why Python was chosen over
Node. Windows users need Python 3 on PATH as `python3` (or adjust the command
strings in `hooks.json`/`settings.json` to `python`).

## Layout

```
plugin/
├── .claude-plugin/plugin.json   manifest
├── settings.json                ships subagentStatusLine
├── hooks/hooks.json             SessionStart, PreCompact, UserPromptSubmit, SessionEnd
├── bin/
│   ├── canary_lib.py            shared: state, canaries, transcript live-window analysis
│   ├── hook_session_start.py    plant / re-plant + post-compaction survival
│   ├── hook_pre_compact.py      pre-compaction snapshot
│   ├── hook_user_prompt.py      per-turn token-free survival refresh
│   ├── hook_session_end.py      final history record
│   ├── statusline.py            the indicator
│   └── cli.py                   OPTIONAL manual tool (init|enable|disable|status)
└── skills/                      /hallucinating-canary:check  (opt-in, model-based)
```

## Installation

### From GitHub (Recommended)

Two commands, no cloning:

```bash
claude plugin marketplace add marinus/hallucinating-canary
claude plugin install hallucinating-canary@hallucinating-canary
```

(The same two `/plugin …` commands work inside Claude Code.)

### Clone, then Install

To read or modify the code first:

```bash
git clone https://github.com/marinus/hallucinating-canary.git

claude plugin marketplace add /path/to/hallucinating-canary
claude plugin install hallucinating-canary@hallucinating-canary
```

Replace `/path/to/hallucinating-canary` with your clone's full path.

For a throwaway, session-only run that installs nothing:
`cd hallucinating-canary && claude --plugin-dir ./plugin`.

**No setup command** — the SessionStart hook self-initializes on first session:
- Creates `.hallucinating-canary.json` (config, gitignored)
- Creates `.claude/hallucinating-canary/` (state directory)
- Wires the statusline into `.claude/settings.local.json`

Because settings are read at launch, the indicator appears on your **next**
session.

### Configuration & Usage

Edit `.hallucinating-canary.json` (in your project root) to toggle or reconfigure:

```json
{
  "enabled": true,
  "canaryCount": 3,
  "warningThreshold": 70,
  "criticalThreshold": 40
}
```

`/hallucinating-canary:check` is the only slash command — an opt-in, model-based
recall check for testing context retention.

### Uninstall

To remove the plugin:

**In Claude Code:**
```text
/plugin uninstall hallucinating-canary
```

**From the terminal:**
```bash
claude plugin uninstall hallucinating-canary
```

**Clean up generated files (optional):**
```bash
rm .hallucinating-canary.json
rm -rf .claude/hallucinating-canary/
```

## Zero recurring permission prompts

The always-on monitoring causes **no Claude Code permission prompts**: the four
hooks and the statusline run automatically (configured executables aren't
prompted per run), and first-run setup happens inside the SessionStart hook
rather than via a Bash command. The only thing that consumes a turn is the
explicitly opt-in `/hallucinating-canary:check`. The `cli.py` tool exists for
manual use from your own terminal and is never invoked by a skill.

### How the indicator is wired (important)

Claude Code allows only **one** status line, and **plugins cannot ship a
`statusLine`** (plugin `settings.json` honors only `agent` and
`subagentStatusLine`). So:

- The plugin ships **`subagentStatusLine`** → the indicator shows in the
  subagent panel automatically.
- For the **main** status line, the SessionStart hook writes a `statusLine` into
  the project's `.claude/settings.local.json` (gitignored) using an **absolute
  path** to `statusline.py` (`${CLAUDE_PLUGIN_ROOT}` is not expanded in
  settings.json). It **never clobbers** an existing statusLine; set
  `"autoWireStatusline": false` in config to opt out and compose the segment
  yourself. `statusline.py` emits just the `🟢 Context N%` segment, so it works
  both standalone and as part of a larger line.

## ⚠️ Before trusting the numbers

Two things bound how much you should trust the indicator today:

1. **Boundary heuristic.** The transcript on disk keeps the full pre-compaction
   history, so survival is measured only over the **post-last-compaction live
   window**. The boundary predicate (`is_compaction_summary` in
   `bin/canary_lib.py`) is a heuristic — confirm it against a real transcript
   (experiment Step 0) and tighten it before relying on survival percentages.
2. **Proxy strength.** How well anchor survival actually predicts degradation is
   the core assumption and is still unvalidated — see the experiment.

## Config — `.hallucinating-canary.json`

```json
{
  "enabled": true,
  "canaryCount": 3,
  "canaryPrefix": "HC-",
  "warningThreshold": 70,
  "criticalThreshold": 40,
  "reinjectOnCompact": true,
  "instructionCheck": false,
  "autoWireStatusline": true
}
```
