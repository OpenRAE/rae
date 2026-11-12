# Issue 967: Concrete Backend Removal Preflight

Date: 2026-10-20

Contract: GitHub #967; no Ground Control requirement. This is architecture
guidance, not an implementation plan or evidence that extraction has shipped.

## Decision and release boundary

Apply ADR-036's ownership boundary, ADR-104's portable control-plane/effect
separation, and ADR-113's ecosystem allocation. RAES retains SDL, processing,
portable runtime/control contracts and their reference enforcement, conformance,
semantic examples, dry fixtures and test doubles. LilRAE owns concrete local
realization, readiness, credentials, allocation, execution and backend rollback
and teardown. Hub and LilRAE own the executable quickstart.

Removal is gated on an independently released, working LilRAE distribution
(OpenRAE/aptl#1215), demonstrated against a named released RAES distribution.
A merged extraction, editable sibling checkout, passing dry fixtures, or a
release tag alone does not satisfy this gate. The supplied issue and current
repository do not establish that prerequisite or the compatible versions;
implementation must obtain release/artifact and interoperability evidence before
removing the bundled path. Do not invent versions or report this preflight as
release approval.

Migration guidance must name the last bundled RAES version, first RAES version
without the backend, first independent compatible LilRAE version, supported
version pairing and relevant contract/profile identities. Link to LilRAE's
installation and lifecycle documentation from RAES's user documentation. State
the removed Python imports and CLI commands and their replacements. Existing
resources and backend state require an explicit owner and upgrade/cleanup
instruction before switching distributions; installing RAES must never discover,
adopt, roll back or destroy them automatically.

Use `specs/evolution/versioning-deprecation-and-migration.md`,
`specs/evolution/deprecation-records.yaml` and
`tools/check_deprecation_lifecycle.py` for removal eligibility and lifecycle
records. ADR-075 is still proposed, but those executable incumbent surfaces
already exist. Package versions, backend versions, schema lineages and evidence
claims remain distinct. Release-please owns versions and `CHANGELOG.md`; this
consumer-visible removal needs release-producing breaking-change classification
under `.gc/plan-rules.md` and `tools/check_pr_title.py`, despite the issue's
`refactor:` title. Older preflights mentioning towncrier are historical guidance.

## Scope by responsibility, not by name

The current wheel includes both `raes_reference_backend` and
`raes_backend_libvirt`. Removing only the former leaves concrete allocation and
lifecycle ownership in RAES and fails the goal. Both packages' executable paths
need a successor disposition covered by the release gate. Do not leave libvirt
as an undocumented exception or remove an uncovered user journey silently.

`raes_cli.main` eagerly imports `raes_cli.libvirt`, which imports
`raes_operations.libvirt_evidence_run` and `techvault_live`. These workflows and
their `_techvault_cleanup`, `_evidence_run_native`, and backend-specific artifact
helpers retain concrete imports even when the user only asks for ordinary CLI
help. Remove backend-owned registration and workflows with the implementation;
optional imports, default dependencies on LilRAE, auto-install, or a subprocess
forwarder would preserve the ownership problem.

Do not delete all of `raes_operations` or everything named `reference`.
`deterministic_participant_fixtures`, dry corpus comparison/validation and
`run_artifacts` contain reusable contract/evidence work. Retained helpers must
have a backend-free import closure; backend-native topology inspection and
effectful archive producers belong with their backend. Keep
`raes_processor.reference.ReferenceProcessor`, `raes_backend_stubs`, portable
time services, and the ADR-104 `raes_cli.runtime` offline store-maintenance
interface. Store backup/restore and portable operation reconciliation are not
backend rollback/teardown. Portable stop, compensation and cleanup *contracts*
remain meaningful without RAES owning native effects.

Backend-specific harnesses such as
`raes_conformance.conformance.reference_participant_opacity` need an explicit
disposition: keep only genuinely dry contract support, and put concrete probe
execution in the backend. An in-process driver is not automatically a test
double: do not transplant the removed backend under `raes_backend_stubs`.
Retain semantic scenarios, invalid fixtures, negative boundaries and honestly
labelled historical evidence; do not rewrite immutable captures or digest pins
to pretend their original producer never existed.

## Canonical seams and cross-cutting gates

Python module names below are under `implementations/python/packages/`.
These gates remain binding for external backends and replacement test doubles;
extraction is no permission to bypass them.

| Layer | Incumbent and required treatment |
| --- | --- |
| SDL and processing | `raes.parser`, SDL validation, `raes_processor.reference`, compiler/planner and their manifests remain the sole semantic path. Plan against an explicit backend manifest; scenario validity is not realizability, and a descriptive inspection plan grants no execution authority. Preserve existing SDL errors and diagnostic summaries. |
| Neutral schemas and decoding | `raes_contracts` owns DTO identity, `ContractModel` (`extra="forbid"`), `json_ingress`, canonical digests and value bounds. `contracts/`, the authority-boundary manifest, `schema-publication-manifest.json` and `contracts/schema-publication/` remain authority. Reuse `schema_bundle()`, `manifest_authority`, conformance validators and native semantic checks; do not fork DTOs or relax validation to accommodate external packages. Backend removal does not itself authorize schema/fixture removal. Any actual schema change still needs publication records, generator parity and removal tombstones where applicable. |
| Attachment and capability shapes | Use public `raes_backend_protocols` protocols/capabilities and `raes_runtime.registry.BackendRegistry`, `RuntimeTarget`, `RuntimeTargetComponents`. Registry shape/signature checks, `registry_target_validation`, profile admission and manifest validation remain mandatory. A `backend-manifest-v2` envelope identity is not the full realization declaration: retain digest-checked joining through `backend_manifest_from_v2_model_with_envelope()` where applicable. Backend config belongs to the backend factory; portable `ControlPlaneConfiguration` and supervision options keep their typed, fail-closed shapes. |
| Execution inputs and results | `raes_runtime.backend_calls`, `backend_input_contracts`, preparation, augmentation/materialization admission, `result_contracts` and the domain-specific result/transition validators remain the invocation boundary. Preserve bounded inputs, isolated arguments, trusted predecessor comparison, validated changed addresses and closed result carriers. Calling an external factory must not become direct unvalidated calls from CLI, processor or conformance code. |
| Authentication and disclosure | Retain `control_plane_security`, API `_auth`, route-authority inventory/composition seal, `control_plane_api_guards` body/capacity limits and no-store responses, actor/run/target-scoped operation admission, and participant crossing/visibility policies. SDK embedding trusts the host; served identities are privileged and must not be delegated to participants. Backend extraction neither opens routes nor transfers organizational authentication or policy into SDL. |
| Secrets, config and environment binding | Keep `SecretReferenceId`, account credential contracts and `backend_account_credentials` value-free result sanitization. `contracts.experiment_bindings.ConfigurationTargetRegistryModel` owns typed target declarations/aliases and literal versus secret-reference rules; `runtime_fact_bindings`, `runtime_fact_binding_policy` and `RuntimeFactDispatchCommand` own scoped sink authorization and just-in-time protected dispatch. Preserve these portable shapes; do not replace them with arbitrary environment dictionaries, inline credentials, or a new RAES secret/config loader. RAES installation and its dry tests require no real backend credentials. |
| Host/OS exposure | Native Docker/Podman/libvirt/QEMU, guest access, cloud-init, sockets, images, resource ownership and native cleanup leave with concrete execution. No installed CLI help/import or dry conformance path may contact daemons, pull images, read credential files or probe the host. Do not introduce shell execution, credentials in argv/URIs, inherited credential environments, or hidden backend discovery as a compatibility bridge. Existing bounded native leaves and image-trust checks must not be replaced by less safe forwarding during migration. |
| Errors and observability | Reuse `Diagnostic`, `portable_diagnostic_payload`, `backend_result_diagnostics`' value-free `runtime.backend-call-failed`, conformance `sanitized_failure_message`, existing report serialization and API `_responses`/redacted handlers. No raw backend exception, rejected payload, secret, host path or subprocess output in public reports/logs. Keep existing bounded rejection audit and operational summaries. ADR-066 separates apparatus telemetry, participant observations, captured evidence and derived analysis; a synthetic report cannot become native realization evidence. No new exception hierarchy or telemetry stack. |
| State, persistence and workflows | Keep `ControlPlaneStore`, its profiled implementations, leases, revision CAS, atomic terminal snapshot/operation/actor-audit commits, compatibility codecs and offline maintenance. Reuse operation policy, supervised dispatch, invocation claims, recovery observation and workflow result validation. Preserve immutable actor/run/target binding and indeterminate effects; neither timeout nor an exception proves cessation. No new backend state repository, migration database, lifecycle controller, retry loop or parallel workflow engine. |

## Installed conformance and extension boundary

Downstream consumers use the public `raes_conformance.conformance` facade:
`run_fixture_suite()`, `run_target_conformance()`, contract validators and the
existing report envelope. `raes conformance backend` is fixture conformance;
it does not prove a live LilRAE deployment. Keep unsupported, skipped,
fixture-only, hermetic-live and native-live outcomes and limitations honest.
Missing harnesses or empty/missing artifacts must not produce a native pass.

The next backend or bounded realization uses the existing injected
`RuntimeTarget` plus manifest/profile, `reference_scenario`, realization envelope,
`realization_harness`, participant-policy/opacity harnesses and execution-basis
parameters. Backend owners supply execution, observation and cleanup through
these seams; RAES owns generic checks and verdicts. Profile JSON remains
artifact-driven, with known runtime-surface dispatch separate from arbitrary
profile IDs. Do not add a LilRAE name switch, product enum, plugin discovery
service or backend-specific schema to the runner. If a needed downstream hook
is private today, expose the smallest typed owning facade rather than exporting
all internals or making downstream import tests or repository tooling.

`raes_contracts.corpus` and `implementations/python/hatch_build.py` already ship
the normative corpus using package resources. Preserve all required families,
provenance and notices through wheel and sdist-to-wheel builds. Explicit fixture
and profile overrides remain development inputs, with profile grammar, identity
and root/symlink containment checks; no remote schema resolution or new hidden
environment-root override. Adding another backend must not require a source
checkout or a separate conformance distribution.

## Whole-repository obligations and verification boundary

The implementation's affected surface includes:

- Package membership, entry points, dependencies and coverage rules in
  `implementations/python/pyproject.toml`; its lockfile; `hatch_build.py`;
  tooling Python metadata, build constraints and reviewed closure/wheelhouse
  manifests. Remove only dependencies whose retained consumers are gone;
  SSH, HTTP, crypto and persistence libraries may serve portable runtime paths.
- `tools/policy/adr_policy.yaml` and oversized-file allowlists: removed module
  roots cannot remain configured because policy validates their existence.
  Preserve import-direction/private-import enforcement and the 500-line cap;
  do not weaken policy to excuse stale imports. Keep
  `test_node_architecture.py` and `test_runtime_contract_boundaries.py` aligned.
- `noxfile.py`, `tools/nox_support`, pytest markers/sharding, `.pre-commit-config.yaml`,
  `.github/workflows/ci.yml` and `canonical-verification.yml`, including the
  explicit Docker job and its required-result aggregation. Backend jobs and
  tests need a deliberate disposition; skipping them is not extraction evidence.
  Retain unrelated runtime/database and package/container supply-chain checks.
  `.devcontainer/` and `implementations/tooling` artifact policy/locks must agree
  with the remaining build and developer dependencies; reuse existing tooling.
- `README.md`, `docs/public` navigation/API pages and redirects, internal
  operational guidance, examples and fixture catalogs. Replace active bundled
  CLI/lifecycle advice with migration links while preserving the dry SDL
  quickstart and semantic examples. Reuse `tools/check_public_docs.py`,
  positioning/example-library and authority/schema gates. Historical research
  evidence is not an active installation instruction.

Preserve contract/security regression coverage currently embedded in backend
tests: move portable assertions to existing stubs or narrow protocol doubles;
concrete driver/effect tests belong downstream. Extend existing tests such as
`test_backend_conformance_cli.py`, `test_runtime_conformance.py`,
`test_conformance_facade_parity.py`, registry/result/security tests and
`test_corpus_packaging.py`; do not create a second acceptance runner.

CI acceptance must exercise the real installed wheel and sdist-derived wheel
away from the checkout, without source `PYTHONPATH`, sibling/editable backend,
credentials, daemons or native tools. Check absent concrete packages/imports,
working normal CLI help/commands and MCP startup, packaged fixture conformance,
and a public target/harness supplied by a small external-style test double.
Positive tests alone can miss unused concrete packages still shipped in an
sdist. Live LilRAE interoperability and lifecycle evidence are a separately
owned release gate, not a new RAES native test dependency.

Local work uses targeted tests and path-scoped repository policy checks under
`AGENTS.md`, `.ground-control.yaml` and `.gc/plan-rules.md`; full policy,
integration, Docker, fuzz and completion suites remain CI/CD-only. This run has
no requirement UID; do not fabricate one to satisfy requirement-backed tooling.

## Non-goals and prohibited shortcuts

This issue does not redesign SDL, relocate the shared RAE runtime, split RAES
into new distributions, implement LilRAE, change portable lifecycle semantics,
add services/endpoints, migrate live stores, publish releases, or execute native
cleanup. Do not copy the backend into stubs, vendor LilRAE, add a dependency
cycle, retain import/CLI forwarding shims, duplicate schemas/validators/errors,
drop negative security tests, or manufacture successful conformance to make the
removal appear complete. This preflight changes guidance only.
