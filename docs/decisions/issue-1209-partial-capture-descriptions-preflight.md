# Issue 1209 partial realization reports and capture preflight

Status: non-normative architecture guidance. Requirement: SEM-218.
Inspected baseline: `c8996122`, branch `1209-partial-capture-descriptions`.

Issue #1209 extends descriptive fidelity in existing lifecycle envelopes. It
does not redefine author authority or introduce another evidence system.
[ADR-105](adrs/adr-105-recursive-partial-description-semantics.md),
[ADR-064](adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md),
[ADR-066](adrs/adr-066-observability-evidence-plane-separation.md), and the
[governing design intent](../research/language-extensibility/design-intent.md)
already decide the architecture; no new ADR is needed. This note locks down the
remaining integration boundaries, not an implementation sequence or public syntax.

## Findings that determine the design

Paths below are relative to `implementations/python/packages/` unless stated
otherwise.

- `raes_processor/semantics/realization_concern_observations.py` validates
  observations with SDL adapters, restores protected values as blanks for shape
  checking, then dumps normalized models. This can introduce authoring defaults
  and completeness requirements into reports. Its `typed_runtime_observation_shape`
  helper also serves `planner/realization_preparation.py`,
  `prepared_node_admission.py`, and `prepared_node_semantics.py`. Globally relaxing
  that helper would weaken preparation admission, not just improve capture.
- `raes_contracts.realization_structure` already owns bounded recursive values,
  domains, references, stable collection identity, local closure, composition,
  refinement, and diagnostic-bearing relation outcomes. Its concrete-value
  evaluator treats a missing required dictionary member as absent/nonconformant.
  A partial capture cannot be passed to it as an ordinary complete dictionary.
  `RealizationKnowledgeValue` is not a complete report-coverage contract, and
  `RealizationPresence.FORBIDDEN` is an obligation, not an observation of absence.
- `raes_contracts/observation_reporting.py` already separates achieved basis from
  requested basis and protects selected descriptions. However,
  `raes_runtime/observation_results.py` embeds JSON in
  `ExperimentRealizedFormDisclosureModel.realized_value_summary` (bounded to
  16 KiB at that producer). The envelope has source/basis/evidence references,
  but this string is not a portable typed recursive report with coverage.
- `RuntimeSnapshot` requires unique concern disclosures. Its observation DTOs
  and store codecs are intentionally restrictive and mostly value-free, with
  governed substrate/OS exceptions. Conflicting observations must not be forced
  into one unique concern slot, overwritten, or smuggled through `metadata`.
- #1212 is present: normalized demand, selector capability resolution,
  description callbacks, lifecycle protection, and retention-aware operation
  results already exist. Built-in selection reporting currently describes bound
  compute substrate; it is not a general Linux/Kali/software inventory reporter.
  `observation_admission.py` rejects requested export and mandatory observation
  combined with mutation until their execution owners exist. Richer DTOs alone
  do not make either operation safe or supported.

## Representation and authority guardrails

Use the shared recursive structural vocabulary through its public contracts
owner. Extend existing report/evidence envelopes with the smallest versioned
descriptive carrier needed for coverage and provenance; do not clone every SDL
type into an observation model or create a parallel recursive relation engine.
Keep report validation distinct from authoring and prepared-resource admission.
Reuse identity/domain/security rules for supplied fields without filling missing
fields from deployment defaults, interpreting report coverage as author closure,
or assigning authority merely because a node has `origin="observation"`.

The report must preserve these independent dimensions at the scope where they
apply, including inherited metadata and explicit per-field overrides:

Metadata overrides cannot weaken applicable marking or lifecycle prohibitions.

| Dimension | Required meaning |
| --- | --- |
| Value and identity | Typed core or extension value, canonical semantic address, collection profile/revision, and exact extension identity. Unknown extension identity is not `other`. |
| Knowledge | Not observed, positively known absent, withheld/redacted, not applicable, and known value remain distinguishable. `null`, empty string, false, zero and empty collection are values, not generic absence markers. |
| Coverage | Named field/collection universe, observed subset, completeness/limitations and applicable window. Missing outside covered scope means unobserved; absence requires explicit evidence/basis covering that subject. |
| Basis and provenance | Observer/selector identity and version, observation time/window, backend-selected versus observed/independently verified basis, and applicable run/operation/configuration/profile bindings. Reuse existing reference and RFC 3339 time contracts. |
| Conflict | Preserve incompatible assertions and their individual sources/times. Reconcile only under explicit comparable scope/window rules; different-time changes are not automatically contradictions, and latest arrival does not establish truth. |
| Policy and authority | Purpose, marking, collection/retention/export policy, and original author constraints remain separate from the reported facts. |

