# ADR-108: Modular Participant Control and Governed Effects

## Status

accepted

Acceptance is recorded by merging the delivery PR for
[#1068](https://github.com/OpenRAE/rae/issues/1068). An unmerged copy is proposed
delivery state. This decision establishes architecture and requirement scope;
it does not declare the implementation children complete.

## Date

2026-09-06

## Classification

Classification: FM3

Required artifacts: [current-state and primary-source assessment](../../research/modular-participant-control/assessment.md),
[revisioned composition contract](../../research/modular-participant-control/composition.md),
[worked cases and counterexamples](../../research/modular-participant-control/cases.md),
[bounded abstract-model evidence](../../research/modular-participant-control/verification.md),
[requirement disposition](../../research/modular-participant-control/requirements.md),
and [dependency-ordered delivery graph](../../research/modular-participant-control/delivery.md).

Waivers: this design does not publish schemas, execute a provider, instrument a
backend, or establish production conformance or an experimental result. The
finite reference model is design falsification evidence only. Formal semantic
publication, closed contracts, runtime enforcement, and independent realization
evidence belong to the named children, in that order.

## Context

Participant control is an experimental and organizational concern. Its uses
include tracking treatment influence, preserving a blind, teaching, resource
allocation, supervisory intervention, adversarial evaluation, and safety.
Security is one application of the participant/world boundary.

ADR-085/095 and SEM-230 already relate participant projections, policy,
memory, state cuts, delivery, and observations. ADR-101 and SEM-233 add an
explicit security profile with independent confidentiality and integrity,
conservative propagation, governed releases, and final-sink enforcement.
Issues #1001–#1004 delivered bounded semantic, contract, runtime-sink, and
capability surfaces. Their existence does not supply an installed IFC engine.
The current runtime's optional `resolve_flow_sink_decision` attribute is not a
public modular provider protocol.

Dynamic information-flow control (IFC) has established label-domain,
propagation, resolution, and enforcement precedents. It need not end in a
block: resolved influence can inform an admitted intervention rule. Capability
restriction, shields, monitors, approval, trusted editing, resource controls,
handoff, interruption, and shutdown also contribute to participant control.
They do not all have information-flow labels.

## Decision

### 1. Establish the declared-world boundary

RAES owns the declared participants, observations, actions, controllers,
interventions, crossings, profiles, decisions, effects, evidence, and claims.
A live source or consequential external sink belongs to that world only when
the apparatus admits its identity, authority, crossing, observation coverage,
and limitations. A declared cyber attack may change an in-world machine.

Protection of the actual provider, host, model service, credentials, process,
container, tenant, or network outside that world belongs to the backend or
participant provider. Interference there invalidates or fails realization;
backend diagnostics and apparatus validity evidence may record that fact, but
RAES must not invent a participant attack occurrence to explain it away.
Being outside RAES semantics is not permission to omit backend protection.

### 2. Adopt modular composition revision 1

The [composition contract](../../research/modular-participant-control/composition.md)
is the architectural contract `participant-control-composition/rev1`.
Its PC-01–PC-15 clauses bind implementation children. It is not a new wire
format or an executable policy language.

One admitted apparatus selects an exact finite composition of profiles and
mechanism instances. Profile instances declare applicability, mandatory or
advisory roles, dependencies, authorized effect rules, failure behavior, and
resource bounds. Evaluation uses one exact state cut. Facts are resolved before
dependent rules; independent inputs are combined without arrival-order
precedence. Cyclic dependencies and ambiguous effect orders are inadmissible.

Mandatory constraints conjoin with incumbent authority, capability, crossing,
and admission gates. Advisory output cannot supply permission or discharge a
mandatory constraint. A deterministic admitted rule may consume that advice
and request an independently authorized effect. Missing mandatory results,
stale cuts, unsupported semantics, unaccepted weakening, and conflicting effects
prevent the affected release or action. Every reason remains reviewable.

### 3. Extend IFC through revisioned domains, preserve SEM-233

SEM-235 owns the new mechanism-composition and extensible IFC requirements.
SEM-230 remains the participant-relative flow foundation. A domain declares
its carrier, order, conservative join, defaults, source resolution,
propagation, permitted relabeling, memory scope, and sink rules. A new domain
requires governed semantic publication and closed contract support; a runtime
cannot interpret an arbitrary `labels` map or import a domain from scenario
code. Distinct domains compose as independently identified coordinates unless
a published cross-domain relation explicitly permits comparison.

`sem-233/rev1` and its published `participant-boundary-flow-policy-v1@rev1`
artifact retain their security meanings, two independent coordinates, default
failure rules, release authorities, and immutable history. Their data is never
retagged as a new general-purpose label domain. New non-security profiles and
observe-influence policies use new identities. An admitted known untrusted
in-world source may satisfy an observation sink's policy without endorsement;
an unresolved source still cannot pass as known merely because a run is
permissive. Downstream proposals retain the influence and face their own sinks.

### 4. Keep facts separate from governed effects

A label, monitor result, or provider response executes nothing by itself.
An admitted rule can request the closed effects: permit, deny, withhold,
transform, mask, inject, delay, route, audit, handoff, request review, interrupt,
and shutdown. PC-09 maps each to its existing owner and identifies the contract
work still required. These are typed alternatives with bounded references,
not callbacks or an open effects map.

Transformations and trusted edits create fresh proposals or representations;
injects create fresh DSL-111 occurrences with DSL-142 participant bindings where
applicable. Handoff, release, approval, lifecycle change, admission, execution,
delivery, and observation remain different events. Each resulting operation
re-enters ordinary gates, preserving provenance, visibility, authority, exact
cut, evidence, and downstream labels.

### 5. Assign implementation responsibility explicitly

| Owner | Responsibility |
| --- | --- |
| RAES semantics | Revisioned profiles, IFC domains, composition and effect meaning; participant/world relations; claim limits. |
| RAES contracts and conformance | Closed data and public provider protocol; schema and version discipline; externally runnable bounded probes. |
| RAES runtime | Mechanism-neutral invocation, exact-cut composition, effect admission and durable commit before dispatch, histories and recovery. |
| Each backend | Independent concrete mechanism selection, provider implementation and installation, instrumentation, lifecycle, external integrity, supported effects and readback. |
| Apparatus author/operator | Select available exact profiles and backend realizations within authority, bind configurations and limitations, admit the run. |
| RAES experiment/evidence surfaces | Pin apparatus and results; distinguish declaration, realization, conformance, evaluation, and broader claims. |
| Hub and backend documentation | Discoverability, release compatibility and user guidance; no runtime discovery service or copied semantic authority. |

The public protocol belongs to `raes_backend_protocols`, its data to
`raes_contracts`, and orchestration to `raes_runtime`. The runtime receives
operator/backend-bound provider instances. It does not load code named by
participant or scenario content. Concrete engines may use external libraries;
RAES does not require a production mechanism package in its own repository.

Two backends can conform to different declared subsets or realize the same
semantic profile with different implementations. Neither fact proves profile
parity, quality parity, semantic divergence, or behavioral equivalence.

### 6. Commit effects with bounded causal execution

Resolve → compose → admit → commit → dispatch → record realization uses the
existing crossing/control and operation-store authorities, including ADR-104.
History conflicts or commit failures prevent dispatch. Retries preserve one
logical effect identity; changed inputs under that identity conflict.
External-effect uncertainty after a crash remains indeterminate until backend
reconciliation supports a conclusion. A local commit is not proof of an
external effect or exactly-once delivery.

Each root occurrence has finite, durably consumed trigger and retry budgets.
Required predecessor effects withhold the parent until satisfied and freshly
revalidated. Subsequent effects are separate admitted operations whose failure
does not erase an already applied parent. Re-entry cannot reset budgets through
handoff, episode reset, retry, or a new derived identity. No provider can apply
hidden effects while resolving a result.

### 7. Create authority before releasing design dependencies

Create DRAFT SEM-235, API-424, RUN-320, and ASR-538. Amend DRAFT ASR-536 to
consume exact modular realization evidence while retaining its adversarial
scope. Existing ACTIVE authorities and their positive evidence remain intact.
Requirement existence authorizes bounded future work; DRAFT is not fulfillment.

Merge this design and requirement set before #1070, #1072, #1069, or #1071
begins its dependent implementation. Backend design may then select mechanisms
independently; its implementation waits for the released RAES prerequisites
and its own accepted requirement-backed design. The
[delivery graph](../../research/modular-participant-control/delivery.md) includes
conditional evaluation dependencies: one evidenced backend is enough for one
backend's result; each additional backend claim needs its own evidence.

### 8. Explicitly amend ADR-101's scope

ADR-101's non-goal of a general-purpose taint engine or policy language is
preserved for the RAES runtime and portable executable surface. This ADR adds
governed extensible IFC domains and composition semantics; backends may choose
general-purpose IFC implementations behind the closed protocol. It does not
add a universal interpreter, scenario-selected code, or a plugin host.

ADR-101 remains the security-profile decision. Its historical DRAFT statements
describe the #812 design cut; SEM-233's later ACTIVE requirement record and
#1001–#1004 evidence are not rewritten. The explicit amendment in ADR-101 links
this narrower scope clarification and the declared-world boundary. ADR-085's
one semantic boundary remains one set of governed relations across many
mechanisms and carriers, not one required implementation.

## Alternatives Considered

- Generalizing SEM-233 in place would change published security meanings and
  reinterpret history. A separate SEM-235 owner preserves them.
- Requiring one IFC engine or all mechanisms to emit labels would confuse
  portable semantics with mechanism choice and exclude valid control methods.
- First-result, last-result, or plugin-order precedence makes behavior depend
  on deployment details. Explicit dependency and conflict rules are reviewable.
- Letting a monitor or label execute a callback bypasses ordinary authority,
  provenance, admission, and final-sink checks.
- A runtime plugin marketplace duplicates backend installation and Hub
  discovery responsibilities without improving portable semantics.
- Treating every influenced value as a denial prevents intentional exposure
  experiments; treating missing state as permissive silently weakens control.

## Consequences

Profiles can track and act on non-security influence, combine control methods,
and intentionally deliver adversarial content while retaining strict final-sink
policies where selected. Concrete providers remain replaceable only within
their evidenced semantic and configuration boundaries.

The cost is explicit admission, provider/effect contracts, bounded scheduling,
and multi-operation recovery. Complete mediation depends on backend
instrumentation and the admitted world's observation coverage. This ADR proves
neither universal noninterference nor controllability, robustness, liveness,
backend equivalence, or protection of opaque internals and undeclared channels.
