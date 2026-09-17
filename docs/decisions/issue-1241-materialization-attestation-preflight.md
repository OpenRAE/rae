# Issue 1241: post-materialization SDL attestation preflight

Recorded 2026-09-14. Architecture guidance for issue #1241 and requirement
SEM-225; the supplied requirement payload is authoritative and the issue narrows
it to post-materialization attestation. This is not an implementation plan or a
declaration that attestation is already supported.

## Decision and existing boundaries

The attestation describes the complete materialized scenario in SDL, including
backend additions and changes within existing elements. It is a separate,
immutable artifact linked to the original scenario and the particular execution.
It must not replace the authored input or become the comparison baseline that
proves that input was honored. Disclosure, authorization, successful delivery,
observation strength, evidence satisfaction and archive integrity are distinct
claims.

The current repository already supplies more of this boundary than the issue's
six-concern example suggests:

- `ScenarioContent` owns the shared world vocabulary; `Scenario`,
  `ExpandedScenario` and `InstantiatedScenario` are closed phase models.
- `RealizationConcernDescriptor`, `RUNTIME_CONCERN_PROFILES` and the recursive
  realization constraints own typed projections, collection identity and
  comparison. Do not freeze attestation coverage to the original six concerns.
- `backend-realization-preparation-v1` and `PreparedNodeCollectionAuthority`
  already admit certain added nodes/networks under enclosing collection
  authority. `backend_entry_transition_diagnostics` rejects unadmitted resource
  transitions independently of concern-value comparison.
- ADR-066 and `ExperimentAugmentationDisclosureModel` already classify
  environment, participant and comparability effects. These disclosures and
  `TypedRealizationDescriptionModel` are useful provenance/evidence carriers;
  neither is a complete SDL document.
- Runtime snapshots are execution/reconciliation state. Their payloads contain
  projections, commitments and backend details, not a lossless SDL serialization.
  `RealizationProvenanceEntry` is value-free conformance provenance.

These incumbents establish the architecture. A scoped design note is sufficient
for this preflight; accepted ADRs remain unchanged. Any normative phase/schema
extension must explicitly reconcile ADR-078 and the SDL document specification,
rather than treating this note as permission to bypass them.

## SDL representation and distinguishability

Use the existing closed SDL phase machinery and shared `ScenarioContent` for
the materialized document. Add only the missing phase/provenance contract needed
to distinguish a backend description from author intent. Do not define parallel
attestation-node, service, mount, environment or command schemas. World values
belong in their existing SDL fields; provenance contains identities, origins,
bindings and evidence references, not a second copy of those values.

The public SDL parser must recognize the materialized document through its
normal bounded source decoding and typed/semantic admission. This is a real
cross-phase integration requirement: today `parse_sdl()` admits authoring input,
while `InstantiatedScenario` requires derivation provenance and permits qualified
identifiers that ordinary authoring rejects. Merely dumping that model, wrapping
it in `{profile, scenario}`, or adding unknown root fields does not satisfy the
same-parser requirement. Do not remove provenance or relax authoring identifier
rules to make a round trip pass. Materialized input must not trigger imports,
ambient variable binding or a second execution while being read.

Retain the original authored artifact and admitted instantiated snapshot as
separate identities. The new document binds their profile-labelled digests,
submitted operation/plan, predecessor revision, selected backend
identity/version/configuration and materialization boundary. Its own digest is
distinct; do not redefine the existing `raes-sdl-semantic/v2` or
`raes-sdl-instantiated-snapshot/v2` profiles. Reuse `raes.canonical` and
`raes_contracts.canonical`; an artifact byte checksum and a semantic digest are
different identities, and neither authenticates the producer.

Origin must be machine-readable at the granularity of actual differences:
authored elements, backend additions, and backend selections/changes inside an
authored element. Preserve processor/operator origins where applicable instead
of attributing every non-authored fact to the backend. Reuse the existing origin
and reference vocabulary; an environment variable's value provenance or a
forwarder's `ownership_role` does not answer who added that element. A parent
node origin alone cannot disclose a new listener or an sshd wrapper on it.
Canonical reference/pointer and collection-identity helpers must resolve every
origin record, reject collisions and dangling references, and prevent a backend
from relabelling an authored member as its own addition.

Compare against admitted concrete input so import expansion, binding and
defaults do not masquerade as backend changes; retain source lineage for the
human-facing authored diff. Preserve qualified identities and significant
omissions. Keyed collections compare by their owning identity; ordered command
or match-rule sequences retain order. For infrastructure counts, instance
addresses must map to authored declarations without collapsing different
realizations of replicas into a single template. Backend names and native IDs
are not a portable identity scheme.

