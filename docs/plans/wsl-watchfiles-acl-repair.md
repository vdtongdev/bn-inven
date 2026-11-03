# Repair WSL watchfiles directory access

## Goal and authorization

The user authorized restoring read/list access to `backend/.pytest-tmp-audit-red`, whose enumeration previously failed in WSL. Repair only this directory's access; preserve other sessions, services, and port configuration.

## Operational plan

1. Recheck that the exact directory exists and reproduce the WSL enumeration failure. Inspect its Windows ACL and verify the Windows account associated with `C:\Users\Asus ROG` (previously observed as `DESKTOP-QH3L0KQ\Asus ROG`, SID ending `-1001`). Treat previous identity and permission findings as historical until rechecked.
   - Agent: implementer
2. Back up the target ACL if readable. Grant the verified Windows user only the read, list, and execute/traverse access needed. The original exact-folder grant succeeded through standard UAC, but live checks revealed denied descendants and peer pytest temporary trees. Limit the follow-up repair to the closed list below, all immediate `.pytest-tmp-*` artifact directories under `backend`. Manually enumerate regular entries without following reparse points; skip every symlink/junction itself. Reject any path outside the verified backend root. Save a per-entry SDDL backup manifest before any grants. Use explicit non-inheritable `RX` grants on each regular entry, preserving all existing ACEs; this avoids propagating permissions to skipped links. Do not alter repository-wide permissions, grant `Everyone` or `CodexSandboxOffline`, delete anything, take ownership, remove denies, or reset the ACL. Run one standard UAC attempt with an auditable temporary PowerShell script and log every backup/grant result. If UAC is declined or administrator access fails, stop and report the exact blocker.
   - Agent: implementer
3. Independently verify that WSL user `asus_rog` can enumerate the target with Python and that a short, finite watchfiles check no longer raises on it. Review the exact permission change and confirm other sessions and port configuration were preserved.
   - Agent: verifier

## Acceptance

- The before/after directory-enumeration check provides the regression evidence; no app-code changes or new test files are needed for this operational repair.
- WSL can read/list the target, and the finite watcher check reports no denied-path crash.
- Permission changes are confined to the target and the verified intended user; other permissions and service configuration remain intact.
- The report includes exact command output, the ACL backup location if captured, and any remaining access or verification limitation.

## Confirmed follow-up allowlist

The actual Windows user could not list these root directories or their regular descendants. Two already readable verifier artifact roots are excluded. Follow-up grants are limited to regular entries under these exact roots:

- `backend/.pytest-tmp-audit-final-focused`
- `backend/.pytest-tmp-audit-final-full`
- `backend/.pytest-tmp-audit-focused`
- `backend/.pytest-tmp-audit-full`
- `backend/.pytest-tmp-audit-impl`
- `backend/.pytest-tmp-audit-red`
- `backend/.pytest-tmp-live-null-content`
- `backend/.pytest-tmp-nemotron-focused`
- `backend/.pytest-tmp-nemotron-full`
- `backend/.pytest-tmp-nemotron-red`
- `backend/.pytest-tmp-openrouter`

## Selected memory and traps

`mem select --path backend/.pytest-tmp-audit-red --topic permissions --topic WSL` returned BN-Inven WSL notes. Historical `MEMORY.md:128` records that `WATCHFILES_IGNORE_PERMISSION_DENIED=true` did not prevent the denied-path Rust watcher crash and identifies Windows read/list access repair as a durable direction. Historical `MEMORY.md:127` records another session changing the BN-Inven proxy/API setup to port 8001. Recheck filesystem state and leave port work to that session.
