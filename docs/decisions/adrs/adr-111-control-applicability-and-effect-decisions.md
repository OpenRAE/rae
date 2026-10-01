# ADR-111: Control Applicability and Effect Decisions

## Status

accepted

Acceptance takes effect when the delivery PR for
[#1352](https://github.com/OpenRAE/rae/issues/1352) merges. An unmerged copy is
proposed delivery state. This decision publishes semantic and contract
obligations; it does not declare executable adoption complete.

## Date

2026-09-22

## Classification

Classification: FM3

Required artifacts: [normative applicability/evaluation relation](../../../specs/formal/participant-semantics/control-applicability-and-evaluation.md),
[worked cases and bounded verification](../../research/control-applicability/cases.md),
[finite model](../../../implementations/python/tests/control_applicability_model.py),
[property cases](../../../implementations/python/tests/test_issue_1352_control_applicability.py),
[migration contract](../../migration/control-applicability-and-evaluation.md),
and canonical SEM-235/API-424 amendments.

Waivers: this design delivery supplies no new wire schema, installed provider,
production runtime change or backend conformance result. The finite model
assumes trusted context and atomic state replacement; it falsifies bounded
relations rather than establishing live enforcement or durable atomicity.

## Context

ADR-108 distinguishes mandatory constraints, optional advice and independent
effects. The [#1352 preflight](../issue-1352-control-applicability-preflight.md)
finds that the published API-424 interface cannot express all those relations:
the whole apparatus must match one sink, profile presence need not cover a
slot, dependent invocations receive no fresh predecessor results, optional
support can block all composition, and a subsequent parent-targeted denial can
leave that parent eligible. These are contract counterexamples, not proof of
a live authorization bypass.

The existing SEM-235 algebra and world boundary remain sound. Their repair
does not require another workflow engine, provider registry, policy language,+store, controller model or security domain.

## Decision

Adopt `participant-control-applicability/rev1`, specified by CA-01–CA-09.
Keep B, the exact admitted apparatus, stable while deriving a covered invocation
subset at K. Required profile obligations exist independently of returned
results. Record applicable, proven-inapplicable and unresolved obligations;
absence never proves inapplicability or permits vacuous success.

Evaluate a finite typed slot/stage DAG with immutable predecessor inputs and
explicit state scopes. A.fact → B.assessment → A.rule is legitimate. The
mandatory input closure is an admitted obligation; required advice retains its
advisory meaning. Failure of truly optional work cannot acquire veto authority.
Bounded support must satisfy the actual admitted coverage and constraints.

Represent parent decisions before effect scheduling. Deny refuses and withhold
remains pending in every phase. Distinguish required predecessors,
success-dependent consequences and independently authorized consequences of
specified dispositions. Check their combined graph with parent events;
independent audit may survive denial without granting parent permission.

Use one incumbent atomic commit for coverage, results, decision, scoped state,
effect intent/claims and budgets. Evaluation-state transitions may commit on
refusal only when explicitly admitted; action-success state cannot. Failed
commit dispatches nothing. All effects retain their owner, originating
authority, current final-sink checks and independent realization evidence.

SEM-235 owns the semantic amendment. API-424 owns its closed versioned
representation and typed provider-input obligations. RUN-320 remains the
shared runtime consumer; backend installation, concrete willingness,
instrumentation and realization remain separately evidenced responsibilities.

## Compatibility and migration

The linked migration contract requires explicit semantic/protocol negotiation
and old/new reader selection. Existing v1 records retain their original content
and meaning; no global reducer change may reinterpret old claims, consumption
or dispatch eligibility. Legacy evidence cannot supply missing dependency or
coverage evidence for the new contract.

API-424's current schemas are draft under ADR-061, but publication flexibility
does not authorize silent semantic reinterpretation. Revised meaning needs an
explicit discriminator/content boundary and coherent reader/capability support.
This delivery changes no wire schema and begins no deprecation window.

## Alternatives Considered

- Filter the apparatus to a crossing subset: loses the admitted identity and
  makes omission indistinguishable from missing mandatory coverage.
- Reorder one call per provider: cannot express A → B → A or supply inputs.
- Treat every selected provider as mandatory: grants optional failure a veto.
- Treat all bounded support as acceptable: silently weakens exact requirements.
- Execute deny after parent release: changes denial into an ineffective event.
- Rewrite historical evaluations with the new reducer: can change retained
  claims, budgets and executable effects without fresh authorization.

## Consequences

A multi-sink apparatus can evaluate only the relevant providers without losing
identity or coverage. Mandatory work remains closed under its dependencies;
optional advice and independent consequences retain precise authority limits.
The cost is explicit coverage, invocation and state bindings, and coordinated
versioned adoption across contracts, runtime, history readers and conformance.

Finite design evidence establishes no backend support, universal security,
provider isolation, delivery, resumability or exactly-once external execution.
