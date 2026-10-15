# Participant tools across imports

These scenarios declare which tools participants may use and how they reach
them. They declare authored intent only. Neither file installs a tool, opens a
session or runs a scan.

- `tool-kit.sdl.yaml`: a reusable module that is also a valid standalone
  scenario. Its red agent holds the `scan` action and an SSH carrier to the
  `web` node. The `network-scanner` affordance binds the `scanner-package`
  content to `scan`, and the agent's own `red-view` boundary classifies the
  affordance.
- `twice-imported.sdl.yaml`: imports the module as `alpha` and `bravo`. Each
  import keeps its own tool, action and boundary, even though the importing
  scenario declares a different `scanner-package` of its own. The blue
  `operator` gets a local affordance over `alpha.scan` and an RDP carrier to
  `alpha.web`. The white `auditor` sees that affordance through the operator's
  boundary but holds no action.

| DSL-117 concern | Authored field |
| --- | --- |
| Tool | `tool_ref`, which names one scenario `content` identity |
| Affordance | `behavior_specifications.<spec>.tool_affordances.<id>` |
| Invocation interface | The bound action contract's `arguments`, reached through the compiled action address; the affordance copies none of it |
| Access interface and channel | `agents.<name>.interactive_access.<id>`: a compute-node `target_ref`, `channel` `ssh` or `rdp`, optional `account_ref` |
| Scope and availability | The owning specification's `participant_refs` or `participant_role_refs` and `authority_scope_refs`, the participant's own `actions` and `observation_boundaries`, and the action contract's preconditions and argument domains |

## Imports

A `tool_ref` inside the module that names one of the module's declarations
binds that declaration in every import, whether it is bare (`scanner-package`)
or section-qualified (`content.scanner-package`). A bare `tool_ref` that the
module gives to two declarations fails composition with the same "is ambiguous"
diagnostic that the module gets on its own. Spell it `content.<name>` or rename
the other declaration. A `tool_ref` that names nothing in the module resolves
against the complete composed scenario.

The paragraph above describes `tool_ref`. A stateful resource's
`ordering_dependencies` and `refresh_dependencies` have their own check. A bare
dependency name that the module gives to both a generated artifact and a
persistent volume fails composition with a "dependency reference ... is
ambiguous; use one of" diagnostic. Behavior `authority_scope_refs` also reject
ambiguous unit-local names before rewriting, with the standalone diagnostic.
Use a qualified scope such as `nodes.web` when another declaration shares its
bare name. Other reference families remain tracked in
[#1575](https://github.com/OpenRAE/rae/issues/1575). Reference-typed action
argument values are neither resolved nor namespaced on import; see
[#1574](https://github.com/OpenRAE/rae/issues/1574).

Tool identities and tool action/observation relations cannot contain authored
`__private` segments, including values supplied by parameters. Export the
intended declaration and name its public import address. Generated private
references inside a module remain valid through composition and instantiation.

An importing scenario cannot add a tool affordance for an imported
participant: the affordance must be classified by one of that participant's own
boundaries, and imports cannot patch them. Export the affordance from the
module, or declare a local participant over imported actions and tools, as
`operator` does here. Role selectors select every participant with that role
in the composed scenario, so a reusable tool binding uses explicit
`participant_refs`. See the
[composition decision](../../../docs/decisions/issue-298-tool-authoring.md).

## Limits

Declaring a tool, or showing it through an observation boundary, authorizes no
invocation and proves no execution. Runtime admission checks the compiled
participant's own actions and requires an implementation-bound request, so the
auditor's attempt is refused and recorded nowhere. Parsing, compiling and
admitting these files makes no backend, apparatus or realization claim. The
examples are read by
[`test_issue_298_tool_authoring.py`](../../../implementations/python/tests/test_issue_298_tool_authoring.py).
