# Development workflow

Use this page to find the canonical local checks. Public contribution steps are
in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Install the locked environment

From the repository root:

```shell
uv sync --project implementations/python --all-extras --frozen
```

## Run verification

The full pull-request gate is:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s verify
```

Use `verify-changed` while you work. It selects a fail-closed subset from the
branch diff. Unknown, source, deleted, renamed, contract, and configuration
changes run the full graph.

The docs session checks the curated source boundary, the RAES Vale style,
warning-strict Sphinx HTML, generated route and search inventories, and links:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s docs
```

## Respect package boundaries

`tools/policy/adr_policy.yaml` defines the public import facades allowed across
RAES packages. Adapters import owning domain APIs only through those listed
facades and never through private modules. For example, the semantic CLI calls
SDL compilation through `raes_processor.compiler`; adding another CLI/compiler
interaction extends that public facade instead of importing compiler internals
or duplicating compiler behavior in `raes_cli`.

Run the repository policy session after changing a cross-package import:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s policy
```

## Release model

Release Please owns `CHANGELOG.md`, package versions, GitHub releases, and the
release pull request. A feature pull request uses a Conventional Commit title
because its squash-merge title becomes the commit that Release Please reads.
Do not edit the changelog or version by hand.

## Review records

Ground Control stores implementation plans, review findings, readiness, and
traceability records for governed work. These developer records stay outside
the hosted public documentation source.
