# Issue 1865: domain-topology preparation equality preflight

Recorded 2026-11-02 against `c8f9340eb`. Non-normative architecture guidance;
the supplied issue #1865 is the delivery contract. No implementation or
implementation plan is included. [ADR-082](adrs/adr-082-authored-identity-domain-topology.md),
[ADR-105](adrs/adr-105-recursive-partial-description-semantics.md), and the
[preparation specification](../../specs/sdl/backend-realization-preparation.md)
already establish the required boundaries; no new ADR or schema is needed.

## Decision and ownership

Preserve exact topology meaning across supported Python-to-JSON transport.
Keep shared JSON equality strict. The comparison boundary must compare portable
views of admitted carriers, rather than require identical Python container
classes or replace structural comparison with digest equality.

Inspection confirms that `compiler.addresses._compiled_domain_binding` produces
ordered tuple controller addresses. `contracts.backend_preparation` deliberately
uses `pydantic_core.to_jsonable_python(..., fallback=jsonable_fallback)` before
constructing its closed response model; `to_runtime()` retains the resulting
payload lists. `planner.realization_preparation._authority_value_valid` compares
the original concern with the converted concern through `structure_matches`.
`domain-topology` is processor-derived and has a payload path but no registered
descriptor projector, so `project_realization_concern` currently returns it
unchanged. Shared `json_equal` then rejects the tuple/list difference.

A local read-only probe reproduced both the supplied minimal refusal and the
same refusal from the existing controller-placement compiler fixture, including
node, account and controller-placement carriers. It also confirmed a second
trap: current same-type tuple comparison accepts `(1,)` versus `(True,)` through
Python equality, while list comparison correctly rejects `[1]` versus `[True]`.
Moving a type check alone is insufficient; supported arrays need recursive,
type-sensitive element comparison in their portable view.

The existing pure owner is `raes_processor.planner.realization_preparation`,
reached through public `raes_processor.planner.prepared_realization_violation`
and `prepared_delivery_violation`. Keep comparison-only transport adaptation
there, using the incumbent codec and public contracts APIs. Cover concern,
residual-payload and selected-completion comparisons consistently, including
nested supported carriers outside concern pointers. Accepting selection must
not merely move the same refusal to delivery. Do not rewrite the authenticated original plan,
compiler dataclasses, backend response, or persisted snapshots for comparison.

`raes_contracts.realization_structure` remains the owner of `structure_matches`,
strict `json_equal`, recursive evaluation, composition and compatibility. Its
shared consumers are a reason to avoid broadening equality for this transport
defect. Contracts must not import processor, runtime, or backend topology types.

## Invariants and extensibility seam

- A tuple and its supported JSON-array representation denote the same ordered
  sequence. Length, position, duplicates, member types and every topology field
  remain significant. Controller candidates are ordered, not a set.
- Preserve strict scalar distinctions recursively, including `True` versus `1`
  inside tuples, lists and records. JCS digests can also collapse numeric
  representations such as `1` and `1.0`; equal digests are neither sufficient
  shape validation nor permission to change a concern.
- Validate finite values before recursive copying or serialization. Reuse
  `validate_realization_value`, `RealizationConstraintLimits`, `PLAN_VALUE_LIMITS`
  and `RUNTIME_SNAPSHOT_VALUE_LIMITS` at their existing owning boundaries. Keep
  aggregate, depth, member, scalar-byte, Unicode and finite-number limits.
  Unknown carriers, sets, bytes, non-string keys and cycles must not become
  admissible through serializer coercion or `jsonable_fallback` marker equality.
- Keep shape validity, exact preservation, delegated choice, configured support
  and observed delivery as separate checks. Do not add defaults, omit unknown
  fields, sort controllers, or turn missing/null/empty into interchangeable values.

The extension seam is the existing admitted-carrier-to-portable-value boundary,
independent of issue number, backend name, resource address and controller count.
Another supported carrier must use the same codec and admission policy without
a new equality flag, topology schema, global serializer registry or backend
configuration knob. Retain the existing `limits=` parameter for bounded value
admission. Concern-specific meaning still belongs to
`project_realization_concern` and its descriptors; transport adaptation must not
replace their environment commitments, set identities or ordered projections.

## Whole-repository gates to preserve

Package paths below are relative to `implementations/python/packages/`.

