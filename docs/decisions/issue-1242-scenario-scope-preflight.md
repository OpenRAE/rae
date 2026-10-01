# Issue 1242: binding scenario scope preflight

Architecture guidance for issue #1242 / SEM-225, reviewed 2026-09-16 against
the current repository and the supplied requirement and issue payloads.
This note records proposed design boundaries, not an implementation plan or a
claim of implemented support. No accepted ADR or published contract changes here.

## Decisions

### Permission is distinct from realization and evidence

Use the in-world-effect definition in
[materialization attestation](../../specs/sdl/materialization-attestation.md)
(`raes-materialization-effects/v1`) for both disclosure and permission. An
effect counts if a participant could in principle observe it, including effects
inside an existing node. Apparatus labels, backend ownership, lack of an actual
observation, or placement outside a participant's logical view do not exempt it.
Out-of-world bookkeeping is excluded; its in-world effects are included.

Permission does not replace ADR-066's independent augmentation classifications.
Reuse `ExperimentAugmentationDisclosureModel`: environment effects need portable
carriers, participant visibility needs markings and authorized projection, and
comparability relevance needs comparability/observer-effect disclosure. An
apparatus-only change may still affect comparability. Absence of an in-world
addition is not proof of equivalent runs, and open scope waives none of these
disclosure or evidence-reference obligations.

Closed scope prohibits backend-introduced effects beyond the admitted scenario.
It does not prohibit choosing an image, operating system, or other realization
value within authority already delegated by that scenario. Reuse original
recursive realization constraints to establish that distinction; the backend's
assertion that an addition is necessary is not delegation. A new listener,
forwarder, sidecar, injected executable/file, sshd `ForceCommand`, changed sensor
rules, mount, capability, or network attachment can change the world even when
no portable node is added. Removal/replacement can also introduce an effect.
Checking only origins with `change="added"` is insufficient: #1241 represents
some such changes as `selected`, and records removed members separately.

Open scope permits necessary additions only within all other admitted
constraints and requires attestation of them. It does not override exact
values, required members, collection closure, resource ownership, participant
policy, artifact-delivery authority, or observation prohibitions. Conversely,
an open realization collection does not itself authorize evidence apparatus.

Apply the same boundary to processor-inserted instrumentation. Preserve authored
intent and explicitness provenance through compilation: inserting apparatus into
the compiled input must not turn it into author permission before backend scope
admission. Ordinary source-mandated derivation remains distinct from augmentation;
`PROCESSOR_DERIVED` or `BACKEND_REALIZED` alone cannot decide permission.

Reuse these owners without merging their meanings:

| Existing owner | Meaning retained |
| --- | --- |
| `RealizationDesignation`, recursive constraints, `PreparedNodeCollectionAuthority` | Permitted realizations, portable membership and lifecycle authority. |
| `EvidenceRequirement`, `CaptureDemand`, `ObservationCaptureOffer`, `CAPTURE_DIMENSIONS` | Required capture and complete compatible capability offers. |
| `ObservationDemandRule` and its normalizer | Observation purpose, selectors, collection, retention, export and prohibitions. |
| `ParticipantObservationBoundary` | Participant information/view semantics; not physical network isolation or an addition grant. |
| `MaterializedScenario`, `MaterializationOrigin`, augmentation disclosures | What was materialized and its effects; neither permission nor proof that capture succeeded. |

### Scope and default

Add only the missing **addition-permission axis**, authored once in shared
`ScenarioContent` alongside the observation/evidence surfaces. Use a scenario
default with scoped node/concern exceptions, resolved through the existing
canonical semantic-address and composition-namespace machinery. Do not put
independent permission booleans on every evidence requirement or node type.
References near evidence/boundary declarations can select the same policy;
they must not create competing authorities. Do not overload the existing
free-text `EvidenceRequirement.scope`, observation lifecycle modes, or
`realization.default` with this new meaning.

