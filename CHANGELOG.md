# Changelog

## v0.2.0 (2026-11-11)

- `/setup`: the project's configuration made and changed in chat, in rounds of options
  (`crew.py config show|discover|apply`); `apply` validates the draft, prints the changes, keeps
  `project.json.prev` and writes through a rename.
- New `project.json` fields: `commit_rules` and `repos` (the table of linked GitHub repositories,
  with checks as presets or argument lists, pushers and tags).
- The door: `/push <repo>` and `/release <repo> vX.Y.Z` (`crew.py push|tag`), with the checks, the
  fast-forward, the visibility and commit-rules checks, the tag rules, and a log.
- PreToolUse guards for Bash and the file tools: the door's line and session, `git push` and
  `git tag` in the table's repositories, remote and GitHub deletes, writes to the configuration;
  every ask is a refusal while a night is on; the git rules say nothing in a folder with no project file, but the configuration's protection does not depend on it.
- The door and `config` find the caller by the process ancestry alone (no `--name` or `--session-id`),
  the door checks pushers itself and refuses a public repository at night, and the project is the
  process's folder.
- The guard holds any line naming the plugin's scripts to exact shapes, guards the whole crew home,
  resolves where a `git push` goes, and looks inside shells, heredocs, substitutions and aliases.
- The guard refuses any write into Claude Code's registry of sessions; the door trusts a registry file
  only when its procStart matches the live process.
- Fix: a session id with two registry files takes the one whose pid is alive, then the newest.
- Docs: a tab keeps the conversations it left with `/clear` and writes their title back when it
  exits, so a retention shorter than a tab's life brings them back as empty files under the
  session's name (README, design fact 9).

## v0.1.0 (2026-10-22)

- Size hook: warns the session, then the user, when a transcript passes `warn_mb` and
  `tell_user_mb`; reminds the user of a pending handoff.
- Unattended nights: a size ceiling instead of a warning while a night runs, a warning when a night
  is started in a heavy session, and a warning when it is started in a permission mode that would
  stop it (N3).
- `/handoff` writes a handover under `~/.session-crew/<slug>/<name>/`; `/migrate` resumes it in a
  fresh conversation, or recovers from the old transcript after a crash.
- Rename hook for the new-tab fallback: gives a name to the new session, stopping an idle older
  session of the same name only when its start time checks out.
- SessionStart hook announces a pending handoff after `/clear`.
- Skills readable by GitHub Copilot in VS Code (script called by hand; no hooks there yet).
