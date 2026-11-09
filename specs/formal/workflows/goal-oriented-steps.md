# Goal-oriented workflow step semantics

SCE-004 adds a realization coordinate to executable workflow steps without
changing objective truth or control-flow semantics.

Let a step realization be

`R = (mode, objective, procedure, scaffolds, affordances, action-families, capabilities, facts)`.

`mode` belongs to the closed set `{scripted, objective, scaffolded}`. Existing
steps project to `scripted`, preserving their historical interpretation.
`objective` and `scaffolded` are admitted only for `objective` and `retry`
control nodes, which already bind an actor, targets, dependencies, a time
window, and evidence-bearing success assertions through the referenced
objective.

## Admission invariants

- `scripted` may identify a governed procedure; procedure identity remains
  realization provenance and never defines proposition truth.
- `objective` forbids a prescribed procedure. Capability, affordance, and
  runtime-fact references bound the available realization space without
  selecting a tool or action.
- `scaffolded` has objective semantics and additionally requires at least one
  governed scaffold, tool-affordance, or allowed action-family reference.
- Objective and scaffolded fields are references only. They do not admit
  commands, private planners, scoring rules, prompts, credentials, or backend
  native payloads.
- Procedure references resolve to `procedure`-granularity participant action
  contracts, allowed action families resolve to `aggregate`-granularity action
  contracts, and scaffold references resolve to observation boundaries carrying
  instruction/scaffold view rules. Capability references use the incumbent
  participant-runtime feature vocabularies; runtime-fact binding references use
  the authority-qualified `workflows.steps.fact_binding_refs` vocabulary.
- A backend that does not declare the compiled `objective-steps` or
  `scaffolded-steps` workflow feature fails capability admission; it does not
  silently downgrade the mode.

## Attempt and success invariants

Each attempt records the authored mode, objective address, exposed scaffold
references, selected action family/tool/affordance, runtime-fact versions,
portable outcome, evidence references, and assertion-truth references.

For attempt `a`, portable success is:

`success(a) => evidence_refs(a) != empty AND assertion_truth_refs(a) != empty`.

A participant report, tool exit status, or workflow-local outcome cannot
satisfy that implication by itself. Different tools may therefore realize the
same objective without changing its backend-neutral success meaning.

## Implementation mapping

- authored mode and fail-closed validation:
  `implementations/python/packages/raes/orchestration/__init__.py`
- compiled realization projection and feature requirements:
  `implementations/python/packages/raes_processor/compiler/workflow_steps.py`
- portable attempt provenance:
  `implementations/python/packages/raes_contracts/workflow/`
- behavioral regression surface:
  `implementations/python/tests/test_sce_004_goal_oriented_steps.py`