The author selected **open by default** on 2026-09-16: closed by default would
place a large, unexpected burden on scenario authors. Preserving compatibility
is a consequence of that authoring decision, not its sole rationale. Authors
who require restrictions must explicitly forbid additions. This supersedes the
initial closed-default recommendation. An omitted declaration retains the existing
negotiated backend contract; an explicit open or closed declaration requires
scope-capable admission and materialization attestation. A scope-capable backend
also treats omitted policy as open. Do not infer an explicit permission from
authored monitoring nodes or change existing realization defaults. Publish the
negotiation and migration rules through the existing evolution policy; older
consumers must refuse an explicit policy they cannot enforce. Historical
archived artifacts retain their original interpretation.

Within one location, the most specific explicit author rule governs; the root
default fills gaps. Reject conflicting rules of equal specificity. Preserve
import namespaces and local restrictions rather than letting an outer default
widen a module's explicit policy. Resolve all affected locations of an effect:
one applicable closed location refuses it, even if its installation location is
open. Thus a management collector can be allowed while a participant-reachable
listener, traffic redirection, host wrapper, or dual-homed attachment is refused.
Network names and the word "management" are not evidence of isolation.
Here "applicable closed" means the effective rule after local specificity
resolution; an explicit closed root default must not defeat its open exceptions.
Reuse address and partition primitives, not observation-specific precedence:
`observation_axis_winner` prioritizes required demands and breaks ties by identity,
which is not permission conflict resolution. Neither experiment capture demand
nor `apparatus_realization_default` may widen author addition permission.

An added member is addressed through its admitted enclosing collection and
proposed native identity; a selector need not reference a nonexistent authored
node. Existing members/concerns use canonical resolved identities. Reuse
`observation_scope`, `realization_structure.canonical_semantic_address`,
`semantic_address_contains`, declaration indexes and native collection profiles;
no string-prefix matching, list-position identity, or second selector language.
Unknown impact/coverage cannot establish closed-scope compliance. Physical
reachability claims need support from the admitted network/listener/participant
contracts; logical observation boundaries alone cannot supply that proof.

### Admission and backend contract

Build on [read-only preparation](../../specs/sdl/backend-realization-preparation.md)
and the existing backend manifest negotiation, not another provisioning workflow.
The missing information is a complete prospective effect declaration, with the
requirements it serves and affected scopes, for the selected backend
configuration. Share #1241's SDL owners, difference/identity logic and coverage
profile. Do not fabricate a post-materialization attestation before execution,
or introduce parallel collector/listener/wrapper DTOs. Prospective selection,
permission, actual delivery and evidence satisfaction remain separate claims.

The declaration must cover all effects, including shared apparatus serving
multiple requirements and effects inside existing resources. A capability offer
alone does not prove that it can be delivered without forbidden additions.
Retain `capture_admission_diagnostics` and its complete-offer matching: do not
combine partial offers, invent capture support, or downgrade required evidence
to best effort. Optional collection also cannot bypass scope permission.

Bind permission and prospective effects to the exact admitted scenario, plan,
operation, backend manifest/configuration and predecessor using the existing
canonical commitments and planner authorization. Check all relevant producers
and phases before the first world mutation, probe, secret resolution, artifact
generation or guest rewrite. Preparation remains pure. It may use configured
support and supplied state, but may not materialize to discover feasibility.
If a backend cannot establish a compliant completion beforehand, it refuses.
Operation/audit records of the refusal are allowed; a half-built range is not.

**Current integration gaps that must not be hidden:**

- `backend_preparation.prepare_backend_invocation` currently prepares only a
  `ProvisioningPlan`. `RuntimeManager` subsequently runs time, participant,
  evaluation and orchestration phases. Per-phase late checks alone cannot
  establish scenario-wide admission before any mutation. Use the incumbent
  execution-plan/control-plane admission owners to admit the complete known
  effect set, while retaining immediate-predecessor checks at each invocation.
  A missing phase/configuration dependency is a refusal, not guessed authority.
