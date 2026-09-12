# Issue 1218 / GOV-913: Python tool, isolated-build, and smoke closure preflight

**Date:** 2026-09-11

**Status:** Architecture preflight; implementation authority remains issue 1218

**Design authority:** issue 1168, ADR-106, ADR-107, and
`docs/decisions/package-artifacts/`

## Purpose and entry gate

Issue 1218 closes the Python-specific acquisition gaps identified as I01, I02,
I03, and O01 in the accepted package-artifact inventory. It does not introduce
a new package manager or release architecture. The implementation must retain
uv, make every project/tool/build/smoke dependency derive from a reviewed
authority, and make missing, unexpected, or wrong-hash inputs fail before an
opportunistic resolution can occur.

This note records boundaries and guardrails, not an implementation plan and not
a new architectural decision. ADR-106 and ADR-107 already decide the relevant
architecture and do not need amendment for this issue.

Implementation may start only after the native blocking relationships on issue
1218 are satisfied and a named Tooling and Release owner is assigned. A prose
reference or the presence of prerequisite files in this checkout is not a
substitute for those live gates. When repository-policy commands cannot infer a
requirement from the branch name, they must run with
`RAES_REQUIREMENT_UID=GOV-913`.

## Authority and concept boundaries

The following authorities are intentionally separate. None may silently become
a second spelling of another.

| Concern | Canonical authority | Boundary |
| --- | --- | --- |
| Project runtime, development, and documentation dependencies | `implementations/python/pyproject.toml` and `implementations/python/uv.lock` | The existing lock remains the only project-resolution authority, including all extras and the governed Z3 pin. |
| Python verification tools and isolated-build inputs | The accepted `implementations/tooling/python/pyproject.toml` plus its frozen `uv.lock`, with distinct named dependency groups | This is one reviewed Python graph. It replaces top-level Python tool-version constants and ad hoc `uv tool run --from ...` environments; it is not copied into the generic artifact lock. |
| Isolated-build constraints | Hashed, deterministic projections from the reviewed Python tool/build lock | Constraints are generated and drift-checked projections, not a hand-maintained version authority. Hatchling and every build-hook dependency are in the reviewed build group. |
| Installed smoke inputs | Purpose- and target-specific hashed exports derived from the project lock, plus an exact raw-artifact manifest | A wheelhouse is a verified materialization of a reviewed export. It is not a resolver, a lock, a mutable uv-cache snapshot, or evidence of release admission. |
| Generic executables and raw bootstrap clients | `implementations/tooling/artifacts.lock.json` and the accepted issue 1216/1217 policy | Python packages and their transitive graphs do not move into this lock. The uv Action source commit, uv executable payload, and Python payload remain distinct identities. |
| Host and acquisition context | The existing internal profile authority under `implementations/tooling/profiles/` | Public, enterprise mirror-only, and offline behavior extends the existing closed profile/schema bundle. It does not create a published product contract or a parallel profile registry. |
| Static policy and selector coverage | `tools/check_tooling_artifact_policy.py` and its existing policy modules | This remains the single deterministic offline validator for tooling authorities and tracked acquisition paths. |
| Verification execution and reporting | ADR-014's Nox graph, `tools/nox_support/runner.py`, and `SessionReporter` | Hooks, Make, Ground Control, workflows, and documentation are thin consumers. They do not own alternate lock selection or error semantics. |
| Candidate output admission and durable publication | ADR-107 and downstream issues 1224, 1226, 1227, and 1228 | Issue 1218 constrains build and smoke inputs and records candidate output identity. It does not promote, attest, retain, or publish an output. |

The reusable-asset trust contract under `contracts/schemas/asset-trust/` governs
SDL ecosystem assets. These development dependency closures are internal
repository policy. They must not be added to that public schema family, to
`schema_bundle`, or to runtime composition/module-registry policy.

There is no application controller, DTO, repository, service, or persistence
layer to add here. The checked-in locks, closed policy documents, semantic
validator, and existing Nox workflow are the incumbent equivalents. Wrapping
them in application-style abstractions would duplicate ownership without adding
a boundary.

## Closure contract

