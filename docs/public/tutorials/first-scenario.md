# Inspect and format a scenario

Build on the quickstart file and use the CLI to inspect its current structure.

## Prepare the repository environment

Clone the repository when you want the CLI and complete example library:

```console
git clone https://github.com/OpenRAE/rae.git
cd rae
uv sync --project implementations/python --all-extras --frozen
```

`uv` creates the environment from the checked-in lock file.

## Check the file format

Run the formatter in check mode:

```console
uv run --project implementations/python raes sdl format \
  --check docs/public/_static/examples/first-scenario.sdl.yaml
```

The example is laid out for reading, not in the canonical format, so the
command exits with code `1` and writes this line to standard error:

```text
docs/public/_static/examples/first-scenario.sdl.yaml: not canonical
```

The file parses; only its text differs from the canonical format. That format
is the YAML that the formatter writes back from the parsed scenario, and the
check passes only when the file's text matches it exactly. For example, the
formatter drops the blank lines, moves `os` after `resources`, and writes
`Switch` as `switch` and `2 GiB` as the byte count `2147483648`. Run the
command without `--check` to print the canonical form without changing the
file. Exit code `0` means a file already uses the canonical format. The
command does not provision the scenario.

## Inspect the admitted declarations

Use the read-only semantic surface to validate the scenario and inspect its
canonical declaration index:

```console
uv run --project implementations/python raes semantic inspect \
  docs/public/_static/examples/first-scenario.sdl.yaml \
  --contract sdl-yaml/v1 --output json
```

The result records the effective source, migration, normalization, and
validation profiles. It does not acquire modules, write a lockfile or cache,
invoke a backend, or provision infrastructure.

## Explore a larger scenario

The [scenario collection](https://github.com/OpenRAE/rae/tree/main/examples/scenarios)
contains authored examples with participants, behaviors, objectives, and
evidence requirements. Check each example's notes before treating it as a
backend-ready deployment.
