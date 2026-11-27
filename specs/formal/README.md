# Formal specs

Find exact invariants, state models, and evidence limits for SDL subsystems here.
Each domain uses this path:

`specs/formal/<domain>/`

## Domain references

- `specs/formal/workflows/`
- `specs/formal/objectives/`
- `specs/formal/planner/`
- `specs/formal/runtime-contracts/`
- `specs/formal/participant-semantics/`
- `specs/formal/participant-behavior-model/`
- `specs/formal/participant-runtime/`
- `specs/formal/time-model/`
- `specs/formal/experiment-core/`
- `specs/formal/scenario-variation-trial-realization/`
- `specs/formal/scenario-satisfiability/`
- `specs/formal/exploit-path-analysis/`
- `specs/formal/validation-admission-profiles/`
- `specs/formal/sdl-phases/`
- `specs/formal/runtime-control-plane/`
- `specs/formal/participant-episode-model/`
- `specs/formal/realization/`
- `specs/formal/artifact-transformations/`
- `specs/formal/assessment/`
- `specs/formal/behavioral-relations/`

Cross-domain references can remain at the top level.
[Composition readiness](composition-readiness.md) gives invariants across source boundaries.
[Observability and evidence](observability-evidence-plane.md) separates the evidence planes.

Each domain directory should include a short README that explains:

- scope
- invariants or properties under study
- relationship to implementation and tests

Formal methods are optional under
[ADR-007](../../docs/decisions/adrs/adr-007-lightweight-formal-methods-policy.md).
The [coding standards](../../docs/explain/reference/coding-standards.md)
explain when they apply.
An optional method does not make a published normative obligation optional.

The canonical mapping from change classification to verification artifacts
lives in `specs/formal/assurance-policy.yaml`, governed by
`docs/decisions/adrs/adr-018-classification-based-assurance-policy.md` and
gated by `tools/check_assurance_policy.py` (`nox -s policy`).

The separate [fulfillment map](assurance-fulfillment.yaml) records delivered artifacts and waivers for each domain.
A waiver needs an ISO date and a tracking reference.
The same checker checks that map.
A waiver remains a gap, not delivered evidence.

## Read the evidence boundary

A formal model states a required relation or invariant.
A bounded test exercises only its declared inputs and state space.
A proof applies only to its stated theorem and assumptions.
None of these alone establishes native backend delivery.
Use each domain's implementation mapping and tests to identify observed coverage.
Use [local checks](../../docs/develop/check-specification-contracts.md) to repeat selected checks.