Malformed duplicate keys or ambiguous collection identities are invalid syntax;
multiple legitimate assertions about one identity are report history/conflict.
Keyed inventory uses semantic keys, ordered sequences retain order, and partial
enumeration/pagination cannot establish collection completeness. Bounds, loss,
withholding, or a failed collector must never be rendered as an empty complete
inventory. Do not infer “no other machine files/packages exist” from closure of a
named portable inventory.

Comparison needs an explicit coverage-aware projection into the existing
recursive relation. Preserve its `conformant`, `nonconformant`, `unresolved`,
`invalid`, `unsupported`, and `limit-exceeded` distinctions. Checking a supplied
value can expose a contradiction; missing evidence cannot prove satisfaction or
violation of an unobserved fact. A conforming observed subset does not prove a
whole realization. Withheld values without an admitted comparison basis remain
unresolved. A valid schema, checksum, manifest claim, or nonempty report does not
prove delivery or independent verification. Preserve #1204 result admission and
its trusted predecessor when a backend claims an invalid successful result.

Private/offline descriptions use `raes_contracts.domain_profiles`: pinned
namespace/name/revision/content identity, bounded inert schema parsing, offline
resolution, and operation-specific semantic support. Preserve bounded unknown
extension content only under the admitted opaque/nonbinding exchange rules;
report unsupported comparison honestly. Required execution or promotion semantics
cannot use that fallback. Do not fetch profiles, load handlers from data, require
profiles for unreported internal backend choices, or promote private recipes into
core catalogs. A digest establishes identity/integrity, not trust or truth.

## Promotion and refinement boundary

Promotion is an explicit selection of captured facts into a **new authored
artifact**. Preserve the original request and capture unchanged. Record source
artifact identity/version/digest, selected semantic paths and facts, actor or
decision identity, time, target artifact identity, and transformation limitations
through existing artifact references and provenance owners. Reuse
`raes_contracts/contracts/artifact_transformations.py` identity/preservation/loss reporting and
SDL phase provenance where applicable; neither currently constitutes a complete
promotion operation. Do not use the intellectual-lineage ledger as run provenance.

Only selected, admissible facts gain authority. Unknown, withheld, conflicting,
or semantically unsupported assertions cannot silently become exact constraints;
resolving a conflict or supplying a value is a separately recorded author decision.
Never promote restored blanks, comparison aliases, default-inserted placeholders,
credentials, or unselected incidental descendants. An actual backend-selected
value can be deliberately promoted with its selection basis preserved. Selecting
one child does not close siblings or a
collection. A deliberate closure promotion requires its own named universe and
adequate coverage. Revalidate the new artifact through normal SDL/semantic gates.

Call the result a refinement only if the existing composition/refinement relation
establishes that it preserves the base constraints. A selected contradictory fact
does not authorize weakening an exact declaration. A changed author decision is a
new revision, not a conforming refinement or retroactive successful realization.
#341 retains task/run/study refinement via `validate_experiment_run_against_task`;
#342 retains realized-source provenance and conditional augmentation disclosure.

## Canonical integration owners

