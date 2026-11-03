# Issue 684: public release controls and acceptance preflight

## Decision

Issue #684 checks the current public release path. It grants no right to replace it.
On 2026-09-19, the maintainer confirmed that this issue needs no new public release.
This replaces the issue-body checks for a published build, public byte comparison, or release-run record.
No release is created for this issue.
Release Please remains the sole version and changelog owner.
`.github/workflows/release-please.yml` remains the sole release workflow.
PyPI Trusted Publishing and the separate GitHub Release job remain the upload boundaries.
Change these only to fix a concrete defect with focused tests.

The public tag `v5.0.0` predates `c7450806`, which added the #1227 same-byte upload and repair work.
Its public provenance can prove who published those bytes.
It cannot prove that the current workflow ran.
Assess the current workflow through its job graph and focused tests.
Do not claim that a later public release ran it.

## Canonical boundaries to reuse

- `release-please-config.json`, `.release-please-manifest.json`,
  `implementations/python/packages/raes/_version.py`, the Conventional Commit PR
  title, and root `CHANGELOG.md` are one version/release-note contract. Do not add
  another version source, changelog fragment system, release classifier, or
  retired package identity.
- `.github/workflows/canonical-verification.yml` owns exact-commit repository
  verification. The release-only `integration-docker-release` job adds the
  required real-container lane; neither should be copied into an acceptance
  script.
- `tools/python_closure.py`, `tools/python_closure_profiles.py`, and the reviewed
  `public-linux-x86_64-cp312-all-extras` profile own constrained build and
  installed-distribution smoke environments. The release workflow's artifact
  smokes are assessed as code and tests here, not as a public-PyPI consumer run.
- `raes_contracts.corpus`, `raes --version`, and `raes conformance backend
  --profile provisioning-only` are the existing consumer probes. Reuse the
  installed-distribution assertions in `test_corpus_packaging.py`: run outside
  the checkout with `PYTHONPATH`/`PYTHONHOME` absent, prove corpus resolution is
  from `site-packages`, require a passing report, and reject zero cases.
- `tools/release_evidence.py`, `tools/release_evidence_admission.py`, and
  `tools/release_evidence_publication.py` own the release identity, admitted
  subject set, evidence index, publication filename/version correspondence, and
  publisher handoff. The attached `release-evidence-index.json` is the canonical
  distribution digest set. Do not add a second manifest, checksum schema,
  exception hierarchy, or evidence model for #684.
- `implementations/tooling/admission-policy.json` and
  `implementations/tooling/schemas/admission-policy.schema.json` own the approved
  attestation issuer, repository, workflow and reviewer role. `AdmissionError`
  and its stable codes remain the local refusal vocabulary; workflow/API
  failures remain concise shell diagnostics.
- `MAINTAINERS.md`, `GOVERNANCE.md`, the `verify`/`sonar` branch checks, the
  release-PR admin merge convention, the `v*` tag rule, and the `pypi`
  environment are the governance/control surface. Roles named in artifact docs
  are responsibilities of the one maintainer, not extra people.

## Acceptance evidence boundary

Keep this issue's control record separate from the runbook in `docs/explain/releasing.md`.
The record names the publisher shown by public PyPI provenance.
It also records GitHub controls, version rules, the job graph, and focused test results.
Historical `v5.0.0` evidence and source tests do not prove that the current #1227 workflow published a release.
Public metadata cannot reveal private PyPI publisher settings or account tokens.
Record that limit. Do not claim to have inspected them.
Do not commit credentials, raw OIDC claims, cookies, signed URLs, or settings exports.

`docs/explain/releasing.md` should describe the current operator procedure, not
retain first-release setup prose now that releases exist. Replace the pending
publisher instructions with verification of the existing publisher tuple,
record the actual one-maintainer authorization point, and remove the historical
enterprise retention prerequisite. Keep the focused #1227 same-run recovery:
re-run failed jobs while the original Actions artifacts remain available; never
rebuild, overwrite, or move a tag for an existing version.

## Control observations (2026-09-19)