One frozen tooling project must cover every Python process currently capable of
resolving an unreviewed tool environment: Nox with its uv integration,
pre-commit, pre-commit-hooks, Ruff, check-jsonschema, Hatchling, and any Python
helper required by isolated builds. Direct requirements are reviewed in the
tooling project; the lock owns their complete transitive environments. The
current `tools/tool_versions.py` Python package constants must not survive as a
co-authority. Generic binary versions in that module remain in their existing
authority.

The project lock and tooling/build lock have different subjects. A smoke export
for an application extra derives from the project lock. An isolated-build
constraint derives from the tooling/build lock. A command needing both receives
both explicitly; it must never resolve one graph from the other or treat a
wheelhouse directory listing as dependency metadata.

Each supported closure is selected by a stable
`python_closure_profile_id`. That record binds, directly or by closed local
reference:

- purpose (`tool`, `build`, `wheel-smoke`, `sdist-smoke`, or an existing
  compatibility/docs purpose);
- project or tool lock identity and the applicable extras/dependency group;
- explicit host, Python interpreter, ABI, and platform tuple;
- acquisition context (public, named mirror-only, or offline);
- hashed requirement/export identity and exact raw-artifact manifest identity;
- allowed source-build disposition and the corresponding build closure; and
- evidence/test-case requirements.

The external seam is the profile identifier, not arbitrary package lists,
commands, index URLs, or environment maps. Adding a target, extra, tool, or
mirror therefore extends a closed profile/lock/export and its evidence. It must
not add conditionals to every caller. Supported tuples are enumerated; no
Cartesian product of host profiles, Python versions, ABIs, and extras may be
inferred.

Exports and wheelhouse manifests must be deterministic and reject duplicate,
missing, unexpected, untracked, symlinked, non-regular, or wrong-hash content.
Raw wheels and sdists are the portable offline inputs. `.venv`, `.nox`, uv
caches, pip caches, and provider caches are disposable performance state and
must never be copied or accepted as a trust authority.

Locking inputs improves repeatability but does not imply bit-for-bit
reproducible wheels. Evidence must record the qualified host/interpreter/client,
all input identities, and candidate output digests without claiming byte
identity across compilers, SDKs, operating systems, or build times.

## Existing validation and workflow to reuse

### Static validation

The existing tooling-policy gate remains the only fail-before-acquisition
entry point. Its current cross-cutting primitives must be reused:

- `safe_repo_path`, `is_regular_repo_file`, and Git-tracked-file discovery for
  repository confinement and symlink/non-regular rejection;
- `load_bounded_json_object` and the internal Draft 2020-12 validator for the
  existing closed profile documents;
- bounded `tomllib` parsing for new TOML authorities rather than another schema
  engine;
- `PolicyFailure` and `failures_to_json` for deterministic, aggregate static
  failures; and
- the current selector, inventory-coverage, and acquisition-discovery modules
  for cross-document and tracked-caller coverage.

Semantic validation must cross-check the tool project's direct requirements
against its frozen lock, every generated constraint/export against its owning
lock, profile references against explicit supported tuples, and every manifest
against its export. A schema-valid but semantically unbound hash, extra, group,
target, source policy, or locator is invalid.

Acquisition discovery currently treats only some uv commands as acquisition
surfaces. Its coverage must include at least `uv tool run`, `uv sync`, `uv run`
when it can synchronize, `uv build`, `uv pip install`, and Python download or
selection paths in tracked Python, shell, TOML, Make, hook, workflow, and command
documentation surfaces. The extension should use the existing context-specific
discovery approach, not a new general shell parser. An unrecognized dynamic
command shape is a policy failure, not an exclusion.

If the global tooling-policy digest is extended to cover the new TOML locks and
generated projections, every stored qualification record bound to the old
digest becomes stale and must be regenerated consistently. Runtime result
records and mutable caches must not be included in that digest. Evidence may
also carry explicit component digests; a single aggregate digest must never
hide which project, tool, build, export, or manifest identity was exercised.

### Execution and consumers

The existing Nox graph owns orchestration, timeout behavior, dependency
selection, and `SessionReporter` START/PASS/FAIL/SKIP observability. Its runner
should consume a validated closure profile and fixed command templates. It must
not accept caller-supplied shell fragments or arbitrary uv arguments.

All present projections must converge on that route:

- `.ground-control.yaml`, `.pre-commit-config.yaml`, `Makefile`,
  `tools/verify_all.py`, and developer command documentation;
