# First scenario learning path preflight

Issue: #1933. Requirement: none. Date: 2026-11-07.
Inspected revision: `a89dd71a6edce5351a3f0d72bdc8beed1ab0867e`.
The supplied issue is the delivery contract. This note gives design boundaries;
it does not rewrite the exercise or give an implementation plan.

## Release boundary

Keep one local learning path through `docs/public/quickstart.md` and
`docs/public/tutorials/first-scenario.md`. Both pages serve a tutorial purpose.
Quickstart owns setup and the first validation result. The next page
uses the same environment and reader-owned file. It teaches one observable
scenario change, deliberate invalid input, recovery, and the next learning step.
Show successful validation before checkout paths or contributor tools.

Use `docs/public/_static/examples/first-scenario.sdl.yaml` as the existing small
scenario. The richer `minimal-validated-scenario` library template serves another
purpose. Do not replace the first exercise with that template or a new scenario.
Keep the checked-in literal intact unless execution proves a correction necessary.
Perform teaching changes in the reader's copy, with a result that exposes the change.
A changed name alone does not teach a change to a scenario declaration.

The local release tag `v11.0.2` resolves to
`036c832d5693c5f6f9351d3a8e1264e5fcfc43e3`.
Compared with the inspected revision, package code, package metadata, contracts,
specifications, examples, and the two target pages have no differences.
This comparison does not verify an artifact on a package index or the deployed site.
Check the supported artifact and its source revision again before editing.
Record an exact tested version; an unpinned install alone cannot identify evidence.

At this revision, `implementations/python/pyproject.toml` requires
`>=3.14,<3.15` and installs `raes = raes_cli.entrypoint:main` without dev extras.
The tutorial's checkout and `uv` requirement is therefore avoidable in the design.
Clean installation must still prove command availability and packaged data.
Do not claim a new Python, operating-system, or CPU support matrix from one host.
Name the tested shell: POSIX heredocs do not work in PowerShell.
Do not weaken execution policy to make a Windows activation command work.

ADRs 009/019 retain normative authority, 014 owns verification, 021 bounds
evidence claims, 115 separates backend ownership, and 116 owns error handling.
The [documentation style guide](../explain/reference/documentation-style-guide.md)
and the [entry-path preflight](issue-1932-documentation-entry-paths-preflight.md)
already cover page purpose and navigation. No new ADR or abstraction is needed.
Issues #1803 and #1804 retain Go instruction migration and publication ownership.

## Canonical flow and checks

The reader copies public YAML into a local file, then uses the installed API or CLI.
The parser constructs typed declarations and runs semantic validation.
The selected presentation reports success or a bounded diagnostic.
No backend, control-plane server, or runtime store participates in this flow.
Separately, maintained docs pass the existing source guards and Sphinx build.
Only the existing docs workflow can publish checked HTML.

| Layer | Existing owner and required treatment |
| --- | --- |
| Installation and packaged authority | `implementations/python/pyproject.toml`, `hatch_build.py`, and `raes_contracts.corpus` own the installed command and bundled contracts. Use the released distribution. Do not compensate for missing wheel data with checkout imports, an editable install, `PYTHONPATH`, or manual schema downloads. |
| Source admission and resource bounds | `raes/parser.py`, `_yaml_loader.py`, `_source_validation.py`, and `_source_profile.py` own UTF-8, bounded YAML 1.2 loading, key checks, tags, aliases, and migration policy. Keep strict defaults. Do not substitute `yaml.safe_load`, bypass limits, or accept legacy syntax to make a teaching example pass. |
| Typed and semantic validation | `raes/scenario.py`, its section models, and `raes/validator/` own shape and meaning. Use public `parse_sdl_file` or `raes semantic validate`; do not write tutorial validators or duplicate schemas. `_nodes_infra_network.py` already checks infrastructure references. An invalid reference can teach rejection without adding a validation rule. |
| Errors and observability | `raes/_errors.py`, `raes_contracts.errors`, `operational_logging.run_application`, and `raes_cli/_semantic_result.py` own diagnostics, sanitization, and exit status. Preserve separate stdout and stderr. Do not add an exception hierarchy, logger, wrapper envelope, or traceback disclosure for the exercise. |
| Auth, secrets, and configuration | The import-free first scenario needs no principal, credential, secret reference, environment binding, or runtime configuration. Keep it that way. No account setup, token in argv or a URL, environment dump, private data, or credential-file access. Existing private-key and Gitleaks hooks remain in force. |
| Host effects and persistence | Only environment installation and the reader's local files are needed. Use explicit paths and shell-appropriate quoting. Avoid overwriting an input through shell redirection. No daemon, listener, elevated privilege, runtime store, lockfile, registry cache, remote module, or backend discovery is part of the first result. |
| Catalogue shape | `examples/library/catalog.yaml`, `tools/check_example_library.py`, and `tools/example_library_checks.py` own IDs, paths, contracts, validation status, users, limits, and template checks. Preserve these fields and meanings. Extend existing entries when needed; do not add a second catalogue or support registry. |
| Published source boundary | `tools/check_public_docs.py`, `public_docs_markup.py`, and `public_docs_guard.py` contain includes, dependencies, downloads, links, and generated routes within `docs/public/`. Keep literal includes there. Link to repository-only examples with absolute repository URLs; do not include or copy their trees into public sources. |
| Build and navigation shapes | `docs/public/conf.py`, its public toctree and `redirects.json`, `tools/nox_support/config.py`, and `_run_docs` in `test_lanes.py` own the Sphinx/MyST/Furo build. Keep page URLs and useful heading anchors. A page redirect does not restore a removed fragment. No build migration or new configuration shape is needed. |
| Workflow and tool safety | Reuse `AGENTS.md`, `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/verification_plan.py`, and file-scoped policy checks. `docs-prose` uses safe repository paths and Vale argv separation. `tools/vale_tool.py` owns verified tool acquisition. Keep existing exception catalogs and safe `PolicyFailure` reporting. Do not invent a requirement UID for this requirement-free issue. |

