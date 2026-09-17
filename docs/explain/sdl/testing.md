# SDL Testing

The SDL and runtime stack use a layered testing strategy. Under the repository's
[coding standards](../reference/coding-standards.md), not every change needs
formal methods, but semantic and stateful changes should add the smallest
adequate artifacts for their classification level.

## Testing Ladder

Use the smallest level that matches the change:

1. **Unit tests** — parser/model/validator/compiler/planner behavior
2. **Property-based tests** — generated inputs and invariant preservation
3. **Semantic invariant tests** — explicit valid/invalid behavior for
   cross-reference, graph, visibility, or portability rules
4. **Abstract models for FM3 work** — optional state-machine/TLA+/Alloy support
   for especially risky control or contract semantics

Formal tools are not part of the default developer loop or CI. They are
optional artifacts for selected `FM3` changes rather than a blanket requirement
for SDL work.

## Test Suites

### Unit Tests (standard run)

```bash
cd implementations/python && \
uv run --extra dev pytest tests/test_sdl_models.py tests/test_sdl_validator.py \
  tests/test_sdl_parser.py -v
```

Tests `sdl-yaml/v1` decoding and migration diagnostics, structural validation
(Pydantic models), semantic validation (cross-reference checks), shorthand
expansion, and the SDL-only format boundary.
The unit suites also cover OCR-derived duration grammar, workflow graphs, direct service/ACL target refs, and `${var}` placeholder handling across supported scalar/reference fields including selected leaf enums.

### Stress Tests (standard run)

```bash
cd implementations/python && \
uv run --extra dev pytest tests/test_sdl_stress.py tests/test_sdl_realworld.py -v
```

19 scenarios from 8 platforms testing expressiveness boundaries:

- **test_sdl_stress.py** — Scenarios 1-13: OCR, CybORG, CALDERA, Atomic Red Team, CyRIS, KYPO, HTB, Enterprise AD, Cloud Hybrid, Exchange+data, CybORG+agents, AD+trust+federation
- **test_sdl_realworld.py** — Scenarios 14-19: Incalmo Equifax, NICE Challenge 17, CCDC Burnsodyne, HTB Offshore-style, Metasploitable 2, Locked Shields IT/OT/SCADA

Objective coverage is exercised in the stress suites as well: the agent-heavy CybORG-derived scenarios and exercise-heavy scenarios include declarative `objectives` so the section is tested against realistic combinations of agents, scoring, orchestration, and team structure rather than only unit tests.

Those suites cover the SDL/runtime surfaces that are currently materialized in
syntax and code. They do not imply full executable coverage for every
participant-, benchmark-, evidence-, or participant-implementation requirement
listed in the requirements architecture. A surface without published syntax,
contracts, named invariant tests, or conformance fixtures is not covered by
these suites.

Each scenario is tested for:
1. Parse + validate success
2. Infrastructure cross-reference integrity
3. Non-trivial content (at least 1 compute node)

### Fuzz Tests (manual trigger only)

```bash
cd implementations/python && \
uv run --extra dev pytest tests/test_sdl_fuzz.py -m fuzz -v
```

