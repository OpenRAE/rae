# Check specifications and contracts

Compare a local checkout with its exact specifications and published schemas.
These checks do not deploy a backend or qualify a live service.
OpenRAE/rae owns the portable artifacts and admission checks.
Each backend distribution owns its native effects and cleanup.

## Prepare the checkout

Use the [repository setup](../../CONTRIBUTING.md#set-up-the-repository).
Run these commands from the repository root.
The checks below were selected against revision
`c2fa955ee90d42950b075de3183dc2bef23ad9a4`.
They describe the development checkout, not additional support in RAES 11.0.2.

1. Record the revision with `git rev-parse HEAD`.
2. Complete the frozen Python and tooling environment setup.
3. Select the exact reference for the artifact under review.

Use the [SDL reference](../../specs/sdl/README.md) for authored meaning.
Use the [schema index](../../contracts/schemas/README.md) for portable shape.
Use the [formal index](../../specs/formal/README.md) for invariants and evidence limits.

## Check authority and catalog agreement

Run each relevant check:

```shell
uv run --project implementations/python --frozen python tools/check_authority_boundary.py
uv run --project implementations/python --frozen python tools/check_sdl_catalog_parity.py
uv run --project implementations/python --frozen python tools/check_schema_publication.py --base-rev origin/dev
```

`origin/dev` is the fetched integration revision used for comparison.
Use the base revision that applies to your change.
Exit `0` means that the selected structural checks passed.
A nonzero result names a mismatch or an unavailable prerequisite.
Read the diagnostic before you edit either authority or implementation.

The authority check compares roots and registered artifact families.
The catalog check compares SDL prose tables, published schemas, and reference registries.
The publication check compares the schema inventory and compatibility with the base revision.
None of these checks proves deployed backend behavior.

## Compare generated schemas

Run the read-only comparison:

```shell
uv run --project implementations/python --frozen python tools/check_generated_schemas.py
```

The checker calls `raes_schemas.schema_bundle()` through the existing writer.
It generates into a temporary directory and compares the complete file set and exact bytes.
Exit `0` means the generated bundle equals the published schemas.
It does not prove semantic conformance beyond that equality.

If the command reports drift, compare the published schema and its owning model or annotation.
Keep published authority under the existing contract review rules.
Do not overwrite published files to clear a mismatch.
The generator's command-line entry point writes into `contracts/schemas/`.
It is not the read-only check above.

## Check fixture behavior

Select only the tests for the fixture family you changed.
For example, check the raw YAML corpus with:

```shell
uv run --project implementations/python --frozen pytest implementations/python/tests/test_sdl_source_format.py::test_normative_source_profile_fixture_corpus -q
```

This case checks acceptance, rejection, and explicit migration of checked-in YAML.
JSON Schema checks normalized objects after source decoding.
It cannot check YAML duplicate keys, directives, tags, or alias limits.

For JSON contract fixtures, keep derived seals separate from the literal payload.
Use the owning corpus loader and
`raes_contracts.contract_seals.seal_contract_fixture` where the test requires it.
Leave invalid fixtures unchanged.
A structurally valid fixture can still fail contextual admission.

## Check prose and rendered pages

Run the existing writing check on explicit changed paths:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -s docs-prose -- specs/README.md contracts/README.md
```

Replace the two paths with the maintained prose you changed.
Follow the [style guide](../explain/reference/documentation-style-guide.md) for meaning and STE review.
Examine repository pages in a local Markdown view.
Check headings, links, retained fragments, diagram alternatives, and keyboard focus.
Use the existing Sphinx/MyST build for public pages.
Full documentation, proof, integration, fuzz, and completion suites run in CI/CD.

Keep the revision, commands, results, corrections, and remaining limits in the PR.
One successful check does not establish the stronger claims in a formal specification.
