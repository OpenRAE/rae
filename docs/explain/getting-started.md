# Getting Started With RAES

Reproducible Agentic Environments System (RAES) supports the description,
realization, control, evaluation, and bounded reproduction of agentic
environments. An agentic environment is a declared and realized setting in
which participants receive observations, take actions, interact with resources
or other participants, and are evaluated under stated controls.

RAES currently provides a Scenario Description Language (SDL), a Python
reference implementation, contracts, examples, tests, and explanatory
documentation. RAES is the overall system; RAES SDL records the authored
scenario and experiment intent that processors, backends, participant
implementations, and runtime choices turn into a realized environment.

Cyber, AI security, AI safety, testing, research, and evaluation are
non-exhaustive application areas. The general model can support additional
domains through their own examples, controlled vocabularies, semantic profiles,
assets, backend profiles, and evidence requirements.

RAES connects authored scenario intent, governed variation, realization inputs,
participant behavior, observations, apparatus identity, provenance, evidence,
replay boundaries, and conformance results for a bounded reproduction attempt.
It does not guarantee deterministic runtime behavior, equal outcomes, exact
replay, scientific validity, or reproducibility.

The repository is not a managed environment service and does not include a
production backend.

Use this page to choose the smallest useful entrypoint for your task.

## Current Boundary

RAES can currently support:

- describing agentic environments as authored scenarios and explicit apparatus
  inputs
- reading and authoring SDL scenario documents
- parsing and validating SDL through the Python implementation
- instantiating variables and compiling runtime models in the reference stack
- checking backend contract fixtures and conformance profiles
- browsing validated, non-normative examples, templates, and reusable patterns
  for scenarios, workflows, participant behavior, tasks, runs, and studies
- reviewing the specifications, ADRs, and examples that define current claims

RAES does not currently provide:

- production range deployment
- hosted backend operation
- first-class SDL sections named `tasks`, `runs`, or `studies`
- backend-specific deployment recipes for the example library
- production run storage, study management, or participant-control services

Treat the examples and library templates as authoring aids, not as conformance
fixtures or schema authority.

## Choose A Path

| Goal | Start with | Current check | Supported statement |
|------|------------|---------------|---------------------|
| Understand the repository | `README.md`, [`docs/index.md`](../index.md), [`docs/explain/reference/canonical-reference-map.md`](reference/canonical-reference-map.md) | Read the referenced docs | The repository layout and current boundaries are understood. |
| Understand the agentic-environment lifecycle | [`docs/explain/reference/glossary.md`](reference/glossary.md), [`docs/explain/sdl/runtime-architecture.md`](sdl/runtime-architecture.md) | Follow the authored scenario, realized environment, evidence, and conformance references | RAES system concepts are distinguished from SDL and backend behavior. |
| Read a complete scenario | `examples/README.md`, `examples/scenarios/*.sdl.yaml` | `pytest tests/test_example_schema_conformance.py` | The checked examples load through the current parser boundary. |
| Start from a reusable template or pattern | `examples/library/catalog.yaml`, `examples/library/templates/`, `examples/library/patterns/` | `python tools/check_example_library.py` | The catalog covers scenario, workflow, participant behavior, task, run, and study surfaces with parser-validated template bodies. |
| Author a small SDL file | [`docs/explain/sdl/index.md`](sdl/index.md), [`docs/explain/sdl/sections.md`](sdl/sections.md), [`docs/explain/sdl/validation.md`](sdl/validation.md) | `parse_sdl_file()` or `load_scenario()` | The file is accepted by the current SDL model and semantic validator. |
| Use an agent-facing authoring surface | `raes-mcp`, then `raes_tool_surface`, `raes_agent_guidance`, `raes_intended_use_profiles`, and [`docs/explain/sdl/language-service.md`](sdl/language-service.md) | `raes_agent_guidance`, `raes_intended_use_profiles`, `sdl_completions`, `sdl_apply_edit`, `sdl_diagnostics`, `sdl_format`, `sdl_references`, `sdl_validate`, `sdl_design_assessment`, `sdl_plan`, `sdl_claims_assessment` | The agent can choose an intended-use scope, inspect current RAES blockers, and help author, edit, dry-run, and qualify claims without repository-local code access. |
| Use variables or imports | [`docs/explain/sdl/parser.md`](sdl/parser.md), [`docs/explain/sdl/sections.md`](sdl/sections.md) | `raes sdl resolve`, `raes sdl verify-imports` | Imports and variable placeholders follow the current parser rules. |
| Inspect current limits | [`docs/explain/sdl/limitations.md`](sdl/limitations.md), [`docs/explain/sdl/testing.md`](sdl/testing.md) | Compare the use case to the listed materialized surfaces | Unsupported or partial surfaces are identified before authoring. |
| Work on backend conformance | [`docs/explain/sdl/runtime-architecture.md`](sdl/runtime-architecture.md), `contracts/README.md`, [`docs/explain/reference/backend-conformance.md`](reference/backend-conformance.md) | `raes conformance --help` and the conformance tests | The backend work is aligned with published contracts and fixtures. |
| Review semantics or authority | [`docs/specs/formal.md`](../specs/formal.md), [`docs/decisions/adrs/`](../decisions/adrs/README.md), [`docs/explain/reference/normative-artifact-authority.md`](reference/normative-artifact-authority.md) | Read the relevant spec, ADR, and tests together | The claim is grounded in the current authority surface. |

