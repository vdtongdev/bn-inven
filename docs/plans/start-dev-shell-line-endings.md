# Fix WSL startup script line endings

## Objective

Make `bash ./start-dev.sh` work in the active WSL worktree and keep Windows Git checkouts from converting shell scripts to CRLF.

## Diagnosis

`start-dev.sh` is committed with LF endings but this worktree has CRLF because `core.autocrlf=true` and no `.gitattributes` policy exists. Bash reads the carriage return after `set -Eeuo pipefail` as part of the option name and exits before startup.

## Implementation sequence

1. Add a focused regression check that reads `start-dev.sh` as bytes and fails when CRLF line endings are present. Confirm it fails in the current worktree.
2. Add a minimal `.gitattributes` rule for shell scripts (`*.sh text eol=lf`) and normalize `start-dev.sh` in the worktree. Keep the script's startup commands unchanged.
3. Run the regression check and confirm `git ls-files --eol start-dev.sh` reports LF in both index and worktree.
4. From the WSL worktree root, run `bash ./start-dev.sh`; confirm it passes the line 2 `pipefail` setup and proceeds into normal dependency/startup output. Report any later unrelated environment failure separately.

## Acceptance

- Regression check fails before the line-ending fix and passes after it.
- `bash ./start-dev.sh` no longer exits with `invalid option name` on `pipefail`.
- Existing API, extraction worker, and frontend startup behavior remains unchanged.
- Main checkout remains untouched.

## Risks and constraints

- A line-ending test should target the launcher or the `*.sh` policy only; it must not alter shell behavior.
- Startup proceeds to dependency preparation, database migration, and service launch. Use the user's active development worktree and report any later startup failure accurately.
