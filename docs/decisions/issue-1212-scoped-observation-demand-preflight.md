# Issue 1212 scoped observation-demand architecture preflight

Date: 2026-09-06

Status: implementation guidance; non-normative

Issue #1212 does not create another evidence or observability system. It adds one
scope-aware demand contract and carries its normalized result through the
existing scenario, task, evidence, run-policy, planning, backend, persistence,
and reporting owners. The normative implementation remains subject to ADR-064,
ADR-066, ADR-105, the recursive realization-constraint specification, and the
authority boundary.

No new ADR is needed for this issue. The governing separation decisions already
exist; this note identifies the repository-wide seams where the implementation
must preserve them.

## Architectural decision

The contract must keep these axes independent:

| Axis | Required distinction | Existing owner to reuse |
| --- | --- | --- |
| Scenario meaning | authored state/behavior constraint versus unconstrained backend materialization | `raes` scenario models and `raes_contracts.realization_structure` |
| Realization description | a backend-known selected value versus an independently observed/corroborated value | `ExperimentRealizedFormDisclosureModel`, `RealizationObservationDisclosure`, and validation-basis disclosures |
| Purpose | experimental data, realization description, or operational-only data | ADR-064/066 evidence-plane taxonomy |
| Demand mode | inherited/no local preference, no experimental data, selected observations, or exhaustive observations within a named supported scope | the new versioned demand normal form |
| Prohibition | collection, retention, and export restrictions, independently applicable to each lifecycle stage | the new normal form plus existing retention/export owners |
| Selector | field/stream/artifact, component, time/window, and coverage | existing targetable references, capture windows, and recursive semantic addresses |
| Verification | measurement basis and achieved claim strength | observation/evidence records and `ValidationBasisDisclosureModel` |
| Operator policy | execution, reconciliation, termination, cleanup, security, and audit needs | runtime/backend owners and control-plane policy |

The shared demand normal form belongs in `raes_contracts`. It must be a closed,
versioned, serialization-safe value contract. SDL syntax is an authoring carrier;
task/run policy is a refinement carrier; neither may define a second semantic
model. Scope evaluation must reuse the stable semantic-address, keyed-collection
identity, profile revision, ambiguity rejection, and budget machinery delivered
for recursive realization constraints. It must not reuse realization closure or
constraint posture as observation policy: the address machinery is shared, the
meaning is not.

An effective demand is configuration-bound data, not advisory metadata. The
normalized result must travel through compiler output, provisioning plans,
direct-plan validation, backend requests, collection decisions, persistence,
and export projection. Closed DTOs and request/idempotency fingerprints must
include it. Planner-created and directly submitted plans must pass the same
normalization and policy gates.

### Defaults and precedence

The implementation must make the following behavior explicit and testable:

1. An omitted local declaration means **inherit/no local preference**. It never
   means prohibit data and never means capture everything.
2. If inheritance reaches the root without an applicable experimental demand,
   the result is **no experimental data requested**. This is not a prohibition
   on independently required operational data.
3. A realization-description request defaults to the backend's truthful selected
   value and selection basis. It does not default to a scan, packet capture,
   repository provenance, or an evidence-backed claim.
4. `selected` requires collection only for its resolved selectors. `exhaustive`
   is exhaustive only inside its named, capability-declared scope; it is not an
   unbounded wildcard over hidden implementation detail.
5. Experimental retention and export default to disabled unless explicitly
   requested or supplied by an applicable named policy. A positive observation
   request does not silently imply either stage.
6. Within an authored scope hierarchy, the nearest explicit declaration for an
   axis replaces inherited preference for that axis. Other axes continue to
   inherit. An explicit prohibition accumulates and cannot be weakened by a
   descendant preference.
7. Requirements from independent authorities compose; they do not overwrite one
   another. Task/run/study changes obey the refinement rules owned by #341.
   Mandatory operator policy remains independently applicable.