- `backend_observation_calls` currently finalizes backend materialization before
  `execute_plan_observation_demand`. Any observation setup that changes the
  world must already be admitted and be covered by the final attestation after
  those effects. A pre-hook attestation cannot claim post-hook completeness.
- #1241's models and result gate are present, but the reference backend's
  `REFERENCE_BACKEND_SUPPORTED_CONTRACT_VERSIONS` explicitly excludes
  `backend-materialization-attestation-v1`. Inspect actual selected manifest
  support; shared schema availability does not imply backend support. Neither
  open nor closed execution under this policy may silently lose attestation.
  Registering a new contract in `BACKEND_SUPPORTED_CONTRACT_IDS` must not cause
  catalog-derived manifest defaults to advertise unimplemented support.
- Capture demand compilation lives in the processor; portable phase plans
  chiefly carry normalized observation demand and negotiated source context.
  Preserve authoritative evidence-requirement identities and policy across
  lowering/serialization so direct runtime submissions cannot omit them.
- `observation_admission` currently refuses required observation alongside
  mutation where compensation is unavailable, and refuses required export
  without a delivery owner. Scope permission must retain those refusals; an
  open scenario is not a promise that every capture/lifecycle request is executable.

Keep `raes_contracts.plan_effects.plan_can_mutate` as the shared effect classifier
for authorization and observation atomicity. Prospective effects cannot escape
these gates because the submitted operation list is empty. Retain the existing
runtime ownership, mutation serialization, idempotency and revision checks;
permission admission is part of that lifecycle, not a separate check-then-apply
endpoint. Planner authorization is process-local: a recovered receipt or a stored
digest is not permission to execute again after restart.

If runtime configuration or state changes after admission, invalidate the bound
choice and refuse/re-admit through the existing operation lifecycle before new
effects. Do not automatically replay apply. Combined backends retain producer
scope and cannot authorize each other's effects or hide contradictory claims.

After materialization, reuse `materialization_differences`,
`validate_materialization_origins`, `admit_materialization_submission` and the
backend result gate to compare the actual complete inventory against both the
original authority and the admitted effects. Closed scope does not waive a
no-additions attestation. Truthful disclosure cannot cure a permission violation.
Unexpected effects or failed mandatory capture prevent success. Preserve honest
cleanup inventory through the existing failure/compensation owners; returning a
predecessor snapshot is not physical rollback or proof of zero side effects.
Replanning must account for previously admitted additions: tightening scope may
require explicit remediation, and must not silently retain them or delete them
as a side effect of a refused admission. Authorized teardown stays available.

### Refusal reaches the operator without leaking values

