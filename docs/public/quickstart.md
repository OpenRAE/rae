# Validate your first scenario

Install RAES 11.0.2 and validate a small Scenario Definition Language (SDL) file.
The result will be `Validated first-scenario with 2 nodes.`
The exercise uses public example data and local files.
It needs no account, paid service, deployment backend, or contributor tools.

## Install RAES

Use a POSIX shell, such as Bash, on Linux or macOS.
The commands use shell heredocs; they do not run unchanged in PowerShell.
You need standard CPython 3.14 with `venv` and `pip`.
The installation needs internet access to PyPI.
The remaining exercise runs locally.

Check your interpreter:

```console
python3.14 --version
```

The command exits with code `0` and prints `Python 3.14.x`.
Here, `x` is your installed patch version.
The walkthrough used Python 3.14.7 on Linux x86_64 with Bash.
It used the released PyPI package, without a repository checkout.
Other platforms were not tested in this walkthrough.

Create a new working directory:

```console
mkdir first-raes
cd first-raes
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip --isolated --no-cache-dir install --index-url https://pypi.org/simple raes==11.0.2
```

Each command must exit with code `0`.
The install output ends with a package list that includes `raes-11.0.2`.
Package download messages depend on the installed dependencies.
If environment creation fails, install your operating system's Python 3.14 venv support before continuing.
If installation fails, check the Python version and access to PyPI.
Continue only after installation succeeds.
Keep this shell and directory open for both lessons.

## Save the scenario

Copy this complete example into `first-scenario.sdl.yaml` in your working directory:

```{literalinclude} _static/examples/first-scenario.sdl.yaml
:language: yaml
```

Keep the indentation as shown.
The `nodes` section declares one network and one host.
The `infrastructure` section requests one instance of each and links the host to the network.

## Validate the file

Run this command from the same directory:

```console
python - <<'PY'
from pathlib import Path
from raes import parse_sdl_file

scenario = parse_sdl_file(Path("first-scenario.sdl.yaml"))
print(f"Validated {scenario.name} with {len(scenario.nodes)} nodes.")
PY
```

The command exits with code `0` and prints:

```text
Validated first-scenario with 2 nodes.
```

This output was observed with RAES 11.0.2.
If the command cannot find the file, check its name and your working directory.
If validation fails, compare your copy with the complete example, including indentation.

RAES checked the structure and current semantic rules.
It created no infrastructure and ran no participant.
Validation alone establishes no deployment result or scientific conclusion.
Continue with the [first-scenario tutorial](tutorials/first-scenario.md) in this same environment.
