# Node presence and runtime inventory choice

This design implements ADR-084 for issue #1625.
The existing experiment lifecycle remains authoritative.

## Architecture

The existing `alternative` point gains a `structural` target.
The closed slot catalog contains `nodes.presence` and explicitly admitted runtime family collections.
Each target names one existing node.
Each choice has a closed type.
Each alternative has a stable member identifier.

A `node-presence` alternative contains a strict Boolean `present` value.
A present alternative can also select named runtime inventory collections.
An absent alternative cannot carry inventory choices.
This form expresses coupled node and inventory choices in one point.

A `runtime-inventory` alternative contains qualified references to existing inventory records.
The target slot selects the collection.
Each reference must identify a top-level member of that collection on the owner node.
The choice preserves record content, identifiers, nested children, and source order.
An empty reference list selects no records in that collection.
Omission does not assert forbidden presence or closed inventory.

The runtime family registry supplies collection identities.
An explicit slot allowlist supplies write permission.
New registrations do not automatically receive write permission.
Packages, environment entries, filesystem entries, and nested collection writes need separate reviewed slots.

SDL applies choices to a fresh payload after composition.
All writes resolve against the original family.
Conflicting values for one target fail admission.
An absent node conflicts with any other write to that node or its descendants.
Coupled inventory choices conflict with separate writes to the same collection when values differ.
Node absence removes the node and its same-key infrastructure entry.
SDL does not remove incoming references or change other declarations.
The ordinary instantiation path validates the complete selected scenario.
The trial compiler rejects the complete trial plan when any requested scenario fails admission.

Choice does not mutate the family or its digest.
Existing trial choices, family pins, snapshots, and run provenance remain the identity records.
Source records stay with each retained record and its stable ID.
The choice removes source records only with their owner.
The bounds on retained records still apply at their new paths.

## Security and data flows

The design protects valid scenarios and stable IDs.
It also protects record ownership and private runtime data.
Family data and experiment outcomes pass through separate checks.
Closed targets prevent arbitrary document writes.
Owner-scoped lookup prevents copying inventory between nodes.
The standard semantic validator rejects surviving dangling references.
Errors identify the point and member without rendering runtime payloads.
No choice reads secrets, starts processes, accesses networks, or provisions resources.
A set of typed choices can still be invalid.
Whole-scenario admission rejects that combination before a plan is sealed.

```text
Author [external entity]
  -- typed family declarations --> SDL parser and composition [process]
  -- admitted family --> Family artifact [store]
Experiment author [external entity]
  -- recorded member outcomes --> Experiment admission [process]
Family artifact [store]
  -- immutable declarations and inventory --> SDL choice [process]
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
The existing ADR-084 lifecycle diagram describes downstream processing and execution.

## Policy and contracts

The slot catalog and authoring schema define the new contract.
The schema publication ledger records every affected schema hash.
The schema bundle must match the published contracts.
The parser and language tools use the same target rules.
Composition and the choice API also use those rules.
Existing static and reference-only families retain their wire meanings.
Concrete scenario schemas do not gain variation declarations.

The existing repository policy tools and targeted tests enforce these boundaries.
No new workflow gate, architecture deployment, backend API, service, or persistence model is required.
ADR-084 already authorizes the extension.
No new ADR is required.

## References and writing review

- Pydantic 2: [Discriminated unions](https://docs.pydantic.dev/latest/concepts/unions/), section “Discriminated unions with string discriminators”.
  The target discriminator selects the closed structural shape.
- NIST SP 800-160 Volume 1, Revision 1: [Engineering Trustworthy Secure Systems](https://csrc.nist.gov/pubs/sp/800/160/v1/r1/final).
  The design connects threats to boundaries, controls, and checks.
- ASD-STE100 Issue 9: [Official standard](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf), sections 1 and 6.
  The review checks consistent technical names, one subject per sentence, and descriptive sentence length.

The prose describes system behavior.
Implementation tasks and test commands belong in the issue plan.