Use `Diagnostic`/`DiagnosticModel`, `ApplyResult`, operation receipts and existing
API/CLI rendering. A known unsatisfied closed-scope requirement needs a stable
error code, its canonical requirement identity, the denying scope, and a safe
description of the effect that would be necessary (for example, "session-log
requires an sshd forced-command wrapper on host"). Multiple unmet requirements
must remain distinguishable. Missing capability and inability to determine
effects are separate reasons, not fabricated claims that a particular collector
would solve them. Return failure and no success/evidence claim.

`prepare_backend_apply` currently catches failures into a generic preparation
diagnostic; it discards even well-shaped backend refusal diagnostics.
`value_free_backend_diagnostics` also removes backend prose for credential plans.
The solution must preserve validated, bounded refusal facts and render their
operator message at a trusted boundary, while retaining those redaction rules
for arbitrary backend text. Do not remove broad exception containment, forward
`str(exc)`, bypass credential sanitization, or add an exception hierarchy.
Schema-valid strings alone are not safe: requirement/effect references must
resolve against trusted input or the admitted proposal, with escaped, bounded
display text and no commands, environment values, source excerpts or secrets.
The HTTP operation routes convert some `ValueError`s to 409 responses using
`str(exc)`. Do not send backend refusal/validation exceptions down that path:
carry expected refusals as admitted diagnostics, and retain redacted 422/500
handling for invalid requests and unexpected failures.

## Cross-cutting layers and canonical incumbents

Python modules below are relative to `implementations/python/packages/`.
These obligations apply to in-process use and HTTP alike.

| Layer / incumbent | Required invariant |
| --- | --- |
| Source ingress: `raes.parser`, `_yaml_loader`, `_source_profile.SDLParserLimits`, `_base.SDLModel`; `raes_contracts.json_ingress` | Keep safe single-document decoding, duplicate-key/alias/depth/work/byte limits, finite JSON and closed fields. Bound aggregate selector/effect/refusal input before copying, hashing or recursive validation. |
| SDL semantics and phases: `SemanticValidator`, declaration/reference metadata, composition, `instantiate`, `phase_contracts`, `ScenarioContent` | Resolve kinds, ambiguities, namespace/replica identities and source lineage. Carry the policy through normalized/expanded/instantiated/materialized phases and ordinary parsing/inspection; never promote descriptive input into execution authority. Permission is control metadata, not a backend-selectable realization dimension. |
| Plan/configuration: `planner.core`, `prepared_node_admission`, `backend_profiles`, `BackendManifest`, `manifest_authority`, `plan_projection`, `control_plane_plan_authorization` | Admit membership, dependencies/cycles, artifacts, joint capabilities and profiles independently of addition permission. Seal policy/effects in canonical plan projections and every DTO/codec; reject missing, changed or unsupported versions/configuration, including empty-operation plans. Authenticated transport or a caller-provided digest is not plan authority. |
| Capture/lifecycle: `capture_admission`, `capture_dimensions`, `compiler.observation_demands`, `observation_demand_resolution`, `observation_admission`, `observation_execution`, `observation_results` | Preserve requirement-to-capture joins, required/prohibited conflict checks, observation strength, retention/export and compensation admission. Selection, attestation, telemetry availability and actual required evidence delivery are distinct. |
| Secret and environment shapes: `RuntimeEnvironmentVariable`, `runtime_values.enforce_observed_value_redaction`, `SshForcedCommand`, generated-artifact validation, `backend_account_credentials` | Preserve literal/`value_from` exclusivity, operator-secret restrictions, safe omissions and command kind/redaction consistency. Existence of a forbidden wrapper remains reportable without its command. Apply rules to additions and refusal data; no ambient secret lookup, secret hashes as substitutes, or snapshot commitments serialized as SDL values. |
| Backend trust boundary: `backend_input_contracts`, `backend_call_contracts`, `backend_snapshot_contracts`, `backend_entry_transitions`, `backend_effect_transitions`, `backend_materialization` | Isolate supplied values; retain exact ownership, transition accounting, original constraints, selected-completion checks and validation after sanitization. Bound typed refusals as well as success results; rejected candidates never acquire accepted-state provenance. |
| Authentication/exposure: `ControlPlaneSecurityConfig`, `control_plane_api._auth`, `_operation_routes` request guards, participant audience/control bindings | Keep verified identity, target-bound roles, bounded requests/queues and authenticated plan admission. No new public endpoint, auth toggle or environment-based bypass. In-world visibility does not authorize participant access to policy, full inventory or operator refusals. |
| Diagnostics/audit: `DiagnosticModel`, `portable_diagnostic_payload`, `backend_result_diagnostics`, control-plane receipt/audit and HTTP exception handlers | Preserve the 512-character message and bounded identity/count contracts, stable codes and pointer conversion. Expected scope refusal remains an operation failure; unexpected exceptions use the redacted envelope. Audit decisions/correlation, never raw backend errors, capture bodies, tokens or commands. |
| Host/process: reference `drivers.oci` injected runner, libvirt `guest_transport` | Admission launches no diagnostic guest scan or installation. Execution keeps fixed argv, bounded timeouts/output and existing credential channels. No shell interpolation, tokens/secret-bearing commands in process argv, or host paths in portable effect identities. |
| Durability: `ControlPlaneStore`, `LocalControlPlaneStore.commit_terminal_operation`, snapshot codecs, `RunMaterializationArchive` | Persist refusal through the existing operation/audit transaction without advancing accepted world state. Successful attestation uses protected immutable bytes before accepted references, checksums and run binding; keep containment/symlink defenses and runtime-owned filenames. No backend URI auto-fetch, parallel refusal database, or false archive/reproducibility success. |

Transport budgets differ: HTTP defaults to 1,000,000 bytes, materialization to
1 MiB, and SDL source to 8 MiB. A valid standalone SDL file plus proposal/plan
envelope may exceed transport capacity. Reuse bounded carriers/artifact handling;
do not remove a limit or copy the full scenario into each refusal/effect record.

## Extensibility and repository boundaries

The extension seam is a versioned, bounded addition policy over canonical scope
identities plus the shared materialization coverage profile. Resolve it with
explicit limits and existing concern/collection profiles. Backend adapters map
their configured mechanisms to that common vocabulary and requirement identity;
the resolver does not enumerate today's collectors or backend names. New concern
families, capture mechanisms and mixed producers extend those owners rather than
requiring a new policy engine. No unrestricted expression language is needed.

Public syntax must stay aligned with `specs/sdl/sections.md`, `references.md`,
language metadata, phase catalogs, concept-authority artifacts and generated
schema exports. Published schemas under `contracts/schemas/` are authoritative;
reuse the publication manifest/per-entry change ledgers and `schema_bundle()`
parity, fixtures, and the existing 500 KB publication budget. A changed default
or incompatible wire shape needs the existing schema evolution/versioning
process; an optional field silently ignored by older consumers is insufficient.
Preserve dependency direction: shared carriers in `raes_contracts`, SDL meaning
in `raes`, lowering in `raes_processor`, execution in `raes_runtime`, native
mechanisms in backend packages. SDL must not import processor/runtime code.

Workflow owners remain `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/nox_support`, repo policy, schema/publication, concept-authority and
generated-artifact checks. The supplied issue explicitly binds SEM-225; set
`RAES_REQUIREMENT_UID=SEM-225` when the branch lacks the UID. Existing #1241
traceability proves neither #1242 permission support nor backend conformance.
Report unavailable governance honestly; a skipped check is not a pass and does
not authorize policy changes or invented traceability. Release tooling owns
versions/changelog.

## Acceptance guardrails and non-goals

Extend the incumbent #1204 preparation/result-admission, #1112 required-capture,
#1212 observation-policy, #1241 materialization/origin/archive and control-plane
tests. Meaningful behavioral evidence must include:

- Open omitted/default and explicit closed scopes; open permitted additions; a closed
  scenario successfully realized without additions; ordinary delegated value
  selection; closed management/participant intersections and unknown coverage.
- Processor-inserted effects retaining author scope, effective open exceptions
  under a closed default, conflicting equal-specificity rules, and independent
  apparatus/comparability classifications with their existing run evidence joins.
- Listener/wrapper/rule changes within authored nodes; membership additions;
  namespace imports, keyed reordering, replicas, multiple requirements sharing
  apparatus, and original realization constraints remaining binding when open.
- Backend/collector/guest/secret/artifact spies proving known refusals precede
  effects across phases; no direct-manager, serialized-plan, empty-operation or
  unsupported-manifest bypass. Configuration/predecessor changes invalidate
  permission, and unauthorized actual effects or failed capture cannot succeed.
- Operator-visible requirement and necessary-effect reasons surviving credential
  redaction, API conversion and restart; malformed/oversized/malicious refusal
  carriers stay value-free; rejected admission leaves accepted world state intact.
- Honest partial-failure cleanup, immutable post-hook attestation, migration
  behavior and existing required/prohibited observation boundaries.

Non-goals: backend installation recipes in portable packs; a universal topology
solver; continuous host surveillance or proof against malicious backends;
cryptographic attestation; a new logging, persistence or workflow framework;
weakening evidence to achieve success; automatic permission expansion, teardown
or apply replay; editing external repositories; implementing this issue during
preflight. A focused design note suffices; normative changes belong to the
subsequent implementation and its existing authority/evolution gates.
