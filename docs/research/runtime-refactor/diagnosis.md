**Milestone 67: completed conceptual diagnosis and affected scope**

Recorded: 2026-09-21. Tracking: [Runtime Refactor, issue 1348](https://github.com/OpenRAE/rae/issues/1348).
Source revision: `21c77af8` on `1348-runtime-architecture-exploration`.

**Assessment**

The evidence supports a substantial but bounded redesign of participant-control contracts and execution integration. It does not support replacing the SDL as a whole, removing participants, or discarding the general information-flow model. Local fixes alone will not resolve the problems: the authored mixed-control model binds execution occurrences too early, and the modular provider contract cannot carry the dependency computation its semantics require.

The largest affected area is the path from authored control through admitted composition to concrete execution and outcome evidence. Problems extend into shared runtime supervision, operation outcomes, and backend coordination. That makes the work larger than a participant syntax revision. It does not make every SDL declaration or every runtime component defective.

The original audit overstated some design conclusions. F01 is withdrawn. F02 does not establish a need for a new controller identity model. F11 establishes a restricted published profile and extension surface, not an invalid IFC algebra. Several other findings contradict sound existing normative clauses; they require faithful contracts and implementation rather than replacement of those clauses. The original calendar estimate and file counts are not a defensible implementation estimate.

**Scope and governing interpretation**

This completes the diagnosis of F01–F16 and their affected language, contract, and runtime boundaries. It adds F17, an applicability/selection contradiction found while tracing F07. The [original scope inventory](../participant-control-audit/scope-2026-09-21.md) accounts for all 41 milestone issues and distinguishes implementation from unfinished demonstration, evaluation, and proof work. This is a conceptual and source-based diagnosis, not a claim to have inspected every repository line or deployed backend.

All 45 repository source paths pinned by the original audit are unchanged between its revision `6bfdb7efdabbf5efe22fa023a16316830cf25380` and this source revision. Their recorded counterexamples therefore remain relevant. Additional inspection covered ordinary orchestration, participant identity, workflow and time semantics, trusted-context validation, and the applicability contradiction. The [original reproduction artifact](../participant-control-audit/reproduce-2026-09-21.py), [environment checks](environment-inject-check.md), and [new applicability check](composition-applicability-check.md) state their respective limits. No backend deployment or implementation change was performed.

The owner's clarifications govern interpretation:

- SDL expresses author intent. Mandatory declarations need semantic justification; application stereotypes do not supply it. Existing open/closed and precision semantics are not reopened by this review.
- Environments and entry points may exist without declared participants. A researcher can affect the world through an inject. Authored controller changes, participant delivery, and general external effects are different cases.
- RAE's shared runtime drives LilRAE, BigRAE, and other backends. [Hub issue 3](https://github.com/OpenRAE/hub/issues/3) assigns concrete realization and organizational responsibilities to those products; it does not require separate scenario runtimes.
- The runtime must respect valid, expressible, plannable, runnable intent and reject an unsuitable or unwilling backend. Concrete willingness, capability, and contextual refusal remain largely backend responsibilities.
- Durability does not imply resumability or permission to repeat an effect. A failed experiment may require a new trial. Physical OT remains a future direction; this diagnosis does not impose operational-OT protection or timing requirements on every scenario.

The following findings are review conclusions, not newly agreed requirements or an implementation plan.

**1. Mixed-control authoring confuses a reusable rule with its occurrences — F03**

ACT-617 explicitly describes a closed authored state graph rather than runtime history. Nevertheless, each `MixedControlTransition` requires fixed `expected_state_revision`, `resulting_state_revision`, and `effective_order`. Validation builds reachability through those fixed revision pairs. Runtime replay and admission require the current revision to equal the authored revision. [Normative model][mixed-spec], [declaration][mixed-model], [runtime fold][mixed-fold], [rejection checks][mixed-rejections].

For example, a transition taking autonomous control at revision 0 to a review state at revision 1 cannot be used again after a return to autonomous control at revision 2. The author must declare another transition for that occurrence. This can represent a finite planned sequence; it cannot express a reusable review cycle whose occurrence count is not authored in advance. Replay is episode-scoped; that scope does not provide repetition within one episode.

The validity check compares the transition's authored effective order with authored validity intervals. It establishes consistency of those declarations, not validity at an independently supplied execution-time coordinate. This is not a demonstrated wall-clock expiry exploit.

This is a genuine language-design defect for reusable mixed control. The required distinction is between a policy's permitted transition and an occurrence's actual revision, order, proposal, and evidence. Merely relaxing a stale-revision check would destroy useful concurrency protection without supplying that distinction.

The dependency chain includes ACT-617 authoring and validation, module reference rewriting, compiler child records, API-409 declarations/occurrences, RUN-310 admission and replay, and DSL-142 direction/intervention bindings that repeat these coordinates. Historical occurrence meanings must remain intact if those contracts change.

This problem is localized within the language. General workflow authoring already separates a graph from step lifecycle/outcome/attempt state. The shared time model separately defines domains, authority, progression, and runtime coordinates. Neither requires this fixed-occurrence controller representation. [Workflow state semantics][workflow], [shared time][time].

**2. Participant identity is not a prerequisite for every interaction — F01/F02 correction**

General scenario declarations and compilation accept environments, services, injects, events, scripts, and stories with no agents. Normative SDL explicitly preserves an inject without participant-delivery bindings as ordinary orchestration input. ADR-109 also separates participant identity, affiliation, objective ownership, assignment, and observed attribution. [Focused evidence](environment-inject-diagnosis.md), [current participant identity][identity].

Consequently, an out-of-world researcher causing a world effect need not be representable as an ACT-617 controller. The audit's proposed controller expansion does not follow from that example. Nor does an authentication principal or an MCP endpoint imply an authored participant.

The narrower participant-directed construct requires a declared recipient; its direction/intervention variants additionally bind a mixed-control transition. Those constraints are not a blanket restriction on general injects. There is not yet a demonstrated case, within this investigation, requiring removal of the controller-as-participant restriction from ACT-617. If a future case actually requires independent supervisory authority over a participant, its meaning must be discussed on its own terms. F03 remains valid independently of that decision.

Later visitors and conditional information sharing do not justify inventing a registration protocol. Their treatment follows the information the authored scenario requires; no such protocol has been selected.

**3. Modular composition is not executable with the relationships it declares — F07–F10, F17**

ADR-108 and SEM-235 already require explicit applicability, mandatory dependency satisfaction, fact-before-rule evaluation, independent effect admission, and advice without direct permission or veto. Those are coherent distinctions. The published API-424 contracts and RUN-320 orchestration lose them in several places. [ADR-108][adr108], [SEM-235][mpc].

| Finding | Concrete failure | Diagnostic consequence |
| --- | --- | --- |
| F07: required coverage | A required profile need only appear in a binding's profile references; the selection may contain no result slots. A trusted runtime resolver may also return `None`, bypassing modular evaluation without an explicit proof of non-applicability. | Profile presence is not obligation coverage. Required applicability, known non-applicability, and unresolved applicability lack a reliably enforced boundary. This does not mean all absent selections should be rejected. |
| F17: apparatus versus applicable selection | The request validator requires every selected binding to apply to the current crossing. The runtime also requires the request's entire selection digest to equal its fixed apparatus selection. | Two installed bindings for disjoint sinks cannot be evaluated at either sink through this configuration: retaining both fails applicability, while selecting the applicable subset fails the runtime's equality gate. |
| F09: provider dependency execution | Every provider receives the same request once, in binding order. The request carries no predecessor results computed during that evaluation. Topological processing occurs afterward in the satisfaction reducer. | A dependent rule cannot consume another provider's fresh fact through the public protocol. Reordering calls alone is insufficient. Hidden shared state or duplicate computation is not the declared composition. |
| F08: effect meaning and phase | A resolved mandatory effect request targeting the parent crossing with `deny` or `withhold` can use phase `subsequent` and still produce an eligible composition. | A request to prevent the parent is treated as satisfied before its supposedly subsequent operation. Target, phase, and contribution to the parent's decision are insufficiently constrained. |
| F10: advice and support | Every selected provider must report resolved `exact` support, including providers contributing only optional advice. Incorrect context/binding on an optional result also rejects the entire composition. | Optional participation can acquire a veto even without a mandatory dependency on it. This contradicts MPC-06's distinction between lost advice and failed mandatory work. |

Source boundaries: [selection validation][selection], [request and composition][composition], [fixed runtime binding][binding], [resolver and provider invocation][orchestration], [provider protocol][protocol], [effect requests][effect-types], [effect compatibility][effect-composition]. The F17 counterexample and exact equality condition are retained in the [applicability reproduction](composition-applicability-check.md).

The contract counterexamples do not establish an attacker bypass of all later trusted-context checks. They establish that the portable model accepts compositions that fail its own intended meaning, or cannot express applicable subsets through the runtime interface. A trusted resolver can reject bad requests, but that does not repair their portable interpretation.

F10's bounded-support subclaim needs narrower treatment. Refusing a weakened implementation under an exact requirement is correct; an authorization to downgrade is not proof of compliance with a weaker requirement. The current model lacks an explicit expected-strength relation adequate to distinguish those cases. This is a support/admission design limitation, not permission to accept all bounded results.

The repair area is the selection/applicability model, profile-to-obligation coverage, provider input/result protocol, mandatory dependency closure, support interpretation, and effect target/phase semantics. These must be coherent together. The high-level SEM-235 distinctions can survive. Patching only the seven original counterexamples would leave the missing evaluation model intact.

**4. Effect declarations and records do not establish the effects — F04/F12/F13**

These findings share a missing connection between portable intent and the owner of the actual operation. They do not justify moving common orchestration out of RAE.

F04: control-transition preparation appends accepted control history and an operation record. Cancellation outcome is derived from target kind: proposal/decision becomes `PREVENTED`, admitted action becomes `PARTIAL_LIMITATION`, and attempt becomes `TOO_LATE`. This path does not obtain a backend cancellation acknowledgment or establish a corresponding general admission interlock. A custom resolver or backend might enforce more, but the recorded outcome is stronger than the built-in evidence. [Transition preparation][mixed-fold], [outcome classification][cancel].

The in-process mutation authority serializes ordinary mutations. Therefore this is not evidence that two built-in mutation paths race freely. The defect is the unsupported outcome assertion and incomplete lifecycle connection. Backend-side progress or interruption cannot be inferred from an accepted history record.

F12: the modular inject owner invokes `deliver_participant_directed_view` with a status-view carrier. Exact participant, episode, view, policy, and cut checks are useful, but do not execute the referenced inject content or establish a fresh orchestration occurrence and recipient receipt. Returning a carrier can be a valid delivery boundary when explicitly defined; that does not make every returned status view the realization of the authored inject. The dispatcher discards the return and uses the operation record as its outcome. [Effect dispatch][effect-runtime], [directed view][directed-view].

The general external-trigger path is also unestablished at the inspected shared boundary. `Orchestrator` exposes plan start/status/results/history/stop; the reference implementation queues narrative objects. Neither defines how a fresh external input becomes the requested event occurrence and concrete world effect. This is an execution integration gap, not proof that general inject syntax is wrong or that all backend-specific triggering is impossible. [Focused source trace](environment-inject-diagnosis.md).

F13: mixed dispatch selects components and records mapping/time references, then passes the governed action request to the selected participant runtime. The inspected coordinator does not apply the edge's translation or time mapping. More directly, one `success` boolean creates separate succeeded-delivery and committed-observation events without distinct evidence for either. This exceeds allocation-aware routing. [Mixed dispatch and result recording][mixed], [action invocation][crossing].

The consequences extend beyond the immediate operation: later admission, replay, histories, experiment interpretation, and conformance may consume these records. The schemas can remain internally valid while those consumers receive unsupported premises.

The minimum affected scope is lifecycle requests and outcomes, general/participant inject realization, mixed-edge execution, backend result/readback bindings, capability admission, and their history consumers. A backend must be able to report inability, refusal, failure, or uncertainty without the runtime promoting that state to success. The detailed refusal protocol and its scenario consequences remain design decisions, not findings invented by this review.

The presence of thirteen effect alternatives and only two implemented dispatch owners (`inject`, `handoff`) is not itself a defect: supported subsets are legitimate. The defect is allowing composition to claim that a required plan is supported without establishing its effect owners at the relevant admission boundary. Optional subsequent failure must remain distinguishable from failure of a prerequisite.

**5. IFC profile expressiveness is narrower than its general model — F11**

SEM-233 defines finite sets of confidentiality and integrity obligations, componentwise union, and independent sink satisfaction. The general definition permits distinct owner-relative clauses. There is no algebraic reason to replace that representation merely because it is finite. [SEM-233][flow-semantics].

The only published security artifact fixes confidentiality tokens to `restricted` and `unknown`, and integrity tokens to `endorsed`, `unknown`, and `untrusted`. Its validator requires the exact published digest. Modular profile validation accepts that profile and the fixed teaching-influence profile. [Security artifact][security-profile], [security contract][flow-contract], [modular profile validation][profiles].

Thus the portable label vocabulary itself cannot distinguish two independent owners' confidentiality obligations. External policy/provenance resolution can retain distinctions beyond those tokens; this investigation does not prove that every such policy becomes unenforceable. It does establish a gap between the general owner-qualified semantic account and what this published profile represents directly.

Closed, revisioned publication is an explicit ADR-108 decision. Requiring a new governed publication and implementation support for another domain is not, by itself, an extensibility defect. The narrower finding is that the current release supplies two specializations and no general author-parameterized domain facility. A future decision must establish what variability belongs in authored intent, a published semantic profile, or backend configuration. No arbitrary new label map, plugin registry, or general policy language is required by this diagnosis.

This affects profile interpretation, publication, source/sink resolution, and any claims of broader supported IFC. It does not require replacing conservative propagation, independent confidentiality/integrity coordinates, explicit release authority, or immutable provenance.

**6. Projection and assurance contain bounded defects, not grounds to discard their models — F05/F06/F14/F15**

F05 is a localized integration error. The v2 decision-surface admission method cannot accept and forward the identity/crossing evidence that ordinary governed action admission requires. The older path can forward submission options. Preserve ADR-095's distinction among decision epoch, state cut, disclosure, delivery, and observation; repair the invocation-context connection. [v2 entry point][decision-v2], [ordinary admission][participant-control], [ADR-095][adr095].

F06 is conditional on deployment. Participant retrieval and full snapshot retrieval share backend/operator/auditor read roles. Those credentials must not be handed to a client with only participant-view authority. If the API is administrative and a backend enforces the participant boundary separately, the absence of a participant-only role is not itself a vulnerability. The required work is to make the trust boundary and its enforced routes unambiguous, not to invent an SDL participant role from an HTTP concern. No deployed disclosure was demonstrated. [HTTP authorization][http-auth], [snapshot route][http-routes], [ADR-104][adr104].

F14 concerns what evidence establishes. The opacity mathematics and finite analyzers remain bounded results over specified carriers and assumptions. Bisimulation implementation descendants were explicitly unfinished in the captured inventory. The runtime opacity profile openly supports uniform denial only and excludes useful allowed-action/delivered-view behavior. That is limited functionality, not a mathematical contradiction. [Runtime profile][opacity-profile], [Isabelle source][opacity-proof].

The reference backend's probe returns the same fixed transcript for its two accepted points. The harness labels this `BACKEND_NATIVE` and `hermetic-live`. It does call a live function, but does not observe the crossing, retry, delivery, or scheduling mechanisms whose behavior the transcript describes. It can witness its constant function's output; it does not establish correspondence with those execution mechanisms. A finite reference model is legitimate when identified as such. The missing correspondence is the evidence defect. [Probe][opacity-probe], [harness][opacity-harness].

F15 is another localized implementation defect with wider consequences. A final flow-sink denial changes the audit to denied, commits, and raises `PermissionError`, while leaving the operation status `SUCCEEDED`. The immediate caller receives no released payload on this path. Durable status and audit nevertheless disagree, undermining outcome consumers including effect realization. The terminal state must mean the final outcome, not an earlier gate decision. [Egress denial][egress].

**7. Shared runtime supervision needs architectural work — F16**

Provider resolution and backend calls execute synchronously while one logical mutation permit is owned. The condition mutex is released, so reads and permit bookkeeping can continue; other mutations cannot acquire the permit. Re-entry protection is useful, but no provider deadline or interruption protocol is supplied by this mechanism. A provider that never returns can prevent the same authority from accepting control mutations intended to stop activity. Finite depth, fan-out, and attempt counts do not bound call duration. [Mutation authority][mutation], [provider invocation][orchestration].

This reaches a shared runtime foundation, not just one participant construct. A repair must reconcile consistent state admission with effective supervision of slow or failed execution. Merely moving a call to another thread, releasing the permit without fencing, or placing a retry decorator around it would not establish those semantics. Concrete worker interruption or containment can belong to a backend while the shared runtime retains a coherent operation lifecycle.

Full-history reconstruction adds a separate scaling issue. Selected crossing appends revalidate accumulated history; causal state and effect draining scan accumulated evaluations. Repeating linear scans as history grows yields quadratic cumulative work on those paths. This is a source-level complexity result, not a measured latency or capacity limit. [Crossing history][history], [causal fold][causal], [effect scans][effect-runtime].

ADR-104's store ownership, atomic terminal commit, and explicit indeterminate recovery are useful foundations. Their reuse must not force long-running external execution and all supervisory mutations into one indivisible operation. The diagnosis does not select a durable-execution engine, require resumable trials, or mandate physical-OT supervision for all use cases.

**Lineage and external checks**

The [existing lineage map](../../explain/sdl/lineage.md) supplies the intended sources: OCR narrative orchestration, workflow/state-machine designs, participant observation models, shared-time/federation standards, and information-flow literature. These sources were used to check distinctions, not to require compatibility or select a replacement stack. The following primary sources were inspected during this diagnosis:

| Primary source | Relevant result | Use in this diagnosis |
| --- | --- | --- |
| [Mernik, Heering, Sloane, section 2.4](https://inkytonik.github.io/assets/papers/compsurv05.pdf) | Integrating an extension with an existing language is a design task; formal notation and language reuse are separate choices. The discussion also cautions against unnecessary generalization. | Assess participant-control extensions against existing SDL meanings rather than assuming either a new universal language or wholesale replacement is needed. |
| [W3C SCXML, sections 3.1 and 3.5](https://www.w3.org/TR/scxml/) | States carry reusable event/condition transitions; the interpreter selects and executes them as events occur. | Supports the policy/occurrence distinction in F03. It does not prescribe SCXML's syntax or transition-priority rules for RAE. |
| [ROS 2 action design](https://design.ros2.org/articles/actions.html) | A cancellation request can be rejected; accepted cancellation enters a canceling state, with completion reported separately. | Direct precedent for distinguishing F04's request, acceptance, and actual cancellation outcome. |
| [Temporal activity execution](https://docs.temporal.io/activity-execution) | Activity timeouts/retries are configurable. Cancellation notification is cooperative and an activity may ignore it. | Durable orchestration does not establish physical interruption or permission to repeat work. Adding it cannot by itself fix F04/F16. |
| [FMI 3.0.2, section 4.2.1](https://fmi-standard.org/docs/3.0.2/#step-mode) | Co-simulation advances through concrete step calls with communication-time arguments and returned outcome information. | Recorded mapping/time references alone do not establish coordination of executing components in F13. |
| [Myers and Liskov, sections 2–3](https://www.cs.cornell.edu/andru/papers/sp98/paper.html) | Decentralized labels carry owner-specific reader policies; declassification depends on authority for the affected owner. | Distinguish SEM-233's general owner-relative intent from the small published token vocabulary. No claim that RAE implements the full decentralized label model. |
| [Saltzer and Schroeder, protection principles](https://web.mit.edu/saltzer/www/publications/protection/Basic.html) | Complete mediation and least privilege concern actual access paths; the paper distinguishes desired authority from mechanisms enforcing it. | Assess F06 at the real credential/interface boundary and F07 at required-control coverage, without importing application policy into SDL. |

The RAE applications in the final column are diagnostic judgments. These comparisons support established separations; they do not prove that robotics plus durable execution is sufficient or that any particular library should be adopted.

**What remains sound, and where propagation stops**

The evidence supports retaining general environment/resource/service authoring; optional participant declarations; general narrative injects; identity/affiliation/assignment separation; the workflow graph versus execution-state distinction; shared clock/domain/progression distinctions; world truth versus participant views, local history, and archival evidence; exact state cuts; independent authority/admission/release decisions; conservative IFC propagation; and bounded formal claims. Relevant authorities include [identity][identity], [workflow][workflow], [time][time], [SEM-230][flow-foundation], and [ADR-095][adr095]. This is counterevidence to a language-wide collapse, not certification of every unrelated implementation.

There are two kinds of propagation. A changed mixed-control declaration propagates through its compiler, contracts, bindings, and replay consumers. An unsupported outcome propagates through anyone relying on it, even when their own data model is sound. Neither propagation requires changing unrelated topology syntax, general reference resolution, module semantics, or the established open/closed and precision meanings on the present evidence.

The recurring defect is that consistent descriptions of obligations and events are accepted as substitutes for executable obligations and evidenced events. The source is particularly clear where a contract names predecessor facts but the provider cannot receive them, or where a success boolean creates observation history. The diagnosis therefore concerns operational meaning across component boundaries, not agent confusion as a system property or insufficient prose volume.

**ADR and architecture-document disposition**

No accepted ADR was changed. The following is the disposition supported by this diagnosis:

| Authority | Disposition |
| --- | --- |
| ACT-617 and the participant behavior model | Redesign the policy/occurrence representation. This defect is present in the normative definition, not only Python code. Preserve separate participant and principal meanings. |
| API-409 / RUN-310 / DSL-142 bindings | Revise affected occurrence, lifecycle, validity, and evidence connections together with ACT-617. Preserve ordinary orchestration outside participant-specific bindings. |
| ADR-085 / SEM-230 | Retain the core information and operation distinctions. Establish their missing execution connections; no wholesale semantic replacement follows. |
| ADR-095 | Retain the coordinate and delivery distinctions; fix the v2 admission integration. The ADR is an existing example of correcting an overloaded concept without rebuilding SDL. |
| ADR-101 / SEM-233 | Retain the algebra and release distinctions. Reconcile published-profile expressiveness and support claims with the general account. A new profile facility requires a separate design decision. |
| ADR-108 / SEM-235 / API-424 | Retain high-level modularity and independent-effect principles. Clarify apparatus versus active applicability, obligation coverage, dependency evaluation, effective support, and effect phases; revise the public contracts and runtime coherently. Many current defects violate the ADR rather than follow from it. |
| ADR-102 / SEM-234 | Retain topology, translation, time, and evidence distinctions. Define and bind executable obligations for the supported subset; correct realization histories. |
| ADR-099 / ADR-100 | Retain bounded formal meanings. Re-establish execution-to-model correspondence and provenance before operational claims; unfinished descendants remain unfinished. |
| ADR-104 | Retain scoped storage authority, atomic outcomes, and indeterminate recovery. Clarify the shared product-runtime interpretation and revisit mutation/execution/supervision coupling. Administrative API authority must not be mistaken for participant-view authority. |

The documentation problem is consequently specific: authorities sometimes describe a distinction correctly while later contract/runtime surfaces claim to implement it without the necessary mechanism. Completion records and diagrams must be reconciled at those seams. Rewriting all ADRs would lose useful decisions and would not repair that inconsistency.

**Size and decisions left for design**

The minimum repair is a coordinated subsystem refactor with two substantial contract/design changes and shared execution integration. It is larger than a small set of patches and smaller in semantic scope than a replacement language.

| Work area | Relative scope | Why |
| --- | --- | --- |
| Reusable mixed-control policy and occurrence model | Substantial, bounded language change | Authoring, compilation, versioned occurrence contracts, dependent inject bindings, and replay must agree. |
| Modular applicability, dependency evaluation, and effects | Substantial contract/runtime redesign | The public protocol lacks necessary data flow; coverage, support, and phase semantics interact. |
| Real effect execution and supervision | Substantial shared runtime/backend integration | Cancellation, injects, mixed coordination, outcome evidence, and blocked-call supervision cross operation families. |
| IFC profile scope and extension | Bounded semantic/publication design decision | Existing algebra can survive; required variability has not been selected. |
| v2 context forwarding and final egress status | Localized corrections | Existing semantics already specify the needed distinctions. |
| HTTP boundary and assurance correspondence | Deployment/contract clarification plus targeted implementation | Scope depends on the exposed interface and the exact operational claim. |

No reliable calendar duration, percentage rewrite, or required framework follows from the source inventory. Backend realization choices and the retained contract compatibility policy will materially affect effort. The original audit's multi-month estimate is superseded by this relative scope assessment.

Design must next settle the reusable control abstraction and any retained finite-script form; the relationship between an admitted apparatus and a crossing's applicable obligations; provider dependency evaluation and supported effects; execution outcomes/refusal/supervision; and the intended variability of IFC profiles. These are decisions identified by completed diagnosis, not a request to restart basic SDL elicitation. No architecture, migration plan, retry default, participant-registration protocol, or implementation has been selected here.

[mixed-spec]: ../../../specs/formal/participant-behavior-model/README.md#act-617---mixed-control-participant-operation
[mixed-model]: ../../../implementations/python/packages/raes/participant_behavior_specification.py
[mixed-fold]: ../../../implementations/python/packages/raes_runtime/participant_control_mediation.py
[mixed-rejections]: ../../../implementations/python/packages/raes_runtime/participant_control_rejections.py
[workflow]: ../../../specs/formal/workflows/state-machine.md
[time]: ../../../specs/formal/time-model/README.md
[identity]: ../../../specs/sdl/participant-identity.md
[adr108]: ../../decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md
[mpc]: ../../../specs/formal/participant-semantics/modular-participant-control.md
[selection]: ../../../implementations/python/packages/raes_contracts/contracts/participant_control_selection.py
[composition]: ../../../implementations/python/packages/raes_contracts/contracts/participant_control_composition.py
[binding]: ../../../implementations/python/packages/raes_runtime/participant_control_binding.py
[orchestration]: ../../../implementations/python/packages/raes_runtime/participant_control_orchestration.py
[protocol]: ../../../implementations/python/packages/raes_backend_protocols/protocols.py
[effect-types]: ../../../implementations/python/packages/raes_contracts/contracts/participant_control_effects.py
[effect-composition]: ../../../implementations/python/packages/raes_contracts/contracts/participant_control_effect_composition.py
[cancel]: ../../../implementations/python/packages/raes_runtime/participant_control_occurrences.py
[effect-runtime]: ../../../implementations/python/packages/raes_runtime/participant_control_effects.py
[directed-view]: ../../../implementations/python/packages/raes_runtime/participant_retrieval.py
[mixed]: ../../../implementations/python/packages/raes_runtime/mixed_runtime_dispatch.py
[crossing]: ../../../implementations/python/packages/raes_runtime/participant_crossing_boundary.py
[flow-semantics]: ../../../specs/formal/participant-semantics/adversarial-flow-control.md
[security-profile]: ../../../contracts/profiles/participant-boundary-flow-policy/participant-boundary-flow-policy-v1.json
[flow-contract]: ../../../implementations/python/packages/raes_contracts/contracts/participant_flow_control_semantics.py
[profiles]: ../../../implementations/python/packages/raes_contracts/contracts/participant_control_profiles.py
[decision-v2]: ../../../implementations/python/packages/raes_runtime/participant_decision_surface_control_v2.py
[participant-control]: ../../../implementations/python/packages/raes_runtime/participant_control.py
[adr095]: ../../decisions/adrs/adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md
[http-auth]: ../../../implementations/python/packages/raes_runtime/control_plane_api/_auth.py
[http-routes]: ../../../implementations/python/packages/raes_runtime/control_plane_api/_operation_routes.py
[adr104]: ../../decisions/adrs/adr-104-runtime-control-plane-architecture.md
[opacity-profile]: ../../../contracts/profiles/behavioral-relation/participant-opacity-runtime-reference-v1.json
[opacity-proof]: ../../../specs/formal/participant-semantics/isabelle/Participant_Opacity.thy
[opacity-probe]: ../../../implementations/python/packages/raes_reference_backend/participant_runtime.py
[opacity-harness]: ../../../implementations/python/packages/raes_conformance/conformance/reference_participant_opacity.py
[egress]: ../../../implementations/python/packages/raes_runtime/participant_crossing_egress.py
[mutation]: ../../../implementations/python/packages/raes_runtime/control_plane_mutation.py
[history]: ../../../implementations/python/packages/raes_runtime/participant_crossing_records.py
[causal]: ../../../implementations/python/packages/raes_runtime/participant_control_causal_state.py
[flow-foundation]: ../../../specs/formal/participant-semantics/information-flow-control.md
