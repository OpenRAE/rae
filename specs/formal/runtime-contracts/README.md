# Runtime Contract Semantics

This directory holds the formal artifacts for portable runtime result contracts.

## Scope

- typed workflow execution envelopes
- typed workflow step execution state
- typed evaluator result envelopes
- typed evaluator history streams
- shared [backend result admission](backend-result-admission.md), including
  resource identity, domain and target ownership, transition accounting, and
  trusted-predecessor preservation (ASR-532)
- backend participant capability declarations
- manager-side validation of backend workflow results
- manager-side validation of backend evaluator results
- participant backend-facing contract surface (API-405/406/407/408/411): see
  [participant-backend-contracts.md](participant-backend-contracts.md),
  governed by ADR-060

## API-405 - Backend Participant Capability Declarations

`API-405` requires backend manifests with a participant runtime surface to
declare the participant roles, behavior features, and interaction features that
surface supports. The declaration lives on `backend-manifest/v2`
`capabilities.participant_runtime`, because the support claim belongs to the
backend apparatus, not to authored participant assignments, control-plane
caller roles, or mutable episode state. If `participant_runtime` is absent or
`null`, the manifest is declaring that it has no participant-runtime surface;
the API-405 role/feature fields are mandatory once that block is present.

The standard vocabulary is intentionally lineage-bound:

- participant roles reuse the existing exercise-role surface (`white`,
  `green`, `red`, and `blue`) from declarative participant framing;
- behavior features name the RAES participant-semantics surfaces established
  by `lineage.md`, ADR-022, and `specs/formal/participant-semantics/`:
  action contracts, preconditions, effects, observation boundaries, behavior
  history, state transitions, failure classes, attribution support, temporal
  contracts, and outcome interpretation;
- interaction features match the SEM-209 classes: coordination, contention,
  interference, and shared-state change.

This follows the primary and adjacent literature without adopting one external
API as the authority. Gym/Gymnasium, PettingZoo, OpenSpiel, POMDP/POSG work,
CybORG, CyberBattleSim, CyGIL, CALDERA, and benchmark-methodology critiques
motivate explicit action, observation, episode, role, interaction,
provenance, and outcome surfaces. Backend manifests therefore make a support
claim that conformance can falsify against published contract support instead
of implying support from runtime presence alone.

The controlled vocabulary extension policy is governed extension. Backend
specific role or feature terms must use an `x-<owner>:<term>` identifier and
remain bound through `concept_bindings`. RAES can verify the syntax and
authority binding for extension terms; backend-specific evidence obligations
remain owned by the backend that defines the extension.

### API-405 Evidence Criteria

Standard API-405 terms have term-level evidence criteria in
`raes_backend_protocols.capabilities.PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS`.
`run_target_conformance()` rejects standard participant capability claims when
the manifest omits the published contracts that carry the corresponding runtime
evidence.

The participant episode evidence set is
`participant-episode-state-envelope-v1`,
`participant-episode-history-event-stream-v1`, and `runtime-snapshot-v1`.
The participant behavior evidence set is
`participant-behavior-history-event-stream-v1` and `runtime-snapshot-v1`.

| Term | Required evidence set | Term-level lineage and rationale |
| --- | --- | --- |
| `white` | Participant episode evidence set | ADR-020 keeps exercise framing separate from runtime identity; RUN-311 episode state/history makes the assessor role observable without converting it into control-plane authorization. |
| `green` | Participant episode evidence set | ADR-020 authored participant identity and operating scope require a runtime episode record for benign/defender infrastructure actors. |
| `red` | Participant episode evidence set | ADR-020 red-team framing and `lineage.md`'s cyber-range lineage require explicit participant episode identity rather than inferring attacker support from scenario prose. |
| `blue` | Participant episode evidence set | ADR-020 blue-team framing requires participant episode state/history so defender support is checkable independently of evaluator outcomes. |
| `action_contracts` | Participant behavior evidence set | ADR-022 and SEM-211 require action applicability, inputs, visibility, and results to be explicit instead of backend-local behavior. |
| `preconditions` | Participant behavior evidence set | SEM-211 requires fail-closed validation for unresolved or unsatisfied preconditions. |
| `effects` | Participant behavior evidence set | ADR-022 and SEM-211 distinguish intended effects, side effects, visibility effects, and downstream state changes. |
| `failure_classes` | Participant behavior evidence set | SEM-211 requires portable failure labels so rejected, unresolved, or failed behavior is not collapsed into opaque backend errors. |
| `observation_boundaries` | Participant behavior evidence set | SEM-210 and `lineage.md` separate participant-visible observations from hidden truth, evidence-only records, and redacted disclosures. |
| `behavior_history` | Participant behavior evidence set | ADR-022 requires ordered participant behavior records so replay, review, and benchmark audit do not depend on backend-private traces. |
| `state_transitions` | Participant behavior evidence set | SEM-208 and SEM-211 require participant-local state and action-result transitions to be explicit and replayable. |
| `attribution_support` | Participant behavior evidence set | SEM-212 follows the Halpern-Pearl caution in `lineage.md`: attribution must be evidence-labeled, not inferred from timestamp adjacency. |
| `temporal_contracts` | Participant behavior evidence set | SEM-213 requires declared time domains, clock authority, cadence, deadlines, dwell, and cooldown semantics. |
| `outcome_interpretation` | Participant behavior evidence set | SEM-215 separates participant-local action/episode outcomes from objectives, rewards, and evaluator success. |
| `coordination` | Participant behavior evidence set | SEM-209 and ADR-022 require joint-action synchronization to be explicit rather than hidden in backend scheduling. |
| `contention` | Participant behavior evidence set | SEM-209 and ADR-022 require exclusive-resource conflicts to be represented as participant interaction, not incidental failures. |
| `interference` | Participant behavior evidence set | SEM-209 and ADR-022 require one participant action's effect on another action's preconditions, observations, effects, or outcome to be reviewable. |
| `shared_state_change` | Participant behavior evidence set | SEM-209 and ADR-022 require shared object reads/writes to be explicit so multi-participant semantics do not collapse into final state only. |

## Implementation Mapping

- shared result constraints: `implementations/python/packages/raes_processor/semantics/workflow.py`
- typed result models: `implementations/python/packages/raes_processor/models/`
- manager contract validation: `implementations/python/packages/raes_processor/manager.py`
- backend example: `implementations/python/packages/raes_backend_stubs/stubs.py`
- participant capability contract model:
  `implementations/python/packages/raes_contracts/contracts/`
- participant capability runtime declaration:
  `implementations/python/packages/raes_backend_protocols/capabilities.py`
- backend manifest renderer:
  `implementations/python/packages/raes_backend_protocols/manifest.py`
- governed vocabulary authority:
  `contracts/concept-authority/controlled-vocabularies-v1.json`

## Tests

- `implementations/python/tests/test_runtime_manager.py`
- `implementations/python/tests/test_runtime_models.py`
- `implementations/python/tests/test_runtime_contracts.py`
- `implementations/python/tests/test_backend_manifest.py`
