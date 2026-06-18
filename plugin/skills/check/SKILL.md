---
name: check
description: Opt-in, model-based context check — verify you can still recall the injected canaries and (optionally) that you are still honoring project instructions. Visible and consumes a turn by design.
---

This is the one intentionally model-based check. It is visible and uses a turn —
that is by design. Perform these steps in order:

1. **Recall first, before reading any file.** From your current conversation
   context only, list every `[hallucinating-canary]` session-anchor token you were
   instructed to retain. Do NOT read `session.json` before answering — that
   would defeat the check.

2. **Get ground truth.** Now read `.claude/hallucinating-canary/session.json` and take
   its `canaries` array as the authoritative list.

3. **Report functional survival.** State how many anchors you recalled correctly
   in step 1 versus the ground-truth total (e.g. "recalled 3/3"). If any were
   missing or wrong, the live context has functionally drifted — recommend the
   user `/compact` deliberately or restart the relevant context.

4. **Optional instruction adherence.** If the user passed instruction text (or
   `.hallucinating-canary.json` lists tracked instructions), briefly assess whether
   your recent responses still honor them (e.g. concision, Markdown, no emojis).

Keep the report to a few lines. Do not modify any state files.
