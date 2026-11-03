# Issue 1866: Preserve absent node identity in plan authority

Date: 2026-11-02. This note defines design limits for issue #1866.

## Responsibility boundary

RAE owns the language, portable contracts, reference processor, and portable runtime enforcement.
Those contracts govern all backend implementations.
Backend and consumer code must conform to RAE's public interfaces and version policy.
Their dependency pins, API migrations, and concrete execution tests do not set this design's requirements.
RAE's own contract and compatibility policies remain binding.

## Decision and invariants

The reported defect converts absent optional node identity values to empty strings.
The fix belongs at the compiler and resource boundary.
`NodeRuntime.os_distribution` and `NodeRuntime.architecture` must keep `None` when the source value is absent.
Their operation payload fields must contain JSON `null`.
Populated values keep their canonical vocabulary.
A planner-only payload patch would leave two conflicting forms of the same resource.

The selected typed source, compiled resource, desired resource, and operation must agree.
Existing explicitness rules may omit the key from `spec.node`.
The fix must not add an authored constraint to fill that map.
A null value and an omitted JSON key are not always equivalent.
This fix preserves the current typed projection of omitted fields.
It does not change explicit-null authoring rules.

Each operation value must reproduce its retained recursive binding.
A changed value with its old binding must fail admission.
The processor must not rebuild trusted bindings from changed payloads.
Modes, provenance, bounds, pointers, envelope identity, and explicitness retain their meaning.
Open authority still requires source integrity.
A backend uses preparation for a later permitted choice.
It cannot substitute that choice into the submitted source.

