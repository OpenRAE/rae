# Issue #1354 — IFC profile variability and publication preflight

Date: 2026-09-23. Inspection baseline: `ddba5049`.
Scope: architecture guidance for the issue contract; not an accepted semantic
decision, implementation plan, new profile or fulfillment claim. The supplied
issue assigns SEM-233 and SEM-235; the supplied SEM-235 payload is sufficient
requirement context.

## Observed boundary

The issue's diagnosis was read from this repository's Git object
`077f7d04:docs/research/runtime-refactor/diagnosis.md`, section 5; it is absent
from the working tree. Its narrow finding agrees with current sources:
the general algebra is more expressive than the published security vocabulary.
It does **not** establish that independently resolved policy/provenance cannot
enforce any owner distinctions outside the label vocabulary.

Paths beginning with package names below are relative to
`implementations/python/packages/`.

| Incumbent | Actual limit that the decision must account for |
| --- | --- |
| [SEM-233](../../specs/formal/participant-semantics/adversarial-flow-control.md), exact revision-1 algebra | `P(C) × P(I)`, independent obligations and union propagation already permit finite owner-relative clauses. Finiteness is not the expressiveness defect; collapsing independently releasable obligations is. |
| [Published security artifact](../../contracts/profiles/participant-boundary-flow-policy/participant-boundary-flow-policy-v1.json) | Confidentiality has exactly `restricted`, `unknown`; integrity has exactly `endorsed`, `unknown`, `untrusted` (each with its coordinate prefix). There are no independent owner tokens. `unknown` is unresolved, not a spare owner slot; `endorsed` is not an owner identity or a global trust rank. |
| `raes_contracts/contracts/participant_flow_control_semantics.py` and `raes_contracts/participant_flow_policy_profiles.py` | Profile ID, revision and authority are fixed; the model checks the exact published digest and the loader resolves an allowlisted ID/revision/digest tuple. The schema's 128-token array limits do not authorize new tokens. There is no latest-version fallback. |
| `raes_contracts/contracts/participant_control_profiles.py`, `participant_control_results.py`, `participant_control_composition.py` | Modular validation recognizes only the security and teaching revision-1 profiles. IFC facts are a closed union of the SEM-233 relation reference and teaching tokens; domain-to-profile dispatch is specialized. A generic artifact reference does not grant new domain support. |
| API-407/API-424 `raes_backend_protocols/participant_feature_admission.py` and `participant_control_admission.py`; `ControlEffectiveSupportModel` and `_support_blockers` in `raes_contracts/contracts/participant_control_results.py` and `participant_control_composition.py` | Strength/evidence negotiation already exists. Current v1 composition nevertheless blocks every non-exact effective support record. [CA-04](../../specs/formal/participant-semantics/control-applicability-and-evaluation.md#ca-04--support-is-relative-to-the-requirement) defines requirement-relative bounded satisfaction, but publication of that amendment did not implement it. |

Profile support therefore spans the loader, literal identity/revision fields,
relation/context validators, modular selection and fact dispatch, capability
admission, runtime binding and history readers. A new artifact or relaxed digest
check alone cannot extend this chain. API-407's existing strength rank is a
declaration check, not proof of CA-04 coverage or comparable loss constraints.
Name any needed API-424/RUN-320 adoption separately from this issue's semantic
publication; do not repair their reducers incidentally under SEM-235.

A read-only probe at this baseline confirmed that the original security
artifact passes model validation, adding `confidentiality:owner-a` passes its
JSON Schema but fails the profile model, and an unknown modular profile is
rejected. Shape validity is not publication or semantic admission. The finite
SEM-233 test model uses richer synthetic universes under revision-1 names;
those witnesses are algebra evidence, not additional published profiles.

`ParticipantFlowReleaseAuthorityCoordinate` currently identifies release kind,
authority/revision and sink/destination/audience, without an owner-token scope.
A multi-owner support claim must establish where trusted resolution proves
authority over each discharged obligation. Adding tokens alone cannot establish
that authorization relation.

There is also a semantic/wire distinction to resolve explicitly: SEM-233's
algebra describes endorsement as removing named integrity obligations, while
`ParticipantFlowEndorsementModel` requires nonempty source-to-result token
replacements and `validate_release` checks that exact delta. The accepted
decision must explain how its endorsement cases map to that carrier, or name
the separate contract change needed. Do not reinterpret historical
`integrity:endorsed` as proof of every owner's endorsement.

## Decision constraints and separating cases

Keep three owners explicit in the eventual decision:

| Boundary | Information it must retain |
| --- | --- |
| Authored intent | Whose independent obligations apply, protected sources, permitted readers/destinations/sinks, relevant possible writers and endorsement requirements, release authority, memory scope, required coverage/guarantee and admissible loss. Selecting a profile may supply these through an exact governed reference; authors need not write a policy language. An author assertion alone grants no release authority. |
| Published semantic profile | Meaning of its carrier/tokens or any explicitly justified parameters; canonical encoding, order/join, source/default and sink relations, release/non-influence rules, memory scope, unknown behavior and exact support limits. Keep semantic identity distinct from schema version, selected policy, provider identity and configuration. |
| Backend/operator configuration | Installed mechanism, concrete source/principal/sink bindings, instrumentation and covered flow classes, resources, implementation/configuration pins and realization evidence. Configuration realizes published meaning; it cannot silently supply a different owner algebra or weaken authored obligations. |

The decision must resolve the following cases, with expected refusal/release
and retained provenance. These are semantic examples, not proposed syntax:

- **Independent confidentiality owners:** A permits readers Alice and Bob;
  B permits Bob and Carol. A derived value influenced by both retains both
  clauses; its audience must satisfy both, so only Bob is common. A's release
  may relax A's clause, never B's. Equal current reader sets do not make two
  owners equivalent: their release authorities can still differ. Union of
  obligations must not become union of allowed readers.
- **Independent integrity obligations:** a proposal influenced by A's
  approved publisher and B's unreviewed feed retains both possible influences.
  An action sink requiring each origin's review cannot be satisfied by A's
  endorsement of A's contribution alone. An intentionally permissive
  observation sink may admit B's known untrusted contribution without
  endorsement; a later action keeps that influence and checks its own policy.
  Endorsement never changes confidentiality or erases writer provenance.
- **Opaque combination and selective release:** summary, parse, redaction,
  trusted edit, shared state, handoff and retained memory carry every possible
  input obligation. Excluding an input needs the published non-influence
  relation and evidence. Release binds exactly the discharged obligations,
  coordinate, source/result, authority, sink/destination, revision and cut;
  naming an authority is not proof that it controls all owners' clauses.
- **Expressible but unrealizable:** distinguish a profile that cannot encode
  the required owner/release distinction from a profile that can, but whose
  installed backend misses a required source, native/control flow or final
  sink. Both prevent a claim of support; neither becomes an ordinary policy
  denial or a successful downgraded execution merely by changing its label.

For each case, establish whether the existing profile plus independently
trusted contextual policy preserves the distinction, a new governed finite
profile is needed, or the requirement remains unsupported. If an encoding
coarsens labels, demonstrate preservation through derivation, independent
release and every required sink; retaining owner names only in audit text is
insufficient. Conservative over-restriction can be an explicitly admitted
limit, but is not exact expressiveness or permission to ignore functional
requirements. Lost owner information cannot be reconstructed from `restricted`.

The natural extension seam is the **exact published profile binding and its
trusted source/sink/authority resolver**, consumed by the existing API-424
selection and backend protocol. A new governed finite publication remains a
valid outcome. If the next independent owner would require duplicating an
otherwise identical profile, evaluate a bounded, typed parameter binding at
that seam; require demonstrated need, admitted principal scope, canonical
identity, complete validation and explicit consumer support before adopting
it. Do not preselect a new parameter syntax or replace publication with dynamic
discovery. Unknown IDs, tokens, revisions and comparisons remain unsupported.
Any owner parameter must resolve to an admitted principal identity, never an
unchecked display name, HTTP role or token prefix. Its finite scope and bindings
are semantic inputs: changing them requires a new admitted binding and cut,
not an unrecorded backend configuration edit.

Preserve MPC-04's general domain contract: a closed carrier with canonical
encoding, partial order and a total, associative, commutative, idempotent,
monotone conservative join. SEM-233's powerset union is its security
specialization; do not require every domain to use sets or a least upper bound.
Failure status remains outside the carrier; unresolved source coverage is
never an empty known input or permission to produce bottom.

Reuse CA-01–04's obligation coverage and support relation. Keep required,
declared, installed, effective and observed guarantees separate. An admitted
bounded requirement can accept evidenced support within those exact bounds;
a weaker result than the admitted guarantee is an execution failure/weakening
that blocks the affected mandatory release. A downgrade authorization does
not prove satisfaction. A changed requirement/profile needs a separately
authorized binding at a new cut and disclosed claim limits, preserving every
other owner's obligation. Optional advice is not a mandatory IFC guarantee.
There is no universal loss scale that makes two unrelated limitations comparable.

The same profile decision must preserve the rest of CA-01–CA-09:

- Keep the admitted apparatus distinct from profile obligations and the
  exact-cut invocation subset. Required coverage is derived independently of
  provider responses; omission, failure and `None` never prove inapplicability.
  Shared results retain every selecting owner's conjunction.
- Use the finite typed slot/stage DAG and immutable predecessor results, not
  one call per provider or ambient shared results. Close mandatory work over
  required inputs without giving negative advisory content veto authority.
  Optional rejection discards its state/effects at that invocation boundary;
  it cannot hide failed mandatory coverage. A false trigger needs evidence.
- Scope provider state by the admitted instance, configuration, authority and
  sharing domain. A profile id alone is not a cache/state key. Coverage,
  decisions, accepted state, effect intents and consumed budgets share one
  atomic commit; unsupported shared-scope atomicity prevents admission.
- Parent deny/withhold has the same meaning in every phase. Prerequisites,
  success-dependent effects and independent consequences have separate
  targets, authorities and outcomes; their combined event graph must be acyclic.
  An independent audit may follow denial without releasing the parent.
  Transforms/injects retain fresh identity, visibility, provenance, ordinary
  downstream admission and finite causal budgets across retries and resets.

## Cross-cutting gates and canonical owners

This preflight creates no executable surface. The publication decision must
identify applicability of each layer below; later consumers cannot claim
support by modifying only a profile file or one validator.

| Layer / incumbent | Required treatment |
| --- | --- |
| Ingress and shape: `raes_contracts/json_ingress.py::parse_bounded_json_object`, `ContractModel`, flow-profile loader, `parse_participant_control_evaluation`; HTTP `RequestSizeLimitMiddleware` | Reuse bounded reads, duplicate-member/non-finite rejection, closed models and `raes_contracts/canonical.py` digests. Bound any new owner/token/graph cardinality and decoding depth explicitly; the profile loader currently bounds bytes, while the evaluation parser also passes depth 32. Resolve packaged artifacts through `raes_contracts/corpus.py::corpus_family_root`, retaining exact-ID/path allowlists; no participant-selected file/URL, second JSON parser or open label/config map. |
| Semantic and contextual validation: `participant_flow_control_validation.py`, `participant_flow_control_profile_validation.py`, `participant_control_resolution.py` in `raes_contracts/contracts` | Resolve the exact published artifact, trusted source labels, policy cuts, per-obligation release authority, safe refs and sinks independently of provider/caller claims. Retain structural, algebra and contextual checks as distinct layers. Reuse API-409/API-423 occurrence validation and ordinary action admission. Schema-only acceptance cannot replace any of them. |
| Authentication and policy: `raes_runtime/control_plane_api/_auth.py`, `control_plane_security.py`, participant crossing policy/state-cut validators | Preserve verified principal/role/target and audience binding. HTTP/operator authority, declared-world owner identity, controller authority, declassification and endorsement are different relations. Profiles grant no credentials or runtime rights. Recheck all applicable gates at the exact cut; profile selection cannot suppress another owner's constraint. |
| Capability/configuration: API-407/API-424 resolvers above; `raes_contracts/contracts/experiment_bindings.py`, participant manifests, `raes_contracts/participant_configuration.py::realize_participant_configuration` | Reuse governed feature terms, required contract sets, installed bindings, evidence and limitations. Use existing target registries, aliases, value types, defaults and complete same-type normalization where configuration is required. A configuration digest or generic modular-control feature does not prove exact domain/owner/sink coverage. No second strength ranking or per-profile admission workflow. |
| Secrets and environment: `raes_contracts/secret_references.py`, experiment binding models, `raes/runtime_environment.py`, `runtime_values.py`, `raes_runtime/runtime_fact_dispatch.py` | Carry only authorized logical secret references at their owning boundary; secret configuration targets permit neither raw literals nor portable defaults. Environment bindings retain literal/`value_from` exclusivity, generated-artifact ownership and observed-value redaction; an in-band generated value cannot claim `operator_secret`. Keep resolved credentials/private state out of profiles, examples, portable evidence and digests. Hashing a low-entropy secret is not redaction. IFC tokens are not runtime sensitivity classifications. |
| Runtime and host: `ParticipantControlProvider` in `raes_backend_protocols/protocols.py`; `raes_runtime/participant_control_binding.py`, `participant_control_orchestration.py`, `participant_flow_sink.py`, `RuntimeTarget` and backend call contracts | Providers remain operator-constructed and effect-free during resolution. Reuse exact admitted-selection/cut checks, re-entry fences and final checks before external calls, serialization, stream chunks, writes, callbacks and errors. No scenario imports, URLs, commands or executable policy. Any later backend binding must protect credentials from argv, environment dumps, filenames and stdout/stderr. Host/process/tenant isolation is backend responsibility outside the declared world; finite graph bounds and re-entry protection are not timeouts or a sandbox. |
| Errors and observability: `StrictJsonIngressError`, bounded resolver `ValueError`, `Diagnostic`/`DiagnosticModel`, `AuditEvent`, `participant_control_diagnostics.py`, conformance `sanitized_failure_message`, HTTP `_operation_routes.py` | Preserve coarse value-safe refusal reasons and safe evidence refs through existing envelopes/loggers, including redacted 422/500 paths. Never return raw Pydantic inputs or provider exceptions. Even owner names, refusal existence and provenance refs may disclose information; project them through SEM-230 audience rules and disclose timing/undeclared-channel limits. Logs are not experimental evidence, and a denied disclosure must not retain a successful durable outcome. |
| Persistence and replay: ADR-104 `ControlPlaneStore`/`AtomicControlPlaneStore`, `commit_participant_transition`, runtime snapshots and `participant_control_evaluation_history.py` | Retain one expected-head/revision commit authority for evaluation, state and intents before dispatch. Preserve source labels, bindings, releases, effect identities, receipts and consumed budgets. No profile-specific repository, side journal or mutable cache as authority. Uncertain external effects stay indeterminate; commit does not prove application or exactly-once execution. |

Do not conflate this profile family with GOV-920 interoperability profiles in
`specs/concept-authority/semantic-profiles.md`, private `DomainProfileBindingModel`
selections, validation profiles, or plan-realization profiles. Those incumbents
offer publication/binding patterns, not authorization to admit arbitrary IFC
domains through their extension points. Package ownership stays contracts/data
in `raes_contracts`, protocol in `raes_backend_protocols`, orchestration in
`raes_runtime`, and concrete instrumentation in each backend.

## Publication, migration and evidence obligations

When #1354's decision is accepted, publish it in the existing authorities.
Amend SEM-233 and SEM-235 where it changes or clarifies their obligations;
retain their separate authority and historical scope. ADR-101 remains the
security decision; ADR-108 remains the modular publication/declared-world
boundary. Reconcile CA-04 rather than publishing a competing support relation.
Under ADR-059, changes to accepted ADRs require an in-band amendment plus
matching `docs/decisions/adrs/adr-index.yaml` entry/pin, or explicit supersession.
This preflight does not amend those accepted artifacts.

The accepted publication must enumerate expressible cases, unsupported cases,
supported source/flow/sink/release coverage, finite bounds and evidence limits.
Separate semantic publication, portable reader support, installed mechanism,
effective realization and assurance; no ACTIVE status or conformance promotion
from prose or a finite model alone.

Preserve old profile bytes/digests and historical interpretations. New readers
must select exact supported interpretations; old readers reject unfamiliar
ones. Conversion records source/target pins, authority, mapping, loss and
unrecoverable distinctions. Never retag old `restricted` values as owner-aware,
rerun historical releases under new rules, or replay old effects as new work.
Explicitly cover pending work, retained memory, provider state, snapshots,
mixed-revision histories and cross-profile comparison; absent a published
authorized mapping, comparison or conversion remains unsupported. Reuse the
[applicability migration boundary](../migration/control-applicability-and-evaluation.md)
for new-cut admission, reconciliation and preservation of effect keys/budgets.

If contracts are actually required by the accepted decision, reuse ADR-009/061:
hand-governed schemas, `contracts/schema-publication-manifest.json` and its
per-contract entries/`last_change`, fixtures, exports, `schema_bundle()` parity
and the `implementations/python/pyproject.toml` packaged-corpus configuration.
Draft schema stability does not authorize silent reinterpretation. Use
`contracts/concept-authority/`, existing governed
vocabularies and `contracts/provenance/sdl-lineage-ledger-v2.json` for actual
concept/lineage changes, without speculative catalogs or a second registry.

Evidence should build on `sem233_boundary_flow_model.py`,
`test_sem_233_adversarial_boundary_flow.py`, `test_sem_233_flow_control_contracts.py`,
the SEM-235/CA finite witnesses, `test_api_424_capability_admission.py`, and the
existing #1003/#1004 sink/capability tests. Distinguish algebra witnesses from
real parser/context/admission checks and from backend realization. Required
counterexamples include selective owner release, independent endorsement,
schema-valid unsupported profiles, bounds exceeded, missing context, stale
cuts, memory/replay laundering and unexpected weakening. Denied live paths
need zero prohibited calls/disclosures and consistent durable outcomes before
they support runtime claims.

Workflow incumbents are `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/check_repo_policy.py`, `tools/check_requirement_governance.py`,
`tools/requirement_context.py`, `tools/policy/requirement_scope.py`,
`tools/policy/requirement_order.yaml`, `noxfile.py`, `.pre-commit-config.yaml`
and `.github/workflows/ci.yml`. Reuse `tools/check_adr_immutability.py`,
`tools/check_schema_publication.py`, `tools/check_generated_schemas.py`,
`tools/check_concept_authority_governance.py` and `tools/check_sdl_lineage.py`
when their artifacts change; do not create a profile-specific workflow.
Set `RAES_REQUIREMENT_UID=SEM-235` for this supplied requirement context.
Publication spanning SEM-233/235 must use the existing exact-path issue-scope
mechanism and phase ownership rules, not infer ownership from a title or bypass
the gate.

Preflight verification: the file-local repo-policy check passes; 12 selected
existing contract/admission tests pass, including trusted-context rejection,
release deltas, sanitized resolver errors and non-exact support refusal. The
read-only schema/profile probes above confirm the vocabulary boundary. These
checks establish current behavior, not #1354 fulfillment. The explicit
SEM-235 requirement-governance check fails with
`requirement-ownership-mismatch`: this note is outside the mapped
`modular-control-semantics` ownership roots. That is a publication blocker to resolve
through the existing ownership/scope workflow; this guidance-only preflight
does not change policy allowlists or claim that gate passed. Local checks
remain file-targeted; full suites belong to CI.

Non-goals: implementing #1354 here; choosing its final variability repertoire;
a general policy language, plugin host, new engine, duplicate schema/validator,
exception hierarchy, logger, state store or workflow; retroactive guarantee
upgrades; and claims of universal noninterference, covert-channel protection,
model trust or backend equivalence. New syntax requires a concrete unmet case
that existing governed publication and bindings cannot adequately express.