The runtime must retain trusted scenario context: a lossy provisioning plan or
sanitized snapshot cannot reconstruct every scenario section or authored origin.
Backend adapters supply what they actually materialized using the shared SDL
models; the runtime validates the binding and origin claims against its input.
Do not hand the backend arbitrary authoring machinery as a provisioning recipe,
reverse-engineer SDL from native inspect dictionaries, or echo planned values as
observed facts. Materialization provenance must not forge a new instantiation
history by copying old constraint-to-value records onto changed values.

Parsing and planning the description must preserve its descriptive status.
The ordinary compiler/planner path must support inspection and comparison of
the materialized SDL; a parser-only round trip does not meet that requirement.
Promotion to a new desired scenario is an explicit derivation using the existing
description-promotion/artifact-transformation boundary; ingestion never silently
grants the backend's observations author authority.

## Disclosure scope and gate behavior

The scope is any in-world change a participant could in principle observe,
including additions to an existing resource. It does not depend on whether a
participant actually observed it or whether the operator calls it apparatus.

| Change | Existing SDL owner and guardrail |
| --- | --- |
| Collector, sidecar or proxy | `nodes`, `infrastructure`, networks and their references; disclose attachment and exposure, not just a container name. |
| Services, listening sockets and host exposure | Existing runtime service families, `runtime_listeners`, `runtime_network`; service inventory, listener bind state, published ports and readiness are separate facts. |
| Forwarders, environment and capabilities | `runtime_forwarding_agent`, `runtime_environment`, `runtime_capabilities`; ownership/classification does not confer permission or prove evidence delivery. |
| Mounts and injected files/rules | `runtime_mounts`, `runtime_filesystem`, `content`, generated-artifact delivery and detection-engine families; report the final content identity and destination, including overwritten bind-source content. Keep persistent volumes and artifact-owned destinations distinct. |
| Login/session wrappers and commands | `runtime_ssh_server.RuntimeSshServer`, `SshForcedCommand`, process/service configuration and corresponding content; preserve match-rule precedence, command posture and executable content identity. A feature recipe alone is not proof of the installed state. |

Attest after all materialization hooks that change this world, including boot
rewrites and evidence setup. Bind the observation window/revision so a pre-hook
snapshot cannot claim the post-hook result. A later materialization creates a
new record; retries must not overwrite a different result under an existing
identity. Out-of-world bookkeeping is excluded, but any resulting in-world
effect remains included. A no-additions result still requires an attestation.

Preserve the original non-approximation checks for required members, exact
leaves, domains, absence and collection closure. A disclosed replacement,
deletion, extra capability or published port can still violate those checks.
The useful distinction is **disclosed and authorized** versus undisclosed or
unauthorized. Attestation is not a retroactive grant. Reuse prepared membership
and recursive collection admission before mutation; an open child concern is
not permission to create arbitrary resource addresses. Cases outside existing
authority remain informative refusals, not global gate relaxations. The
separately proposed scenario-wide open/closed policy is outside this issue.

The backend-return gate must reconcile the full attested inventory with delivered
state and admitted additions, and detect omissions and contradictions. Checking
only addresses already present in the plan cannot discover undisclosed extras.
Coverage and observation basis reuse the existing description/observation
vocabulary: backend-selected or synthetic facts are not independent readback.
Unknown, withheld, absent and unobserved remain distinct. A backend unable to
describe a required in-world effect must not issue a complete success claim;
use the existing bounded failure/evidence paths. This is a backend attestation,
not a cryptographic proof that no malicious process concealed state.

## Cross-cutting admission and delivery

Python module names below are relative to `implementations/python/packages/`.
These boundaries apply to direct runtime calls as well as HTTP calls.

