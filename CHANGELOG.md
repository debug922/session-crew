# Changelog

## 0.2.0 (unreleased)

- `/setup`: the project's configuration made and changed in chat, in rounds of options
  (`crew.py config show|discover|apply`); `apply` validates the draft, prints the changes, keeps
  `project.json.prev` and writes through a rename.
- New `project.json` fields: `commit_rules` and `repos` (the table of linked GitHub repositories,
  with checks as presets or argument lists, pushers and tags).
- The door: `/push <repo>` and `/release <repo> vX.Y.Z` (`crew.py push|tag`), with the checks, the
  fast-forward, the visibility and commit-rules checks, the tag rules, and a log.
- PreToolUse guards for Bash and the file tools: the door's line and session, `git push` and
  `git tag` in the table's repositories, remote and GitHub deletes, writes to the configuration;
  every ask is a refusal while a night is on; nothing is said in a folder with no project file.
- Fix: a session id with two registry files takes the one whose pid is alive, then the newest.

## 0.1.0 (unreleased)

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
