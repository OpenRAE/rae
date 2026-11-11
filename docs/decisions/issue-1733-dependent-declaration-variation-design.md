# Dependent declaration presence and consumer choice

This design implements ADR-084 for issue #1733.
It applies the binding guidance in the [issue #1733 preflight](issue-1733-dependent-declaration-variation-preflight.md).
The [issue #1625 design](issue-1625-node-inventory-design.md) remains valid for node presence and runtime inventory.

## Architecture

The `structural` target gains two slot groups.
A declaration presence slot selects one whole keyed declaration.
A resource consumer slot selects the consumer rows of one resource.
The owner is a declaration in the slot's owner section, not a node.
Each target owner must resolve to exactly one declaration in that section.

| Slot | Owner section | Alternative member |
| --- | --- | --- |
| `accounts.presence` | `accounts` | `declaration-presence` |
| `content.presence` | `content` | `declaration-presence` |
| `persistent_volumes.presence` | `persistent_volumes` | `declaration-presence` |
| `generated_artifacts.presence` | `generated_artifacts` | `declaration-presence` |
| `relationships.presence` | `relationships` | `declaration-presence` |
| `propositions.presence` | `propositions` | `declaration-presence` |
| `assertions.presence` | `assertions` | `declaration-presence` |
| `evidence_requirements.presence` | `evidence_requirements` | `declaration-presence` |
| `persistent_volumes.consumers` | `persistent_volumes` | `resource-consumers` |
| `generated_artifacts.consumers` | `generated_artifacts` | `resource-consumers` |

A `declaration-presence` member contains a strict Boolean `present` value.
An absent member removes the declaration only.
It does not remove incoming references.

A `resource-consumers` member lists the consumer rows that the resource keeps.
Each selector contains a `node` reference and a `mount_destination` path.
The pair is the existing consumer identity in the resource.
The node reference uses the resource consumer rule: a bare name or a `nodes.` name.
The path uses the resource mount-path validator.
Each selector must identify one existing row of the owner resource.
The choice keeps each selected row with its payload and source order.
It removes the other rows.
An empty list selects no rows.
The ordinary resource validators then decide if the result is valid.

Authors couple these points to a node presence point with `requires` and `excludes` relations.
SDL does not infer dependencies or remove declarations automatically.
Explicit points keep write permission in the closed slot table.
The `assertions.presence` slot is necessary because an assertion names its proposition.
Proposition removal otherwise leaves the assertion as a dangling reference.
The `generated_artifacts.presence` slot is necessary because SDL rejects an orphan artifact.
An artifact that only absent nodes consume must leave with them.

The canonical target identity is `<owner section>.<owner name>.<slot field>`.
Existing node presence and inventory identities do not change.
All writes resolve against the unchanged family.
Equal writes are idempotent.
Different values for one canonical target fail admission.
A removed declaration conflicts with all other writes to that declaration.
These writes include consumer, reference, collection, and logical-timing writes.
Write paths use exact declaration tokens, so `host` does not own `host.child`.

The selected payload drops field evidence that a removed declaration owns.
Consumer compaction moves retained rows to new positions.
Retained evidence follows each row by its consumer identity.

Composition rewrites each owner through its owner section symbols.
It rewrites each selector node through the node symbols.
Resource consumer node references use the same section rule.
That rule also rewrites a `nodes.` consumer reference in an imported module.

Editor completion offers owners from the slot's owner section.
It offers nodes for a selector `node` field.

## Security and data flows

The design protects valid concrete scenarios and stable declaration identities.
It also protects resource consumer payloads, secret output selections, and field evidence.

| Threat | Control | Verification |
| --- | --- | --- |
| A point writes an arbitrary document path. | Closed slot enumerations and closed member models. | Schema and model tests reject unknown slots, fields, and coerced Booleans. |
| A point writes a declaration of a different kind. | Owner resolution in the slot's owner section only. | Tests use one name in two sections and a wrong-section owner. |
| A selector copies or invents a consumer row. | Selectors match existing rows by node and mount path. | Tests reject unknown, duplicate, and wrong-node selectors. |
| A selection leaves a dangling reference or orphan artifact. | Whole-scenario semantic admission after all writes. | Tests select partial removals and expect atomic refusal. |
| Point order changes the result. | Conflict checks on the complete write set before application. | Tests reverse point order for conflicting and equal writes. |
| Removal leaves stale field evidence. | Provenance remap by declaration name and row identity. | Tests check pointers after removal and compaction. |
| Diagnostics expose payload values. | Existing value-free selection diagnostics. | Tests check that messages omit mount paths. |

No choice reads secrets, generates artifacts, mounts storage, or deletes data.
Selection changes desired declarations only.
Residual risk: authors can still declare points with no valid joint selection.
Whole-scenario admission rejects each such selection, and the trial compiler rejects the complete plan.

```text
Author [external entity]
  -- typed family declarations --> SDL parser and composition [process]
SDL parser and composition [process]
  -- admitted family --> Family artifact [store]
Experiment author [external entity]
  -- recorded member outcomes --> Experiment admission [process]
Family artifact [store]
  -- declarations and consumer rows --> SDL choice [process]
Experiment admission [process]
  -- admitted outcomes --> SDL choice [process]
SDL choice [process]
  -- fresh selected payload --> Instantiation and semantic validation [process]
Instantiation and semantic validation [process]
  -- admitted scenario and provenance --> Snapshot artifact [store]
```

The family boundary admits authored structure.
The experiment boundary admits explicit choices.
The snapshot boundary admits complete concrete scenario semantics.
The ADR-084 lifecycle diagram describes downstream processing and execution.
No component, deployment, or state diagram changes.

## Policy and contracts

The slot catalog in `specs/sdl/variation-points.md` defines the new contract.
The authoring schema and its publication ledger record the new shapes.
The generated schema bundle must match the published schema.
The parser, composition, validator, selection API, and editor tools share one slot table.
Concrete scenario schemas do not gain variation declarations.
Existing families keep their wire meaning and canonical bytes.

The existing repository policy tools and targeted tests enforce these boundaries.
The contract models are the architecture as code.
No new workflow gate, service, backend API, or persistence model is necessary.
ADR-084 already authorizes typed structural slots.
No new ADR is necessary.

## References and writing review

- Pydantic 2.12: [Unions](https://docs.pydantic.dev/latest/concepts/unions/), section "Smart Mode".
  The member union has no shared discriminator, so a literal `kind` selects each closed member model.
- JSON Schema 2020-12: [Conditional schema validation](https://json-schema.org/understanding-json-schema/reference/conditionals), section "If-Then-Else".
  The published schema binds each structural slot group to its member kind.
- NIST SP 800-160 Volume 1, Revision 1: [Engineering Trustworthy Secure Systems](https://csrc.nist.gov/pubs/sp/800/160/v1/r1/final), section "System Security Design".
  The design connects threats to boundaries, controls, and checks.
- ASD-STE100 Issue 9: [Official standard](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf), sections 1, 5, and 6.
  The review checks technical names, one subject per sentence, and sentence length.

The prose describes system behavior.
Implementation tasks and test commands belong in the issue plan.