| Layer / canonical incumbents | Required behavior |
| --- | --- |
| SDL source and local shapes: `raes.parser`, `_yaml_loader`, `_source_profile.SDLParserLimits`, `_base.SDLModel`, owning runtime models | Apply strict UTF-8/single-document, duplicate-key, alias/depth/work/scalar bounds, finite JSON and closed-field checks. Reuse enum/profile/identifier and path validators. Bound backend object input before recursive copying/serialization too; HTTP limits alone do not protect in-process calls. |
| Semantic and phase admission: `SemanticValidator`, `instantiate`, `_scenario_instantiation`, `phase_contracts`, canonical snapshot admission | Resolve node/network/service/listener/content references, stateful destination exclusivity, qualified identities, concrete values and provenance consistency. Preserve shared semantic checks for a materialized document; no `skip_semantic_validation` or unsafe model construction at acceptance. SDL shape validity alone is insufficient. |
| Plan, configuration and authority: `realization_concerns`, `realization_runtime_concern_profiles`, recursive relations, `backend_preparation`, `backend_profiles`, `backend_realization_authority`, `control_plane_plan_authorization` | Bind exact plan, backend manifest/configuration, operation and predecessor; retain profile support and collection admission. Reuse manifest capability negotiation for attestation support/version, not per-backend flags or a silent optional-field fallback. Preparation describes a selection, never post-materialization success. |
| Secrets and binding shapes: `runtime_values.enforce_observed_value_redaction`, `runtime_environment.RuntimeEnvironmentVariable`, `SshForcedCommand`, `backend_account_credentials`, realization projections/sanitizers | Preserve `value`/`value_from` exclusivity and classification restrictions, generated-artifact ownership and secret resolution boundaries. Redacted/operator-secret values stay omitted; a redacted forced command has empty command text and consistent kind/flag. Apply these to backend additions as well as planned paths, including origin notes, URIs and inline content. Do not reuse snapshot commitments as SDL values or hash low-entropy secrets as a disclosure workaround. |
| Observation/retention: `observation_demand`, its resolution/validation helpers, `observation_execution`, `observation_results` | Express required safe description and archival obligations through the existing scoped lifecycle policy. Required-versus-prohibited collection/retention conflicts fail admission before mutation; no silent opt-out and no bypass of a prohibition. Mandatory post-apply work must respect the existing compensation/atomicity admission. Independent raw capture remains separately governed. Export still needs a governed delivery owner. |
| Backend return: `_call_backend_apply`, `_finalize_backend_apply`, `backend_call_contracts`, `backend_snapshot_contracts`, `backend_entry_transitions`, `backend_effect_transitions` | Admit the typed attestation and bindings before accepting success, persistence or API conversion; revalidate the sanitized result. Preserve domain ownership, changed-address accounting, transition checks, defensive isolation and value-free failure handling. Failed/partial cleanup inventory is not a completed attestation. Returning the baseline snapshot is not physical rollback of backend side effects. |
| Authentication and information flow: `ControlPlaneSecurityConfig`, `control_plane_api._auth`, `RequestSizeLimitMiddleware`, participant audience/control bindings | Retain verified identity/bearer authentication, target-bound roles, planner authorization and bounded input. Default HTTP input is 1 MB while SDL source permits 8 MiB: payload transport must respect both configured budgets or use the existing bounded artifact-reader pattern. In-world observability does not authorize publishing the full SDL to every participant; preserve audience, marking and redaction rules. No new public endpoint or auth configuration is needed merely to carry the artifact. |
| Diagnostics and audit: `Diagnostic`, SDL error types, `backend_result_diagnostics`, existing control-plane audit and HTTP handlers | Report bounded identities, paths and reason codes. Do not render source snippets, Pydantic input values, raw backend exceptions, command output, tokens or artifact bodies in logs/errors. Reuse the redacted backend/HTTP failure envelopes and existing audit correlation; no exception hierarchy or logging stack for attestation. |
| Host execution and storage: reference `drivers.oci` injected runner, libvirt `guest_transport`, `raes_operations.run_artifacts` | Use fixed argv/no shell, bounded readback and existing secret-input channels; never put tokens or secret-bearing commands in argv. Record guest paths where SDL requires them, not host cache paths or credentials. Archive destinations are runtime-owned: validate run IDs, keep subdirectory/filename parameters trusted, enforce containment including symlinks, use protected temporary files, and never dereference a backend-supplied URI automatically. |

Do not drop required facts merely to sanitize the artifact. Use the owning SDL
redaction/presence representation and an explicit limitation; if it cannot
represent the safe fact, that is a contract gap to settle before claiming
support. A safely redacted SDL document is not a promise of self-contained replay
without separately authorized secret/artifact inputs.

## Persistence, evidence and extensibility