## Rigor Levels

Use the lowest level that answers the question.

| Level | Use when | Current artifact | What it can show | What it cannot show |
|-------|----------|------------------|------------------|---------------------|
| Orientation | You need to know what RAES is and is not. | README, docs index, reference map | Current repository scope and entrypoints | SDL validity, backend behavior, or experiment adequacy |
| SDL parse and validation | You have an SDL file and need current parser feedback. | `parse_sdl_file()`, `load_scenario()`, SDL parser/model/validator tests | Structural and semantic acceptance by the reference implementation | Deployment viability or general domain completeness |
| Example-backed authoring | You need a worked scenario to study or adapt. | `examples/scenarios/*.sdl.yaml`, `test_example_schema_conformance.py` | The example loads from disk without advisories under current tests | Suitability for another range, backend, exercise, or research design |
| Template and pattern authoring | You need a reusable starting shape for a scenario, workflow, participant behavior, task, run, or study. | `examples/library/catalog.yaml`, `tools/check_example_library.py` | The cataloged template body validates as current SDL and the pattern has stable metadata | New runtime semantics or first-class task, run, or study sections |
| Runtime and contracts | You need processor or backend integration context. | Runtime compiler/planner, contract schemas, backend profiles, conformance fixtures | Current reference-stack and contract behavior | Production backend correctness or operational reliability |
| Specification review | You need to evaluate a semantic or authority claim. | `specs/`, ADRs, formal notes, tests | The current reasoning and normative boundary for a claim | Completed implementation when the materialized code/contracts are absent |

## Basic Setup

From the repository root:

```shell
cd implementations/python
uv sync --all-extras
uv run raes --help
```

Parse and validate a scenario from Python:

```python
from pathlib import Path

from raes import parse_sdl_file

scenario = parse_sdl_file(
    Path("../../examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml")
)

for advisory in scenario.advisories:
    print(advisory)
```

Run the current disk-backed example tests:

```shell
cd implementations/python
uv run --extra dev pytest tests/test_example_schema_conformance.py -q
```

Work with SDL module imports:

```shell
cd implementations/python
uv run raes sdl resolve ../../examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml
uv run raes sdl verify-imports ../../examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml
```

Inspect a compiled execution plan as JSON:

```shell
cd implementations/python
uv run raes processor plan ../../examples/scenarios/techvault-defensive-min.sdl.yaml --format json
```

This is a read-only dry run: it parses, compiles, and plans the scenario against
the reference backend manifest and prints the resulting provisioning,
orchestration, and evaluation plans as published-contract JSON. It does not
apply or start anything. Pass `--manifest <backend-manifest-v2.json>` to plan
against an explicitly supplied backend manifest.

See how the planner reconciles one scenario version against another:

```shell
cd implementations/python
uv run raes processor reconcile \
  ../../examples/scenarios/reconciliation-demo-v1.sdl.yaml \
  ../../examples/scenarios/reconciliation-demo-v2.sdl.yaml \
  --format json
```

This plans the first version, projects that plan into a snapshot, plans the
second version against the snapshot, and reports every resulting `create`,
`update`, `delete`, and `unchanged` action across provisioning, orchestration,
and evaluation. Both versions are planned against the same manifest, so the
reported delta reflects the authored difference rather than a change of target.

The projected snapshot is synthetic assumed state, not backend readback or
proof that anything was realized, and this too is a read-only dry run. The
report summarizes resource identity and dependencies; resource payloads are
deliberately omitted because they can carry authored credentials and content. A
rejected version exits non-zero: a rejected baseline stops before the snapshot
is projected and reports no action counts at all, rather than reporting zeroes.

Expose the agent-facing MCP tools:

```shell
cd implementations/python
uv run raes-mcp
```

Start with `raes_tool_surface`, then call `raes_agent_guidance` for
machine-readable scope boundaries, invariants, review priorities, and
safe-operating expectations. Call `raes_intended_use_profiles` to select an
intended-use scope and inspect current RAES delivery blockers. Use
`sdl_claims_assessment` before making research
or range-readiness claims. These tools do not execute participant actions or
start a live range.

When an agent is authoring SDL, use the language-service tools before and
after text changes:

- `sdl_completions` to ask which fields or references are valid at a path
- `sdl_apply_edit` to apply a minimal JSON-pointer edit
- `sdl_diagnostics` to get structured parse and semantic errors
- `sdl_format` to normalize the SDL before returning it
- `sdl_references` to find definitions and usages before reference-sensitive
  edits

See [SDL Language-Service Tools](sdl/language-service.md) for concrete request
and response shapes.

See [Agent Guidance Profile](sdl/agent-guidance.md) for the structured guidance
payload agents can cite in plans and reviews.

The CLI does not expose a separate general-purpose `validate` command today.
Use the Python parser boundary or the test suite for direct validation.

## Current Example Use

The current positive example corpus is under `examples/scenarios/`. Each file
is real SDL and is loaded and checked without advisories by
`implementations/python/tests/test_example_schema_conformance.py`.
The reusable authoring library is under `examples/library/` and indexed by
`examples/library/catalog.yaml`.

Use examples to:

- inspect large SDL structure
- see current workflow, objective, relationship, content, and runtime surfaces
- exercise parser and semantic validation with real files
- start from validated templates for scenario, workflow, participant behavior,
  task, run, and study authoring
- compare reusable patterns against current limitations before claiming support
- identify authoring friction against current limits

Do not use examples to claim:

- production backend support
- complete cyber-range domain coverage
- complete participant-behavior adequacy
- first-class task, run, or study runtime support
- conformance to any backend beyond published fixtures and tests

## Template And Pattern Boundary

The current library provides validated authoring aids, not new runtime
authority.

Current status:

- Scenario examples exist as valid SDL files.
- Workflow examples exist inside scenario files, workflow specs, and the
  workflow template.
- Participant behavior has a reusable action-contract and observation-boundary
  template validated through current SDL semantics.
- Tasks, runs, and studies have reusable templates and patterns that map those
  concepts onto current objectives, workflows, timing, conditions, and evidence
  references. Graded scoring/reward is an experiment/evaluator-plane concern
  (ADR-073), not an SDL section.
- Evidence and provenance concerns are documented at architecture and
  limitation surfaces, but not fully materialized as published runtime
  contracts.

When adding an artifact, put it where its current role matches the repository
authority boundary:

- valid worked SDL examples: `examples/scenarios/*.sdl.yaml`
- reusable non-normative templates and patterns: `examples/library/`
- explanatory snippets: `docs/`
- normative rules: `specs/`
- published schemas and fixtures: `contracts/`
- implementation tests: `implementations/python/tests/`

Invalid SDL specimens belong in focused tests or contract fixtures, not in the
positive example corpus.
