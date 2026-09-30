# Issue 971: Independent Participant-Crossing Models Preflight

Date: 2026-09-27. Requirement: SEM-232; supporting authorities: SEM-230,
API-423, RUN-319. Scope: #971 only.

Resolution: the user approved one fresh operation and retries; #1395 records
the separate multiple-operation scope. The [executable rev2 rules](../../specs/formal/participant-semantics/participant-crossing-models.md)
and [construction record](../research/participant-bisimulation/model-construction.md)
resolve the design gates recorded below. ADR-100's #971 amendment records the
rev2 target and these semantics. Runtime behavior is unchanged.

The crossing-kernel boundary in [ADR-100](adrs/adr-100-participant-crossing-bisimulation.md)
stands. The original preflight found the rev1 design **not ready for mechanical
transcription into two exporters**. The historical design gates below are now
resolved by the linked rev2 authority and the ADR amendment. This note records
architecture constraints; the ADR amendment is the revision authority. It supplements the historical [#811 preflight](issue-811-participant-bisimulation-preflight.md).

## Design gates

### Transition labels and state updates must be unambiguous

The [formal authority](../../specs/formal/participant-semantics/participant-crossing-bisimulation.md)
has decision values `transform` and `declassify`, but visible decision labels
only for permit, deny, and unsupported. Abstract schema 2 says to emit the
decision selected by the policy table; schema 3 separately emits the change.
The concrete schemas instead describe permit followed by change. Pin whether
these outcomes mean permit-then-change, and give the corresponding phase and
delivery-coordinate updates. Do not invent extra decision labels, silently
emit a change twice, or let a change remain indefinitely enabled in `decided`.

Likewise, reconcile the abstract `decided` invariant with refusal becoming
terminal after its visible decision. An unlabeled implementation update cannot
be an extra abstract transition: this profile declares no abstract hidden
steps. Every schema needs guards and target coordinates sufficient to determine
the reachable graph, including when `Pending`/`Intent` and gate state reset.
Internal rank decrease must hold on actual concrete edges; naming phases in a
rank list is not evidence that every hidden transition decreases it.

### Replay and history must actually admit a complete finite carrier

The design permits fresh requests from `terminal`, has one request id, stores
`Last = Rid x K x D`, and bounds `Head` to four values. It does not specify when
that request is fresh again, how a changed input under the same identity is
distinguished from replay, or what a fresh commit does at `h3`. Resolve these
questions together. Declare whether identity reuse is excluded by the finite
environment or represented with an input/fingerprint coordinate; do not
silently assume either. Bound the logical commits by semantics, or govern a
justified finite abstraction of history. Saturation, wraparound, dropping the
next request, or stopping exploration at `h3` is not an acceptable implicit
solution. Repeated idempotent replay may produce infinite visible paths in a
finite graph; that is different from hidden divergence.

Same-cut replay repeats the declared observations without another logical
commit; later-cut rejection preserves the recorded result. Real runtime
fingerprints, history heads, and replay checks remain mapping obligations,
not facts established by using the same names in the model.

### Termination must survive the export

The profile calls states `terminal` while enabling subsequent requests and
possibly cut advance. Distinguish completion of one crossing from global LTS
termination. Ordinary `.aut` contains an initial state, counts, and labelled
edges; it has no terminal-state predicate field. Thus a sidecar flag alone
cannot make success, refusal, and deadlock distinguishable to the checker.
Explain how the governed observable behavior represents each promised
distinction, or revise the claim/profile through normal governance. Do not add
an undeclared success label or silently equate an unexpected dead end with
successful completion. See the official [AUT format](https://www.mcrl2.org/web/user_manual/tools/lts.html).

The candidate abstraction `alpha` and witness `B0` are proposals. In particular,
commit/refusal phases must map into reachable abstract states. Neither exporter
may prune or rewrite its transitions to satisfy that proposed correspondence.
The greatest-fixed-point equivalence decision belongs to #974, not #971;
graph fixed-point enumeration in #971 is a different operation.

### Extend the existing profile boundary, including its consumers

`raes_contracts.behavioral_relation_profiles.BehavioralRelationProfileModel`
currently fixes `relation_id` to opacity, has opacity-specific `parameters`,
and resolves only three opacity ids. The theorem object in
`docs/research/participant-bisimulation/implementation-program.json` is design
data, not a loadable relation profile. Use a closed DPBB parameter variant in
the existing profile family, resolver and corpus; no parallel registry,
arbitrary dictionary, opacity placeholder, or skipped join validation.

The DPBB variant must bind both model carriers, their revisions/digests and
initial states, complete domains, projection and label partition, and supported
dimensions. `behavioral_relations._validate_binding_profile()` currently joins
only the left carrier. Its shared validation boundary must also check the right
carrier when admitting binary profiles. Preserve unary opacity behavior.
Opacity processor admission and `participant_opacity_runtime.py` directly
access opacity parameter fields: they must reject an incompatible variant
before those accesses. Do not turn a new profile into an `AttributeError` or
accidentally route it through the opacity kernel.

Current catalog authority is `rev12`; the theorem design explicitly pins
`rev8`, which is retained in `contracts/concept-authority/history/` and supported
by `load_behavioral_relation_catalog_revision()`. Use exact revision loaders
for catalog and profile. Do not downgrade the current catalog, substitute
ambient latest, or rewrite historical artifacts. If semantic clarification
changes the named profile/model/projection, record the revision decision and
new digests; never silently change bytes under an established identity.

Published profile evolution uses ADR-061 compatibility assessment,
`contracts/schemas/profiles/behavioral-relation-profile-v1.json`,
`schema_bundle()`, schema invariants, valid/invalid fixtures, publication
entries and manifest `last_change`, and corpus wheel/sdist parity. A local
Pydantic change alone is insufficient. Any necessary accepted-ADR amendment
uses ADR-059; the #971 amendment and updated acceptance pin now record it.

### Export is a semantic boundary

Each model independently determines enabledness, successors and reachability.
They share only governed profile/projection data and nonsemantic plumbing
(ingress, canonical bytes, serialization). Do not share a decision/transition
oracle, generate one graph from the other, use the candidate witness as a
generator, or promote `tests/sem230_information_flow_model.py` to normative
authority. Different function names and source hashes do not establish
independent construction; review must inspect transition dependencies.

For each graph, enumerate until the reachable set and edges close, then check
initial-state membership, endpoint closure, domain membership and exact counts.
Completeness means closure under every admitted transition rule, not merely
that a supplied edge list references existing nodes. Resource limits terminate
with failure and no complete artifact. Do not use depth/sample bounds,
epsilon elimination, minimization, or a selected schedule to hide missing work.

Pin state numbering, edge order, encoding/newlines and duplicate-edge handling.
Keep a digest-bound ordinal-to-synthetic-state map for review. Validate the
`.aut` header against emitted bytes, including isolated states and the declared
initial state, and check export/readback agreement. Reject duplicate labels,
visible/hidden overlap, unknown labels, unsafe strings and unsupported format
features. Preserve the five original hidden classes in review data before
their deliberate many-to-one conversion to `internal`.

`--tau=internal` hides actions **in addition to** internal actions already in
the input. The exporter must therefore exclude undeclared native internal
encodings, not just validate that flag. Do not assume DPBB diagnostic-formula
support from another equivalence mode; the official documentation lists tested
counterexamples for other modes. Those result/counterexample obligations belong
to #973/#974. See [`ltscompare`](https://www.mcrl2.org/web/user_manual/tools/release/ltscompare.html).

## Cross-cutting layers and incumbents

Paths below are repository-relative; Python module names are under
`implementations/python/packages/`. These are required boundaries for the
intended implementation, not claims of checks delivered by this preflight.

| Layer | Canonical incumbent and required behavior |
| --- | --- |
| File and JSON ingress | `raes_contracts.json_ingress.parse_bounded_json_object()` rejects duplicate members, invalid roots and nonfinite numbers; supply nesting and byte bounds. It accepts already-read bytes, so bound regular-file reads before parsing. Use `tools.policy.common.safe_repo_path()` for repo containment and the no-follow bounded-file pattern in `raes_operations.run_artifacts.RunMaterializationArchive` where writable input paths require race protection. Reject absolute/traversing/symlink-escaping paths, special files and oversized inputs. A `SafeRef` string is not filesystem authorization. |
| Schema and semantic admission | Reuse `ContractModel(extra="forbid")`, bounded field types, shared profile loaders, catalog loaders and `validate_behavioral_claim_binding()`. Closure does not imply strict scalar types: require genuine integer ordinals/counts, not booleans or coerced strings. Keep cross-field joins in one owner and expose published invariants through the existing schema machinery. New internal bundle metadata needs one closed checker, not an unsolicited public proof DTO. |
| Participant carrier ownership | The published `participant-crossing-occurrence-v1` schema and `ParticipantCrossingOccurrenceModel` use `ParticipantRuntimeBaseEnvelopeModel`; `validate_participant_crossing_occurrence_context()` owns the typed subject, policy, evidence and predecessor joins. API-406 owns observation, history and outcome carriers; API-409 owns control occurrences; DSL-142 owns inject-delivery identity. The finite LTS represents selected crossing facts by reference and projection. It must not duplicate payloads, mint a generic message carrier, or treat a valid occurrence as proof that delivery or observation happened. |
| Source and artifact identity | Reuse `raes_contracts.canonical.canonical_json_bytes()` / `canonical_json_digest()` for semantic JSON identities. Bind source and `.aut` file identities to exact bytes separately. `serialize_run_artifact()` writes pretty sorted JSON, not RFC 8785 bytes: do not interchange those digests. Record both independent source closures, exporter, profile, projection, revisions, counts and generated artifacts. Compute identities from bytes actually consumed; a commit id alone misses dirty files. Keep digest dependencies acyclic rather than hashing a manifest into itself. |
| Authentication and policy | #971 is an offline repository model producer; it traverses no HTTP, backend or live control-plane authorization boundary. Its singleton identity and finite gates do not establish authentication. Concrete derivation must account for `participant_crossing_policy.py` identity/role/subject binding, independent semantic gates and effective API-407 support. Required unresolved gates fail closed. Later mapping uses `ControlPlaneSecurityConfig.strict_defaults()`, verified identities, request bounds and the existing boundaries, not a new auth route. |
| Runtime context and persistence | API-423 `validate_participant_crossing_occurrence_context()`, `participant_crossing_history.py`, `RuntimeSnapshot` and `ControlPlaneStore.commit_participant_transition()` already own subject/policy/predecessor joins, append-only history and expected-head atomic commit. Reuse them for typed fixtures and later mapping, not as an abstract transition oracle. Refusal may commit safe refusal evidence while preserving unrelated state. No proof fields in snapshots, audit events or backend reports, and no new store. |
| Current runtime boundary | `participant_crossing_boundary.py`, `participant_crossing_egress.py`, `participant_crossing_records.py` and `participant_crossing_commit.py` now include flow-sink, opacity and modular-control interactions. Pin the source inventory and explicitly bound which behaviors the formal kernel represents. Visible effects of newer gates cannot be hidden by calling them bookkeeping. Source drift must fail review; #972 owns evidence that a selected runtime configuration realizes the model. |
| Secrets, errors and observability | Synthetic bounded ids, safe ordinals, counts and public digests only in models, fixtures, maps, diagnostics and artifacts. No secret file access, dotenv loading, runtime payloads, policy bodies, memory, environment dumps or host paths. Hashing secrets is not redaction. Use `Diagnostic`/`DiagnosticModel` and existing `sanitized_failure_message()` at appropriate outer boundaries, with fixed messages/known schema addresses. Some incumbent profile errors interpolate rejected ids: sanitize those too. No raw exception/Pydantic input/traceback/tool output in CLI errors or retained evidence. Progress summaries are not proof evidence; add no logger or exception hierarchy. Any future HTTP wrapper retains the generic internal-error envelope. |
| Environment and host process | Model/profile contents are file inputs, never env overrides, import paths, expressions or shell arguments. Reproducibility uses fixed safe path/id arguments and explicit nonsecret operational settings. No shell, network, credentials, daemon or privilege is required for export. Keep CPU/memory/output limits distinct from semantic domains; exhaustion is failure. Never acquire or run the equivalence checker just to construct models. |
| Artifact publication | `run_artifact_path()` validates only the run-id component, not `subdir`, `filename`, symlinks or output-root containment; callers must constrain these. Reuse `atomic_write_json_artifact()` for suitable JSON after complete validation. It provides per-file replacement, not a multi-file transaction or immutable revision guarantee. Publish a bundle only once every digest/count matches, using the existing verified-tree publication pattern if transactional directory publication is needed. Avoid mixed old/new files and never expose a partial graph as complete. |
| Tool/config admission | Later mCRL2 acquisition follows `implementations/tooling/README.md`: `artifacts.lock.json` is authority; `tools/tool_versions.py` is a checked projection. Reuse `tools/tooling_policy_gate.py`, `maintained_client_acquisition.py`, `verified_tree_installation.py`, tooling schemas, admission policy, development profiles and selector bindings. `isabelle_tool.py` / `isabelle_sandbox.py` demonstrate verified acquisition and isolated offline execution, not a DPBB wrapper to copy wholesale. No floating version, PATH-discovered binary, live checksum trust, shell installer or unvalidated environment selector. |
| Workflow and governance | Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`, authority/concept/behavioral-claim gates, schema generation/publication/JSON gates, and assurance policy. Canonical execution is `noxfile.py`, `tools/nox_support/{graph,policy_lanes}.py`, `tools/verification_plan.py` and `.github/workflows/ci.yml`; the older note's `tools/verify_all.py` no longer exists. Use `RAES_REQUIREMENT_UID=SEM-232` when required. Targeted tests locally; full/integration/fuzz/completion lanes remain CI-only. |

## Verification and extensibility boundaries

Existing test incumbents include `test_issue_811_participant_bisimulation_design.py`
(design structure only), `test_behavioral_relations.py`,
`test_behavioral_relation_claims.py`, `test_json_ingress.py`,
`test_corpus_packaging.py`, `test_api_423_participant_crossing_contracts.py`,
and `test_run_319_participant_flow_policy.py`. Opacity model-check admission
offers count/domain/unsupported-result patterns, not a reusable bisimulation
algorithm. No new general graph framework or opacity evidence reuse is needed.

Model acceptance must exercise each issue negative case independently, plus
export/readback agreement, source-order determinism, no partial publication,
resource exhaustion, safe error output, and cross-profile rejection. Regeneration
must compare against retained expected bytes/digests rather than blessing both
new output and new expectations in the same check. Passing design-structure
tests or matching two traces does not establish either model's completeness.

The extensibility seam is the resolved, revisioned relation-profile variant
and independent transition authorities feeding a deterministic export boundary.
Observer, complete domains, label/projection rules, order, policy cuts and
supported dimensions belong in that profile, not environment defaults or
hardcoded assumptions in a generic serializer. A larger carrier or another
audience gets an explicit profile/model revision; exact historical replay
remains possible. Time, probability, concurrency, controller handoff and new
policy gates require reviewed semantics and capability admission, not merely
larger resource limits. Do not generalize the first finite result across them.

## Non-goals

#971 supplies independent complete finite models and reproducible export
evidence only. #972 owns runtime realization; #973 counterexamples; #974 the
equivalence decision; #975 independent reproduction; #976 publication of
reproduced assurance. Do not import those tasks into the model exporter or
fabricate placeholder positive claims to satisfy downstream evidence fields.
Formal equivalence, live realization, backend conformance, policy
noninterference and predicate opacity remain distinct. No new SDL, endpoint,
controller, backend service, policy engine, persistence layer, exception tree,
logging system, generic proof schema or workflow is justified here.
