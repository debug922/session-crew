---
name: handoff
description: Write the handover of this long-lived session so a fresh conversation can resume it with /migrate. Use when the size hook says the session is heavy, or when the maintainer asks for a handoff.
argument-hint: "[--name NAME]"
---

# /handoff

Write the handover of this session, then tell the maintainer how to resume it.

1. Close the item under way if it can be closed in a few minutes; otherwise say where it stands.
2. Write the body in Markdown with exactly these four sections, in this order:
   - `## Work under way`: the item, its branch or worktree, what is done and what is not, in a few
     lines.
   - `## His last requests and decisions`: the maintainer's own words, quoted, for each request and
     decision still in force. Quote; do not paraphrase.
   - `## What remains`: the next steps, in order, with the first one stated so a fresh session can
     start on it.
   - `## Where things are`: branches, unpushed commits, worktrees, run folders, files in progress.
   Never copy the memory: point to the file that holds a fact. In a kcalloc session also add the
   report that `guidelines/agents.md` section 9 asks for.
3. Save it by piping the body to the script (add `--name NAME --cwd DIR` when running under
   Copilot, which has no session registry):

   ```
   python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/crew.py" handoff save <<'HANDOFF'
   ## Work under way
   ...
   HANDOFF
   ```

   The script refuses a body with a missing section and prints the path of the file it wrote.
4. Tell the maintainer, in his language: type `/clear` and then `/migrate`.
