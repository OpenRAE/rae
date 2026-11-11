# Author RAES SDL

Create a scenario that passes local semantic validation.
Use RAES 11.0.2 and Python 3.14. You need write access to a local SDL file.
This task changes only that file; it needs no runtime identity or backend permission.

## Author and check the scenario

Start with four parts:

1. Give the scenario a stable `name`.
2. Declare resources under `nodes`.
3. Set requested counts and links under `infrastructure`.
4. Run `raes semantic validate scenario.sdl.yaml` on your file.
5. Correct each reported error before adding more sections.

Replace `scenario.sdl.yaml` with your file path.
Exit `0` and `validate: success` mean that structural and semantic checks passed.
Exit `1` means refusal. Read [diagnostics and recovery](validate-compile-plan.md#read-diagnostics).
For imported modules, use [file parsing from Python](../guides/python.md#read-and-validate-a-file).

The [quickstart](../quickstart.md) shows all four parts. Larger scenarios can
add services, identities, participants, behaviors, objectives, workflows,
variation, and evidence requirements. Follow [validate, compile, and inspect a scenario plan](validate-compile-plan.md) to add a condition, evidence, attacker behavior, participants, and objectives one at a time.
Then compile the scenario and read its plan.

## Read the exact reference

The published schemas and normative specifications remain the authority for
accepted fields and meaning:

- [SDL schema for RAES 11.0.2](https://github.com/OpenRAE/rae/tree/v11.0.2/contracts/schemas/sdl)
- [SDL document and source rules](https://github.com/OpenRAE/rae/blob/v11.0.2/specs/sdl/document-model.md)
- [Exact section catalog](https://github.com/OpenRAE/rae/blob/v11.0.2/specs/sdl/sections.md)
- [Reference resolution rules](https://github.com/OpenRAE/rae/blob/v11.0.2/specs/sdl/references.md)
- [Normative SDL specification index](https://github.com/OpenRAE/rae/tree/v11.0.2/specs/sdl)
- [Worked examples](https://github.com/OpenRAE/rae/tree/main/examples/scenarios)

The development specification defines [safe-state declarations](https://github.com/OpenRAE/rae/blob/dev/specs/sdl/safe-state.md).
It describes desired states, observed proof, and the backend execution boundary.

## Finish

Keep the validated source. No native resources were created, so no backend cleanup is needed.
Continue with [compile and inspect](validate-compile-plan.md#compile-the-scenario).
Read [scenario concepts](../concepts.md) to understand the authored/runtime boundary.

Read [current limits](../limitations.md) before assuming that a backend can
realize every valid authored section.

```{toctree}
:hidden:

validate-compile-plan
```
