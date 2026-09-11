# Issue #1216 Development Artifact Lock and Policy Preflight

Date: 2026-09-06

Issue: #1216. Requirement: GOV-913 (MUST, Wave 3). The issue title, body,
acceptance criteria, requirement, and accepted form of ADR-106/ADR-107 are the
implementation contract.

This note records architecture guardrails only. It does not accept either ADR,
implement a lock or validator, qualify a profile, or satisfy T22/T23.

## Accepted design context

Issue #1168 and merged PR #1229 constitute maintainer acceptance of ADR-106,
ADR-107, and the linked package-artifact design set. Issue #1216 therefore
proceeds against that accepted design.

T22 is applied here as verification of the lock, policy, inventory coverage,
and fail-closed discovery introduced by #1216. Existing acquisition paths whose
removal is assigned to #1137 and #1220--#1222 remain visible, owned findings
rather than being hidden by broad allowlists or pulled into this issue. T23's
negative drift cases are fully within #1216.

## Authority boundaries

| Concern | Canonical authority | Boundary for #1216 |
|---|---|---|
| Python project resolution | `implementations/python/pyproject.toml` and `implementations/python/uv.lock` | Reference the owning lock/revision; never copy its package graph, versions, hashes, or markers into the generic lock |
| Python tool/build closure | The `implementations/tooling/python/` lock and constraints selected by ADR-106, owned by #1218 | Record coverage and current selector bindings only; do not anticipate #1218 with a hand-written Python dependency list |
| Generic development inputs | `implementations/tooling/artifacts.lock.json` | Own immutable non-Python raw/installed artifact identity by canonical platform |
| Bootstrap and operating support | `implementations/tooling/profiles/` | Own platform aliases, qualified client/host capabilities, locator classes, supported contexts, and credential/trust-root references, never values |
| GitHub Actions admission | `implementations/tooling/actions-policy.json` plus literal workflow `uses` values | Policy approves exact action identities; workflow YAML remains the executable selector and must match the policy |
| Artifact admission/revocation policy | `implementations/tooling/admission-policy.json` | Own policy ids/revisions, accepted evidence authorities, denials, and freshness rules; a checked-in policy is not an authenticated status snapshot or per-run evidence |
| Vocabulary meaning | Existing `contracts/concept-authority/` artifacts and their validators | Preserve each source's incumbent `source_digest` meaning. Reference it where it already binds raw bytes; otherwise add a distinct tooling-lock identity for retained upstream bytes without redefining the canonical/semantic digest |
| Portable SDL and runtime artifacts | Existing `specs/`, `contracts/`, runtime models, and module-registry policy | Out of scope. Development locks are not `artifact-requirement-v1`, associated-artifact manifests, reusable-asset policy instances, runtime OCI locks, or backend DTOs |

The schemas for the new JSON documents are internal implementation contracts and
belong under `implementations/tooling/`, beside their data. They must be closed,
explicitly versioned, use only locally resolved schema references, and never be
registered in `contracts/schemas/`, `schema_bundle()`, or the schema-publication
manifest. That publication path is reserved for portable ecosystem contracts.
Authority documents and schemas must themselves be Git-tracked regular files;
validation must reject symlinks, submodules, untracked substitutes and paths
outside the checkout before reading them.

Every `I01`--`I16`, `A01`--`A07`, `O01`--`O04`, `C01`--`C04`, `S01`--`S02`, and
`D01` inventory row must have exactly one coverage disposition. Do not create
fake artifact entries for caches, outputs, live services, or excluded domain
assets merely to make the count match. A separate coverage projection may mark
a row locked, delegated to another authority, retained, derived, external,
excluded, or blocked, while still naming its role owner, consumers, trust basis,
availability class, retention class, policy references, and owning follow-up
issue. Policy data names the accountable repository roles documented in the
inventory rather than hard-coding individual maintainers.

## Data and validation contract

