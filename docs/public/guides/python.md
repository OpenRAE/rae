# Validate SDL from Python

Read a local scenario and obtain a validated `Scenario` for your application.

## Before you start

Use Python 3.14 and RAES 11.0.2 in a virtual environment.
Save the [first scenario](../_static/examples/first-scenario.sdl.yaml)
as `first-scenario.sdl.yaml` in your working directory.
You need read access to that file. No runtime identity is required.

## Read and validate a file

Use `parse_sdl_file` when your app stores a scenario as a file:

```python
from pathlib import Path

from raes import parse_sdl_file

scenario = parse_sdl_file(Path("first-scenario.sdl.yaml"))
print(scenario.name)
```

The file example prints `first-scenario`. It does not compile or execute the scenario.
For imports, apply your existing module trust and resolution policy.

## Validate text already in memory

Set `sdl_text` to your SDL text. For this example, use the downloaded file's contents.
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

Success prints `frontend`. A refusal returns diagnostics and no output artifact.

The rename updates resolved references, module exports, and any explicitly
supplied external-concept binding documents as one all-or-none operation. An
alias, collision, stale linked artifact, or invalid target is refused. Renaming
a node does not rename its `infrastructure` entry, and each `infrastructure`
key must name a node. The rename therefore refuses a node that has an
`infrastructure` entry, such as `web` in `first-scenario.sdl.yaml`, with
`artifact-transformation.target-invalid`.

Loss is rejected by default. Remove the unreferenced `index-page` content
declaration with a policy that permits that loss:

```python
from raes import (
    ArtifactTransformationPolicy,
    RemoveSDLDeclarationRequest,
    remove_sdl_declaration,
)
from raes_contracts.contracts import ArtifactTransformationLossKind

result = remove_sdl_declaration(
    scenario,
    RemoveSDLDeclarationRequest(target_address="content.index-page"),
    policy=ArtifactTransformationPolicy(
        allowed_loss_kinds=(
            ArtifactTransformationLossKind.DECLARATION_REMOVED,
        )
    ),
)
if result.succeeded:
    print("index-page" in result.output.content)  # False
else:
    for diagnostic in result.report.diagnostics:
        print(diagnostic.code)
```

Success prints `False`. The original `scenario` still contains `index-page`.
Review the report before saving the result under a new filename.
On refusal, correct the target or explicit loss policy. Do not save a missing output.

Use `canonicalize_portable_contract()` to reconstruct an isolated portable
contract under its closed model, and `compare_canonical_artifacts()` for exact
canonical identity before and after an operation. Canonical identity is not a
claim of behavioral or backend equivalence. Consumers remain responsible for
file transactions, pack layout, persistence, and user-interface behavior.

## Finish

The examples create in-memory models only. No backend cleanup is needed.
Remove the downloaded example when you no longer need it.
Read the [SDL API reference](../api/sdl.rst) for exact signatures.
Read [artifact boundaries](../concepts.md) before treating identity as behavioral equivalence.
Continue with [compilation and plan inspection](../sdl/validate-compile-plan.md#compile-the-scenario).
