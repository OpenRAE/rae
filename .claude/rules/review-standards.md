## Review fix standards

- Fix ALL issues found during code review and security review.
  Do not categorize issues as "defer" or "low priority" to avoid
  doing work. Repair the cause and verify the fix.

- Never recommend deferring fixes because of "time constraints",
  "scope", or "follow-up PRs". Repair the cause and verify the fix.

- Consult the user when a fix needs a decision about architecture, security,
  authority, or a material scope change.
  Follow the current workflow approval gates.

- Do not surface nitpicks about PR titles or descriptions unless
  they are grossly misleading.

- Run only targeted tests locally, including after review repairs.
  Full verification runs in CI/CD.
- Release Please owns version and changelog edits.
  Do not require them in a feature PR.