| Concern | Incumbents and required reuse |
| --- | --- |
| Recursive semantics | `raes_contracts.realization_structure`, `bounded_domains`, `domain_profiles`, and `specs/sdl/recursive-realization-constraints.md`; reuse stable addresses, limits, profile resolution, composition and explicit relation outcomes. Pure contracts must not import SDL, processor, backend, or runtime services. |
| Runtime field ownership | `realization_concerns.py`, `realization_runtime_concern_profiles.py`, `realization_concern_projections.py`, `realization_typed_runtime_projection.py`, and `realization_snapshot_sanitization.py`; extend their owner/adaptation seams, keeping preparation validation and public safe projections intact. |
| Author-to-execution integrity | `raes.explicitness`, `phase_contracts`, compiler realization owners, `planner/realization_authority.py`, runtime preparation/authority/result admission; reporting cannot alter admitted author constraints, envelope/configuration binding, or execution success. |
| Demand and callbacks | `observation_demand`, scope/resolution/validation helpers, `observation_reporting`, `observation_lifecycle`, runtime `observation_capabilities`, `observation_admission`, `observation_execution`, `observation_native`, and `backend_observation_calls`; one demand resolver and one lifecycle, including direct-plan admission. |
| Capture and evidence | `ObservationCaptureOffer`, `ObservationCapabilities`, `raes_processor.capture_admission.capture_admission_diagnostics`, `ExperimentCaptureSpecModel`, `ExperimentEvidenceRecordModel`, and `evidence_satisfaction.validate_experiment_run_evidence`; #1112 owns matching actual offers and evidence to required capture, including source/window/redaction/loss. Do not union unrelated offers into fictitious complete coverage. |
| Report and claim strength | `ExperimentRealizedFormDisclosureModel`, `ValidationBasisDisclosureModel`, `ExperimentRunModel` reference checks, `raes_conformance/conformance/observability.py`, and operations evidence-run validators/artifact writers. Structured detail must survive these consumers; prose summaries are presentation, not semantic authority. |
| Persistence and recovery | `observation_results.py`, `ControlPlaneStore`/`LocalControlPlaneStore`, snapshot and observation codecs, local revision/record codecs, and terminal operation commits; one durable representation with existing migration, revision/CAS, lease and idempotency behavior. Update typed DTO conversion in both directions, including `control_plane_api_models.py`. |

## Security and whole-repository gates

These are obligations on the eventual implementation, not claims established by
this documentation review. Apply them to ingestion, comparison, promotion,
storage/recovery and every report/export surface, not just the edited helper.

| Layer | Required design behavior |
| --- | --- |
| Source and payload parsing | Reuse `raes.parser`, YAML mapping validation and `SDLParserLimits` when accepting authored/promoted SDL; closed `ContractModel` and versioned schema validation for reports. Bound bytes, depth, nodes, collection members, references and diagnostic work before traversal, copying, hashing or serialization. Reject nonfinite numbers and ambiguous identities; do not coerce partial records through full SDL defaults. |
| Profile/config validation | Reuse `domain_profiles` safe schema/admission machinery and selected configuration/profile bindings. Pinned schema shape and installed semantic comparison support are different checks. Do not bypass `prepared_node_*` or `realization_preparation` completeness/capability checks to accept partial reports. |
| Secrets and environment binding | Preserve `SecretReferenceId`, `contracts/experiment_bindings.py`'s discriminated `BindingValue` and configuration-target validation, `RuntimeEnvironmentVariable`, and existing concern-specific classification/presence/commitment projections. Reports carry no resolved operator secrets, ambient environment dump or new environment lookup. Protected blanks are validator placeholders, never facts. Commitments are not encryption and must not be newly emitted for low-entropy secrets merely to enable comparison. |
| Trust, URI and artifact ingress | Reuse `uri_safety.validate_safe_absolute_uri`, artifact integrity/trust admission and exact profile resolution. References remain inert and credential-free; no automatic network retrieval, host path traversal, executable profile loading, or recursive archive import during report parsing. |
| Authorization and audiences | Reuse `_ControlPlaneApiAuth`, `ControlPlaneSecurityConfig`, target/role binding, participant visibility/marking gates, and `control_plane_plan_authorization`. Read/report access is not promotion authority, backend submission is not author consent, and reportability does not authorize participant access or export. Any exposed promotion mutation needs an explicit author-authorized operation through existing mutation admission, not automatic promotion by a report receiver. |
| Host/backend collection | Extend `ObservationRuntime` callbacks and existing reference/OCI/libvirt driver and `guest_transport` boundaries. Select permitted fields before probes or buffering; enforce deadlines and producer-side item/byte limits (post-collection tuple checks alone cannot bound acquisition). Keep command arguments fixed/validated and secrets out of argv, environment diagnostics, stdout/stderr and temporary artifacts. Pure projection/promotion starts no process. Preserve readiness, ownership, fresh binding and cleanup checks as operational inputs. |
| Diagnostics and audit | Reuse `Diagnostic`/`DiagnosticModel`, runtime portable diagnostic sanitization, bounded control-plane audit/offload, and `_operation_routes.py` redacted 422/500 handlers. Expose stable safe codes and addresses, never raw Pydantic inputs, captured values, exception text or probe output. Bound/sanitize attacker-controlled identities too; add no exception hierarchy or logging channel. |
| Retention and storage | Enforce #1212 independently before collection, queues/buffers, terminal payloads, snapshots, temporary files, history and backups. Reuse secure local store paths, private modes, symlink/reparse/link checks, transactions and snapshot revisions. Freeze/copy admitted nested payloads to prevent mutation after validation. Nonretained descriptions are immediate-result only; do not reacquire on polling/restart, or claim recoverability without authorized retention. |
| Export and failure recovery | Reuse audience-safe serializers and lifecycle admission. Keep the existing unsupported-export and required-observation-plus-mutation rejections until governed delivery/compensation is integrated with the existing owners. Database atomicity is not infrastructure rollback; retry/idempotency cannot silently recollect forbidden data or repeat a promotion. A projection pass must not erase a detected realization violation. |
| Repository publication/workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `Makefile`, `noxfile.py`, `.pre-commit-config.yaml` and canonical `tools/` checks govern changes. Published schemas under `contracts/schemas/` remain authoritative: synchronize schema publication entries/manifest, versions, generated bundle/exports, fixtures and compatibility decisions per ADR-009/061. Reuse package-boundary and generated-artifact checks; do not edit generated mirrors, release versions or changelogs by hand. Set `RAES_REQUIREMENT_UID=SEM-218`. |

