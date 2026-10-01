# Issue #1313: Developer and release workflow scope preflight

Date: 2026-09-17

Contract: issue #1313; GOV-913. This is architecture guidance,
not an implementation plan or evidence that the cleanup has shipped.

## Scope and authority

Design for connected local development and GitHub-hosted CI, with the one
accountable maintainer in `MAINTAINERS.md`. Security, Tooling and Release labels
do not establish independent human reviewers. In particular,
`implementations/tooling/action_policy_sources.py` currently treats disjoint
owner/reviewer role sets as a guarantee; that is not a valid independence check.
Machine permission separation remains necessary regardless of maintainer count.

GOV-913's normative authority remains
`specs/supply-chain/reusable-asset-trust-integrity.md`, ADR-071 and
`contracts/schemas/asset-trust/reusable-asset-trust-policy-v1.json`. Identity,
payload integrity and signer authenticity remain distinct. Simplifying tooling
ownership does not amend runtime signer thresholds, family coverage or vocabulary
source requirements. The requirement's broad traceability is not a mandate to
refactor every linked subsystem; issue #1313 bounds this change.

The issue's scope correction governs this work. Earlier preflights for #1216–1223,
#839, #1238 and `package-artifacts/issue-1226-preflight.md` describe the former
design and must not silently reintroduce cancelled requirements. Implementation
must explicitly reconcile ADR-106/107 and the package-artifact README,
architecture, decision matrix, inventory, operations/acceptance matrix and
migration table/diagram. Preserve historical decisions and measured results as
history; identify which requirements no longer apply, rather than deleting
history or relabelling old evidence as proof of new behavior.

Accepted ADR changes must follow ADR-059: an in-band amendment and matching
`adr-index.yaml` pin/amendment entry, or explicit supersession with index/status
updates. `tools/check_adr_immutability.py` owns this check. This note does not
itself amend the accepted ADRs or complete the issue's documentation criteria.

#1224, #1225 and #1228 are cancelled. There is no artifact-distribution,
promotion/revocation service, disconnected-development bundle, mandatory deputy,
independent-copy backup, service-load, retention/GC or recovery-drill program to
replace. #1227 owns release-byte verification and partial-publication recovery;
#684 owns actual PyPI/GitHub publication acceptance; #1277 owns verified,
accurately documented dev-container entry points. Reconcile native GitHub
dependency edges and milestone 69's description as well as repository prose;
editing a Mermaid graph does not update GitHub metadata. Coordinate shared files
without making #1313 a blanket blocker for those issues.

## Boundaries and canonical incumbents

| Concern | Reuse and intended boundary |
| --- | --- |
| Generic tool identity | `implementations/tooling/artifacts.lock.json`, `tools/tool_versions.py`, and existing selectors/installers. Keep one reviewed owner for each version/hash; remove redundant authorities or make retained projections derive/check against that owner. Never acquire expected checksums from the same live download as the bytes. |
| Python environments | Project and tooling `pyproject.toml`/`uv.lock` pairs have distinct ownership. `tools/python_closure.py`, `python_closure_profiles.py`, and `generate_python_closures*.py` already implement build/smoke selection and derived constraints. Keep frozen project/tool resolution, constrained build backends and installed wheel/sdist smokes; drop unused contexts and projections, not their integrity guarantees. |
| Selection versus repository checks | `select_tooling_artifact`, `select_tooling_host_profile`, and `load_python_closure_profile` currently invoke `evaluate_tooling_artifact_policy`. Selection must validate only its owning document and necessary selected dependencies. The explicit repository check composes the surviving focused checks; selection must not invoke workflow, inventory, container or qualification evaluation. |
| Workflow authority | `.github/workflows/*.yml` and `.github/dependabot.yml` own execution and updater configuration. Simplify `actions-policy.json`/`action_policy_*.py` into focused checks of actual configuration; do not maintain a second workflow graph, condition interpreter, use-site inventory or Dependabot model. |
| Execution and reporting | ADR-014's `noxfile.py`, `tools/nox_support/{graph,runner,policy_lanes,test_lanes}.py`, `SessionReporter`, `tools/verification_plan.py`, and `tools/pytest_shard*.py`. Make, hooks, `.ground-control.yaml`, `tools/verify_all.py`, CI and docs remain consumers. Preserve #935 shard completeness, coverage reduction, stable gate contexts and concurrent execution. |
| Acquisition and persistence | `tools/maintained_client_acquisition.py`, `verified_tool_installation.py`, `verified_tree_{installation,archive,manifest,validation}.py`. Native clients own transfer; local helpers own safe admission, locking and atomic installation. Private caches are disposable local state, not a distribution service or provenance authority. |
| Consumer meaning | `isabelle_tool.py`, `isabelle_sandbox.py`, `check_participant_opacity_proof.py`; vocabulary refresh/check scripts; `oci_release_{selection,image}.py`; `real-daemon/live_runner_inputs.py`; `release_evidence*.py`. Preserve each consumer's existing identity and correctness checks while removing unused operating modes. |
| Container configuration | `.devcontainer/Dockerfile` and `devcontainer.json` own their native configuration; `devcontainer_setup.py` remains the setup entry point. Simplify the profile/render/check machinery without replacing it with another complete Dockerfile/devcontainer model. |

