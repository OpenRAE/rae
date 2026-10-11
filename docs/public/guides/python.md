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

Given only text, `parse_sdl` has no file location for resolving `imports`, so
it raises `SDLParseError` for SDL with top-level `imports`. Use
`parse_sdl_file` for a scenario that imports modules.

Both functions check the file shape and its meaning by default. Treat parse
errors as authoring failures. Show the error message to the author. Keep
semantic checks on unless your workflow has a clear reason to inspect the file
shape alone.

See the [API reference](../api/sdl.rst) for signatures and model details.

## Transform an admitted artifact

Transformation functions operate on already parsed models and never write
files. A successful result contains a newly admitted output and a portable
report; a refusal contains no output.

Rename one declaration by its exact canonical address. In this scenario, the
content entry `index-page` refers to the node `web`:

```python
from raes import RenameSDLDeclarationRequest, parse_sdl, rename_sdl_declaration

sdl_text = """
name: rename-example
nodes:
  web:
    type: compute
    os: linux
    resources:
      ram: 2 GiB
      cpu: 1
content:
  index-page:
    type: file
    target: web
    path: /var/www/index.html
"""
scenario = parse_sdl(sdl_text)
result = rename_sdl_declaration(
    scenario,
    RenameSDLDeclarationRequest(
        target_address="nodes.web",
        new_local_name="frontend",
    ),
)
if result.succeeded:
    transformed = result.output
    print(transformed.content["index-page"].target)  # frontend
else:
    for diagnostic in result.report.diagnostics:
        print(diagnostic.code)
```

The rename updates resolved references, module exports, and any explicitly
supplied external-concept binding documents as one all-or-none operation. An
alias, collision, stale linked artifact, or invalid target is refused. Renaming
a node does not rename its `infrastructure` entry, and each `infrastructure`
key must name a node. The rename therefore refuses a node that has an
`infrastructure` entry, such as `web` in `first-scenario.sdl.yaml`, with
`artifact-transformation.target-invalid`.

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
