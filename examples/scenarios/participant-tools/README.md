# Participant tools across imports

Inspect tool identities, affordances, and access carriers across imports.
The files state the author's intent only.
Neither file installs a tool, opens a session, or runs a scan.

| File | Purpose | Required support |
| --- | --- | --- |
| [Tool kit](tool-kit.sdl.yaml) | Bind the red agent's `scan` action, `network-scanner` affordance, `scanner-package` content, and SSH carrier to `web`. | RAES file parser; the module is also a valid standalone scenario. |
| [Repeated imports](twice-imported.sdl.yaml) | Import the kit as `alpha` and `bravo`, then add local participants over an imported action and tool. | File parser with local imports; compilation and admission use the participant contracts. |

The kit's `red-view` boundary classifies its affordance.
Each import keeps its own tool, action, and boundary.
The importing scenario's `scanner-package` remains a different tool.
The blue `operator` has a local affordance over `alpha.scan` and an RDP carrier to `alpha.web`.
The white `auditor` sees the affordance through the operator's boundary but holds no action.

## Imports

An imported participant needs an affordance classified by its own boundary.
An importer cannot patch that boundary.
Export the affordance from the module, or use a local participant as `operator` does here.
Role selectors select every matching participant in the composed scenario.
The reusable binding therefore uses explicit `participant_refs`.

See the [import reference](../../../docs/explain/reference/example-library.md#participant-tool-references) for qualification rules, diagnostics, and field ownership.
The [composition decision](../../../docs/decisions/issue-298-tool-authoring.md) explains the design.

## Limits

Declaring or displaying a tool authorizes no invocation and proves no execution.
Admission checks the compiled participant's own actions.
The request must bind to an implementation.
The auditor's attempt is refused and recorded nowhere.
Parsing, compilation, and admission establish no backend or apparatus result.
They prove no realization.

The [tool-authoring tests](../../../implementations/python/tests/test_issue_298_tool_authoring.py) exercise these boundaries.
The [participant reference](../../../specs/formal/participant-semantics/README.md) owns their semantics.
Return to the [catalogue](../../README.md) for other examples.