No application controller, service, repository or DTO layer is needed. Existing
`LockedArtifactSelection`, `PythonClosureProfile`, installer protocols and
release identity types already delimit the relevant inputs. Internal tooling
schemas stay under `implementations/tooling/`; portable SDL contracts,
`schema_bundle()`, runtime OCI/module resolution and their publication ledger
are separate authorities and outside this change.

Include `.pre-commit-config.yaml`, `.readthedocs.yaml`, `Makefile` and documented
commands in the consumer audit: their frozen-environment entry points must
remain usable without restoring deleted profile machinery. Vocabulary checks
keep #1221's distinction between raw transport hashes and canonical semantic
`source_digest` values (notably NIST CSF); the tooling lock cannot redefine them.

`test_release_workflows.py` already checks every remote action pin and the
workflow/job write-permission boundaries, and executes release identity guards.
Build on those assertions when shrinking the Actions model. An action's source
SHA does not pin executables it subsequently downloads: retain the necessary
version/hash selection for actual setup/scanner inputs without preserving a
second transitive workflow inventory.

## Validation and security layers the design must pass

| Layer | Required boundary |
| --- | --- |
| Repository files and parsing | Reuse `tools.policy.common.safe_repo_path` and `load_bounded_json_object`, plus `tooling_artifact_policy_common.is_regular_repo_file` and tracked-authority checks. Containment alone does not reject all symlinks. Preserve byte bounds, duplicate-key rejection, regular files and path confinement. The private loader in `python_closure_profiles.py` uses ordinary `json.loads`; removing its preceding full evaluator must not expose duplicate-key acceptance or missing schema validation. |
| Internal shapes and semantics | Reuse the existing closed/versioned schemas and Draft 2020-12 validation with local references only. Shrink them alongside their consumers. Selection must reject ambiguity, unsupported platforms, invalid paths/locators, missing selected dependencies and bad raw/installed identities before acquisition. Remove cancelled policy/evidence joins explicitly; do not leave dangling fields and suppress their errors. |
| Workflow parsing | Reuse `implementations/tooling/action_policy_yaml.py`'s safe, duplicate-key/alias-rejecting parser for focused checks. Account for YAML's `on`/boolean-key interpretation already handled by callers. Check actual reusable-workflow contracts and security-relevant conditions without recreating a general Actions expression evaluator or accepting an unknown privileged shape as safe. |
| Process response shapes | `tooling_policy_gate.py` parses selector JSON into `LockedArtifactSelection`; `tooling_installed_tree.py` and `tooling_oci_selection.py` enforce consumer shapes. Change producer, boundary parser and tests together. Response checks at a subprocess boundary are useful; copying the whole policy schema into a second evaluator is not. A clean bootstrap must not require installing the tool that its own selector needs to run. |
| Environment and OS invocation | Reuse `closure_environment`, `frozen_tool_command`, maintained-client fixed argv and timeouts. Keep typed/allowlisted values and native commands, not command strings, arbitrary environment maps or shell interpolation. Prevent ambient `UV_*`, `PIP_*`, Python import paths, user config, netrc/keyring and proxy/index state from changing the selected identity or carrying credentials. Review PATH resolution separately from argument validation. Keep credentials out of argv, URLs/query strings, shell tracing, image layers, cache keys and uploaded diagnostics. |
| Transport and input identity | Reuse `acquire_locked_bytes`/`acquire_locked_file`, credential-free HTTPS locator checks, native TLS verification, size/hash checks and bounded transfer budgets. `curl_transfer_argv` puts the URL in argv: the selector's secret-query checks cannot disappear merely because the transfer helper rejects URL userinfo. Preserve the large-object budget for Isabelle. No custom HTTP/retry stack, TLS bypass, live checksum discovery or fallback after integrity failure. |
| Local installation | Preserve private directory ownership, no-follow/path checks, archive traversal/link/device/expansion limits, per-identity cross-process locking, private staging and atomic publication/recovery. A cache hit or marker is not integrity evidence. Generic archives and Isabelle's allowed confined symlinks have different extraction rules; do not flatten them into an unsafe common extractor. |
| Actions authentication | Inspect real workflow/job permissions, triggers, checkout refs, reusable-workflow inputs/secrets and credential-bearing steps. Retain SHA-pinned remote actions, digest-pinned images, `persist-credentials: false`, narrow publisher/OIDC permissions and untrusted-PR isolation. Explicitly cover the CI-to-canonical Sonar secret path, Pages/Scorecard identities and release jobs. Do not treat every OIDC job as a publisher, or every same-repository PR as trusted. Privileged jobs must not execute candidate-controlled scripts or restore candidate executable caches. |
| Native hosts and containers | Preserve signed OS package sources, CA verification, non-root development execution and scoped mounts/caches. Do not add daemon sockets, privileged containers or broad host mounts to make proof/container tests pass. AWS keeps scoped SSH ingress, authenticated host keys via the existing AWS control-plane path, private key files, cleanup traps and visible setup/backend failures. Validate shell-bound identifiers/paths before remote command interpolation. |
| Errors and observability | Static failures use `PolicyFailure`/`failures_to_json`; command stages use `SessionReporter`; acquisition/install/image/evidence adapters retain their stable reason codes and existing exceptions. Selection currently forwards validator stderr: bound and sanitize that boundary, including exception causes, rather than logging raw candidate data, subprocess argv, native stderr or secret-bearing values. Preserve failure versus skip, timeout and integrity failure; do not turn cancelled qualification into a passing evidence record. |
| Release evidence and publication | Preserve #1110/#1125 exact-SHA and required-container gates, read-only build/test jobs, installed-package identity and separate publishers. Reuse standard provenance/SBOM output and existing digest/producer identity types where needed; trusted expectations cannot come from candidate-supplied evidence itself. Simplification may remove custom admission machinery, but must preserve the same tested bytes through publisher handoff and post-approval tag/release identity checks. No new service or blanket gate. |