| Layer and canonical incumbents | Required boundary |
| --- | --- |
| Authored topology: `raes.semantics.domain_topology`, compiler `addresses`, `provisioning`, `placement`, `realization_requirements` | Keep the existing analyzer, typed binding, canonical addresses and exact processor-derived authority on nodes, domain accounts and controller placements. Topology context is distinct from controller-bootstrap instructions and runtime directory evidence. |
| Typed topology and graph admission: `raes_backend_protocols.domain_topology.DomainTopologyBinding.from_mapping`, `domain_topology_plan_diagnostics`; planner `core`; runtime `control_plane_submission` | Reuse closed field parsing, string/address checks, non-empty unique controllers, roles, supported domain profiles, matching node/account/placement bindings and ordering/refresh dependencies across operations, resources and predecessor state. Generic portable-value validation does not replace this graph validation. No second topology model or validator. |
| Transport/config shapes: `contracts.backend_preparation`, `contracts.plan_operation`, `contracts.realization_plans`, `contracts.plan_projection`, `contracts.realization_preparation` | Retain closed response/operation models, strict success boolean, bounded diagnostics/inventory, unique addresses, actions and dependency identities. Preserve request/predecessor digests, execution policy, profile bindings and canonical digest algorithms. The payload's generic dictionary type is not a topology schema. No published shape/version change is expected. |
| Authentication and authority: runtime `control_plane_api` package, `control_plane_api_guards.RequestSizeLimitMiddleware`, `ControlPlaneSecurityConfig`, `RuntimePlanAuthorizationMixin`, `backend_preparation` | Preserve bounded HTTP parsing, authenticated target/role admission, planner registration, manifest/configuration commitment and request/predecessor matching before selection. Equal payload digests do not authenticate a plan. Retain operation-authority, prepared collection, capability, envelope and backend `validate` gates; normalization grants no added operation or topology membership. |
| Profile configuration: runtime `backend_profiles`, `ControlPlaneConfiguration`; contracts `domain_profiles`, `realization_profiles` | Existing legacy and typed domain-profile forms remain owned here. Keep closed configuration options, negotiated target context, profile/configuration digests, resource ownership and installed `validate_profiles` checks. Do not strip typed profile fields to make equality pass or introduce new settings. |
| Secrets and environment: `raes.runtime_environment`, processor `realization_concern_observations`/`realization_concern_projections`, runtime `backend_account_credentials` | Preparation remains read-only and resolves no ambient secrets. Preserve literal-versus-reference environment shapes, sensitivity checks, commitments and credential egress/diagnostic redaction. Account topology carries an authority address, never credential material. Do not serialize raw environment/account data into new diagnostics or artifacts. |
| Host/runtime and publication: `backend_input_contracts`, `backend_calls`, `backend_snapshot_contracts`, `backend_entry_transitions`, `backend_apply_results`, `realization_snapshot_sanitization`, `control_plane_store*` | Keep pre-copy bounds, callback isolation, identity/change accounting, exact selected delivery and post-sanitization revalidation. Rejection keeps the trusted predecessor and no candidate details or success provenance. Existing revision/history publication owns persistence; no migration or comparison cache. The change is in-process: no subprocess, token in argv, environment override, filesystem secret lookup, socket exposure or new service. |
| Errors and observability: `Diagnostic`, `ApplyResult`, `raes_contracts.errors`, `operational_logging`; runtime `prepare_backend_apply` | Value-object validators retain safe `ValueError`; admission uses existing `InvalidInputError`. Preserve `runtime.backend-preparation-invalid` and the fixed value-free refusal. Unexpected foreign callback failures are logged once with `foreign_failure_record`; no payload dumps, exception text, new exception family or logging configuration. See [the shared policy](../develop/exceptions-and-logging.md). |

## Evidence and delivery boundaries

Regression evidence must start with real compilation, retain its tuple until the
actual preparation-response conversion, and exercise runtime admission before
apply. The hand-built issue reproducer alone does not cover compiler drift.
Existing fixtures and patterns live in `test_authored_domain_topology.py`,
`test_domain_controller_placement.py`, `test_issue_1204_backend_preparation.py`,
`test_issue_1204_result_shapes.py` and `test_issue_1200_mixed_runtime_constraints.py`.
Include node/account/controller-placement carriers and nested residual carriers;
check direct and serialized preparation, detached copies, unchanged readback and
changed readback. Prove altered controller membership/order, topology fields,
missing/extra fields, invalid carriers and nested boolean/integer substitutions
still fail. Refused proposals must never call apply or publish candidate state.
Use focused mutation checks for removed type/value/ordering gates when practical.
Targeted tests run locally; full, integration and fuzz suites remain in CI.

Release delivery must reuse `.ground-control.yaml`, `.gc/plan-rules.md`,
`noxfile.py`, `tools/policy/adr_policy.yaml`, `tools/policy/import_contracts.toml`,
`release-please-config.json` and `.github/workflows/release-please.yml` under
[ADR-107](adrs/adr-107-artifact-promotion-and-release-admission.md).
Use `fix:` metadata for the consumer-visible correction. Release Please
owns versions and changelog. Preserve exact-source verification, tested wheel/
sdist admission and protected publishing. Release publication is outside
this comparison change.
Do not invent a version or publish here.

## Non-goals

- Implement the issue during preflight.
- Change universal backend subsumption, recursive semantics, topology authority, or compiler tuple APIs.
- Add a LilRAE/capture-specific bypass or bypass transport validation.
- Create a schema, exception hierarchy, persistence format, or release workflow.
- Import LilRAE or use lab files, Docker, credentials, or another checkout.
- Retry TechVault startup or change the downstream pin.

Preparation acceptance does not prove that a domain was operationally realized.

## Implementation design refinement

The runtime regression also found tuple/list differences in original-authority readback.
The [comparison design](issue-1865-preparation-comparison-design.md) therefore places the shared conversion in `semantics.realization_comparison`.
Planner comparisons and the fallback concern projector reuse its public `portable_realization_value` function.
Shared JSON equality stays strict, and existing descriptor projectors keep their meaning.