The canonical path prefix in the parser rows is
`implementations/python/packages/`. The docs pipeline also passes through
`.vale.ini`, `styles/RAES/`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`,
`.github/workflows/docs.yml`, `.readthedocs.yaml`, and `docs/Makefile`.
Keep workflow permissions, main-only publication, and frozen dependencies.
No new service, upload, hosting, or external processing is authorized.

## Meaning and catalogue boundaries

Parsing, validation, formatting, compilation, planning, deployment, runtime
observations, and scientific conclusions are separate results.
`raes semantic parse` does not make a semantic validity claim.
`raes semantic validate` does not prove realizability or report all
semantic-validator advisories. `parse_sdl_file` retains them on `scenario.advisories`;
the catalogue gate rejects them for validated entries.
Preserve that stronger coverage; do not equate exit zero with no advisories.

`raes sdl format --check` can fail on valid, noncanonical text.
That is not the deliberate invalid-SDL exercise.
The semantic CLI has its own status taxonomy and sanitized diagnostics.
Use observed output from the selected command, not Python exception text or
another CLI's exit codes. Do not expose raw values to make an error more detailed.
The formatter and file-backed parser can follow imports; the first file has none.
The semantic CLI's read-only operations must not be described as import acquisition.

`examples/README.md` is the catalogue entry, not another guided first exercise.
Each item needs a purpose, required support, validation status, limits, and a route
to its existing reference or explanation. Distinguish installed commands,
checkout tests, controlled fixture effects, and native backend execution.
The catalogue's `validation` strings are checked for shape, not executed by its gate.
Passing that gate alone does not meet the issue's command-execution criterion.

Review maintained prose across all six Markdown files in `examples/`, library
summaries, pattern instructions, YAML comments, and `docs/examples/revised-control.md`.
Do not assume a YAML extension excludes prose. Preserve scenario bodies and
literal commands unless a verified correction is necessary.
Detailed API facts and theory belong in existing API, SDL, backend, and explanation
owners. Link them instead of repeating normative tables in introductions.
Keep legal text, quotations, generated output, and
`docs/examples/mixed-control-demonstration/record.json` intact.
Record exact exclusions; historical evidence does not exempt surrounding prose.

RAES is owned by `OpenRAE/rae` and supplies language, portable processing,
contracts, runtime interfaces, and conformance fixtures.
`docs/public/backends.md` identifies `OpenRAE/lilrae` as a concrete backend owner.
Use each actual distribution's owner for native execution, credentials, and cleanup.
Do not imply a verified compatible backend version or execution result from a link.

## Extensibility and verification evidence

The seams are the existing small scenario, stable page URLs, public command
interfaces, and catalogue metadata. Keep release version, platform, shell, and
reader file path explicit in evidence rather than hidden in checkout assumptions.
Future examples use the catalogue's existing contract and support distinctions.
Future releases repeat the same exercise against their artifacts; they do not
require a product-name switch, new workflow engine, or generated route registry.

Reuse `test_public_docs_policy.py`, `test_issue_938_landing_page.py`,
`test_public_guide_examples.py`, `test_semantic_cli.py`, and `test_sdl_format_cli.py`.
They live under `implementations/python/tests/`.
The current tutorial test assumes a heading, `uv` commands, repository-relative
paths, and format output. The quickstart test assumes a POSIX Python heredoc.
Change obsolete presentation assumptions without deleting execution assertions.
Keep `PUBLIC_DOCS_EXAMPLE_TESTS` aligned with any renamed test selectors.
Preserve `test_scenarios.py`, catalogue metadata tests, and invalid fixtures.

Checkout tests cannot prove released installation. Delivery needs a separate
clean temporary first-use run outside the checkout, without inherited module
paths, system site packages, caches, or undeclared tools.
Record the tested OS/architecture, shell, Python and artifact versions, source
revision, exact commands, exit codes, stdout, stderr, and meaningful results.
Follow only the published steps, including the change and error recovery.
If artifacts or a platform cannot be checked, report the gap; do not substitute
a locally built wheel or call a checkout run clean release evidence.
Label illustrative output separately from observed output.
An author or agent walkthrough is not first-time-user research.
Record confusing assumptions and fixes without claiming independent participants.

Use existing changed-path writing checks and targeted tests locally.
Full verification, integration, fuzz, and completion suites belong in CI/CD.
Review STE meaning and page purpose manually; Vale does not prove either.
Vale selects Markdown and reStructuredText, so examine other maintained prose
directly. No custom documentation tool is needed.
Render public pages with the existing build and repository prose in a Markdown view.
Check heading order, descriptive links, text alternatives, and changed keyboard
navigation. Meaning must not depend on color.
Check repository links and fragments explicitly: Sphinx skips this repository's
GitHub URLs. Record sources, corrections, exclusions, and results in the delivery PR.

## Non-goals

No product behavior, schema, validation rule, error contract, logging, storage,
auth, or backend changes. No new controller, DTO, service, repository class,
test harness, dependency, analyzer, or personal-skill copy.
No Go instructions, build migration, publication, release metadata edits,
changelog edits, new hosting, or private data.
Resolve a code-versus-normative conflict with its owner; prose cannot redefine it.
One implementation PR delivers #1933 through the existing requirement-free route.