Property-based testing using [Hypothesis](https://hypothesis.readthedocs.io/).
The dedicated mapping-key property tests run in the standard suite; the fuzz
session adds mutation coverage and generates about 1,150 inputs per run across
8 strategies:

| Test | Strategy | Examples |
|------|----------|----------|
| `test_valid_sdl_never_crashes` | Structurally plausible SDL scenarios | 200 |
| `test_arbitrary_text_never_crashes` | Completely random text | 500 |
| `test_extra_fields_rejected_cleanly` | Scenarios with unknown fields | 50 |
| `test_fuzz_service_ports` | Random port/protocol/name combos | 100 |
| `test_fuzz_vulnerability_class_validation` | Random CWE class strings | 100 |
| `test_fuzz_feature_dependency_cycles` | Random dependency graphs | 100 |
| `test_fuzz_structural_key_alias_mutations_fail_closed` | Normalized field-alias collisions | 50 |
| `test_fuzz_exact_identifier_duplicate_mutations_fail_closed` | Exact symbol-key duplicates | 50 |

The invariant: the parser **never** raises an unhandled exception. Every input either produces a valid `Scenario` or raises `SDLParseError`/`SDLValidationError`.

Fuzz tests are excluded from the standard `pytest` run via the `fuzz` marker. They take ~70 seconds.

### Full Suite

```bash
# Standard tests (excludes fuzz)
cd implementations/python && uv run --extra dev pytest tests/ -v

# Everything including fuzz
cd implementations/python && uv run --extra dev pytest tests/ -m '' -v
```

### Example Scenarios

The `examples/scenarios/` directory contains curated large SDL files that are
meant to be reusable starting points rather than inline test-only
fixtures. They are loaded directly from disk by
`implementations/python/tests/test_example_schema_conformance.py`
so they stay valid, advisory-free SDL artifacts:

- `hospital-ransomware-surgery-day.sdl.yaml`
- `satcom-release-poisoning.sdl.yaml`
- `port-authority-surge-response.sdl.yaml`

`test_example_schema_conformance.py` proves each shipped SDL example through
two independent legs: strict `sdl-yaml/v1` decoding followed by direct
validation of the decoded longhand object against the checked-in normalized
authoring schema, and reference-parser model serialization against that same
schema. `test_scenarios.py` retains loader failure cases and focused assertions
about the curated complex examples. The valid/invalid/migration source-profile
corpus lives under
`contracts/fixtures/sdl/sdl-yaml-v1/`.

The up-front design briefs for the complex examples live in
[`docs/explain/sdl/complex-scenarios.md`](complex-scenarios.md).

Those example files also serve as disk-backed coverage for current SDL surfaces: enum-backed variable values, direct service/ACL objective targets, and the redesigned workflow language (`decision`, `retry`, explicit join barriers, failure transitions, and workflow state predicates, including post-join branch-state inspection). The runtime/compiler unit suites additionally pin fail-closed behavior for missing same-node feature dependencies and malformed backend lifecycle payloads.

For workflow and runtime semantics specifically, prefer explicit invariant tests
that name the semantic rule being protected. Property-based tests are a strong
fit when the graph/state space can be generated cheaply. Abstract models become
appropriate only for `FM3` changes that materially alter branching, join,
re-entry, or portable result-contract behavior.

Participant exposure/visibility boundaries, evidence-capture disclosures,
apparatus augmentation, and participant-implementation manifests are not
covered by these tests unless named invariant tests or conformance fixtures
exist for the relevant syntax or contract.

## Adding New Scenarios

Use the corpus leg that matches the artifact's purpose:

- **Reusable example scenarios** live in `examples/scenarios/*.sdl.yaml`.
  They are real SDL artifacts and are loaded from disk by
  `implementations/python/tests/test_example_schema_conformance.py`.
- **Synthetic stress and real-world topology fixtures** may stay inline in
  `test_sdl_stress.py` or `test_sdl_realworld.py` when they are test-only
  specimens rather than reusable examples. Add them to the relevant `SCENARIOS`
  list so the parametrized tests pick them up.
- **Negative-path cases** should stay close to the parser, model, or validator
  rule they exercise. Parser-negative SDL fixtures live under
  `implementations/python/tests/data/sdl/invalid/`. Do not add invalid files
  under `examples/scenarios/`; that directory is the positive example corpus.

All scenario corpus loading should continue to flow through the existing
`load_scenario()` / `parse_sdl()` boundary so it receives the same source-marked
safe composition, mapping-key preflight, Pydantic structural validation,
semantic validation, advisory logging,
and `ScenarioValidationError`/`SDLParseError`/`SDLValidationError` behavior as
the rest of the SDL stack.

The canonical example-corpus location is repo-root relative
`examples/scenarios/`. If another suite needs to enumerate the same examples,
reuse or extract a small shared path helper from the existing test boundary
rather than introducing a second hard-coded corpus root or a new discovery
schema.
