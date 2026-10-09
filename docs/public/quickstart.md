# Validate your first scenario

Install RAES, validate a small SDL file, and print its name. You need
standard CPython 3.11 through 3.14.

## Install RAES

Create a virtual environment and install the published package:

```console
python -m venv .venv
source .venv/bin/activate
python -m pip install raes
```

On Windows PowerShell, activate the environment with
`.venv\Scripts\Activate.ps1`.

## Save the scenario

Copy this file to `first-scenario.sdl.yaml`:

```{literalinclude} _static/examples/first-scenario.sdl.yaml
:language: yaml
```

The `nodes` section declares the network and host. The `infrastructure`
section asks a backend for one instance of each and links the host to the
network.

## Validate the file

Run:

```console
python - <<'PY'
from pathlib import Path
from raes import parse_sdl_file

scenario = parse_sdl_file(Path("first-scenario.sdl.yaml"))
print(f"Validated {scenario.name} with {len(scenario.nodes)} nodes.")
PY
```

If validation succeeds, the command prints:

```text
Validated first-scenario with 2 nodes.
```

RAES has checked the file's structure and current semantic rules. It has not
created infrastructure. Continue with the
[first-scenario tutorial](tutorials/first-scenario.md) to inspect and format
the scenario.