The generic identity key is `(artifact_id, canonical_platform_id)`. Platform
aliases such as `amd64`/`x86_64`, `aarch64`/`arm64`, and `Darwin`/`macOS` must
normalize through one profile-owned table before uniqueness or lookup. A
platform-independent entry uses one explicit non-wildcard identity; wildcard
rows that overlap exact rows are ambiguous and must fail.

Each governed document needs a closed `schema_version`. Artifact records keep
version, upstream repository/release/asset identity, bounded raw manifest,
installed manifest, dependency ids, approved locator ids, owner/consumers,
supported profiles, availability and retention classes, license/redistribution
decision, verification references, and separate integrity and authenticity
decisions. A checksum, OCI digest, action commit, Git commit, signature, and
distro repository root are different evidence kinds. Absence of an upstream
signature is an explicit reviewed decision, not an empty signature object and
not a synthesized signature over repository data.

No lock or policy record may carry a shell fragment, argv template, executable
hook, post-install command, arbitrary environment expansion, transport option,
or plugin entry point. Artifact class selects a fixed implementation-owned
adapter; data selects only identity, policy, platform/profile, and bounded local
admission parameters.

Validation has one fail-closed path with these inseparable layers:

1. Repository containment, file type and byte bounds, UTF-8 JSON parsing, and
   duplicate-key rejection reuse `tools.policy.common.safe_repo_path()` and
   `load_bounded_json_object()`.
2. Draft 2020-12 shape/version validation runs from the frozen Python project
   environment, which already locks `jsonschema==4.26.0`, against an explicit
   in-memory registry of the bounded internal schemas. Reject unresolved or
   non-local references; never delegate URI retrieval to the validator. Do not
   add another schema language or validator dependency. The internal schemas
   remain outside the portable contract target registry.
3. One tooling-policy semantic validator owns normalized identity uniqueness,
   dependency existence/acyclicity, manifest presence, profile/platform support,
   policy-reference joins, inventory coverage, action coverage, and prohibited
   executable fields. JSON Schema alone cannot establish those joins.
4. The same validator cross-checks normalized selector bindings from tracked
   Nox/Make/hook/Ground-Control/docs commands, tool wrappers, vocabulary source
   records, OCI tests, native/bootstrap scripts, and every workflow. It reports
   all unmatched and multiply owned bindings in deterministic path/order.
5. Every repository-owned acquisition entry point calls this validation boundary
   before selecting a locator, checking a cache, or starting a native client. A
   cache hit, mirror hit, offline file, or direct standalone tool invocation does
   not bypass policy/reference validation. The Nox gate must run before the
   current Gitleaks hygiene acquisition, Conftest priming, Vale/OSV acquisition,
   proof acquisition, or remote vocabulary verification; a late CI drift check
   alone does not satisfy "fails before acquisition." Nox/project bootstrap is
   separately dispositioned under I01--I04 and #1217/#1218, not silently claimed
   as solved here.

The current selector surface includes Nox, pre-commit-hooks, Ruff,
check-jsonschema, Conftest, Gitleaks, OSV-Scanner, Vale, Isabelle, CPython/uv,
native Git/curl/CA/hash and proof packages, Docker/Podman/libvirt/QEMU, the
Alpine OCI digest, CirrOS/live-runner inputs, and all five governed vocabulary
source snapshots across the four current vocabulary validators.
Action coverage includes every external `uses` family in all tracked workflows,
the local canonical reusable workflow, its source revision rule, and each
action's exact full commit. Version comments, cache keys, artifact names, tags,
minor Python selectors, and action names are not trust roots.

Update guidance must identify the accountable role, an independent
Tooling/Security review role for identity, integrity, authenticity,
license/redistribution and policy changes, and the native client that will
consume the record (`uv`, the host package manager, Git/GH, curl,
Docker/Podman/Skopeo, or the GitHub Actions runner). Bot proposals and upstream
metadata are evidence, not independent approval. Reusable policy data identifies
stable roles rather than hard-coding a current maintainer name.

