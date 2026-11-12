# Participant control-context references

Inspect references to instruction, directive, policy, and guidance assets.
The descriptors are public and synthetic.
They contain no private bytes.

| File | Purpose | Required support |
| --- | --- | --- |
| [Context kit](context-kit.sdl.yaml) | Select a shared instruction for red, withhold it from blue, and give blue a distinct policy in `rules`. | RAES file parser and control-context validation. |
| [Repeated imports](twice-imported.sdl.yaml) | Import the kit as `alpha` and `bravo` with separate declaration namespaces. | File parser with local imports. |

The reusable specification selects version `two` of the directive.
It uses red's `followup` slot.
The guidance declaration has no selection.
Each import keeps the same descriptor and asset pin.
The descriptor is immutable.
Each import gives local names and participant addresses its own namespace.

## Required support and limits

These descriptors apply by role.
That scope stays valid across imports.
A descriptor scoped by address must name its final canonical participants.
Declaring or selecting an asset places no content.
It creates no item for a participant to see.
`withheld` states the author's intent.
It records no runtime withholding or delivery.
Slots impose no order or precedence.
They do not compose instructions.
Consumers must still check lifecycle, authority, content, audience, and delivery under ACT-620.

See the [normative reference contract](../../../specs/sdl/participant-control-context.md) for selection rules.
Use the [migration guide](../../../docs/explain/sdl/control-context-migration.md) to author selections.
The [factor example reference](../../../docs/explain/reference/example-library.md#control-context-factor-target) retains the target configuration example and validator requirements.
Return to the [catalogue](../../README.md) to select another example.