8. A required action overlapping an effective prohibition is a diagnosed
   conflict, not a precedence win, waiver, or best-effort omission. Reject it
   before the prohibited side effect. Unsupported required selectors likewise
   fail before execution.
9. Normalization must preserve the winning declaration/policy origin for each
   axis so conflict, admission, and report diagnostics can explain the result
   without exposing values.

These defaults let the same exact image/filesystem constraints run with no
experimental telemetry, selected observations, or exhaustive supported
observations without rewriting the authored environment.

## Canonical incumbents and required reuse

| Concern | Canonical incumbent | Required use |
| --- | --- | --- |
| Governing semantics | `docs/research/language-extensibility/design-intent.md`, ADR-064, ADR-066, ADR-105 | Preserve the five evidence planes and partial-description semantics. |
| Stable recursive scope | `raes_contracts.realization_structure` and `specs/sdl/recursive-realization-constraints.md` | Reuse portable addresses, collection identity/profile revisions, normalization limits, and ambiguity failure. |
| SDL shape and resolution | `SDLModel`, `ScenarioContent`, `_mapping_scopes.py`, and `SemanticValidator` | Add one authoring carrier and resolve references through the existing targetable-symbol machinery. |
| Positive capture intent | `raes.evidence_requirements` and `ExperimentCaptureSpecModel` | Reuse source, channel, window, redaction, integrity, retention, and loss vocabulary; do not clone it into demand selectors. |
| Actual evidence and measures | `ExperimentEvidenceRecordModel` and `ExperimentDerivedMeasureModel` | Create these only for requested experimental capture with its actual basis. |
| Realized-form reporting | `ExperimentRealizedFormDisclosureModel` | Report a backend-selected value with backend basis without fabricating observation evidence. |
| Claim strength | `ValidationBasisDisclosureModel` | Cap claims to their achieved basis; evidence-backed claims require evidence references. |
| Capability admission | `ObservationCapabilities`, `RealizationSupportDeclaration`, and `observation_capability_contract_gaps()` | Check only effective required observation demand. Capability availability is not demand. #1112 remains the capture-capability owner. |
| Compilation and planning | `CompiledRealizationRequirement`, `CompiledRealizationAuthority`, `ResolvedRealizationAuthority`, and `ProvisioningPlanModel` | Remove implicit evidence floors from realization detail and carry the separate effective demand explicitly. |
| Direct submission | `raes_runtime.control_plane_submission` | Apply the same demand, capability, prohibition, and policy-conflict gates as the planner path. |
| Runtime operation | `RuntimeSnapshot`, runtime evaluation, reconciliation, and `trial_cleanup.py` | Keep safety/control inputs at their real owner; project them into experimental evidence only when demanded and allowed. |
| Backend collection | reference and libvirt provisioners/drivers | Separate required ownership/readiness checks from optional experimental probes; gate collection at the impurity boundary. |
| Persistence | `ControlPlaneStore`, `LocalControlPlaneStore`, snapshot codecs, and realization snapshot sanitization | Reuse atomic storage and sanitization; enforce retention before queues, temporary buffers, snapshots, or archives are written. |
| Export/API | existing control-plane serializers, auth, and experiment artifact/report contracts | Apply export and audience policy independently from collection/retention. Omission from a final response is not a lifecycle control. |
| Refinement | #341 task/run/study refinement contracts and `validate_experiment_run_against_task()` | Extend the effective demand without mutating or silently weakening the authored base. |
| Augmentation | ADR-066 and #338/#339/#340 apparatus and augmentation disclosures | Preserve environment-visible, participant-visible, and comparability disclosures even when experimental telemetry is absent. |

### Existing conflation points that must be corrected

- `raes_processor.semantics.realization_concerns.RealizationConcernDescriptor`
  currently attaches fixed verification scope and observation strength to a
  realization concern.
- `raes_processor.compiler.realization_requirements` propagates that strength
  into compiled requirements and authorities, and derives compute observation
  strength from open/exact/constrained realization posture.
