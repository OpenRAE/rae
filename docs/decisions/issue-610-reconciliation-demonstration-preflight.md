# Issue #610: Reconciliation demonstration preflight

Issue #610 is the authoritative contract: plan scenario v1, snapshot its planned
state, plan a modified v2 against that snapshot, and report
`create/update/delete/unchanged`. This is non-normative design guidance, not an
implementation plan. No new ADR is needed: ADR-008, ADR-015, ADR-036, ADR-057,
and ADR-066 already govern processing, layering, disclosure, and evidence.

## Boundary and reuse

Keep the harness a thin composition of the existing processor, with an offline,
self-contained bundled demonstration. The
incumbent user-facing surface is `raes_cli.processor` and its read-only `plan`
command; use that command group and Typer conventions for a runnable entry
point. Keep orchestration out of the planner and avoid a second standalone
command framework. Example SDL belongs in `examples/scenarios/`, with a
discoverable invocation and limitations in `examples/README.md`. Those files
are positive authoring examples, not new conformance fixtures.

Use `raes_processor.reference.run_reference_processor` for both versions. It
already accepts `Path` inputs, `parameters`, `profile`, `base_snapshot`, and
`scope`, and drives parsing, instantiation, compilation, and planning. A plain
string is SDL text, not a filename. Use
`raes_backend_stubs.manifest.create_stub_manifest` as the default planning
target, without creating or applying stub backends. The CLI may depend on both
packages; the processor must not import the CLI, stubs, or runtime.

The canonical reconciliation authority is
`raes_processor.semantics.planner.reconcile_resource_actions`, reached through
`raes_processor.planner.plan`. The planner's `ordering` and `operations`
modules own equality, dependency propagation, and domain operation ordering.
The harness consumes their result; it must not call private builders, compare
YAML/JSON to derive actions, or implement another reconciliation algorithm.

## Snapshot and action meaning

- The v1 snapshot is **synthetic assumed state**, following the existing
  `_snapshot_from_plan` demonstration pattern in `test_runtime_planner.py`.
  Label it explicitly. It is neither backend readback nor an instantiated SDL
  snapshot, durable checkpoint, execution receipt, or proof of realization.
- Use `raes_contracts.runtime_state.RuntimeSnapshot` and `SnapshotEntry`, plus
  the existing `ChangeAction`, `RuntimeDomain`, and plan DTOs from
  `raes_contracts.planning`. No parallel snapshot, action enum, or plan schema.
- Admit v1 only when the reference result is valid. Preserve each resource's
  canonical address, domain, type, payload, ordering dependencies, refresh
  dependencies, and profile bindings. The old test helper omits profile
  bindings; copying it literally loses part of today's reconciliation identity.
  Consult the planned resources for bindings where an operation lacks them.
  Copy mutable payloads so inspection or later processing cannot mutate v1
  through the snapshot. Never fabricate realized values, histories, observations,
  materialization attestations, or successful execution statuses.
- For the initial empty baseline, snapshot non-delete v1 resources across
  provisioning, orchestration, and evaluation. This narrow adapter is not a
  general operation replay engine: skipping deletes would be wrong when
  applying a later plan to an existing snapshot.
- Report v2 operations themselves, including `unchanged`; `actionable_operations`
  deliberately excludes those. Show domain, address, resource type, action,
  and all four counts (including zero). Counts describe v2 against the v1
  snapshot, not subtraction of the two plans' action histograms. A rename is
  delete plus create. A refresh-dependent resource may update with identical
  payload. Preserve the planner's apply/delete ordering in operation listings.
- A small fixture pair should make all four outcomes visible. The v1 baseline
  and synthetic snapshot identity/dependency summary should also be inspectable.
  A summary is a non-normative report, not a complete serialized snapshot or a
  newly published contract. Do not silently truncate listings or claim coverage
  of participant execution: the current planner builds three domain plans.

## Cross-cutting gates

