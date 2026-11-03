# Go integration branch admission

## Design

GitHub owns branch admission. An active `merge-policy-go-cutover` ruleset matches
only `refs/heads/go-cutover`. It requires pull requests and successful checks.
The existing legacy protection remains in place. Its administrator enforcement,
force-push prohibition, deletion prohibition, and non-strict check policy remain.

No bypass actors are configured. Administrators must meet the checks.
An administrator can change repository settings; that authority remains a residual risk.
The maintainer selects each merge manually. Zero required review approvals preserve
the single-maintainer model. Automatic merging remains disabled.

Use the existing workflow graph without copying its commands or module inventory.
`verify` covers mutation, architecture, and parity through the canonical aggregate.
`sonar` remains a separate quality check. Require the observed security, compatibility,
fuzz, and PR-policy contexts separately. Bind each context to its observed GitHub App.
Keep the existing non-strict base-update policy. A new head still needs its own checks.

## Security and data flows

```mermaid
flowchart LR
    M[Maintainer] -->|Authenticated settings request| G[GitHub administration API]
    G -->|Exact branch policy| R[(GitHub rule store)]
    P[Contributor] -->|Proposed commits| PR[Pull request]
    PR -->|Head and test merge revisions| A[GitHub Actions]
    A -->|App-bound check conclusions| C[(GitHub check store)]
    R -->|Required PR and contexts| E[GitHub admission]
    C -->|Current revision conclusions| E
    M -->|Manual merge request| E
    E -->|Admitted commits| B[(go-cutover)]
```

The API credential crosses the local host boundary through existing CLI authentication.
Do not record credentials. The rules and check stores cross the contributor trust boundary
at admission. Required PRs prevent direct updates. App bindings reduce check impersonation.
Existing workflow review and base-loaded PR validators protect the check producers.
The aggregate rejects failed, cancelled, or unexpectedly skipped dependencies.
GitHub can accept neutral or skipped individual checks; document this platform limitation.

Read back the effective rules and legacy protection through the API.
Observe a mergeable, non-draft PR with a failed or pending required check and blocked merge state.
Conflicts alone do not prove check enforcement. Never attempt a merge as a test.

## Existing owners and limits

The preflight identifies the canonical workflow, security, architecture, and parity owners.
No product module, public interface, schema, or runtime architecture changes.
The native ruleset is the policy model; no reconciliation service is needed.
ADR-014 and the existing Go ADRs remain authoritative and need no new decision.
Go push Sonar guards exclude this branch; same-repository PR analysis supplies admission evidence.
Fork and Dependabot secret restrictions remain in force.

## References

- [GitHub REST rules API](https://docs.github.com/en/rest/repos/rules), current REST documentation:
  Create a repository ruleset; Get rules for a branch. Defines native fields and effective rules.
- [GitHub branch protection](https://docs.github.com/en/rest/branches/branch-protection), current REST documentation:
  Get branch protection. Defines the incumbent protection evidence.
- [Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches),
  Require status checks. Defines merge admission and administrative authority.

The official STE website returned HTTP 403 during research. The prose uses short,
direct sentences; this is not a claim of certified STE compliance.