Existing ADRs cover this correction.
ADR-105 and the [recursive constraint contract](../../specs/sdl/recursive-realization-constraints.md) distinguish values, presence, defaults, and delegation.
ADR-036 and ADR-121 own package boundaries.
ADR-070 owns configuration-bound realization.
ADR-115 assigns concrete backends to separate distributions.
The [architecture preflight for #674](issue-674-target-node-cpu-architecture-preflight.md) prohibits host-derived target architecture.
No new ADR is needed.

## Existing owners and checks

Package paths below start at `implementations/python/packages/`.

- Source shape: `raes.nodes.Node`, governed normalizers, and `raes.validator._nodes_infra_network` own typed validation.
  Keep aliases, governed extensions, OS field dependencies, and node/package architecture agreement.
  Empty strings are not new supported authored values for these fields.
- Source admission: `raes_processor.trial_compiler` and `trial_realization.realize_admitted_trial_entry` own exact input joins.
  Keep plan reconstruction, apparatus choice, instantiation provenance, and target/run/instantiation scope.
  Do not change the source to match a lossy payload.
- Projection: `compiler.provisioning`, `models.resources.NodeRuntime`, `resource_payload`, and `planner.resources` own compiled values.
  Keep their shared dataclass projection.
  Do not add another node model, field registry, or serializer cleanup pass.
- Authority: concern descriptors, recursive constraint compilation, and authority materialization own source bindings.
  Reuse their registered paths and bounded canonical binding.
  A digest is neither authentication nor a support claim.
- Plan shape: `PlanOperationModel`, `ProvisioningPlanModel`, plan projection, and `control_plane_api_models` own portable plans.
  Keep closed outer models, unique addresses, canonical pointers, and domain checks.
  Payload dictionaries already permit JSON null.
  Test forward and reverse projection without losing it.
- Capability: manifest validation, capability domains, and coupled OS checks own support decisions.
  Keep manifest conversion, supported contracts, concept vocabularies, finite domains, and configuration digests.
  Nullable intent must not make required realizer configuration nullable.
  It must not take a value from that configuration.
- Completion: `prepared_node_admission`, `realization_preparation`, and `realization_node_defaults` own prepared nodes.
  Keep typed node and infrastructure admission, identity equality, residual payload checks, and joint OS support.
  Comparison defaults must not change source commitments.
- Runtime: experiment admission and provisioning submission own checks before effects.
  Keep installed-target shape, manifest equality, authority inventory, pointer, binding, selection, envelope, and operation-guarantee checks.
  Control-only trials get no exception.
  Refusal must precede backend apply and committed experiment admission.
- Access: runtime ownership, actor/scope selection, and planner authorization remain enforced.
  HTTP callers retain target-bound identity and role checks.
  This fix needs no route, role, token handling, or authorization exception.
- Protected values: environment, generated-value, secret-reference, and redaction owners remain unchanged.
  Do not replace false-like values across the payload.
  That could break source exclusivity, redaction, or unrelated bindings.
  Use synthetic fixtures and existing secret channels.
- Host boundary: injected `RuntimeTarget` and installed component checks remain authoritative.
  Add no host probe, native dependency, backend-name switch, daemon contact, or service.
  RAE's reference stubs exercise the portable interfaces.
  Credentials must stay out of arguments, URLs, shell text, and reports.
- Errors: reuse shared diagnostics, `ConflictError`, operational logging, and fixed HTTP envelopes.
  Follow [the maintained error policy](../develop/exceptions-and-logging.md).
  Do not log source values, raw exceptions, environment values, or backend objects.
- Persistence: canonical digests and existing stores carry new plan values.
  Newly generated digests may change.
  Retained commitments, source digests, ledger records, and archives must not change in place.
  Recompile refused artifacts through the public path.
  No data migration or repair service is required.

## Adjacent hazards and extension points

Prepared-node identity checks must preserve nullable field values.
They must compare nullable fields with their typed specification.
They must still refuse inconsistent pairs.
Keep this change field-specific in the existing owner.

The OS capability comparison requires strings in its selected OS tuple.
An absent source value differs from a selected concrete completion.
The existing partial-choice contract must govern any comparison conversion.
Null intent must not admit an unsupported or mismatched concrete OS tuple.

`os_family` also converts absence to an empty string.
The Linux reproduction supplies that field.
Record any analogous failure found during this work.
Do not treat all identity fields as one sentinel migration.
`os_version` has an authored empty string default.
Package architecture has a separate empty sentinel.
Neither becomes nullable through this fix.

Future nullable identities belong in typed fields, concern descriptors, and governed vocabularies.
Backend variation stays in injected targets, manifests, envelopes, backend keys, and plan scope.
No global absence registry is needed.

## Evidence and scope

Reuse existing authority, recursive-carriage, preparation, trial-realization, external-backend, and experiment-runtime tests.
Cover both fields omitted and each field omitted alone.
Cover supported values and aliases.
Keep the original binding when testing a substituted supported value.
Check source, resource, operation, binding, and portable JSON round trips.
Test public realization followed by public experiment admission.
`ExecutionPlan.is_valid` alone does not prove runtime admission.
Test that refusal causes no backend apply or admission record.
Keep preparation's positive and rejection cases.
Mutation checks must detect restored string coercion and bypassed binding comparison.

RAES ships portable contracts and stubs, not a native backend.
Its tests establish the portable semantics and enforcement that RAE owns.
They make no claim about concrete backend execution.
A particular backend's installed harness is not a gate for this correction.
No other repository needs to change to establish the RAE contract.

Reuse repository configuration, plan rules, policy tools, the locked tooling project, and the nox graph.
Run targeted checks locally.
Full, integration, installed-distribution, and fuzz suites run in CI/CD.
Keep policy, review, CI, and release gates.
Use a release-triggering `fix:` title.
Release Please owns versions and `CHANGELOG.md`.
Add no fragments or second package.
Follow RAE's published compatibility and release policies.
No schema change is expected.
Any actual published-schema change must follow ADR-061 and the publication manifest.
It must also keep `schema_bundle()` output equal to the published schemas.

## Non-goals

The fix adds no authority waiver or new absence algebra.
It does not widen backend capabilities or infer identity from the host.
It adds no duplicate schema, validator, model, exception, or workflow.
It changes no observation or retention policy.
It rewrites no stored history and implements no native backend.
It changes no other repository or release lane.
