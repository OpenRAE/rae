# Getting started with RAES

Use this page to choose a task in the Python reference checkout.
RAES describes agentic environments. SDL records authored scenario and experiment intent.
Processors, runtimes, and backends have separate responsibilities.
The repository is not a managed environment service or a production backend.

## Current boundary

The Python stack parses and validates SDL, compiles models, and checks contract fixtures.
It also provides a CLI and agent-facing MCP tools.
A valid scenario does not prove deployment, exact replay, or scientific validity.
Use the [current limits](sdl/limitations.md) before making a stronger claim.

## Choose a path

| Task | Start here |
| --- | --- |
| Prepare a contributor checkout | [Contributor setup](../../CONTRIBUTING.md#set-up-the-repository) |
| Run a targeted check | [Development workflow](../DEVELOPMENT_WORKFLOW.md#run-verification) |
| Validate a first scenario | [First scenario tutorial](../public/tutorials/first-scenario.md) |
| Find exact fields or parse rules | [SDL sections](sdl/sections.md) and [parser behavior](sdl/parser.md) |
| Use imports and variables | [Parser behavior](sdl/parser.md) |
| Use CLI validation or JSON output | [CLI guide](../public/guides/cli.md) |
| Use agent tools | [Language service](sdl/language-service.md) and [agent guidance](sdl/agent-guidance.md) |
| Understand execution ownership | [Runtime architecture](sdl/runtime-architecture.md) |
| Build a backend | [Backend conformance](reference/backend-conformance.md) and [contracts](../../contracts/README.md) |
| Investigate meaning or evidence | [Canonical reference map](reference/canonical-reference-map.md) |

## Rigor levels

Choose the evidence that answers your question:

- Parsing and validation show acceptance by the current reference implementation.
- Example tests show that the selected example loads under its test conditions.
- Planning shows proposed operations against a selected manifest.
- Fixture conformance checks published contracts under the selected profile.
- Runtime behavior needs observations from the actual runtime and backend.

None of these results alone establishes experiment validity or reproducibility.
Keep authored intent, live state, and archival evidence distinct.

## Basic setup

Complete the [frozen environment setup](../../CONTRIBUTING.md#set-up-the-repository).
Run these commands from the repository root.
Inspect the installed CLI:

```shell
uv run --project implementations/python --frozen raes --help
```

Check the disk-backed examples:

```shell
uv run --project implementations/python --frozen pytest implementations/python/tests/test_example_schema_conformance.py -q
```

Exit `0` means that the selected checks passed.
For file-backed validation with import expansion, use Python:

```python
from pathlib import Path
from raes import parse_sdl_file

scenario = parse_sdl_file(
    Path("examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml")
)
for advisory in scenario.advisories:
    print(advisory)
```

Use the [parser reference](sdl/parser.md) for errors and import trust rules.
The CLI `raes semantic validate` rejects top-level imports in its text-input path.
Use file-backed parsing when validating a composed scenario.

For a read-only plan, run:

```shell
uv run --project implementations/python --frozen raes processor plan examples/scenarios/techvault-defensive-min.sdl.yaml --format json
```

This uses the reference stub dry-run manifest unless you supply `--manifest`.
It prints proposed provisioning, orchestration, and evaluation plans.
It does not apply operations or start a range.
For reconciliation, use `raes processor reconcile --help` and the [CLI guide](../public/guides/cli.md).
A projected snapshot is assumed state, not backend readback.
A rejected baseline produces no action counts.

For agent-facing tools, start the MCP server:

```shell
uv run --project implementations/python --frozen raes-mcp
```

Start with `raes_tool_surface`, then inspect `raes_agent_guidance` and `raes_intended_use_profiles`.
Use `sdl_claims_assessment` before making research or readiness claims.
These tools do not execute participant actions or start a live range.
Stop the stdio server when your client has finished.

## Current example use

Read [the example catalogue](../../examples/README.md) to choose a worked scenario.
Use `examples/library/catalog.yaml` for reusable templates and patterns.
These inputs help with authoring.
They do not qualify a production backend, domain completeness, or an experiment.
The [testing guide](sdl/testing.md) identifies the owning example checks.

## Template and pattern boundary

Templates are non-normative authoring aids.
They do not introduce first-class SDL `tasks`, `runs`, or `studies` sections.
Graded scoring and reward belong to the evaluator plane, as ADR-073 defines.
Use [the section reference](sdl/sections.md) for supported syntax.
Use [the authority reference](reference/normative-artifact-authority.md) before proposing new rules.

Put valid reusable scenarios in `examples/scenarios/`.
Put invalid specimens in focused tests or contract fixtures.
Put normative rules in `specs/` and published schemas in `contracts/`.
Follow [CONTRIBUTING.md](../../CONTRIBUTING.md) to propose a change.
