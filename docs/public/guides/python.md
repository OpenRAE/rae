# Validate SDL from Python

Use `parse_sdl_file` when your app stores a scenario as a file:

```python
from pathlib import Path

from raes import parse_sdl_file

scenario = parse_sdl_file(Path("first-scenario.sdl.yaml"))
print(scenario.name)
```

Use `parse_sdl` when you already have SDL text:

```python
from raes import parse_sdl

scenario = parse_sdl(sdl_text)
```

Both functions check the file shape and its meaning by default. Treat parse
errors as authoring failures. Show the error message to the author. Keep
semantic checks on unless your workflow has a clear reason to inspect the file
shape alone.

See the [API reference](../api/sdl.rst) for signatures and model details.

## Admit an import-free experiment family

Use `admit_scenario_family` to pass a parsed scenario without imports to the
experiment APIs:

```python
from raes import admit_scenario_family, parse_sdl

family = admit_scenario_family(parse_sdl(sdl_text))
```

The function returns a semantically validated `ExpandedScenario`. The experiment
selection validator, binding-target resolver, scenario selector, and trial
compiler accept this family. Build family digest references from the returned
object with `canonical_sdl_digest(family)`.

Admission checks current content and preserves source diagnostics and realization
intent. It does not select outcomes or grant permission to execute. Unresolved
imports and other document phases are rejected. For a family with imports, use
the existing `parse_sdl_file` composition path.

Treat the admitted family as read-only. Python still permits edits.
After edits, reparse the SDL and admit the new `Scenario`. If an edit changes
an omitted default field on the input, admission also asks you to reparse.
This prevents serialization from silently losing that edit. The parser return
types remain unchanged.

## Transform an admitted artifact

Transformation functions operate on already parsed models and never write
files. A successful result contains a newly admitted output and a portable
report; a refusal contains no output.

Rename one declaration by its exact canonical address:

```python
from raes import RenameSDLDeclarationRequest, rename_sdl_declaration

result = rename_sdl_declaration(
    scenario,
    RenameSDLDeclarationRequest(
        target_address="nodes.web",
        new_local_name="frontend",
    ),
)
if result.succeeded:
    transformed = result.output
else:
    for diagnostic in result.report.diagnostics:
        print(diagnostic.code)
```

The rename updates resolved references, module exports, and any explicitly
supplied external-concept binding documents as one all-or-none operation. An
alias, collision, stale linked artifact, or invalid target is refused.

Loss is rejected by default. Removal therefore requires a policy naming the
exact accepted loss kind:

```python
from raes import (
    ArtifactTransformationPolicy,
    RemoveSDLDeclarationRequest,
    remove_sdl_declaration,
)
from raes_contracts.contracts import ArtifactTransformationLossKind

result = remove_sdl_declaration(
    scenario,
    RemoveSDLDeclarationRequest(target_address="nodes.obsolete"),
    policy=ArtifactTransformationPolicy(
        allowed_loss_kinds=(
            ArtifactTransformationLossKind.DECLARATION_REMOVED,
        )
    ),
)
```

Use `canonicalize_portable_contract()` to reconstruct an isolated portable
contract under its closed model, and `compare_canonical_artifacts()` for exact
canonical identity before and after an operation. Canonical identity is not a
claim of behavioral or backend equivalence. Consumers remain responsible for
file transactions, pack layout, persistence, and user-interface behavior.
