# Public guide checks

PR #1492 corrects the Python and CLI guides. Its review also found an invalid
removal target and gaps in executable examples and reStructuredText linting.

## Ownership and flow

The existing `tools.nox_support.test_lanes._run_docs` entry point owns the
documentation checks. `tools.nox_support.config.PUBLIC_DOCS_EXAMPLE_TESTS`
selects their tests. Extend those owners rather than adding a runner or service.

The existing public-documentation test apparatus reads checked-in guide blocks,
supplies local fixture files in a temporary directory, and invokes public Python
APIs and the Typer application. Expected output and success assertions check
the documented results. Mark host-dependent fragments with their missing
prerequisites; the inventory test reports those skips and rejects new untested
sample pages. Mutation cases restore the broken rename and removal targets and
remove loss permission to check that the examples detect refusal.

```text
Checked-in guide blocks + local fixtures
  -> existing pytest documentation lane
  -> public Python APIs / Typer CLI
  -> asserted output and success or refusal

Public Markdown + reStructuredText
  -> pinned Vale, with locked project tools on PATH
  -> existing style rules
  -> documentation gate
```

Vale runs through the existing frozen Python project environment so the
Sphinx dependency's `rst2html` command is available. Both extensions receive
the same style rules. Correct newly exposed prose and headings rather than
disabling rules.

## Security and verification

Run the contributed code in the PR's isolated CI. Example files stay in pytest
temporary directories. CLI examples use argument lists and `CliRunner`, never
a shell. No network, deployment secrets, backend execution, or new service is
needed for these examples. The control-plane fragment requires a host-owned
plane and secret channel and is explicitly excluded from standalone execution.

Use the existing command-construction tests to verify the docs lane retains
source/output checks, executable examples, and warning-strict Sphinx. Run the
new examples and their negative mutations in that lane, then require all PR
checks to pass. Refresh source-bound runtime-mapping evidence through the
existing producer in CI and preserve all earlier captures. This changes no
product API, schema, runtime behavior, or architecture dependency direction.
