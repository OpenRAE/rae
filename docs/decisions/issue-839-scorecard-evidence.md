# Issue #839 Scorecard and Action-Admission Evidence

Date: 2026-09-11

Requirement: GOV-913. Issue: #839.

## Live Scorecard evidence

The repository has successful public Scorecard evidence, so the README badge is
enabled. The evidence predates this delivery branch and proves the incumbent
scheduled service path; it does not claim that this unmerged policy revision has
already executed.

- Scheduled workflow run
  [34099892356](https://github.com/OpenRAE/rae/actions/runs/34099892356)
  completed successfully for `main` commit
  `056fe65c57d1489489cff978019011f284106ba9` on 2026-09-07. Job
  `101671658567` completed the harden-runner, checkout, Scorecard, artifact, and
  code-scanning steps successfully.
- The run retained the `scorecard-results` artifact (16,392 bytes, five-day
  workflow retention) at the same commit. Code-scanning analyses
  `1734572985`, `1734572968`, and `1734572949` report Scorecard 5.5.0 at that
  commit.
- The public badge endpoint
  `https://api.securityscorecards.dev/projects/github.com/OpenRAE/rae/badge`
  returned HTTP 200 with SVG media type during the 2026-09-11 review.
- Harden-runner remained in `audit` mode. Observed outbound service classes
  included GitHub API/source/action endpoints, bestpractices.dev, OSS-Fuzz
  build logs, deps.dev, OSV, Scorecard publication, and Sigstore Fulcio, TUF,
  and Rekor endpoints. The exact reviewed origin set is recorded in
  `implementations/tooling/actions-policy.json`.

The workflow continues to run weekly at `17 3 * * 1`, publishes Scorecard
results, uploads SARIF even after an earlier step fails, retains the artifact
for five days, and sends SARIF to GitHub code scanning. Manual dispatch was
removed so the write-scoped job can execute only for the scheduled,
branch-protection, or protected-`main` push events.

## Admission and trust boundary

The v2 action policy separates exact action-source commits, action-transitive
payload/host/service closure, and normalized workflow job/use-site contexts.
The policy records each effective permission set, credential class, runner
profile, allowed origin, literal action input, cache role, and artifact role.
Nested composite-action revisions are separate source records. Service-managed
inputs are bounded nonclaims with independent owner/reviewer roles and a review
date; they are not represented by invented digests.

The Scorecard Docker action resolves `ghcr.io/ossf/scorecard-action:v2.4.4` to
OCI manifest digest
`sha256:ae5104dd3cc28466ebeb11144354be4cac4b7ff829654f9fab89021d71c46670`
(4,281 manifest bytes). The Sonar action's reviewed metadata selects scanner
8.1.0.6389 for Linux x64 with archive SHA-256
`bb8f709f9cb73352f8d1260a3b3c506c0f41146754bc630762c126d795499d0b`
and size 61,626,644 bytes. Both identities are recorded once in the artifact
lock and referenced from the action closure. Neither upstream supplies a
publisher signature admitted here, so both authenticity states are recorded as
`absent-reviewed`, not `verified`.

Candidate and fork-capable jobs have read-only repository permissions, no
enterprise secret or OIDC credential, no trusted cache write, and no promotion
or publication authority. Run-scoped candidate artifacts remain explicitly
untrusted. Sonar runs only for protected pushes. Manual release recovery must
select `refs/heads/main` before its privileged dependency chain can run, and
PyPI publication still passes through the protected `pypi` environment.

## External controls and nonclaims

The repository gate runs after GitHub has fetched an action. It therefore
cannot replace the GitHub Actions allow policy, protected branch/ruleset,
environment protection, or human review of Dependabot source and payload
changes. Those hosted control-plane settings remain external enforcement and
must be checked operationally.

GitHub-hosted Actions, caches, artifacts, Pages, code scanning, OIDC,
Dependabot, SonarCloud, Scorecard publication, PyPI, container registries, and
the StepSecurity service do not work offline. Disconnected execution must
report those controls as unevaluated. This implementation adds no custom
downloader, HTTP/TLS/redirect stack, runner, or replacement service.