Selector discovery must scan Git-tracked repository paths, not only a maintained
consumer list. Context-specific extractors should emit one normalized binding
shape rather than treating every version-looking string as a tool. A new
acquisition or `uses` syntax that has no extractor/explicit disposition fails
closed. Acquisition coverage includes the discovered site count, so a listed
file cannot hide an additional call, and dynamic executable forms require an
explicit disposition. Runtime-selection calls are independently derived from
all tracked Python files and must exactly match the declared consumer mapping.
This is the enforcement needed for T22/T23; a list of expected literals alone
cannot discover a new bypass. Reuse the NUL-delimited tracked-file pattern in
`tools/check_identity_cutover.py`; do not parse newline-delimited Git output or
recurse into untracked trees/submodules.

## Required incumbents and cross-cutting layers

- Verification and workflow: ADR-014, `noxfile.py`,
  `tools/verify_all.py`, `tools/verification_plan.py`,
  `tools/nox_support/config.py`,
  `tools/nox_support/policy_lanes.py`, `tools/nox_support/graph.py`,
  `SessionReporter`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`,
  `.readthedocs.yaml`, `README.md`, `CONTRIBUTING.md`,
  `docs/DEVELOPMENT_WORKFLOW.md`, `Makefile`, and `.ground-control.yaml`. Wire
  the repository drift checker once into the
  canonical Nox policy graph; hooks, CI, and Ground Control stay thin triggers.
  `implementations/tooling/` must also enter the existing tooling-test trigger
  classification so a data-only change cannot skip its focused policy tests.
  Because branch `1216-artifact-lock-policy` contains no requirement UID, the
  workflow must bind `RAES_REQUIREMENT_UID=GOV-913`; new executable/config and
  test artifacts must remain aligned with Ground Control IMPLEMENTS/TESTS links.
- Parsing and errors: `PolicyFailure`, `failures_to_json()`,
  `safe_repo_path()`, and `load_bounded_json_object()` in
  `tools/policy/common.py`. Malformed data becomes stable rule-id/path/JSON-pointer
  failures, not a new exception hierarchy, traceback, `KeyError`, or assertion.
- Schema mechanics: `tools/check_json_artifacts.py` and
  `CHECK_JSONSCHEMA_TOOL_SPEC` are the incumbent schema-checker interface and
  batching pattern, but that CLI's transitive tool environment is a documented
  pre-#1218 coverage gap. The #1216 no-acquisition gate must use the already
  project-locked Draft 2020-12 engine; #1218 later moves the complete tooling
  closure. Do not import domain-profile validation policy, add internal tooling
  schemas to the published contract registry, or make the project lock a second
  hand-written tool catalog.
- Existing selectors and stronger checks: `tools/tool_versions.py`, the four
  generic tool wrappers, `tools/isabelle_tool.py`, the four vocabulary
  validators, and the OCI integration test remain consumer projections during
  this issue. Preserve OSV's bounded no-follow/per-use hash rules as the minimum
  future local-admission posture; do not weaken them while centralizing data.
- Workflow/action policy: preserve the exact-SHA and required-container controls
  in `test_release_workflows.py` and the release/canonical workflows. The new
  cross-repository action inventory supplements those focused tests; it does not
  replace release identity, permissions, OIDC, or publisher checks.
- Persistence: reviewed Git files are the only new persistent state. Do not add a
  database, runtime repository, cache marker, control-plane DTO/service, or
  `LocalControlPlaneStore` integration. Status snapshots, intake evidence, and
  promoted storage belong to their later owning issues.

Security layers touched by the intended design are:

- **Auth and trust.** Profiles and policies may name scoped credential, CA,
  signer/issuer, environment, and repository identities by reference only. The
  validator neither resolves credentials nor grants admission because a mirror
  credential exists. Action permissions and secret *names/classes* may be
  inventoried; token or key values may not be stored.
- **Secret handling.** Existing private-key detection and Gitleaks gates remain
  mandatory. Reject credential-bearing URLs, signed query strings, headers,
  environment values, private keys, and inline CA/key material. Diagnostics do
  not echo full locators or instance values.
- **Environment/config shape.** Do not add ambient `RAES_*` overrides,
  `${...}` interpolation, user-home configuration, curlrc behavior, or a hidden
  profile fallback. Profile/platform/policy and any dated evaluation instant are
  explicit validator inputs. Time-dependent admission uses a trusted explicit
  UTC instant so tests are deterministic; static consistency validation does not
  consult the wall clock.
- **OS/process exposure.** Static validation performs no acquisition and needs no
  network, shell, elevated privilege, daemon socket, or secret-bearing argv.
  Shape validation stays in process; any fixed-argv Git helper receives only the
  checkout and revision/path selectors. Native client execution, controlled
  environments, wall deadlines, and redacted stderr are later consumer
  responsibilities under ADR-106.
- **Error and observability envelope.** Reuse `PolicyFailure` and
  `SessionReporter` START/PASS/FAIL/SKIP summaries. Expose stable logical ids,
  paths/pointers, and reason codes; never raw JSON documents, response bodies,
  native stderr, signed URLs, or credential/private-package details. Sort
  failures so offline and CI runs over the same tree produce the same result.

## Extensibility seam

The primary seam is a normalized selector context parameterized by
`artifact_id`, canonical `platform_id`, and `profile_id`, with a normalized
selector binding carrying its owning authority and source location. A new
supported platform/profile should add reviewed profile data and artifact
variants without adding host-name conditionals throughout wrappers or rewriting
existing identities. A new consumer syntax adds one extractor that produces the
same binding, not a second drift checker. A genuinely new artifact class adds a
closed schema branch and fixed adapter; it never gains an arbitrary command
escape hatch.

## Gotchas and anti-patterns

- Do not duplicate any Python dependency or hash already owned by an `uv.lock`.
- Do not make `tools/tool_versions.py`, workflow comments, docs snippets, cache
  keys, or generated reports co-equal resolution authorities.
- Do not equate the vocabulary `source_digest` with raw fetched bytes. In
  particular, each source keeps its current raw or canonical meaning; the
  development lock adds a distinct raw-byte identity only where one is absent.
- Do not equate a digest with publisher authenticity, an action source SHA with
  its transitive payload closure, a policy with evidence, availability with
  admission, or a cache with retained immutable storage.
- Do not accept live checksum files from the same release endpoint as review
  authority. Do not invent signatures for unsigned Conftest, Gitleaks, Vale,
  OSV, Isabelle, source-snapshot, action, or OCI inputs.
- Do not use wildcard/implicit platform fallback, public-index fallback in an
  enterprise profile, unsupported-profile downgrade, missing-dependency skip,
  or "best matching" selection.
- Do not parse or execute install commands from JSON. Do not add custom HTTP,
  redirect, retry, TLS, framing, socket, downloader, or outer retry logic.
- Do not copy test-only workflow parsers into production policy code or maintain
  separate action lists in tests and the validator. Focused release tests may
  assert stronger release properties against the single policy authority.
- Do not mark known legacy network paths T22-compliant, silently exempt new
  paths, or let an exception omit owner, reason, reviewer, scope, and expiry.

## Non-goals and implementation boundaries

- No new acquisition, installation, extraction, cache, concurrency, or
  crash-safety client; those belong to #1137 and #1219--#1222. Wiring existing
  clients to consume exact reviewed lock selections is required here.
- No bootstrap/client/host qualification (#1217), frozen Python tool/build/smoke
  closure (#1218), or action transitive-payload qualification (#839).
- No intake service, mirror/provider selection, promoted storage, offline
  export/import, status-snapshot signing, SBOM/provenance, release admission,
  publication, retention/GC, recovery, or operations qualification
  (#1223--#1228 and #684).
- No new public schema, SDL/runtime artifact ontology, module-registry resolver,
  backend/controller/service/repository contract, semantic vocabulary, or
  canonicalization rule.
- No secret resolution, production service activation, infrastructure purchase,
  protected-branch merge, or claim that proposed ADRs or downstream migration
  guarantees have shipped.