- `raes_processor.semantics.realization_runtime_evaluation` and
  `realization_observation_admission` turn that derived metadata into a runtime
  corroboration/admission requirement.
- Reference, OCI, and libvirt provisioning paths consequently acquire realization
  observations even when no experimental observation was requested.
- `RuntimeSnapshot` codecs and control-plane API models persist/project those
  observations without an independent lifecycle decision.

The implementation must replace that chain's demand source with the normalized
contract. It must not remove operational ownership, readiness, reconciliation,
termination, or cleanup checks merely because their results are not study data.

The current non-empty observation/evidence shapes in experiment evaluation,
apparatus context, traceability, and archival run contracts need explicit
compatibility review. Do not satisfy them with placeholder evidence or duplicate
run models. Changes to task/run/study refinement remain under #341; #1212 should
provide the common demand carrier those owners consume.

## Cross-cutting and security gates

Every path carrying the contract must pass these existing layers:

| Layer | Guardrail |
| --- | --- |
| YAML/source parsing | Use the YAML 1.2 safe loader, mapping-key analyzer, source validation, and `SDLParserLimits` byte/depth/node/alias/import/composition budgets. Demand nesting and selector counts must also be bounded. |
| Model/config shape | Keep SDL and contract models closed (`extra="forbid"`), version discriminators explicit, collections bounded, and enums finite. Register the SDL carrier in the existing mapping-scope and semantic-validation dispatch. |
| Reference resolution | Use targetable-symbol resolution and normalized semantic addresses. Reject missing, cross-kind, ambiguous, duplicate, stale-profile, and budget-exhausted selectors; do not invent string-prefix scope matching. |
| Secrets and environment | Selectors carry identities, never credentials or secret values. Reuse `SecretReferenceId`, `BindingValue`, participant configuration, and `RuntimeEnvironmentVariable` rules. Do not add ambient environment lookup or expose secret material in normalized demand, diagnostics, snapshots, or reports. |
| URI/trust boundary | Keep demand references inert and credential-free. Reuse URI/module-registry safety if external artifacts are referenced; demand normalization itself performs no network or filesystem resolution. |
| API authorization | Reuse `_ControlPlaneApiAuth`, target binding, role checks, request-size middleware, and bounded denial audit. Reportability never grants access: operator, backend, auditor, and participant audiences remain distinct. |
| OS/process exposure | Normalization is pure and launches no process. Backend probes retain fixed argv, allowlisted executables, bounded timeouts, restricted environments, and private stdout/stderr. Never place selectors, tokens, credentials, or observed secret values in argv or logs. |
| Diagnostics/errors | Reuse `Diagnostic`/`DiagnosticModel`, portable diagnostic payloads, request-validation handling, and the redacted 500 envelope. Use stable codes for unsupported demand, required/prohibited conflict, policy conflict, ambiguity, incomplete coverage, and loss. Messages identify scope/policy references, not captured values or raw backend output. Do not add an exception hierarchy. |
| Logging/audit | Reuse control-plane lifecycle/audit events and bounded audit queues. Record decisions and policy identities, not evidence bodies, secret values, environment contents, or subprocess output. |
| Persistence/lifecycle | Enforce purpose and lifecycle before collection and before every persistence/export boundary. Reuse store codecs, atomic writes, sanitization, redaction, integrity, and loss disclosure. Operational durability does not create an experiment evidence record; experimental non-retention must also prevent hidden queues, temporary files, and snapshots. |
| Repository policy | Public contracts follow the schema publication manifest, bundle/export parity, authority-surface rules, package dependency policy, and generated-artifact checks. Do not hand-edit generated mirrors or create a package-boundary cycle. |

## Extensibility seam

The stable seam is a versioned selector algebra plus a versioned policy profile:

- selectors name semantic scope, subject/component, data kind
  (field/stream/artifact), time/window, and coverage;
