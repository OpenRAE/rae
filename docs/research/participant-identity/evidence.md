# Participant audit evidence

Observed 2026-09-21 on repository revision
`e4136a6e1f2fadc0fa174421532b91360aee0f73` before implementation changes.
The [audit](audit.md) interprets these observations. No native backend action
was executed. The probes establish parser/compiler/editor behavior, not a
complete conformance or security result.

## Minimal probe input

This valid audit specimen was passed through `yaml.safe_dump`, `raes.parse_sdl`
and `raes_processor.compiler.compile_scenario_runtime_model` using the
repository Python environment with `PYTHONPATH=implementations/python/packages`.
The deliberately undeclared objective action distinguishes the entity and agent
paths; it is an observation of current behavior, not recommended authoring.

```yaml
name: audit
entities:
  team: {role: red}
agents:
  one: {entity: team}
  two: {entity: team}
propositions:
  ok:
    description: declared state
    subjects: [agents.one]
    basis: declared_state
    predicate:
      kind: boolean
      property: ready
      semantic_ref: urn:raes:declared-property:ready
      operator: equals
      expected: true
assertions:
  done: {proposition: ok, role: postcondition, polarity: positive}
objectives:
  goal:
    entity: team
    actions: [undeclared-operation]
    targets: [agents.two]
    success: {assertions: [done]}
```

For E1 and E5, use only `name`, `entities` and `agents` from this specimen.
For E4, omit `objectives` and add the participant relationship shown below.
No mocks, permissive model construction, or skipped parser validation were used.

## Observations and negative controls

| ID | Operation | Observed result | Limit |
| --- | --- | --- | --- |
| E1 | Parse and compile two agents with `entity: team`; inspect `model.participant_behaviors` and `build_declaration_index(scenario).reference_aliases(targetable=True)` | Two keys: `participant.behavior.one`, `participant.behavior.two`; `agents.one` and `agents.two` each resolve to their own targetable declaration | Shared entity does not collapse identity; this does not settle affiliation semantics |
| E1-negative | Replace `agents.one` with an empty mapping | `SDLParseError`: `Agent requires 'entity'` | Actual model validation, not the field's empty-string default |
| E2 | Parse/compile the full specimen; inspect the objective's `actor_type`, `actor_name`, and retained `spec` | `entity`, `team`; undeclared action and participant target remain in objective spec | No native action execution claim |
| E2-negative | Replace objective `entity: team` with `agent: one` | `SDLValidationError`: action `undeclared-operation` is not declared by agent `one` | Demonstrates asymmetric validation, not why it was intended |
| E2-entity-only | Remove `agents`; change proposition subject and objective target to `entities.team` | Compiles an entity actor with zero participant behaviors | Organizational objective may be valid ownership; actor terminology is the conflict |
| E3 | Independently replace objective target with `assertions.done` or `propositions.ok` | Both parse/compile; target string retained in objective spec | Acceptance alone does not establish that these objects are inappropriate objective subjects |
| E3-extension | Call `is_targetable_section('future_declaration_kind')` | `True` | Tests the exclusion policy only; actual generic indexing also requires referenceable-section registration |
| E4 | Request `language_completions(text, cursor_path='/relationships/pair/target')` for the relationship below | Offers `one`, `two`, `done`, `team`, `ok`, `pair`, with declaration addresses in `detail` | Successful completion uses the declaration index; subtype filtering is missing |
| E4-negative | Replace relationship target with `entities.team` and parse | Participant endpoint validation rejects it; existing ACT-612 tests exercise the same boundary | The editor offers a choice rejected by the owning semantic validator |
| E5 | Add `starting_conditions: []` to an agent | `SDLParseError` directs the author to precondition `starting_assertions` | Deliberate ADR-079 migration; not evidence that the old field should be restored |

E4's added relationship:

```yaml
relationships:
  pair:
    type: participant
    source: agents.one
    target: agents.two
    participant: {kind: cooperation}
```

## Inspected seams

Coordinates are repository paths plus stable symbols, at the revision above.
These complement the concrete probes; they do not claim exhaustive runtime
coverage.

| Concern | Source and inspected symbol |
| --- | --- |
| Entity requirement, legacy field | `raes/agents.py`: `Agent.validate_required_entity`, `reject_legacy_starting_conditions` |
| Organizational entity | `raes/entities.py`: `Entity`, `flatten_entities` |
| Objective actor/action treatment | `raes/objectives.py`: `Objective.validate_actor_binding`; `raes/semantics/objective_semantics/_analysis.py`: `_check_agent`, `_check_entity` |
| Declaration target eligibility | `raes/_declarations.py`: `_REFERENCEABLE_SECTIONS`, `_add_section_declarations`, `_add_runtime_children`; `raes/_reference_targetability.py`: `is_targetable_section` |
| Relationship and reference purposes | `raes/validator/_content_objectives.py`: `_verify_relationships`, `_verify_agent`, `_verify_participant_interaction_refs`; `_participant_relationships.py`: endpoint and objective checks; `_core.py`: `_operating_scope_ref_index` |
| Observation and effect refs | `raes/observation_scope.py`: `canonical_observation_reference`; `raes_processor/models/behavior_ref_checks.py`: action-result visible-reference checks |
| Composition and address projection | `raes/composition/_behavior.py`; `raes_processor/compiler/addresses.py`: `_participant_behavior_address`; `participant_behaviors.py`: `_compile_participant_behaviors`; `alias_index.py`: `_runtime_addressable_ref_index` |
| Editor | `raes/_language_metadata.py`: `REFERENCE_COMPLETION_TARGETS`; `raes/language_service.py`: `_reference_completion_items` |
| Apparatus and service | `raes/nodes.py`: `ServicePort`; ADR-041 and ADR-092; published participant implementation and execution contracts |

All package paths above are relative to `implementations/python/packages/`.
The [audit](audit.md) links the files directly and distinguishes confirmed
observations from open questions about their intended meaning.

## Existing behavioral checks

From `implementations/python`, ran:

```sh
RAES_REQUIREMENT_UID=ACT-613 .venv/bin/python -m pytest \
  tests/test_act_612_participant_relationships.py \
  tests/test_sem_208_participant_behavior.py \
  tests/test_semantics_objectives.py -q --disable-warnings --maxfail=1
```

Result: **162 passed in 8.68 seconds**. This covers existing participant
relationships, behavior and objective semantics, including negative endpoint
cases. The tests passing alongside E2/E4 is why the audit does not treat green
tests as a conceptual correctness argument.

Initial file-local repository policy passed with `RAES_REQUIREMENT_UID=ACT-613`.
Final publication checks and native issue dependency readback are recorded in
the [remediation plan](remediation-plan.md). No requirements were promoted to
ACTIVE, published schema changed, accepted ADR repinned, or runtime evidence
rewritten by this audit.
