# Scientific-Scenario Completeness

An SDL document can be valid without being ready for deployment or scientific
use. REV1 makes that distinction inspectable through five intended-use
profiles, from a valid fragment through a reproducible benchmark/study input.

Completeness is relative to the selected abstraction and intended-use claim.
An abstract two-computer/three-action scenario can be complete without an OS,
image or package inventory; an effective open materialization scope delegates
choices to the backend rather than requiring the author to finish a concrete
deployment recipe. Scenario specificity also does not select experimental
capture or evidence strength. [#1201](https://github.com/OpenRAE/rae/issues/1201)
deliberately corrects contrary design drift; see the
[clarified intent](../../research/language-extensibility/design-intent.md).
This clarification does not promote the current delivery assessment below.

The normative
{download}`scientific-scenario completeness specification <../../../specs/sdl/scientific-scenario-completeness.md>`
defines the computation and links the canonical taxonomy and delivery
assessment. The complete concern matrix lives in those machine-readable
artifacts rather than being copied into this guide.

The current assessment is deliberately conservative. Only
`valid-sdl-fragment` is complete. The four stronger profiles expose their
blocking concerns directly, including authored/observed-state binding,
specificity, teardown, credentials, time and clocks, participant budgets,
verifiers, hidden assets, and trajectories. Behavioral-relation semantics are
now implemented as `raes-behavioral-relations@rev8`. Each stronger formal
relation retains its explicit assurance-axis status; the participant-opacity
entry records one exact finite-model result without promoting it to a
mathematical proof or runtime/backend result.

These profiles are scope contracts, not validators that silently strengthen
ordinary SDL parsing. They also do not certify a backend, an experiment result,
reproducibility, or behavioral equivalence.

## Participant Control Delivery

The canonical delivery assessment keeps `participant-action-observation`
partial. The shipped surface now includes SEM-230 participant-relative
information-flow semantics, API-423 crossing facts, RUN-319 deny-first
reference-runtime mediation and persistence, API-407 capability selection,
ASR-535 finite falsification evidence, issue #802 migration guidance, and the
issue #803 [role-routed reader guide](../../public/participant-control.md).

That evidence does not promote the concern to implemented. The reference
backend declares all six participant-policy features unsupported, and native
backend realization remains unestablished. The finite cases do not establish
universal noninterference, projected-history equality, trace inclusion,
simulation, refinement, strong or weak bisimulation, model checking, or proof.
Documentation explains the assessed status; it does not change the canonical
profile or assessment.

## Use Through MCP

Agents using `raes-mcp` should call `raes_intended_use_profiles` before
authoring or making readiness claims. With no argument, the tool lists the five
profiles and their computed RAES delivery outcomes. Passing `profile_id`
returns the required concerns, current delivery status, evidence references,
limitations, blocking issue references, explicit nonclaims, and the existing
authoring tools relevant to that intended use.

For example:

```json
{"profile_id": "controlled-experiment-scenario"}
```

The result is an assessment of **what the current RAES ecosystem delivers**.
It deliberately reports `scenario_assessment.status` as `not-assessed`: the
tool does not inspect or certify a particular SDL document, experiment spec,
backend, or run. Authors use the result to choose the appropriate SDL and
`experiment_*` tools and to see which stronger claims remain blocked.