Paths below `implementations/python/packages/` are abbreviated by package name.

| Layer | Canonical incumbent and required treatment |
| --- | --- |
| SDL ingress | `raes.parser.parse_sdl_file`, `read_sdl_source`, and the existing parser limits enforce bounded reads, encoding, syntax, and source/alias limits. Pass paths into the reference processor; do not pre-read unbounded YAML or use a permissive loader. Retain SDL model, reference, semantic, instantiation, and compiler validation. |
| Auth and operator secrets | This is a local read-only CLI using ordinary filesystem permissions. It needs no control-plane server, MCP session, token, credential provider, or authorization bypass. Do not read operator credential stores or resolve secret references. Live execution would require the existing runtime auth/admission boundaries and is outside this issue. |
| Module imports and supply chain | File-backed parsing can call `raes.composition.expand_sdl_modules` and `raes.module_registry.resolve_import`, loading `raes.lock.json` and `raes-trust.yaml`. Custom inputs retain composition budgets/cycle checks, local-path rules, registry allowlisting, transport policy, digest/signature/export verification, and safe archive/cache handling. OCI resolution can fetch and write caches even during planning. Use import-free bundled fixtures; do not claim arbitrary custom paths are offline, replace the resolver, auto-trust a registry, or disable integrity checks. |
| Authored environment and credentials | `raes.runtime_environment`, `runtime_generated_value`, `runtime_values.enforce_observed_value_redaction`, `_classification_guard`, `accounts.account_credential_binding_issues`, and planner account validation remain authoritative. Preserve literal versus generated-reference shapes, explicit classification rules, consumer-output restrictions, and account binding semantics through normal compilation. No host environment substitution, generated secret realization, custom secret-name classifier, or second env-binding schema. |
| Backend/config admission | Reuse the typed `BackendManifest` from the stub factory and the planner's complete admission chain in `planner/core.py` and `manifest_validation.py`: capabilities, realization/envelope, artifacts, profiles, ordering, topology, materialization, and other current diagnostics. A demo must not clear errors or broaden capabilities to make a fixture pass. If a manifest file is exposed, share the incumbent CLI loader's bounded UTF-8 JSON, object, `BackendManifestV2Model`, adapter, and capability checks, including rejection of unresolved realization envelopes. No new configuration file or environment lookup. |
| Plan/state shape | `raes_contracts.addressing`, `_planning_validation`, `SnapshotEntry`, and `RuntimeSnapshot` own address grammar, map-key identity, dependencies, and state invariants. Retain those constructors. Profile ownership at a serialized boundary belongs to `SnapshotEntryModel`. If full snapshot JSON is exposed, validate it with `RuntimeSnapshotEnvelopeModel` against `contracts/schemas/snapshots/runtime-snapshot-v1.json`; do not dump dataclass internals and call them that contract. The published envelope is flattened, unlike the internal `RuntimeSnapshotEnvelope.snapshot` carrier. |
| Secrets and output | Default to action/identity/dependency summaries, with JSON escaping for authored names and paths. Raw payloads can contain scenario credentials or content. `raes_cli.processor._execution_plan_payload`, `raes_contracts.plan_projection`, and `account_credentials.value_free_account_placement_payload` are the existing full-plan projection path; the account projection is not a universal sanitizer. `realization_snapshot_sanitization` owns concern-specific comparison/projection and is not a general export scrubber. Never redact the authoritative comparison state merely to make display safe. |
| Errors and observability | Use `SDLError` subtypes, existing `Diagnostic`/`Severity`, and CLI exit conventions. `ReferenceProcessorResult.is_valid` governs success; invalid v1 must stop before snapshot/v2, and invalid v2 must not look successful. Follow `raes_cli.processor._sdl_error_summary` and `_manifest_validation_summary`: safe codes, positions, kinds/counts, not raw exception text, rejected values, YAML snippets, or tracebacks. Catch expected file/encoding/validation failures at ingress with similarly safe errors. Diagnostic JSON conversion (`diagnostic_payload` or `portable_diagnostic_payload`) enforces representation, not secrecy; free-form messages still need an appropriate disclosure boundary. Keep report JSON on stdout, errors on stderr; add no logging framework or audit/evidence claim. |
| Host/OS/runtime | The harness itself runs in-process without shell commands, subprocess argv payloads/tokens, new sockets, daemon discovery, elevated privileges, backend apply/start/stop, or host mutations. The import-free bundled demonstration avoids the resolver side effects described above. Document `uv run --project implementations/python --frozen ...` and Python support from `pyproject.toml`. Explicit paths must work without test-only `sys.path` or imports from tests. Checkout example paths are not installed-wheel assets; do not assume they exist beside an installed package. |
| Persistence | The required snapshot can live in memory; stdout inspection does not require a database or checkpoint repository. Actual durable snapshots already belong to runtime control-plane stores, revision/CAS handling, and codecs. Do not reuse their private APIs or add a competing store for a synthetic demo. Full persisted snapshot import/export, if later requested, needs the existing published contract and disclosure review rather than a demo-specific round-trip format. |