- policy independently resolves purpose, demand mode, collection, retention,
  export, redaction/integrity, and requested basis;
- capability declarations map supported selector kinds and coverage bounds to
  backend capture mechanisms;
- new data kinds, backend-specific capture mechanisms, lifecycle destinations,
  or policy profiles extend registries/discriminated variants without changing
  the core precedence rules or realization-constraint tree.

The normalizer should accept explicit limits and a scope/profile resolver rather
than hard-code current component types. Backend adapters consume the normalized
contract; they do not parse SDL syntax or infer author intent.

## Test and acceptance guardrails

Tests must cover semantic normalization, planner and direct-submission parity,
backend impurity boundaries, persistence, and export—not only final report shape.
At minimum they must prove:

- exact image/filesystem constraints produce no experimental probe, buffer,
  evidence record, snapshot field, retained artifact, or export by default;
- the unchanged scenario can request selected or exhaustive supported scope;
- an abstract two-computer/three-action scenario can exhaustively request action
  traces without acquiring OS, package, or packet-network detail;
- disjoint scopes can request packets, operational-only data, no experimental
  data, and independent retention/export behavior in one scenario;
- a backend-known Linux/Kali or software selection is reportable with backend
  basis and no invented scan/provenance evidence;
- unsupported required observations and policy/prohibition conflicts fail before
  side effects with portable diagnostics;
- mandatory operational checks still run, but do not become study evidence;
- loss, redaction, integrity, participant visibility, and claim-strength rules
  still apply inside selected scopes;
- collector/probe spies, queue/store assertions, temporary-file checks, and
  exporter spies establish that forbidden or unnecessary data was never
  collected or retained.

## Non-goals and anti-patterns

Other issues retain these owners:

- integrated realization admission: #1204;
- report/capture fidelity and lifecycle projection: #1209;
- capture capability admission: #1112;
- task/run/study refinement: #341;
- augmentation conformance: #340;
- realized-source provenance: #342;
- evidence integrity: #273;
- migration and tooling: #1210; and
- the end-to-end acceptance package: #1211.

Issue #1212 supplies scoped demand semantics and carriers to those owners.

### Consolidated review boundary

The issue's [agreed corrective plan](https://github.com/OpenRAE/rae/issues/1212#issuecomment-5610102813)
keeps these owners intact. Required observations paired with backend mutation
are rejected before apply until a compensating execution owner exists; a store
transaction alone is not resource rollback. Export requests are rejected until
governed delivery exists. The implementation fixes selector-local policy and
child partitioning, canonical identities, pre-probe native selection, transient
operational validation, exact API plan authorization, and explicit description
retention. Built-in backend-selected substrate reports use bound metadata only.
It does not claim end-to-end live capture, delivery, or recovery of nonretained
report bodies. Regression verification targets those boundaries as a single
corrective set rather than expanding #1212 into the downstream work.

Avoid all of the following:

- deriving observation, corroboration, retention, or export from exactness,
  closure, backend recipes, or availability of a typed observation surface;
- treating absent/inherited demand as prohibition, or as capture everything;
- using `EvidenceRequirement`, `ObservationCapabilities`, realization authority,
  or `RealizationObservationDisclosure` as a second demand schema;
- describing backend-known selection as independently observed, evidence-backed,
  or repository-provenanced without the corresponding basis;
- satisfying no-data runs with empty/placeholder evidence records;
- filtering only the final report after data was already probed, buffered,
  logged, persisted, or exported;
- letting a more specific policy silently waive an ancestor prohibition or an
  independent mandatory operator policy;
- making every ordinary scenario enumerate per-field opt-outs or model hidden
  infrastructure merely to avoid collection;
- weakening security, ownership, cleanup, audit, augmentation, redaction,
  integrity, or loss-disclosure obligations under a no-experimental-data mode;
- adding a parallel store, serializer, validator, exception family, logging
  channel, backend workflow, or authorization path.
