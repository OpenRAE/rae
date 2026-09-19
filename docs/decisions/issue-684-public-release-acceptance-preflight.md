# Issue 684: public release controls and acceptance preflight

## Decision

Issue #684 checks the incumbent public release path, not authority to replace
it. The maintainer clarified on 2026-09-19 that a new public release is not an
acceptance prerequisite. The issue-body criteria requiring an actual published
distribution, public byte comparison, or a release-run record are superseded;
no release is created for this issue. Release Please remains the sole version and
changelog owner; `.github/workflows/release-please.yml` remains the sole release
orchestrator; PyPI Trusted Publishing and the separate GitHub Release publisher
remain the publication boundaries. Change those surfaces only for a concrete
defect covered by focused tests.

The current public tag `v5.0.0` predates `c7450806`, which introduced the
narrowed #1227 same-byte publication and recovery work. Its public provenance
can establish the historical publisher identity, but not execution of the
current workflow. The current workflow is assessed through its dependency
graph and focused tests, without asserting that a later public release ran it.

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

Keep the issue's observed-control record separate from the reusable operator
runbook in `docs/explain/releasing.md`. It records the public PyPI provenance
publisher identity, GitHub environment and branch controls, configured
Conventional Commit classification, workflow dependencies, and focused test
results. Do not turn historical `v5.0.0` evidence or source tests into a claim
that the current #1227 workflow completed a public release. Private PyPI
publisher settings and account tokens cannot be inferred from public metadata;
record that visibility limit rather than claiming they were inspected. Do not
commit credentials, raw OIDC claims, cookies, signed URLs, or settings exports.

`docs/explain/releasing.md` should describe the current operator procedure, not
retain first-release setup prose now that releases exist. Replace the pending
publisher instructions with verification of the existing publisher tuple,
record the actual one-maintainer authorization point, and remove the historical
enterprise retention prerequisite. Keep the focused #1227 same-run recovery:
re-run failed jobs while the original Actions artifacts remain available; never
rebuild, overwrite, or move a tag for an existing version.

## Read-only control observations (2026-09-19)

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
- The repository ruleset API listed those two branch rulesets and no active
  tag-targeting ruleset. The operator runbook still requires `v*` tag
  protection before a future release. Adding that live administrative control
  needs a separate maintainer decision; this document does not claim it exists.
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

1. Untrusted PR titles and commit messages pass `tools/check_pr_title.py`; Release
   Please applies the configured Python release rules. Acceptance observes this
   behavior and does not implement a second Conventional Commit parser.
2. A tag must pass the stable-SemVer shape check, resolve through the bounded
   annotated-tag walk to a full lowercase commit SHA, belong to `main`, and match
   the numeric draft Release object. Revalidate this identity at each existing
   publication boundary.
3. Candidate source passes the reusable exact-SHA verifier and required
   real-container gate without publication authority. Build, signing, admission,
   PyPI publication and GitHub finalization retain their current separate jobs
   and least-privilege permissions.
4. Release evidence remains size-bounded, duplicate-key rejecting, shape-checked,
   digest-bound and attestation-checked before the four shell-safe publisher
   scalars are emitted. Publisher jobs check out and execute no candidate source.
5. PyPI/GitHub responses and downloaded files are untrusted inputs: require the
   expected response shape, bounded and time-limited reads, exact filename set,
   regular files, version correspondence and SHA-256 equality. An
   unavailable/ambiguous response fails closed and is not interpreted as
   absence.
6. Secrets stay in the GitHub/OIDC credential channel. `GH_TOKEN` is passed by
   environment, PyPI uses short-lived OIDC through the pinned publisher action,
   checkouts do not persist write credentials, and no credential appears in
   process arguments or diagnostics.

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
