# Workflow library assessment

Keep RAES workflow rules and the compiler in their current modules.
Use existing libraries for type checks and graph order.
The user expanded issue #2009 to include this review.
This review compares source documents.
It does not prove that a new library or backend meets RAES rules.

## Existing owners

| Concern | Existing owner and interface | Choice |
| --- | --- | --- |
| Input shape. | Pydantic through `raes_contracts.sdl_model.SDLModel` and `raes.orchestration.WorkflowStep`. | Keep type checks and field aliases. |
| Graph order. | `raes_contracts.graphs.has_cycle()` and `stable_topological_order()` use Python `graphlib`. | Reuse these helpers under ADR-118. |
| Step results. | `raes_contracts.workflow.semantics` defines step state, outcomes and attempts. | Keep these RAES rules. |
| Join and prior state checks. | `raes.validator` walks branch and prior-step paths through nested calls. | Use graph order to remove deep calls. |
| Compiler. | `raes_processor.compiler.workflows` and `workflow_steps` resolve typed names and produce portable contracts. | Keep this RAES mapping. |
| Execution. | Temporal adapters and the local runtime follow ADR-113. | Keep their current roles. |

The reviewed source revision is `1cb8f78946214fa20da0d185335bffed256debdf`.
The workflow compiler produces data contracts.
This review treats graph checks and live execution as separate concerns.

## Candidate comparison

| Candidate | What it gives | Fit for this code |
| --- | --- | --- |
| Python 3.14 `graphlib`. | Cycle checks and graph order. | Reuse the shared graph owner. No new dependency is needed. |
| pytransitions 0.9.3. | Nested and parallel state machines, with async variants. | Can drive state changes. SDL input and prior-state checks still need RAES rules. |
| python-statemachine 3.2.2. | Statechart execution, graph checks and callbacks. | Checks its own statechart model. RAES joins and portable results still need a mapping. |
| Sismic 1.6.11. | Statechart execution, simulation and contract checks. | Can run statechart models. Its Python guards and actions need a separate security review before use. |
| SCXML 1.0 and BPMN 2.0.2. | Standard state-machine and process rules. | Useful references. Adoption needs an SDL mapping and conformance checks. |

None of the reviewed interfaces directly replaces the SDL checks and compiler.
Further work could map SDL to one of these tools.
This change installs none of them and keeps the dependency locks.
The review does not rank speed, reliability or Python support.

## Selected implementation boundary

Keep cycle checks and graph order in `raes_contracts.graphs`.
The new `workflow_join_states()` helper belongs to `raes_contracts.workflow.semantics`.
Join and prior-state checks share its results.
A node gets a result only if every path from that node reaches the join.
The result lists only observable steps present on every path.
The join's next step is outside this check.

The shared graph helper puts each successor before its predecessors for this check.
The validator checks incoming predicate state in the opposite order.
At ordinary merges, intersect prior step state.
At joins, add the owner's prior state and guaranteed state from each explicit branch.
Keep the parallel failure route separate from successful barrier release.
Reject cyclic control graphs before these ordered checks.

This removes deep calls without adding another execution engine or language form.
Keep the attempt, outcome, compiled field and backend admission contracts.
The approved shared-execution rule remains normative.
Static graph checks alone do not enforce live execution counts.

## Security and verification

The parser and validator check SDL graphs before compilation.
Long valid graphs must not exhaust the Python call stack.
Invalid branch paths must not expose state as guaranteed after a join.
The shared graph helper sets the check order.
RAES rules decide which inputs pass.

The existing design's data-flow diagram and manager trust boundary still apply.
There is no new expression evaluator, service, credential or data transfer.

Tests cover long branches, deep prior-state paths and cyclic refusal.
Small-graph tests compare the helper's results with a separate list of all paths.
Existing tests check the parallel failure route and prior-state rules.
Mutation checks must detect weakened join and state intersection rules.
Full test, integration and formal suites remain in CI.

## Sources

- [Python 3.14 graphlib](https://docs.python.org/3.14/library/graphlib.html): `TopologicalSorter`, predecessor orientation and cycle refusal.
- [pytransitions 0.9.3](https://github.com/pytransitions/transitions/blob/0.9.3/README.md): hierarchical, parallel and asynchronous extensions.
- [python-statemachine 3.2.2 validation](https://python-statemachine.readthedocs.io/en/stable/validations.html): statechart graph checks.
- [Sismic 1.6.11](https://sismic.readthedocs.io/en/latest/): interpreter, guard/action language and contract checks.
- [SCXML 1.0](https://www.w3.org/TR/2015/REC-scxml-20150901/): parallel states, invocation and transition selection.
- [BPMN 2.0.2](https://www.omg.org/spec/BPMN/2.0.2/About-BPMN): normative specification and machine-readable artifacts.

The library documentation versions above were read on 2026-11-10.
Stable and latest documentation URLs can change after that date.