- `tools/nox_support/runner.py` and `tools/check_json_artifacts.py`;
- CI, canonical-check, documentation, bootstrap-qualification,
  compatibility/free-threaded-preview, and release workflows; and
- corpus packaging and release workflow tests.

The cutover is incomplete while any tracked path can still create an ad hoc
Python tool environment, perform an unfrozen build, install from an implicit
index, or copy mutable cache internals as an offline dependency source. This
includes documentation snippets because they are executable operator guidance,
not harmless duplication.

Compatibility and packaging behavior remains with the existing runners and
tests. `test_corpus_packaging.py` must continue to prove the packaged corpus and
imports outside the checkout. The compatibility lane must continue exact
runtime assertions. Release tests must continue stage ordering, exact version
checks, no checkout import leakage, zero-case rejection, and read-only candidate
build permissions. The closure is an input to those incumbents, not a reason to
create parallel smoke services or exception hierarchies.

## Security and information-flow guardrails

Every layer crossed by the design must fail closed as follows.

| Layer | Required guardrail |
| --- | --- |
| Repository/file admission | Resolve only repository-relative allowlisted authorities; require Git-tracked regular files; reject traversal, symlinks, special files, oversize documents, duplicate logical identities, and unreviewed generated projections. |
| Shape validation | Keep profiles closed and versioned with local schema references. Do not accept arbitrary command arrays, environment maps, credentials, executable hooks, or unknown keys as extension points. |
| Semantic policy | Bind purpose, extras/group, target tuple, index context, hashes, raw artifacts, build disposition, and evidence. Validate the complete graph before uv, a build hook, or an installer runs. |
| Client invocation | Use the issue-1217-qualified uv executable with fixed argv generated from a validated profile. Preserve `--frozen` where resolution is forbidden, enforce hash checking for materialization, disable implicit Python downloads, and prohibit shell evaluation. |
| Environment binding | Start from a minimal allowlist. Bind interpreter/platform values from the profile. Clear ambient `UV_*`, `PIP_*`, `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, user config, keyring/netrc, proxy, and index variables unless the selected context explicitly owns them. Do not use a free-form environment overlay. |
| Authentication and secrets | Policy stores credential/trust references only, never values. Public profiles are credential-free. Supply private-index credentials through a protected native-client mechanism, never a URL, command line, generated lock/export, cache key, artifact name, or log. Untrusted PRs and candidate builds receive no enterprise or publication credentials. |
| Index/network policy | Public and enterprise mirror-only are separate contexts. Mirror-only maps approved namespaces explicitly and has no public `extra-index` fallback. Authentication failure, 401/403, TLS/trust failure, missing package, or hash mismatch is terminal; no context switch or opportunistic retry is allowed. Use uv's transport only. |
| Offline policy | Use exact raw wheels/sdists and manifests with network disabled, no index, Python downloads disabled, private temporary HOME/cache/work directories, and empty pre-existing caches. Preflight the whole requested closure before executing tools or build hooks. |
| Build/install isolation | Run candidate build hooks and sdist-to-wheel builds unprivileged, outside the checkout, without publish/OIDC/write credentials. Feed them only the selected build constraints and materialized artifacts. Installed smokes run outside the checkout with no `PYTHONPATH`/`PYTHONHOME` escape hatch. |
| Error envelope | Static errors use `PolicyFailure`; stage execution uses the existing reporter. Errors identify the logical profile, target, purpose, and safe repository-relative authority, but redact credentials, private URLs/namespaces, auth references, response bodies, and unbounded tool stderr. Distinguish missing/offline input, hash failure, authentication failure, and scanner/client failure without leaking secret-bearing detail. |
| Persistence and cache | Checked-in locks, profiles, constraints/exports, schemas, and evidence definitions are authority. Writable caches are disposable and content is revalidated on every admission. No shared database, mutable cache marker, or retained candidate artifact is introduced by this issue. |

No code in this issue may implement HTTP, Simple API, redirect, retry, proxy,
TLS, framing, resolver, or package-install behavior. uv and the native provider
clients retain those responsibilities.

## Qualification and evidence boundary

Issue 1218 exercises the Python-closure slices of T03, T10, T11, T13, and T23
from `docs/decisions/package-artifacts/operations.md`:

- T03 covers explicit CPython 3.11-3.14 tuples, all claimed project extras,
  frozen tool environments, constrained direct-wheel and sdist-to-wheel builds,
  and installation/import smokes outside the checkout.
- T10 covers Python Simple-index public and enterprise mirror-only selection,
  namespace routing, credential containment, and terminal failure. It does not
  qualify generic or OCI acquisition.
- T11 covers clean-cache offline restoration of the selected Python tool,
  build, and smoke closures from raw hashed artifacts. It does not claim the
  complete proof/offline export covered by issues 1220 and 1225.
- T13 covers missing, unexpected, corrupt, and malicious Python package/build
  inputs before execution. Fonts, interpreter payloads, and OCI layers retain
  their existing owners.
- T23 covers selector and authority drift across locks, exports, profiles,
  Nox, hooks, workflows, documentation, bootstrap, and release projections.

Existing issue-1217 records named T03 prove the earlier bootstrap/client slice;
they do not prove this fuller closure contract and must not be silently
reinterpreted. New evidence must bind the implementation commit and harness,
qualified host/interpreter/uv identities, selected closure profile, project and
tool lock digests, build constraint and smoke export digests, exact materialized
artifact manifest, outcome, and candidate output digests. Aggregate reporting
must preserve the partial scope above and must not state that complete T10,
T11, or T13 has passed.

Negative contract tests should mutate every authority boundary: direct and
transitive versions, hashes, lock ownership, extras/groups, target tags,
manifest membership, index context, credentials in forbidden fields, cache
contents, offline network settings, tracked invocation shapes, and evidence
digests. They should extend `test_tooling_artifact_policy.py`,
`test_issue_1217_bootstrap_profiles.py`, packaging/compatibility tests, and
`test_release_workflows.py` as appropriate rather than introduce duplicate
policy or workflow test stacks.

## Gotchas and anti-patterns

- Preserve `z3-solver==4.16.0.0` and its governed profile. The current macOS
  x86_64 source-build behavior cannot remain an ambient
  `UV_NO_BINARY_PACKAGE` exception: its exact sdist, build prerequisites,
  target, and disposition must be explicit and hash-bound, or the tuple is not
  supported.
- `uv tool run`, `uv run`, `uv sync`, `uv build`, and `uv pip install` can all
  cross an acquisition boundary. Treating only explicit install commands as
  acquisition leaves a bypass.
- A top-level pin is not a complete environment. A frozen transitive lock is
  still required for Nox, hooks, Ruff, schema tooling, and build backends.
- A lock is not a wheelhouse, a wheelhouse is not a lock, a cache is neither,
  and a successfully built candidate is not admitted for release.
- Direct wheel build and sdist-to-wheel build are distinct paths. Both must use
  the same reviewed build closure and be smoked outside the checkout.
- Read the Docs and other provider-managed environments are consumers of the
  same project/docs closure, but this issue must not claim offline or private
  mirror behavior that the provider configuration has not qualified.
- Candidate release builds must remain read-only and credential-free. Publisher
  jobs must not rebuild or gain dependency-resolution authority.
- Preserve release-please ownership of versioning and `CHANGELOG.md`; dependency
  closure work must not add a competing version or changelog generator.
- Never add a second Python version table, copied hash list, profile schema,
  validator CLI, workflow DAG, acquisition retry layer, exception hierarchy,
  log format, or offline-cache format.
- Never make public-index fallback, source-build fallback, Python download,
  stale-cache reuse, ignored hash failure, or unknown-platform coercion a
  recovery path.

## Explicit non-goals

Issue 1218 does not:

- change SDL/runtime schemas, reusable-asset trust semantics, composition, or
  module-registry behavior;
- replace uv or implement a package resolver, transport, installer, or mirror;
- qualify raw Python/uv/bootstrap clients already owned by issue 1217;
- complete generic/OCI mirror qualification, proof-runtime closure, complete
  air-gap export/import, SBOM/provenance, durable candidate storage, release
  admission, signing, promotion, or publication;
- promise support for an unenumerated host/interpreter/ABI/platform tuple or for
  the advisory free-threaded preview as a release target;
- claim bit-for-bit reproducible builds; or
- introduce a database, service/controller layer, public contract, or reusable
  package-management framework.
