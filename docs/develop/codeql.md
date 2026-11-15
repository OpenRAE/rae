# Code scanning across branches

CodeQL default setup uses one language list for the whole repository.
Main and dev contain the release helper's JavaScript source.
Go cutover has no JavaScript source.
The shared list makes its JavaScript scan fail before analysis.

The CodeQL workflow uses the PR base or push branch to select languages.
It also runs on each `dev` merge group, because default setup does not (ADR-122).
Actions and Python scans run on all three branches.
JavaScript scans run on main and dev.
The current Go compiler, analyzer, Sonar and OSV checks stay required.
Update this language matrix as part of the hard cutover.

The workflow uses pinned GitHub actions and the default security query suite.
Pull request source flows through CodeQL to the existing GitHub scan store.
The token is read-only except for scan result publication in the analysis job.
Checkout stores no credentials. The job needs no application secrets.
Use the pull request event, not the pull request target event.

The workflow policy admits this token only in the CodeQL analysis job.
That job may run only pinned checkout, CodeQL init and CodeQL analyze actions.
It may not add command steps, build source code or acquire other write scopes.

## Rollout

1. Review the workflow on dev and in the Go cutover PR.
   Land the dev copy and promote it to main.
   Leave CODEQL_ADVANCED_ENABLED unset and default setup active during staging.
   This gate prevents advanced uploads while default setup rejects them.
   Staged jobs use distinct check names to keep live scan results visible.
   Hold other Go cutover merges until its workflow PR passes the new scans.
2. Switch CodeQL from default to advanced setup.
   Set CODEQL_ADVANCED_ENABLED to true to enable the replacement.
3. Check branch baselines and the current heads of open PRs.
   Enable the CodeQL workflow if GitHub disabled it during default setup.
   Use its manual trigger on main and dev to start baseline scans.
   Refresh the Go cutover PR head to discard stale default-setup check results.
   Verify its replacement scans before merging it as the first cutover change.
   That merge adds the workflow to the protected Go branch for future scans.
   Keep the required CodeQL and analysis checks in place.
4. If a replacement scan fails, unset CODEQL_ADVANCED_ENABLED.
   Restore default setup, retain the failure evidence, and fix the workflow.

The dev change reaches main through the existing promotion PR.
The Go cutover copy travels with the module verification change.
Activate after the main and dev copies land and the cutover copy is reviewed.
Do not merge a Go cutover change that lacks the replacement workflow.

[GitHub workflow configuration](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options)
and [advanced setup](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configuring-advanced-setup-for-code-scanning)
define the supported configuration.