## Extensibility and reliability

Accept explicit v1 and v2 source paths rather than embedding a fixed pair in
the algorithm. Keep the same manifest, instantiation parameters/profile, and
`PlanScope` across the comparison unless the caller intentionally varies them.
The callable composition can use these existing parameters without exposing
every option in the first CLI. This is the seam for another scenario pair or
backend target, not a registry, plugin system, or new configuration hierarchy.

Generated values with per-run/per-instantiation regeneration depend on scope
identity (`planner/core.py`); changing or omitting that identity can change
actions or invalidate planning independently of authored v2 changes. Use
deterministic fixtures without those dependencies for the basic demonstration.
Do not inject timestamps, random IDs, or machine-dependent paths into snapshot
comparison state or otherwise imply byte-for-byte reproducibility where the
inputs vary. Unsupported scenario/manifest combinations should fail normally.
Old planner fixtures may assert action lists without asserting plan validity;
their mere existence does not prove current stub admission. In particular,
`test_plan_inspection_cli.py` accounts for the stub's realization/readback
limits. Select supported demo content rather than stripping diagnostics.

The behavior oracles are `test_runtime_planner.py`, `test_semantics_planner.py`,
`test_reference_processor.py`, and `test_plan_inspection_cli.py`. Verification
of the eventual harness needs actual fixture-to-entry-point coverage, exact
address/action outcomes, all three domain aggregations, same-input unchanged
behavior, profile/dependency preservation, refresh-driven updates, invalid
input/nonzero exits, and safe deterministic output. Avoid tests that merely
reproduce the counting implementation or change existing planner expectations.

## Repository workflow and non-goals

Respect `.ground-control.yaml`, `.gc/plan-rules.md`, `.pre-commit-config.yaml`,
`noxfile.py`, and `tools/nox_support/`: nox is the verification graph and Make
delegates to it. `tools/policy/adr_policy.yaml` and `check_repo_policy.py` govern
authority paths, imports, and the source-file size cap; hygiene includes
private-key detection and gitleaks. Targeted local checks cover changed
behavior; CI owns repository-wide verification. This issue has no requirement
UID: do not invent one or attach unrelated traceability. The policy runner
already has a requirement-free `--skip-requirement` lane. Use current `raes`
identities; older preflight notes retain historical package names.

No planner semantics changes, backend execution/reconciliation certification,
runtime-controller/startup recovery, durable storage, replay/fidelity claims,
new published schemas, duplicate validators/DTOs/exceptions, or generalized
workflow engine belong here. No MCP/HTTP endpoint or auth/config expansion.
Do not expand this into a planner refactor, change accepted ADRs, relax policy,
edit release-owned versions/changelogs, or make the demonstration depend on
pytest internals or optional host infrastructure.
