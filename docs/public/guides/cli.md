(work-with-raes-artifacts-from-the-command-line)=
# Check an artifact from the command line

Validate a local artifact and obtain diagnostics that your application can read.
The semantic commands do not call a backend or change the input file.

## Before you start

Use Python 3.14 and RAES 11.0.2 in a virtual environment.
For the checkout commands below, use the repository's supported uv setup.
For an installed package, run `raes` instead of `uv run --project implementations/python raes`.

Save the [first scenario](../_static/examples/first-scenario.sdl.yaml) as `scenario.sdl.yaml`.
For the portable-record check, save the
[successful operation fixture](https://github.com/OpenRAE/rae/blob/v11.0.2/contracts/fixtures/control-plane/operation-status-v1/valid/succeeded.json)
as `operation-status.json`. You need read access to both files.
Run the commands from the repository root when using uv.

Semantic commands read text in memory. They do not expand SDL `imports`.
For a file with imports, use [file validation from Python](python.md#read-and-validate-a-file).
A valid composed scenario can fail semantic CLI parsing with `sdl.parse`.

## Check available operations

Read the help without changing any artifact:

```console
uv run --project implementations/python raes semantic --help
```

The result lists the supported commands. It does not establish support for every contract/operation pair.

## Separate parsing from validation

Parse the scenario and obtain one JSON result:

```console
uv run --project implementations/python raes semantic parse scenario.sdl.yaml \
  --contract sdl-yaml/v1 --output json
```

Exit `0` and `status: success` mean that parsing succeeded.
Parsing builds the typed model; it does not run all semantic checks.
Use `raes semantic validate scenario.sdl.yaml` before compilation.
Read `status` and `diagnostics` when using `--output json`.

## Validate a portable operation record

Select the portable contract explicitly and supply its bytes through stdin:

```console
uv run --project implementations/python raes semantic validate - \
  --contract operation-status-v1 --output json < operation-status.json
```

Exit `0` means that the supplied record passed that contract's validation.
It does not prove that a backend performed the reported operation.
If validation fails, correct the source record through its owner. Do not replace it with fixture success.

## Normalize a scenario for inspection

Print the normalized result without rewriting the source:

```console
uv run --project implementations/python raes semantic normalize scenario.sdl.yaml \
  --contract sdl-yaml/v1 --migration-policy reject
```

An accepted result uses current semantics. Normalization does not authorize a legacy semantic conversion.
For rejected legacy data, select its [owning migration](https://github.com/OpenRAE/rae/blob/main/docs/migration/README.md).

## Summarize compiled resources

Compile the scenario and inspect the returned summary:

```console
uv run --project implementations/python raes semantic compile scenario.sdl.yaml \
  --contract sdl-yaml/v1 --output json
```

Read `payload.resource_counts` after success.
These counts cover eleven runtime resource kinds, not every compiled declaration.
Continue with [plan inspection](../sdl/validate-compile-plan.md#inspect-the-plan) to inspect planned operations and refusals.

## Obtain canonical SDL bytes

Select the canonical transform:

```console
uv run --project implementations/python raes semantic transform scenario.sdl.yaml \
  --contract sdl-yaml/v1 --transform canonical --output json
```

Only the `canonical` transform emits RFC 8785 SDL bytes.
Pretty JSON is a stable CLI result format, but it is not the canonical SDL byte representation.
No command above saves an output file. Redirect stdout only to a new path that you intend to write.

## Logs and unexpected failures

Results go to stdout. Diagnostics and operational logs go to stderr.
Logs include exception types and code locations, but omit exception messages.
Use `raes --log-level DEBUG <command>` for more records.
Replace `<command>` with the command you need; do not include credentials in its arguments.
An unexpected failure is sanitized and exits `70`.
Keep the input and safe diagnostics for the owning maintainer. Do not copy protected source into public reports.

## Existing compatibility surfaces

Use `raes sdl format --check` to check canonical source formatting.
Module resolution and OCI publication have different effects from semantic checks.
Read the [module command boundary](../semantic-cli-results.md#existing-compatibility-surfaces)
before using them. They can write lockfiles, caches, or an OCI layout.
Pack distribution belongs to OpenRAE/env-packs.

## Finish

The result is a checked artifact or an explicit refusal. No infrastructure cleanup is needed.
Delete disposable input copies and redirected output when you no longer need them.
Read [command results and exit codes](../semantic-cli-results.md) for automation.
Read the [CLI API reference](../api/cli.rst) for implementation details
and [artifact concepts](../concepts.md) for validation limits.

```{toctree}
:hidden:

../semantic-cli-results
```
