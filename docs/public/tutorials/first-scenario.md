# Inspect and format a scenario

Change the host's RAM request, correct an invalid reference, and inspect the accepted declarations.
Use the file and activated environment from the [quickstart](../quickstart.md).
These steps were run with released RAES 11.0.2.
They need no checkout, `uv`, backend, or network access.

(prepare-the-repository-environment)=
## Continue in your working directory

Keep the quickstart shell open in `first-raes`.
Your directory contains `.venv` and `first-scenario.sdl.yaml`.
The commands below change only your local copy.

## Change the memory request

Increase the request from 2 GiB to 4 GiB:

```console
python - <<'PY'
from pathlib import Path
from raes import parse_sdl_file

path = Path("first-scenario.sdl.yaml")
path.write_text(path.read_text().replace("ram: 2 GiB", "ram: 4 GiB"))
scenario = parse_sdl_file(path)
print(f"Web RAM: {scenario.nodes['web'].resources.ram // 1024**3} GiB.")
PY
```

The command exits with code `0` and prints:

```text
Web RAM: 4 GiB.
```

The parser accepted the changed resource request.
It stores RAM in bytes; this command prints GiB.
No host received that RAM: this is still an authored declaration.
The two nodes remain the network and host declarations.

## Reject and correct a reference

Deliberately link the host to a network that does not exist:

```console
python - <<'PY'
from pathlib import Path

path = Path("first-scenario.sdl.yaml")
path.write_text(path.read_text().replace("      - lab-network", "      - missing-network"))
PY
```

The edit exits with code `0` and prints nothing.
Now validate the file:

```console
raes semantic validate first-scenario.sdl.yaml
```

This command exits with code `1`.
It prints `validate: invalid` to standard output and the diagnostic to standard error:

```text
validate: invalid
error [sdl.validation] SDL semantic validation reported 1 error(s).
```

The YAML structure still parses, but the network reference is invalid.
Restore the declared network name:

```console
python - <<'PY'
from pathlib import Path

path = Path("first-scenario.sdl.yaml")
path.write_text(path.read_text().replace("      - missing-network", "      - lab-network"))
PY
```

The edit exits with code `0` and prints nothing.
Validate the corrected file:

```console
raes semantic validate first-scenario.sdl.yaml
```

The command exits with code `0` and prints:

```text
validate: success
```

The 4 GiB RAM request remains in the accepted scenario.

## Check the file format

Check the layout of your corrected file:

```console
raes sdl format --check first-scenario.sdl.yaml
```

The command exits with code `1` and writes this line to standard error:

```text
first-scenario.sdl.yaml: not canonical
```

The file is valid, but its text differs from the formatter's canonical layout.
This result is different from the invalid reference above.
The [SDL command reference](../api/cli.rst) describes the formatter options.

Save the formatted output to a separate file:

```console
raes sdl format first-scenario.sdl.yaml > canonical.sdl.yaml
raes sdl format --check canonical.sdl.yaml
```

The final command exits with code `0` and prints nothing.
The first command also returns status `0`; its output goes to `canonical.sdl.yaml`.
Keep the input and output paths different to prevent shell redirection from emptying the input.
Formatting creates no infrastructure.

## Inspect the admitted declarations

Inspect the corrected scenario:

```console
raes semantic inspect first-scenario.sdl.yaml --contract sdl-yaml/v1 --output json
```

The command exits with code `0` and prints JSON.
Find `"status": "success"` and `"scenario_name": "first-scenario"`.
The payload reports `"declaration_count": 5`.
It lists the scenario, two nodes, and two infrastructure declarations.
The output also identifies the effective validation profiles.
See the [semantic command guide](../guides/cli.md) for the result fields and exit statuses.

You changed a resource request, observed rejection, recovered, and checked the accepted file's layout.
These operations validate and inspect declarations.
They do not compile a plan, deploy resources, or establish runtime results.
Scientific conclusions require evidence beyond this exercise.

## Explore a larger scenario

Continue with [validate, compile, and inspect a scenario plan](../sdl/validate-compile-plan.md) to examine a planning result.
For exact fields, use the [SDL reference](../api/sdl.rst).
For the relationship between declarations and execution, read [RAES concepts](../concepts.md).

The [example catalogue](https://github.com/OpenRAE/rae/blob/main/examples/README.md) gives purposes, required support, and limits for larger examples.
[Backend ownership](../backends.md) identifies the separate distributions responsible for concrete deployment and native execution.