Return a first-class attestation carrier/reference through the existing apply
and runtime lifecycle (`raes_backend_protocols`, `ApplyResult` and the runtime
result adapters). The obligation belongs to completed materialization, not every
evaluation or participant call that also happens to return `ApplyResult`.
Producer scope must be explicit when a target uses multiple backends: preserve
their provenance and reject overlapping contradictory claims rather than using
last-writer-wins assembly or making one backend attest another's work.
Keep `ExperimentRunModel.scenario_snapshot_ref` bound to the admitted input. A
materialization attestation needs a separate typed artifact/reference identity;
do not relabel it `scenario-snapshot` or hide it under `other`. If that identity
extends `ExperimentReferenceModel.ref_kind`, `ExperimentArtifactRefModel.role`
or the associated-artifact parent set, update their narrowed subclasses, schema
conditionals, matchers and semantic validators together. In particular, today's
associated-artifact scenario-snapshot matcher deliberately excludes
`InstantiatedScenario`, so it cannot admit a new materialized phase unchanged.
Archive the actual admitted SDL bytes, with checksum,
size, sensitivity and execution binding. Reuse `ExperimentArtifactRefModel`,
`ExperimentRunModel.evidence_artifacts`, augmentation disclosures and their
evidence traceability validators. `ExperimentRealizedFormDisclosureModel` can
reference the result; its summary or `typed_description` must not substitute for
the SDL file. Reuse the associated-artifact manifest and bounded byte validators
when attaching companion content. A URI or successful JSON serialization is not
proof that the referenced bytes were archived.

Existing augmentation rules still require evidence for non-apparatus claims,
an environment effect and portable carrier for environment-visible additions,
markings for participant-visible additions, and observer/comparability effects
when asserted. Creating a collector or its attestation does not itself satisfy
the scenario's `evidence_requirements`.

Persist accepted identity and recovery information through the existing
control-plane terminal commit, operation records and snapshot revision/CAS
machinery. Snapshot carriage, if used, must round-trip through
`_snapshot_payload`, `_snapshot_from_payload`, `_snapshot_model` and
`RuntimeSnapshotEnvelopeModel`; the durable codec checks exhaustive fields.
Do not hide SDL in `details`, snapshot metadata, audit blobs or a new side store.
`run_artifact_path` and `atomic_write_json_artifact` are the archive incumbents;
extend their shared writing boundary for SDL bytes only as needed. Their JSON
pretty printer is not RFC 8785 canonicalization. Atomic rename alone does not
make a file and a database commit one transaction: publish immutable bytes and
their verified reference with recoverable failure handling. Required archival
failure cannot be reported as a reproducibly completed run. Preserve cleanup
state and avoid repeating materialization on recovery.

Extensibility belongs at existing seams: concern descriptors and owning SDL
models supply field/collection semantics; a versioned, bounded coverage profile
supplies the attested universe; backend manifest/configuration and execution
bindings distinguish producers and revisions; the shared artifact writer and
injected bounded reader own transport. The next runtime family, backend or
materialization revision must not require another six-kind table, bespoke diff
engine, world schema or archive workflow. The coverage profile cannot silently
exclude any effect required by #1241.

## Verification and implementation boundaries

Implementation evidence should reuse the SDL phase/serialized differential
tests, runtime-contract and preparation tests, realization-honesty conformance,
`test_sem_225_augmentation_semantics.py`, scoped-observation runtime boundary
tests, and crash-consistency/CAS tests. Discriminating cases include same-parser
round trips with imports/replicas and redaction; disclosed permitted additions;
undisclosed extras; disclosed violations of exact or closed authority; a wrapper
or content rewrite on an authored node; stale bindings; no-additions success;
invalid/oversized input; secret-free errors; and archive/restart failure. A fake
backend validates contract behavior, not independent production readback.

Schema changes follow ADR-009/061: the hand-governed `contracts/schemas/` bundle
is authoritative. Keep `schema_bundle()` parity, publication entries/ledger
under the current manifest index, valid/invalid fixtures, SDL section/catalog
parity, semantic revision/profile rules, concept bindings/lineage and packaged
corpus exports aligned wherever touched. Old consumers must explicitly reject
unsupported attestation contracts rather than silently discard disclosure.
Preserve package dependency direction: shared carriers stay in `raes_contracts`,
SDL admission in `raes`, planning in `raes_processor`, and execution/storage in
their runtime/operations owners. Do not make a contract validator import a
backend, call the runtime, or depend on a checkout-relative corpus path.
Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `.pre-commit-config.yaml`,
`noxfile.py`, `tools/check_repo_policy.py`, generated-schema/publication checks
and `tools/verify_all.py`. The branch name lacks a requirement UID, so run the
policy and verification commands with `RAES_REQUIREMENT_UID=SEM-225`; do not use
`--skip-requirement`. Release-owned versions/changelogs and accepted ADR pins
remain governed.

Non-goals: implementing the issue in this preflight; moving TechVault/APTL capture
topology or editing other repositories; introducing the separate global scope
policy; collecting every host/guest fact continuously; new deployment recipes,
auth endpoints, exception/logging stacks, stores or cryptographic attestation;
automatic promotion/redeployment of observed SDL; changing participant visibility
or evidence-satisfaction semantics; and claiming that valid SDL, a digest or
backend self-report proves complete independent observation or exact replay.
