# Issue 1667: materialization producers in target conformance

Issue: #1667. Requirement: none. The supplied GitHub issue is the delivery
contract. This is architecture guidance. It is not an implementation plan.

The fix belongs in target-probe composition. Keep materialization admission,
inventory authority and protected publication in their existing owners. Do not
add new SDL, a contract schema, a backend profile or a persistence system. The
fix needs none of them.

## Findings and decisions

- `conformance/target_planning.py::target_probe_execution_plan()` calls
  `run_reference_processor()` without `scope`. Negotiated reporting needs the
  full admitted source and a safe run identity. Descendants also need the
  selected target identity. Keep that planner refusal.
- `conformance/target_probes.py::_target_runtime_cases()` does not supply an
  archive owner. It also does not supply the matching control-plane run scope.
  Source context alone does not resolve these two boundaries:
  - Operation admission rejects a plan whose run is not the same as the
    control-plane scope.
  - Materialization preconditions reject missing archive ownership before
    backend mutation.
- `tools/policy/adr_policy.yaml` currently excludes `raes_operations` from the
  imports that conformance can use. To reuse `RunMaterializationArchive`, add a
  narrow dependency allowance on purpose for `raes_operations.run_artifacts`.
  Add a matching public-prefix limit. Keep the ADR-036 package direction. Do
  not:
  - permit arbitrary operations imports;
  - bypass the gate dynamically;
  - copy the writer;
  - move filesystem ownership into `raes_contracts`/`raes_processor`.
- `_hermetic_snapshot_payload()` drops `materialization_attestations`,
  `realization_provenance`, `realization_observations` and
  `realization_envelope`. Its partial projection must not become the proof of
  an accepted reporting result. Keep and validate the related typed carriers
  through `RuntimeSnapshotEnvelopeModel`, `_validate_payload()` and
  `_semantic_diagnostics()`.
  - The runtime `_snapshot_model()` and the store
    `_snapshot_payload()`/`_snapshot_from_payload()` set the carrier mapping.
  - `snapshot_semantics._snapshot_from_envelope()` already restores these
    fields.
  - Reuse the serializers of the owning models.
  - Do not import private API/store modules across the package gate.
  - Do not make another snapshot codec or schema.

For negotiated materialization, the runner must supply a run ID before
planning. The ID must be fresh, value-free and bounded. The runner must bind
`PlanScope.target_name` to `RuntimeTarget.name`. Use the target-selection
pattern of `RuntimeManager.plan()`. The target instance name is not the same as
`manifest.name`. The `manifest.name` value identifies the producer.

Put the same unprefixed run ID in the planning/source context. Put `run:<id>` in
`RuntimeControlPlane.run_scope`. Do not make a new ID between planning and
execution. Do not change the source after plan registration. Keep
non-negotiating targets on their existing probe behavior. If you add run scope
to all targets, generated-value reconciliation can change.

The public runner should stay usable without new mandatory arguments. If
callers need to select scope or keep artifacts, use additive typed options in
`_TargetConformanceOptions`. These options are the
existing `PlanScope` and the `MaterializationArchive` protocol. Do not add a new
conformance context or DTO. The runner owns target binding. It rejects a
supplied target that conflicts.

If the run identity is missing, the runner can apply the safe default. A
malformed supplied identity must fail before apply. Do not rewrite it silently.
Do not fall back to another run.

The default archive is a `RunMaterializationArchive` in a private temporary
directory. Its scope is the existing lifetime of the target-adapter probe. The
`with control_plane:` lifecycle stays the owner of execution and draining. The
archive must stay available until all callbacks, snapshot checks and archive
verification are complete.

Delete runner-owned artifacts after runtime closure. Do this on success and on
ordinary failure. This includes early returns and initialization failure.
Do not:

- race unresolved callbacks when close or drain fails;
- hide a cleanup failure behind a pass;
- delete an archive that the caller owns.

Temporary conformance artifacts prove delivery during the probe. They are not a
durable experiment archive after return.

## Cross-cutting boundaries and canonical owners

Python paths below are under `implementations/python/packages/`.

