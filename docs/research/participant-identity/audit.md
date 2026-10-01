# Participant identity and actor/target audit

Issue [#215](https://github.com/OpenRAE/rae/issues/215), reviewed 2026-09-21
against `e4136a6e1f2fadc0fa174421532b91360aee0f73`.

RAE already represents participants as actors and targetable declarations. Its
main weakness is the meaning of the relations around that identity: affiliation
is described as identity, objectives call organizations actors, reference
eligibility combines several purposes, and examples use several address spaces
without consistently explaining their joins. A parser accepting a reference
does not settle any of those questions.

This audit delivers evidence and implementation ownership. It does not change
the language or establish ACT-613 as implemented. Read the
[source assessment](research.md), [reproducible evidence](evidence.md), and
[remediation ownership and dependency order](remediation-plan.md) together.
The [architecture preflight](../../decisions/issue-215-act-613-participant-identity-preflight.md)
records the repository boundaries used here.

## Governing meaning

The following constraints come from #215, rather than an imported definition
of agency. A participant is an **author-designated autonomous subject of the
scenario**. Authors choose sufficient autonomy and the identity boundary.
RAE neither sets an autonomy threshold nor decides what qualifies as an agent.
A harness, twenty tools, an LLM, and four deterministic actions can constitute
one participant. Their composition does not designate twenty-six participants.

Participant semantics apply only to participants, including agents designated
as participants. Executability, a service interface, a target address, or an
implementation manifest does not establish participation. The same participant
can act and be acted upon. Its identity is distinct from affiliation, ownership,
assignment, resources, selected implementation, episode, and execution machinery.

An abstract participant need not enumerate its components, host, service ports,
or implementation. This follows the issue's constraints and the repository's
[language-extensibility intent](../language-extensibility/design-intent.md).
Explicit refinements remain binding; selected execution and assurance claims
still need their actual prerequisites.

## Current boundaries and findings

Finding classes distinguish an observed defect, an unresolved design question,
and an intentional difference. A recommendation is an engineering judgment,
not evidence that its implementation already exists.

### F1 — identity and affiliation are conflated in guidance

**Established semantic/documentation inconsistency; owner P1.**
[Agent](../../../implementations/python/packages/raes/agents.py) requires a
nonempty `entity`, and [Entity](../../../implementations/python/packages/raes/entities.py)
describes organizations, teams, and people. ADR-020 §2 calls the relation
identity or alignment; the [Agents guide](../../explain/sdl/sections.md#agents)
says participant identity and role both come from it. But two different agent
keys referring to one entity compile into two participant identities (E1).
The binding cannot therefore mean identity equality.

The separate compiled keys are useful existing behavior. The unresolved design
is what the mandatory entity relation means, including for a composite subject
with no relevant organizational affiliation. Requiring a synthetic organization
to express that subject adds authoring detail without supplying identity.
Entity hierarchy also does not constitute a participant component hierarchy.

**Recommendation:** make the authored participant declaration the identity
boundary; distinguish optional affiliation/representation from that identity.
Retain existing entity-derived role behavior through an explicit compatibility
rule. P1 must settle role sourcing and objective assignment together before
changing fields. Do not infer membership, shared identity, delegated authority,
or identical observations merely from a shared entity.

### F2 — objective ownership can masquerade as acting

**Established semantic inconsistency; owner P1.**
[Objective](../../../implementations/python/packages/raes/objectives.py) requires
exactly one of `agent` and `entity`, describing both as who acts.
The [objective analyzer](../../../implementations/python/packages/raes/semantics/objective_semantics/_analysis.py)
emits the ACTOR reference kind for both. Only the agent path checks declared
actions. An entity-only scenario compiles `actor_type=entity` with zero
participant behaviors; an entity objective accepts an undeclared action label
that the participant objective rejects (E2). This proves differing treatment,
not unauthorized runtime execution.

The [participant relationship validator](../../../implementations/python/packages/raes/validator/_participant_relationships.py)
also accepts an objective as belonging to an endpoint through its entity.
That can be legitimate organizational ownership, but does not establish that
the endpoint was assigned the objective or performed an action.

**Recommendation:** separate objective owner/beneficiary, assignment, and
acting participant. An organization may own an objective without becoming a
participant. Acting requires a designated participant, possibly a participant
representing that organization. P1 must define action constraints on unassigned
organizational objectives and migration of legacy `entity` objectives; guessing
an actor from all participants sharing that entity is unacceptable.

### F3 — four service meanings need an explicit relation boundary

**Intentional separations, with an unresolved modeling question; owner P3.**

| Surface | Current meaning | What it does not establish |
| --- | --- | --- |
| `nodes.*.services`, `ServicePort` | Authored node-local transport binding | Participant, live listener, traffic authority, or implementation identity |
| Authored `agents.*` plus autonomous behavior | Participant intent and policy | Selected implementation or its deployment |
| ADR-041 manifest/configuration/provenance | Apparatus that chooses or relays decisions | Another participant merely because it runs |
| ADR-092 execution binding and service readback | Action-to-native-target/implementation binding, generation and lifecycle | Participant-to-resource identity or automatic promotion of targets to participants |

See [ServicePort](../../../implementations/python/packages/raes/nodes.py),
[ADR-041](../../decisions/adrs/adr-041-participant-implementation-manifest-and-provenance.md),
and [ADR-092 §§4–8](../../decisions/adrs/adr-092-autonomous-benign-participants-under-shared-time.md).
Their separation is sound. A service becomes a participant through author
designation, not a port, process, deterministic scheduler, or implementation kind.

Current generic `manages`, `depends_on`, and `uses_shared_service` relationships
cannot be assumed to mean that a resource realizes a participant. The inspected
surfaces do not specify a general participant/resource equivalence relation.
This is a design gap for the dual-role service task, not proof that a new
mandatory relation is needed for every participant.

**Recommendation:** P3 first compare reuse of existing relations, optional
typed realization/representation relations, and no relation when the resource
detail is irrelevant. If a relation is needed, define direction, cardinality,
shared resources, and consequences of acting on it. Affecting one resource
does not automatically affect all participants using it, and targeting a
participant does not grant access to its implementation internals.

### F4 — eligibility expands by exclusion and is reused across purposes

**Established policy mechanism; design weakness requiring explicit policy;
owner P2.**
[`is_targetable_section`](../../../implementations/python/packages/raes/_reference_targetability.py)
returns true for any section outside nine exclusions. In
[`_add_section_declarations`](../../../implementations/python/packages/raes/_declarations.py),
this applies only after a section enters `_REFERENCEABLE_SECTIONS`. Special and
nested declarations can instead set `targetable=True` directly. It is incorrect
to claim that every new top-level section is automatically admitted.

Adding a referenceable kind without an exclusion nevertheless extends all
consumers of the boolean without a purpose-specific decision. Current objective
targets accept participant, assertion, and proposition declarations (E3).
The last two are not proved intrinsically invalid: an objective can concern a
proposition, but that does not make it a native action target or authority scope.

| Reference use | Observed rule | Required semantic distinction |
| --- | --- | --- |
| Objective targets | Generic targetable aliases | What the objective concerns, separate from who acts |
| Action interaction targets/shared-state refs | Generic targetable aliases, plus interaction checks | A peer/resource must fit the declared interaction; a shared-state ref must denote suitable state |
| Action effect targets | Contract/result and participant-visible-reference checks | An effect's declared object and visibility basis; neither arbitrary world access nor a generic identity alias |
| Generic relationship endpoints | Generic targetability, then subtype checks where present | Endpoint kinds depend on relation meaning |
| Participant relationship endpoints | Unambiguous agents only; distinct endpoints | Organizations/resources cannot gain participant semantics |
| Observation subjects | Proposition/observation-scope targetability, with boundary-specific checks | Observable information, subject, audience, and disclosure authority differ |
| Agent authority anchors | All referenceable named declarations | Basis cited in scenario meaning; no execution permission by itself |
| Behavior authority scopes | Generic targetability | Scope of a particular declared authority |
| Agent operating scope | Separate compute/network/service/content index | Resource scope is already narrower than generic targetability |

Evidence paths: [content/objective validation](../../../implementations/python/packages/raes/validator/_content_objectives.py),
[scope validation](../../../implementations/python/packages/raes/validator/_core.py),
[observation scope](../../../implementations/python/packages/raes/observation_scope.py),
[effect validation](../../../implementations/python/packages/raes_processor/models/behavior_ref_checks.py),
and the [normative reference catalog](../../../specs/sdl/references.md).

**Recommendation:** explicit eligibility by purpose and declaration kind at the
existing declaration/reference seam. An unclassified future kind must not gain
eligibility accidentally. This concerns declared reference use, not a closed
catalog of every possible private service or a requirement to describe it.
P2 must inventory compatibility before narrowing existing accepted references.

### F5 — completion disagrees with participant endpoint validation

**Established editor defect; owner P2.**
[`REFERENCE_COMPLETION_TARGETS`](../../../implementations/python/packages/raes/_language_metadata.py)
maps all relationship source/target fields to generic targetability. For a
`type: participant` relationship, completion offers `entities.team`, an
assertion, and a proposition as well as participants (E4). The validator rejects
the entity endpoint. In an incomplete document the fallback also uses section
exclusions. This is a concrete authoring failure, not merely terminology taste.
Subtype-aware completion/navigation must consume the same reference policy as
validation, including incomplete-document handling and ambiguity.

### F6 — cross-layer names need a binding contract, not a blanket rename

**Intentional layer mapping plus unresolved compatibility/documentation gap;
owner P4.**

| Layer | Inspected identity | Interpretation |
| --- | --- | --- |
| Authored participant | Declaration key under `agents`; qualified reference `agents.one` | Role-neutral participant, despite the historical section name |
| Composition | Existing symbol maps rewrite agent/entity and other references under imports | Imported identity includes its module namespace; components are not new participants |
| Compiler | `participant.behavior.one` and retained `participant_name`, `entity_name` | Explicit projection of the authored participant, not a new participant |
| Runtime/history | `participant_address` plus episode/sequence/action coordinates | Participant lifetime identity differs from episode occurrence |
| Standalone provenance fixture | `participants.red` | String-valued contract example; not an SDL declaration or evidence of an accepted alias |
| Standalone episode fixture | `participant.alice` | Another contract example; not a compiler address demonstrated by the fixture |
| Editor | `agents.*` via declaration/completion catalogs | Author-facing namespace, not runtime address syntax |

See [composition](../../../implementations/python/packages/raes/composition/_behavior.py),
[address builders](../../../implementations/python/packages/raes_processor/compiler/addresses.py),
[participant projection](../../../implementations/python/packages/raes_processor/compiler/participant_behaviors.py),
[provenance example](../../../contracts/fixtures/participant-implementation-provenance/participant-implementation-provenance-v1/valid/reference.json),
and [episode example](../../../contracts/fixtures/control-plane/participant-episode-state-envelope-v1/valid/initialized.json).
The runtime authority/scope alias index deliberately omits semantic-only
entities/relationships and also does not map agent refs; it preserves raw refs.
P4 must assess that projection per consumer, not equate an omitted runtime
dependency with lost authored identity.

The examples establish address diversity, not a demonstrated cross-system
failure. P4 must classify each contract field as opaque external identity,
compiled address, or authored reference, define its scope and join, and reject
unbound or ambiguous joins where binding is required. Historical evidence must
not be rewritten by string substitution. Swapping a selected implementation
must not silently rename a participant, reset its history, or authorize a caller.

### F7 — historical decisions conflict with current author guidance

**Established documentation drift; owner P5; diagnosis resolved here.**
[ADR-079 §5](../../decisions/adrs/adr-079-backend-neutral-proposition-and-truth-semantics.md)
deliberately replaces `starting_conditions` with precondition
`starting_assertions`. The current model rejects the old field even when empty
(E5); the reference catalog and Agents guide use the new field. ADR-020 §6
still publishes the old name. The correct reconciliation is a dated companion
and current navigation to the later decision, not restoring an alias that
equates a probe with truth or silently editing pinned ADR history.

Adjacent checks found: ADR-020's reward-calculator context is historical under
[ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md);
its generated-schema authority wording predates the published-schema authority
in ADR-009/061; ADR-067 remains proposed; role comes through entity today;
operating scope is narrower than generic targetability. ADR-092's `green` role
restriction is a rule of its non-evaluated autonomous execution profile, not
the definition of participant autonomy. P5 owns a current-versus-historical
crosswalk covering these points and the decisions delivered by P1–P4.

## Alternatives assessed

| Alternative | Benefit | Cost or counterexample | Disposition |
| --- | --- | --- | --- |
| Keep mandatory `entity` and explain it better | Small migration | Unaffiliated/composite subjects still require a surrogate entity; ownership/acting still conflated | Insufficient alone; P1 must separate meanings |
| Identity at participant declaration, optional affiliation and explicit assignment | Matches shared-organization and composite cases | Role inheritance and legacy objectives need migration | Recommended semantic direction; exact field syntax belongs to P1 |
| Rename `agents` to `participants` immediately | More neutral spelling | Breaks authoring, import maps, fixtures and clients without resolving entity semantics | Do not select a rename as the semantic fix; P4 evaluates migration if justified |
| Add both participant and agent roots | Familiar words for different readers | Two identities/sources of truth for one concept | Reject parallel roots absent a distinct concept |
| Make every process/service/tool a participant | Easy discovery from deployment | Contradicts author designation and composite identity | Reject |
| Require a component/deployment graph per participant | Makes one realization explicit | Makes abstract authors describe irrelevant machinery | Reject mandatory graph; retain optional meaningful refinement |
| One universal targetable boolean | Simple lookup | New kinds and editor contexts inherit inappropriate eligibility | Replace accidental default with purpose-specific policy at existing seams |
| Copy UML/PROV/TOSCA or a learning API as the ontology | Familiar external vocabulary | Each has different identity, responsibility, topology or execution assumptions | Use bounded precedents, not imported authority |

## Adoptability assessment

This is a heuristic author-task walkthrough using Cognitive Dimensions, not a
user study or measured adoption result. Source relevance and limits are in
[research.md](research.md). These tasks become #221 acceptance scenarios.

| Author task | Current cost or ambiguity | Acceptance and counterexample |
| --- | --- | --- |
| Model one composite harness/tools/model subject | `Agent` is role-neutral but entity/identity language suggests a person/team mapping | One authored participant; components need no participant declarations or mandatory inventory |
| Put two participants on one team | Guide implies shared identity while compiler keeps two keys | Two identities and histories; shared team does not share authority or observations |
| Give an organization an objective | Entity is called an actor and skips agent action checks | Ownership without action; assign a participant explicitly before attributing an action |
| Model a service solely as a resource, then also as a participant | Several service meanings; no general relation contract | Explicit designation and optional meaningful relation; a port/daemon alone never starts an episode |
| Make one participant act on another | Generic targets work, typed relationship completion offers invalid choices | Same subject in actor and target positions; completion and validation agree |
| Import the same participant module twice | Author must follow several namespace forms | Distinct imported identities with stable, inspectable joins through runtime/evidence |
| Swap implementation for an existing participant | Standalone examples use different participant-address prefixes | Change apparatus selection, retain participant identity; do not rewrite historical evidence |
| Follow ADR-020's starting-state example | Old field is rejected with a migration diagnostic | Current entrypoint explains assertions/probes and links the superseding decision |

Mandatory affiliation creates premature commitment; overloaded actor/entity
language weakens role expressiveness; address joins are hidden dependencies;
bulk renaming creates viscosity; broad completion creates error-prone choices.
These are specific inspection judgments. P1–P5 acceptance reduces those costs
without requiring a new notation or unrequested evidence collection.

## Coverage and disposition

All four issue constraints are the governing meaning above and are carried into
the remediation acceptance cases. Identity/affiliation is F1–F2; services F3;
target rules F4–F5; names/references F6; definition drift F7. The literature,
lineage and alternatives are recorded; every finding has an implementation owner.
Intentional layer separations are retained. Runtime fidelity, security assurance,
and empirical usability are not inferred from the 162 passing existing tests.
The [publication record](remediation-plan.md) supplies actual issue links and
verified native dependency direction. ACT-613 delivery remains with that backlog.
