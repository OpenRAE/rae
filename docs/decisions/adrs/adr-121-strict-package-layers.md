# ADR-121: Strict Package Layers and a Schema Composition Root

## Status

accepted

## Date

2026-10-31

## Classification

Classification: FM1
Required artifacts: ADR invariant list (Decision §7), unit tests (boundary interfaces, published-schema reader, schema composer, retired public paths), structural policy tests (layers, public interfaces, private members, hidden imports, imports inside functions), generated-schema comparison
Waivers: none

The decision moves code between packages and changes the import graph.
It keeps every check, message, digest and persisted byte.

## Context

ADR-036 makes `raes_contracts` the owner of neutral types at the backend and runtime boundaries.
But `raes_contracts` imports `raes` at 57 places, and `adr_policy.yaml` allows it.
Thus 404 modules form one import cycle across the two packages.
Imports inside functions keep the cycle from failing at import time.

Some contracts code does SDL work.
It builds the SDL schemas, admits scenarios, embeds scenario snapshots and computes SDL digests.
Contract fields also use SDL models, for example `EvidenceRequirement`.
Every package depends on `raes_contracts`, so an SDL change can force a change to the base of every backend.

Inside `raes_contracts`, ADR-117 records two cycles between the children of the package (84 and 2 children)
and two cycles inside `raes_contracts.contracts` (79 and 3 modules).
The `contracts` subpackage and the top-level modules import each other in both directions.

## Decision

### 1. Dependency rule

A package imports only lower packages.
`raes_contracts` is the lowest package and imports no first-party package.
`raes` imports `raes_contracts` and no higher package.

### 2. Ownership rules

- **Shared types move down.** A type that two layers share has one owner in the lower layer.
  The authored types that contract fields use move to `raes_contracts`.
  The `SDLModel` base class moves as one class, so its subclasses keep their identity and configuration.
- **SDL work moves up.** Code that needs the SDL model has its owner in `raes` or above.
  `raes` owns scenario admission and identity, the artifact-requirement contract that extends `Source`, and the SDL schema parts.
- **Analysis evidence belongs to its producer.** `raes_processor` owns the satisfiability and exploit-path contracts.
- **One public path.** A moved name has one public path. No module keeps a compatibility re-export.
  A former owner that still uses a moved name imports it under a private alias.
  The `raes` facade keeps its documented exports.

### 3. Boundary interfaces

A lower layer that needs facts about a higher-layer object declares a small interface.
The owner of the object implements it.

- `raes_contracts.associated_artifacts.ArtifactParent` gives `matches_parent_ref`.
  `raes` implements it for scenario, snapshot and materialization parents.
  `raes_contracts` implements it for experiment parents.
- `raes_contracts.contracts.experiment_evidence_refinement.AuthoredScenarioEvidence` gives the scenario identity and its evidence requirements.
  `raes` implements it and computes the SDL digest on first use.

`raes_runtime` gets these implementations only through public `raes_processor.compiler` functions.
`raes_runtime` imports no `raes` module.

### 4. Schema composition root

The new top-level package `raes_schemas` composes the published schemas.
Each owner gives its schema parts and transforms through public functions.
`raes_schemas.schema_bundle()` applies them in a fixed order and checks every validator locator.
The schema tools call it.

Code that needs published schemas at run time reads them as data through `raes_contracts.published_schemas`.
That module reads the corpus through `raes_contracts.corpus` and finds files through an index of contract ids.
`tools/check_generated_schemas.py` proves that the generated bundle equals the published schemas (ADR-009).

### 5. Layers inside `raes_contracts`

The `contracts` subpackage holds the published contract models and the checks that their validators call.
A top-level module of `raes_contracts` is below `contracts` or above it, never both.
A module that composes the contract schemas is above `contracts`.

Inside one package, these rules remove a cycle:

- Modules that change together merge into one module.
- A function moves to the module of the type that it uses.
- A wrapper that only calls a higher module goes. Callers import the owner.
- A module with mixed purposes splits into one module for each purpose.
- A container that must not know its records takes a record policy from its owner.

### 6. Imports

Each import that only prevented the cross-package cycle moves to module level.
An import inside a function needs another reason, for example an optional dependency, a platform module or a PEP 562 `__getattr__`.
ADR-117 checks these rules.

### 7. Invariants

- **L1** No `raes_contracts` module imports a first-party package, in any scope.
- **L2** No `raes` module imports a package above it.
- **L3** No compatibility module re-exports a moved name from its new owner.
- **L4** Each moved class keeps its name, base classes, configuration and validators.
- **L5** `raes_schemas.schema_bundle()` gives the published schemas byte for byte.
- **L6** The published-schema reader never turns a contract id into a file path.
- **L7** Each moved check gives the same result, exception, message and order for the same input.
- **L8** No import cycle exists between the children of `raes_contracts` or of a subpackage of `raes_contracts`.
- **L9** No `raes_contracts` module imports a first-party module inside a function.

## Alternatives Considered

- **An interface for each SDL operation.** The SDL is the only implementation of admission and digests.
  The interfaces need wiring at every entry point, and a wrong implementation weakens a check.
- **The whole SDL model in the base package.** The base package then changes with every SDL change,
  and every backend loads SDL code.
- **Re-exports from `raes_contracts`.** A re-export of a `raes` name is an import of `raes`.
- **Imports inside functions, `import_module` or start-up registration.** They hide the cycle and keep it.
- **Published schemas as the generator output.** The generated-schema check then compares the publication with itself.

## Consequences

### Positive

- The base package depends on nothing above it, so a backend loads only contracts.
- Each concept has one owner and one public path.
- New schema parts go into their owner. Nothing below it changes.
- The checks keep the layers, so a new reverse import fails in CI.

### Negative

- Code that imports a moved name from its old path fails. All callers in the repository change.
  This includes the modules that move into or out of `raes_contracts.contracts`.
- Seven validator locator strings change in five published schemas. Each change has a ledger entry.
- `raes_runtime` reaches SDL facts only through `raes_processor`.

### Risks

- An in-process caller can build a fake parent or scenario view. The current parent argument has the same property.
- A published schema that is not current gives stale content to readers. CI refuses such a change.

## References

- R. C. Martin, *Design Principles and Design Patterns* (2000): the acyclic and stable dependencies principles.
- J. Lakos, *Large-Scale C++ Software Design* (1996), chapter 5: escalation and demotion.
- R. C. Martin, *The Clean Architecture* (2012): the dependency rule and boundary data.
- M. Seemann, *Composition Root* (2011).
- [Issue 1711 design](../issue-1711-strict-layers-design.md).