- The public [PyPI project](https://pypi.org/project/raes/) is `raes`.
  The [wheel](https://pypi.org/integrity/raes/5.0.0/raes-5.0.0-py3-none-any.whl/provenance)
  and [sdist](https://pypi.org/integrity/raes/5.0.0/raes-5.0.0.tar.gz/provenance)
  provenance for historical `v5.0.0` each report a GitHub Trusted Publisher
  with repository `OpenRAE/rae`, workflow `release-please.yml`, and environment
  `pypi`. This proves how those files were published, not the current private
  PyPI publisher registration or absence of other project/account tokens.
- The [GitHub `pypi` environment](https://github.com/OpenRAE/rae/settings/environments)
  exposes one deployment branch policy, `main`, and no required human-review
  rule. The active release workflow is `.github/workflows/release-please.yml`;
  only `publish-pypi` combines that environment with `id-token: write`.
- The [branch protection](https://github.com/OpenRAE/rae/settings/branches)
  for both `main` and `dev` requires the named verification/security checks,
  forbids force pushes and deletion, and requires zero approving reviews.
  Active branch rulesets `merge-policy-main` and `merge-policy-dev` require a
  PR and likewise name no independent reviewer. This matches the single
  maintainer in `MAINTAINERS.md` and `GOVERNANCE.md`.
- After maintainer authorization, the active
  [`protect-v-release-tags` ruleset](https://github.com/OpenRAE/rae/rules/23692605)
  targets `refs/tags/v*` and restricts updates and deletions with no bypass
  actors. It does not restrict creation, so Release Please can still create new
  version tags. The rule was read back from the repository ruleset API; no
  release was created to test it.
- The current release workflow contains the exact-SHA verifier, required
  real-container lane, constrained build/smokes, separate attestation and
  admission, and two credentialed publisher jobs. The #1227 recovery tests
  cover same-byte destination reconciliation. These are repository-level
  observations, not an assertion that a post-#1227 release completed.

## Release eligibility behavior probe (2026-09-19)

The release workflow pins `googleapis/release-please-action` to
`45996ed1f6d02564a971a2fa1b5860e934307cf7` (v5.0.0). That action's
package lock pins `release-please` 17.6.0. In a temporary, non-repository npm
installation of that exact library version, invoke the Python strategy's
`buildReleasePullRequest` with the checked-in `changelog-sections` and parsed
single-commit fixtures. Only file-update methods are stubbed to avoid GitHub
and filesystem writes; conventional-commit parsing, changelog generation, and
the release-PR eligibility decision run from Release Please itself. Results:

| Commit type | Release PR candidate? |
| --- | --- |
| `docs`, `chore`, `refactor`, `test`, `ci`, `build`, `style` | No |
| `feat`, `fix`, `perf` | Yes |

This checks the decision made by the pinned library, not a live GitHub release
run. `test_release_workflows.py` locks both the section mapping and action SHA,
so updating either requires the behavior check to be revisited.

## Cross-cutting validation and security gates

The acceptance path crosses the following existing gates:

1. Untrusted PR titles and commit messages pass `tools/check_pr_title.py`.
   Release Please applies the Python release rules. Observe this behavior.
   Do not add a second Conventional Commit parser.
2. A tag must pass the stable-SemVer shape check.
   The bounded annotated-tag walk must resolve it to a full lowercase commit SHA on `main`.
   It must match the numeric draft Release object. Recheck this at each upload boundary.
3. Candidate source passes the shared exact-SHA checks and required real-container gate.
   Neither gate grants upload rights. Build, signing, admission, PyPI upload, and GitHub release each keep their own job.
   Each job keeps only the rights it needs.
4. Check evidence size, shape, digests, and attestations. Reject duplicate keys.
   Only then emit the four shell-safe values for the upload jobs.
   Those jobs check out and run no candidate source.
5. Treat PyPI/GitHub responses and downloaded files as untrusted inputs.
   Require the expected shape and exact file names. Bound read size and time.
   Require regular files, matching versions, and equal SHA-256 digests.
   An absent or unclear response fails closed. It does not mean that the file is absent.
6. Secrets stay in the GitHub/OIDC credential channel.
   Pass `GH_TOKEN` through the environment. PyPI uses short-lived OIDC through the pinned upload action.
   Checkouts do not retain write credentials. No credential appears in process arguments or logs.

The release evidence index and public destination state are not error envelopes
or logging schemas. Preserve `AdmissionError` codes for local admission and
short, non-secret workflow messages for external failures; do not introduce a
parallel structured logger or expose response bodies merely to make the
acceptance record verbose.

## Extensibility seam

Keep Release Please's configured changelog-section mapping as the seam for
commit-type policy. The workflow's existing release coordinate—tag/version,
full SHA, run id/attempt, Release id, and admitted subject records—remains the
seam for a future, separately authorized end-to-end acceptance exercise. Do
not add another release classifier, manifest, or multi-registry framework.

## Non-goals and anti-patterns

- No unauthorized release, test publication, second package, retired-identity
  publication, semantic-release/towncrier restoration, or manual
  version/changelog edit.
- No enterprise artifact host, offline bundle, promotion/quarantine/revocation
  service, backup/DR program, retention/GC service, deployment, or operational
  acceptance matrix.
- No fictional independent approver or deputy. Human governance stays
  single-maintainer; machine credentials and duties stay separated.
- No rebuild for recovery, mutable tag acceptance, `--clobber`, blind
  `skip-existing`, successful-HTTP-as-integrity, or checksum computed only after
  destination upload.
- No public-PyPI consumer smoke is required to close this issue.
- No new release manifest/schema, duplicated digest/validation code, copied
  workflow graph, custom HTTP client, persistence layer, release service, or
  exception/logging framework.

## Release ancestry and version notes

The 10.4.0 run omitted #1811: GitHub returned the 10.3.0 release commit
before the older-dated breaking commit that a subsequent promotion merged.
Release Please 17.6.0 stopped at that release boundary. This is the upstream
[chronological-history limitation](https://github.com/googleapis/release-please/issues/1533),
not a failure to parse `refactor!:` or a changelog-section visibility problem.

The release tooling module `implementations/tooling/release-please/run.cjs`
owns the adapter. Its `useReleaseRange` interface supplies the existing
Release Please SCM iterator with the exact Git ancestry difference.
The range runs from the manifest version's tag to the checked-out main head.
The release boundary follows that range. GitHub still supplies the commit objects and PR metadata,
including commit overrides. An incomplete API scan, a missing tag, a tag
outside main's ancestry, or a moved remote head fails before a release PR write.
The adapter buffers the selected commits before yielding any of them.

The pinned upstream action still creates tags and draft releases. It delegates
release PR maintenance to the same pinned Release Please library, installed
from a committed npm lock with lifecycle scripts disabled. The adapter changes
no commit parsing, version strategy, notes generation, publication authority,
or exact-SHA artifact gates. A read-only workflow job exercises the adapter and
the actual library on PRs before the write-capable job can run on main.
No new ADR or runtime package interface is required.

The #1841 local behavior check also replayed the actual `v10.3.0..v10.4.0`
Git range through the adapter and Release Please 17.6.0: the candidate was
`11.0.0` and its breaking-change notes included #1811. The synthetic regression
first reproduces the empty candidate from the chronological scan, then checks
the corrected major candidate. Replacing the adapter with the chronological
iterator makes that regression fail. No GitHub release or registry publication
was made by these checks.
