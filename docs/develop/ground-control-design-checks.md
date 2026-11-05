# Ground Control design checks

This page tells you how this repository configures the Ground Control design checks for `/implement`.
The configuration is in `.ground-control.yaml`, in `workflow.design` and `architecture.modules`.
The file declares `schema_version: 2`, so the Ground Control server must read schema version 2.
The Ground Control guide [Configure design checks](https://github.com/autarchy-ai/Ground-Control/blob/beed5db2/docs/public/design-configuration.md) defines the fields and the command rules.

`grndctl init` does not write these settings.
An `ok` result from `gc_get_repo_ground_control_context` and a passing `grndctl doctor` do not run the design commands.

## Prerequisites

Install the two locked environments before you run a design command:

- the Python project environment in `implementations/python/.venv`;
- the tooling environment in `implementations/tooling/python/.venv`.

[CONTRIBUTING.md](../../CONTRIBUTING.md) tells you how to set up the checkout.
Each design command uses `uv run --frozen --no-sync`, so it does not install or download packages.
The commands need no credentials.

## Commands

Each command runs from the repository root.
No command changes HEAD, the index, or the tracked and untracked working tree.

| Field | Command | What it checks |
| --- | --- | --- |
| `compile_command` | `python -m compileall` in the project environment | Each Python file in `implementations/`, `tools/` and `noxfile.py` compiles with the project interpreter. The bytecode goes to a temporary directory that the command removes. |
| `structural_command` | `tools/check_repo_policy.py --check-set structural`, then the structural fixture tests | The ADR-117 structural checks and the ADR-121 package layers. The fixture tests prove that each check finds its violations. |
| `wiring_command` | `tools/design_wiring.py` in the tooling environment | Prints the import graph between the first-party packages as a Mermaid flowchart. grimp reads the source; nothing imports it. |
| `acceptance_command` | `tools/design_acceptance.py` in the project environment | Runs one exact pytest case and reports its outcome as JSON. |

The structural check set runs only the ADR-117 checks: the import-linter contracts in `tools/policy/import_contracts.toml`, the cycle, private-import, class-ancestry, hidden-import and private-member checks, and the baselines in `tools/policy/structural_baseline.json`.
The full policy set and the full test suite run in CI.

`tools/design_wiring.py --depth 2` shows the direct children of each package.
The configured command uses depth 1.

## Acceptance adapter

`tools/design_acceptance.py` reads one JSON object from stdin:

```json
{"test_file": "implementations/python/tests/test_example.py", "test_name": "test_example_case"}
```

`test_file` is a repository-relative path to a regular Python file in `implementations/python`.
`test_name` matches a case when it is equal to the case name, for example `test_x` or `test_x[a]`.
It also matches when it is equal to the node id after the file, for example `TestY::test_x`.

The adapter runs the case in the pytest project and writes one JSON object to stdout:

```json
{"test_name": "test_example_case", "status": "failed", "matches": 1, "message": "assert 1 == 2"}
```

Pytest output goes to stderr.

| Status | Meaning |
| --- | --- |
| `failed` | One case ran, and its test body failed. |
| `passed` | One case ran and passed. |
| `missing` | No case has the exact name, or more than one case has it. `matches` gives the count. |
| `skipped` | The case was skipped or is an expected failure, or the default marker expression deselected it. |
| `broken` | The file did not collect, setup or teardown failed, or the test body raised `SyntaxError`, `NameError` or `ImportError`. |

The adapter exits 0 when it reports an observation, also for a failing case.
It exits 1 for an invalid request or when pytest cannot run, and writes the reason to stderr.
The tests in `implementations/python/tests/test_issue_1919_design_checks.py` check each status.
They use the cases in `implementations/python/tests/fixtures/design_acceptance/`.

## Module map

`architecture.modules` gives the owners and the governing ADRs for each area.
The `.` entry holds the repository-wide decisions: ADR-009, ADR-014, ADR-116, ADR-117 and ADR-121.
Each package in `implementations/python/packages/` has its own entry.
`contracts`, `specs`, `docs`, `docs/decisions/adrs`, `examples`, `tools`, `.github`, `implementations/formal`, `implementations/tooling` and `implementations/python/tests` also have entries.

All entries that contain a changed path apply.
Each reference is a file path in the repository.
When an ADR is superseded, change the references to the new ADR.
When you add a package or a top-level area, add its entry.

## Verify the configuration

1. Call `gc_get_repo_ground_control_context` and make sure that `errors` is empty.
2. Run each command from the repository root, and make sure that it exits 0.
3. Make sure that `git status` shows no change after the commands.
4. Call `gc_get_design_context` with the changed paths, and repair each path that it reports as unmapped.