| Layer | Required reuse and guardrail |
| --- | --- |
| Profile/corpus and manifest ingress | Keep `raes_contracts.corpus`. Keep the published `contracts/profiles/backend/` and its fixtures. Keep `backend_manifest_payload()` and `BackendManifestV2Model`. Keep the supported-contract and concept-vocabulary validators, `_declared_contract_gaps()` and the capability-gap checks. Use the contract constants in `raes_contracts.materialization` and `materialization_inventory`. Do not make a second negotiation table. `RuntimeTarget` and `registry_target_validation.validate_inventory_contract()` still need both contracts. They also need a `refresh_inventory` that is callable and has the correct shape. |
| Runner and runtime configuration | `_TargetConformanceOptions` stays the option boundary. Unknown options still fail. `ControlPlaneConfiguration` validates the normalized run scope and the existing apparatus configuration. Inject only typed scope and archive dependencies. Do not add environment-based configuration, credential discovery or a backend-name switch. |
| Identity shapes | `PlanScope` permits colons in run IDs. `MaterializationSource` and the archive `is_valid_run_id_label()` need a narrower, filesystem-safe form. That form has a limit of 128 characters. Choose an ID that all three accept. The ID must not have the `run:` prefix, path separators or a leading dot. Also validate the `InventoryTargetScope` of the source. A runtime target name can be broadly valid and still not satisfy that narrower reporting shape. Never use a target name as a filesystem path. Never change a target name into a slug for a different authority identity. |
| SDL/source and plan authority | Keep `ScenarioInput` resolution and `parse_sdl`/`parse_sdl_file`. Keep ordinary compilation and planning, and `planned_materialization_source()`. `MaterializationSource` validates the complete canonical instantiated snapshot. It also validates the original digests, the closed shape and the portable bounds. Its current source/report budget is 1 MiB. This budget is smaller than general SDL ingress. Keep the `runtime_plan_digest()` and `register_planner_produced_plan()` authorization. Do not rebuild the source from plan resources. Do not register a fabricated phase plan. |
| Operation authorization and audit | These stay authoritative: `RuntimeControlPlane.submit_provisioning()`, `operation_admission_context()`, existing operation IDs and inventory attempt IDs. Request commitments, mutation authority, receipts and statuses also stay authoritative. Bounded value-free audit stays authoritative too. Let the runtime bind the operation, attempt and predecessor identity. An HTTP server is not necessary. If you use an existing HTTP harness, keep `ControlPlaneSecurityConfig`, target-bound route roles and `_auth`. Also keep the request-size middleware and safe response envelopes. An archive dependency gives no access rights. |
| Preparation and result admission | Keep `_call_backend_apply()` isolation and the materialization preconditions. Keep realization preparation and augmentation preparation and admission. Keep the existing result, snapshot, domain and transition validation. `admit_materialization_submission()`, `admit_runtime_inventory()` and `validate_actual_augmentation()` own these items: source, producer, configuration, plan, operation and predecessor bindings, coverage, collection authority, receipts and provenance projection. The harness must not fabricate descendants. It must not write runtime-owned provenance or accepted references. |
| Host filesystem and bytes | `RunMaterializationArchive.publish()`/`read()` own local protected publication and readback. This includes bounded SDL, trusted relative record paths and directory containment with `O_NOFOLLOW`. It also includes regular files, `0600` artifacts, immutable identity, size and checksum checks, and synchronization. Use a private `0700` temporary root and keep these checks. Do not add a generic file writer, URI fetch, shell or host scanner. Do not add a native daemon dependency or a new service. Caller-supplied archives stay trusted apparatus. They have the same protocol obligations. |
| Persistence and lifecycle | Keep `MaterializationArchiveRecord` and `RuntimeSnapshot.materialization_attestations`. Keep the existing snapshot DTOs and codecs and the operation terminal commits. Keep the revision/CAS and idempotency owners. Publication comes before accepted references. A path or a serialized report alone is not delivery. Do not add a conformance database or store. Do not replay apply after an archive failure. A refusal can leave physical effects. Keep the existing runtime handling for failed and indeterminate results. Keep the recovery and cleanup boundaries. |
| Errors, secrets and observability | Use `Diagnostic`, `ConformanceCaseResult`, `BackendConformanceReport` and `sanitized_failure_message()`. Also use runtime result diagnostics and the existing audit correlation. Missing or invalid reports must produce failed cases. Failed publication must also produce failed cases. These cases keep stable reason codes. Never echo rejected SDL, source snapshots, Pydantic input values or backend exception text. Never echo native stdout/stderr, host paths, URIs, tokens or environment contents. Do not add a new exception hierarchy or logger. Do not put credentials in argv, report bodies or scope labels. Native access stays configured by the caller. |