These are required boundaries, not a claim that every current helper satisfies
them alone. In particular, `load_bounded_json_object` provides containment and
duplicate-key checks but needs `is_regular_repo_file` for component-wise symlink
rejection; schema error messages may echo candidate values; and the selector
subprocess currently inherits its environment. Preserve a reviewed bootstrap
interpreter and its minimal environment when removing the outer evaluator.
The selection result must derive from the same parsed input that was validated,
not a second mutable-path read. Do not extend tooling environment selection into
SDL/backend credential-binding contracts or their validation layers.

Removing global evaluation is not a `skip_validation` switch. Whole-document
parse/shape failure in the owning lock is a legitimate refusal; an unrelated
workflow/container/qualification edit is not. Share the selected-input checks
between lookup and explicit policy validation instead of maintaining competing
validators. Remove inventory-site and aggregate qualification-hash obligations
from ordinary updates, including their hidden callers and test expectations.

Repository guards still apply: `tools/policy/repo_policy.py` owns ADR-015 source
size/import boundaries; `tools/check_authority_boundary.py` distinguishes
internal tooling schemas from published contracts; and `tools/requirement_context.py`
plus `tools/check_requirement_governance.py` own issue/UID resolution and
traceability. Use `RAES_REQUIREMENT_UID=GOV-913` on the numeric issue branch.
Do not disable these checks or create a mixed-requirement scope merely because
the supplied requirement has historical links to other issues.

## Consumer gotchas and extension seams

- Qualification triggers must cover their real component inputs, shared helpers,
  locks, schemas, workflow and tests, including renames/deletions. Keep explicit
  maintenance dispatch. A workflow-level path filter can leave a required check
  pending; preserve a truthful required-gate result where necessary. The
  canonical workflow also calls `offline-kit-fetch` for same-run generic tool
  inputs: audit callers beyond `bootstrap-qualification.yml` before removing
  kit APIs. A small verified per-run input cache is not a disconnected bundle.
