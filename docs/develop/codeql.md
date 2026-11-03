# Code scanning across branches

CodeQL default setup uses one language list for the whole repository.
Main and dev contain the release helper's JavaScript source.
Go cutover has no JavaScript source.
The shared list makes its JavaScript scan fail before analysis.

The CodeQL workflow uses the PR base or push branch to select languages.
Actions and Python scans run on all three branches.
JavaScript scans run on main and dev.
The current Go compiler, analyzer, Sonar and OSV checks stay required.
Update this language matrix as part of the hard cutover.

The workflow uses pinned GitHub actions and the default security query suite.
Pull request source flows through CodeQL to the existing GitHub scan store.
The token is read-only except for scan result publication in the analysis job.
Checkout stores no credentials. The job needs no application secrets.
Use the pull request event, not the pull request target event.

## Rollout

1. Land the reviewed workflow on dev, main and go-cutover.
   Leave CODEQL_ADVANCED_ENABLED unset and default setup active during staging.
   This gate prevents advanced uploads while default setup rejects them.
   Staged jobs use distinct check names to keep live scan results visible.
2. Switch CodeQL from default to advanced setup.
   Set CODEQL_ADVANCED_ENABLED to true to enable the replacement.
3. Check branch baselines and the current heads of open PRs.
   Enable the CodeQL workflow if GitHub disabled it during default setup.
   Use its manual trigger on main, dev and go-cutover to start baseline scans.
   Keep the required CodeQL and analysis checks in place.
4. If a replacement scan fails, unset CODEQL_ADVANCED_ENABLED.
   Restore default setup, retain the failure evidence, and fix the workflow.

The dev change reaches main through the existing promotion PR.
The Go cutover copy travels with the module verification change.
Activate only after the reviewed copies have landed.

[GitHub workflow configuration](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options)
and [advanced setup](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configuring-advanced-setup-for-code-scanning)
define the supported configuration.