## Claim boundaries and gotchas

Keep the requirements of issue #606:

- a succeeded provisioning operation;
- non-empty changed addresses;
- a valid snapshot with provisioning-domain state.

A callable refresh interface is not sufficient. To reach `apply()` is also not
sufficient. A negotiated producer must give a valid materialization, also when
it adds no resources. When descendants are negotiated, it must give the
complete typed inventory report. Runtime admission must succeed before the
probe can pass. Actual protected archive delivery must also succeed.

Keep the `reference_scenario` seam of the caller from issue #663. A backend that
makes descendants needs enclosing collection authority. It can also need
prospective augmentation permission. A run ID gives neither. Do not do these
things to accommodate a producer:

- open the constraints of the default scenario;
- suppress report failures;
- remove declarations;
- relax exact/import restrictions;
- promote descriptive materialized SDL into an executable plan.

Adapter qualification, producer assertions and independent native realization
are different claims (ADR-115 and ADR-066). `run_target_conformance()` also
calls `run_realization_conformance()`. Thus the required realization envelope
of a producer can show missing independent-harness diagnostics after the
adapter fix. Its `_positive_case()` also plans without scope.

This public call can reach an additional executable probe. Each such probe must
use the same scope discipline and the archive lifecycle of its owning harness.
It must not silently receive a plan that is not valid. Do not label unrelated
native, cleanup or observation obligations as passed because target
provisioning or snapshot cases pass. Keep the no-mutation guarantees of
negative probes. Keep the caller's ownership of native cleanup.

Archive deletion and backend resource cleanup are different operations.
`RuntimeControlPlane.close()` drains runtime resources. It does not promise to
destroy the provisioned world. Keep the cleanup contracts of the caller and the
native harness. The temporary archive of the runner must not become a dangling
durable evidence link in its public report. Persistent ownership that the
caller selects is the extension seam for kept artifacts. Do not copy SDL into
report details or metadata.

## Verification and delivery boundaries

Get the required evidence through the public `run_target_conformance()` facade.
Keep both declarations intact. Use a real protected writer and an in-memory
valid reporting backend. Do not build another producer schema. Reuse these
tests and fixtures:

- `runtime_descendant_fixtures.py`;
- `test_issue_1241_materialization_context.py`;
- `test_issue_1241_materialization_runtime.py`;
- the archive and durability tests;
- `test_issue_1649_runtime_descendants.py`.

Their scenario and address assumptions must match the selected probe. Cover
these cases:

- accepted bytes, reference, inventory and provenance;
- reporting with no additions;
- missing, malformed and misbound reports;
- failed publication;
- invalid scope before apply;
- lifetime and cleanup;
- isolation of repeated and concurrent calls.

Check the existing non-negotiating targets and the supplied scenarios. Assert
stable codes and case results. Do not assert raw exception prose. Do not assert
only the aggregate report boolean.

Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `.pre-commit-config.yaml`
and `noxfile.py`. Also reuse `tools/check_repo_policy.py`, the ADR-015 size and
import gates and `tools/verify_all.py`. Local verification is targeted. The
full, integration, fuzz and release suites belong to CI. This issue has no
formal requirement UID. Do not invent one. Do not attach this issue to an
unrelated requirement.

The release criterion is separate from source correctness. Use a
consumer-facing `fix:` title. Use the existing Release Please/PyPI path in
`.github/workflows/release-please.yml`, `release-please-config.json` and
[releasing.md](../explain/releasing.md). Keep the installed wheel/sdist proof in
`test_corpus_packaging.py` and in `tools.python_closure`/canonical CI
verification. That proof needs no source checkout. It also needs no implicit
external backend dependency.

Do not:

- edit versions or changelogs by hand;
- promise an unpublished pin;
- patch installed internals;
- replace the release process.

Maintainer promotion and release approval stay delivery gates. Actual
publication that the resolver can see also stays a delivery gate.

Non-goals:

- Implementation of #1667 during preflight.
- Changes to SDL, published schemas, backend profiles, semantic admission, auth,
  native backend implementations or other repositories.
- New refresh scheduling, probes/collectors, stores, credential/config systems
  or exception/report families.
- Wider native conformance claims.
- A merge or a release during this preflight.