- Acquisition TLS fixtures import `cryptography` at module collection time.
  Moving a dependency to an optional group without separating test collection
  can still break ordinary tests. Keep specialized fixture dependencies locked
  and selected by their lane. `raes/module_registry/{signing,publishing}.py`
  also uses cryptography at runtime: do not remove that legitimate dependency.
  Reassess Intel Mac support against actual interpreter, wheel/source-build,
  native-client and project dependencies, including the governed Z3 pin; neither
  vulnerable downgrades nor deleting a platform guard proves support.
- Native arm64 development needs tested base-image/platform selection, available
  signed native packages and the existing verified bootstrap inputs, not an
  enterprise snapshot program. A signed moving package repository does not
  imply bit-for-bit image reproducibility. Native execution, emulation and an
  exported multi-platform image are distinct claims. Coordinate entry-point,
  UID/cache ownership, lifecycle and worktree-mount documentation with #1277.
- The ordinary release image path needs a digest-pinned pull and real-container
  execution, not same-job OCI export/import or retained unused platforms. Keep
  unique concurrent resource names, failure cleanup, no-skips/zero-test rejection
  and teardown fixes. Do not remove the separate runtime OCI archive/cache
  implementation merely because tooling distribution modes disappear.
- Installer simplification targets private local/GitHub-runner caches. Remove
  unused multi-user seed and filesystem-qualification machinery without losing
  actual filesystem lock/rename semantics. If complete Isabelle tree hashing on
  every use is reduced, state the trust assumption and the admission, restore,
  mutation and rebuild boundaries first. Read-only modes, mtime or a writable
  marker do not prove immutable content. Keep full verification wherever a safe
  replacement is not established; measure any claimed speedup. Preserve the
  bubblewrap network/environment/filesystem sandbox, bounded resources, kernel
  replay and proof-source/theorem checks. Offline proof execution is not a
  disconnected development requirement.
- Online AWS setup may acquire verified inputs on the instance and use signed
  native packages without complete local pre-seeding/snapshots. Preserve CirrOS
  size/hash checks before use, locked Python/build inputs, AMI owner/image
  validation and both smoke/certification consumers. No pipe-to-shell installer,
  security downgrade, silent download failure or real AWS deployment in this
  preflight. Preserve the tracked, revision-bound source handoff; simplifying
  pre-seeding must not replace it with a copy of the working tree, ignored files
  or local credentials.
- Release cleanup must distinguish source SHA, workflow SHA, output digest,
  attestation producer and installed runtime dependency graph. An SBOM is not
  authenticated provenance; an sdist-built test wheel is not the published
  wheel. Keep those identities distinct in useful standard output. Coordinate
  byte-preserving partial-publication recovery with #1227; no clobber, moved tag,
  same-version rebuild or claim that PyPI/GitHub publication is transactional.
- The extension seam is the existing selection input: artifact/version and
  normalized platform, or Python purpose/interpreter/extras from its owning
  lock. A new supported platform/tool should extend that data and its consumer
  evidence without changing every caller or regenerating unrelated hashes.
  Runtime choice remains the existing Docker/Podman parameter. Do not preserve
  speculative mirror/offline flags or invent a plugin/provider framework for
  hypothetical future distribution needs.

## Evidence boundary and non-goals

Extend the incumbent tests under `implementations/python/tests/`:
`test_tooling_artifact_policy.py`, the #1137/#1217/#1219/#1220/#1222 suites,
`test_issue_1238_development_container.py`, `test_oci_release_image.py`,
`test_release_workflows.py`, #1226 evidence tests, packaging smokes and shard
tests. Preserve behavior tests; retire assertions that merely encode cancelled
machinery. The coupling regression must exercise real artifact and Python
selectors with unrelated workflow/container/qualification changes, while
selected-input corruption still fails before download/execution. Trigger tests
must prove both unrelated exclusion and relevant inclusion.

Evidence must include representative clean connected setup, ordinary checks,
concurrent/corrupt/interrupted installations, locked builds and installed
wheel/sdist smokes; affected proof/container lanes and release boundaries remain
required. Platform claims need actual platform evidence. Mocked transport, a
green YAML assertion or old qualification record alone does not establish these
outcomes. This note claims none of that implementation verification.

No implementation, ordered work plan, new policy framework, operational
acceptance program, public schema change, runtime architecture rewrite, new
exception hierarchy or logging format is introduced here. No release, external
deployment, protected-branch merge or PR merge is authorized. Release-please
continues to own versions and `CHANGELOG.md`; do not create a requirement UID
or broaden GOV-913 to cover unrelated implementation work.
