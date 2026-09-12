# Design verification and acceptance coverage

[check_design.py](check_design.py) is a finite abstract reference model for
ADR-108. It is deliberately separate from production providers, contracts and
runtime code. Run it with:

```bash
implementations/python/.venv/bin/python docs/research/modular-participant-control/check_design.py
```

## Model boundaries

The result reducer enumerates 11 outcomes for three independently mandatory or
advisory slots and all six input permutations: 63,888 permutations. It checks
that order cannot override a mandatory blocker or incumbent denial. A resolved
fact satisfies a fact slot; it does not authorize a sink. Typed slot/result
validation is assumed and must be tested by #1072, not inferred from this
projection. Effect-order and target conflicts are worked counterexamples in
case E; this model is not a complete implementation of PC-07.

The IFC model exhausts the four-element powerset of two influence tokens and
all triples, checking closure, associativity, commutativity, idempotence,
monotonicity and upper bounds. It exposes a counterexample to erasing retained
memory. It proves nothing about instrumentation completeness or arbitrary
future domains, implicit flows or opaque participant internals.

The transition model explores nine events through seven steps over one effect
key and one root budget unit. Its states distinguish absent, committed,
dispatching, applied and indeterminate. Invariants require a committed identity
before dispatch, append-only history, no second call on replay, no call after a
failed admission/commit, and no blind retry after uncertain dispatch. Durable
atomic state and dispatch-start fencing are assumptions. Real crash windows,
multiple keys, concurrent stores, authorized re-dispatch after proof of absence,
and external delivery must be tested by #1069 and the backend proof issues.

A two-rule cyclic trigger model explores root and depth bounds 0–3 with replay,
checking that new effect keys cannot exceed the durable root budget. This
bounded exploration cannot prove unbounded liveness or fairness. The graph
check validates all 15 nodes (design plus 14 delivery issues), acyclicity,
required authority paths and independent alternative backend proof branches.

## Invariants and design counterexamples

| Invariant | Counterexample rejected | Evidence / future real-boundary owner |
| --- | --- | --- |
| Mandatory constraints and incumbent gates cannot be weakened by composition. | Last permit overwrites deny; optional monitor failure erases a required slot. | Exhaustive reducer; #1070/#1071. |
| Conservative derivation preserves every possible influence. | New episode or trusted edit clears retained influence. | Finite join laws and case D; #1070 plus backend instrumentation proofs. |
| Authority and visibility apply independently to each effect. | IFC fact schedules an inject callback; supervisor evidence leaks to the subject. | Cases A/B/C and PC-08/09; #1072/#1069. |
| Commit and stable identity precede effect; external uncertainty remains explicit. | Crash causes blind duplicate delivery, or a changed retry payload reuses an accepted key. | Transition exploration and case F; #1069 and both backend proof issues. |
| Causal effects remain finite and do not bypass ordinary admission. | Self-inject cycle resets its root at handoff or retry. | Trigger exploration and PC-12; #1069/#1071. |
| Conflicting mandatory corrections cannot acquire order from deployment. | Lexically first route or last-arriving transform wins. | Case E; #1070 semantic model and #1071 real-target probes. |
| Architecture and claims retain separate evidence stages. | A provider fixture or capability manifest is promoted to realized IFC. | Assessment, requirements and delivery gates; #1071/#1007/#1008. |

## Issue #1068 acceptance map

| Acceptance criterion | Design evidence |
| --- | --- |
| Dynamic IFC is recognizable and one of several mechanisms. | Assessment primary sources and mechanism table; PC-02/04; ADR-108 §3. |
| In-world adversarial input can be delivered and tracked. | Case B uses SEM-233 sink admission without endorsement; case C tracks permissive influence. |
| Out-of-world integrity/containment stay backend-owned. | ADR-108 §1; PC-14; cases B/G classify invalid realization. |
| Multiple mechanisms/profiles have deterministic composition. | PC-01/05/06/07, case E, exhaustive permutation checks. |
| IFC can trigger governed injects and other effects. | PC-09–PC-12; case A inject, case C review/withhold, cases E/G transformation/delay/handoff/lifecycle constraints. |
| Semantic, runtime, provider, declaration, realization, conformance and evaluation statuses stay distinct. | PC-13/15; assessment inventory; requirement fulfillment boundaries. |
| Backend children do not require the same mechanisms. | ADR-108 §5, case G, independent graph branches and backend issue bindings. |
| Requirements precede implementation children. | Four new DRAFT records, ASR-536 amendment, requirement-order entries and merged-design gate. |

The delivery PR records actual command results for repository policy,
requirement parsing/order, this model and canonical verification. The older
HTTP governance checker can report `skipped-unavailable` because Ground
Control's service was retired; that is not a live governance pass. The
canonical file reader and local requirement-order evaluation provide the
applicable file-backed check, with the service limitation disclosed separately.
