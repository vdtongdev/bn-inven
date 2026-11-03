# Add Codex memory lookup to Foreman `mem`

## Goal

Make `mem select` search Codex's memory index alongside Foreman's existing user and project memory. Keep the Codex store read-only and preserve the current Claude memory behavior.

## Current behavior

- Foreman derives memory locations from `FOREMAN_HOME` (or the user home) and only loads `.claude/memory` and `.claude/projects/<repo>/memory`.
- Codex memory is stored separately under `CODEX_HOME/memories` (or `~/.codex/memories`) and is indexed in `MEMORY.md`; its entries do not use Foreman's frontmatter schema.
- `mem select` currently prints only matches and returns success silently when there are none.

## Design

- Add Codex memory as a third, read-only source for `select`; do not replace either existing source.
- Resolve the root from `CODEX_HOME` when set, otherwise `Path.home() / ".codex"`; read only `memories/MEMORY.md`. Treat a missing index as an empty source.
- Parse the existing Codex index by its headings and bullet entries; do not write, validate, regenerate, or reformat any Codex memory file.
- For Codex entries, match `--topic` case-insensitively against the entry title and description/keywords. Match `--path` against the normalized repository/path scope recorded by the enclosing memory section. Multiple requested topics or paths retain the current any-match behavior.
- Print Codex results with a `[codex]` source label and enough original index text to identify the topic and its linked rollout notes. Keep Foreman output and ordering unchanged.
- Leave `validate`, `index`, `stale`, and `deprecate` operating only on Foreman-managed entries.

## Work plan

1. Add regression tests for Codex index parsing, topic and path matching, `CODEX_HOME` override/default discovery, missing index behavior, `[codex]` attribution, and read-only behavior. Confirm existing Claude selection tests still pass.
   - Agent: implementer
2. Implement the Codex read-only `select` source and its parsing/matching helpers. Keep all non-select commands scoped to Foreman memory.
   - Agent: implementer
3. Independently review the diff; verify the new regression tests fail against the base implementation and pass after the change, then run the Foreman test suite.
   - Agent: verifier

Acceptance: tests demonstrate matching Codex entries and preserved Claude results; Codex memory files remain byte-for-byte unchanged; the full Foreman suite passes.

## Access and approval checkpoint

The Foreman source checkout is `C:\Users\Asus ROG\projects\foreman`, outside the current writable workspace (`C:\Users\Asus ROG\projects\bn-inven`). The current session also received Git's dubious-ownership refusal for that checkout. Before implementation, create an isolated worktree/branch without changing `main`, and obtain the required write approval for the Foreman checkout. Do not patch the installed plugin cache as a substitute for changing and verifying the source repository.

## Selected facts and traps

- `mem select --topic codex --topic memory` returned no Foreman memory entries.
- The installed CLI currently reads `~/.claude/memory` and `~/.claude/projects/<slug>/memory`; Codex's store has a distinct index and formats.
- Do not modify anything under `~/.codex/memories`; it is user-owned data. Codex lookup must be read-only.
- Before Foreman changes, the user preference is to use an isolated branch/worktree, write a plan, wait for approval, and keep `main` clean.
