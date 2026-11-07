# Repository design tools

This page tells you how to run the repository design tools by hand.
The Ground Control server reads schema version 1 of `.ground-control.yaml`.
Schema version 1 has no design commands, so `/implement` does not run these tools.

## Prerequisites

Install the two locked environments before you run a tool:

- the Python project environment in `implementations/python/.venv`;
- the tooling environment in `implementations/tooling/python/.venv`.

[CONTRIBUTING.md](../../CONTRIBUTING.md) tells you how to set up the checkout.
Run each tool with `uv run --frozen --no-sync`, so that it does not install or download packages.
The tools need no credentials.

## Commands

Run each command from the repository root.
No command changes HEAD, the index, or the tracked and untracked working tree.

| Command | What it checks |
| --- | --- |
| `python -m compileall` in the project environment | Each Python file in `implementations/`, `tools/` and `noxfile.py` compiles with the project interpreter. Send the bytecode to a temporary directory. |
| `tools/check_repo_policy.py --check-set structural`, then the structural fixture tests | The ADR-117 structural checks and the ADR-121 package layers. The fixture tests prove that each check finds its violations. |
| `tools/design_wiring.py` in the tooling environment | Prints the import graph between the first-party packages as a Mermaid flowchart. grimp reads the source; nothing imports it. |
| `tools/design_acceptance.py` in the project environment | Runs one exact pytest case and reports its outcome as JSON. |

The structural check set runs only the ADR-117 checks: the import-linter contracts in `tools/policy/import_contracts.toml`, the cycle, private-import, class-ancestry, hidden-import and private-member checks, and the baselines in `tools/policy/structural_baseline.json`.
The full policy set and the full test suite run in CI.

`tools/design_wiring.py --depth 2` shows the direct children of each package.
The default depth is 1.

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