## Extensibility and acceptance boundaries

The extension seam is a versioned, coverage-bearing description carried by the
existing lifecycle contracts, with explicit semantic address/profile resolver,
work limits, scope/time coverage, achieved basis and protection policy inputs.
Backend selector-family capabilities and describe/collect callbacks supply data;
they must not define independent coverage or authority semantics. A second private
profile, nested collection, or abstract action trace should use those parameters
without adding another backend-specific report schema or editing a core catalog.
Specify lossless round-trip and negotiated revision behavior before publishing a
changed contract. Older consumers must reject unsupported required meaning or
disclose permitted loss, never silently flatten it to a successful summary.

Acceptance must exercise the existing #1203/#1204 recursive and result-boundary,
#985/#1078 secret/projection, #1112 capture, #1212 lifecycle, experiment-contract,
and control-plane API/store regression families. Required evidence includes:

- Partial core/private/offline captures round-trip with absent, false/null/empty,
  withheld, unsupported and conflicting facts distinct; reordered keyed members,
  ordered sequences, stale bindings, profile mismatches and exhausted budgets
  preserve honest outcomes across serialization and restart.
- Explicit siblings remain binding under open aggregates. A partial observation
  cannot fabricate defaults or prove whole-object conformance. Selected promotion
  preserves source artifacts and records a new authored identity and its decision.
- Five Linux boxes and Kali/tool selections report actual bound choices at the
  requested supported depth without fabricated independent observations; an
  abstract model reports its own semantics without invented machine inventory.
- Exact filesystem/image detail with no experimental data and an abstract model
  with exhaustive supported action traces remain independent combinations.
  Collector, store, queue, temporary-file and exporter assertions establish that
  prohibited data was never acquired/retained, not merely omitted at response time.
- Authorization, hostile extension payloads, secret-bearing validation failures,
  source/window conflicts, failed capture, retry/recovery and direct submission
  preserve existing security, capture-satisfaction and result-admission gates.

Non-goals: a new authority algebra, generic inventory scanner, universal product
catalog, mandatory backend recipe authoring, full-machine completeness, a new
store/API/workflow stack, or implementation of all live capture/export backends.
Do not repurpose raw evidence, derived measures, runtime metadata or summary
strings as the missing typed contract. Do not weaken exact unsupported rejection,
ADR-070 universal subsumption, #1204 delivery checks, #341 refinement, #342 source
provenance, or conditional augmentation disclosures. #1212 supplies demand; #1112
supplies capture admission; #1210 retains program-wide migration. The supplied
issue requires native blockers to clear before dependent implementation; their
current GitHub status was not re-fetched for this local preflight.
