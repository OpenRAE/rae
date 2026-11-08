# API and command reference: architecture preflight

Issue #1935 is the contract for this docs change. It has no formal requirement.
Inspection baseline: `315e5d50ea55c7a209b22aac972cd5ba2bdbca77`, branch
`1935-api-command-reference`. This explanation gives design boundaries, not an
implementation plan. It does not show that the issue is complete.

## Decision and authority

Keep the supported Python interfaces and the existing Sphinx/MyST build.
Edit reference pages and source docstrings. Edit existing generator prose where needed.
Do not change program behavior to make documentation claims true.
No new ADR, architecture-model entry, schema, or documentation service is needed.
The existing boundaries in ADR-009, ADR-036, ADR-104, ADR-115, and ADR-116 apply.

The source checkout, installed distribution, and published release are distinct
identities. Record the actual source commit and installed package version with
the reference review. Local metadata reports `raes` 10.2.0 and Sphinx 9.1.0.
That result does not prove that this branch is the published release.
`docs/public/conf.py` derives its release label from distribution metadata.
Its repository source links currently select `main`. Check their destination
against the documented revision rather than treating the label as evidence.

The [style guide](../explain/reference/documentation-style-guide.md) owns page
purpose, STE review, protected text, source evidence, and rendered checks.
Code establishes observed usage. `specs/` and `contracts/` establish required
meaning. Report and resolve conflicts rather than changing either authority
through documentation. Even a model-description edit can affect generated
schemas. Keep published schema bytes stable under this issue.

## Coverage and support boundary

Build the coverage comparison from source. Do not derive it from existing pages.
For Python, examine packaged modules and exports. Check lazy export maps,
supported submodule imports, and relevant tests too. Start with
`implementations/python/pyproject.toml` and the package facades under
`implementations/python/packages/`. Include `raes`, `raes_processor`,
`raes_contracts`, `raes_runtime`, backend protocols, and conformance surfaces
when their release support evidence applies. Installed code, a public-looking
name, or an `__all__` entry alone does not establish released support.

Compare command registration and recursive help from `raes_cli/main.py` with
each command parser. Include global options, nested groups, aliases, defaults,
required arguments, and parser refusal behavior. The console entry points are
`raes_cli.entrypoint:main` and `raes_mcp.server:main`. Account for `raes-mcp` and
its registered tool surface in the coverage decision. Do not mistake Python
callback signatures for CLI syntax, or MCP tools for CLI subcommands.

For supported HTTP interfaces, start with `create_control_plane_app` and its
route families. Compare request and response models, authority declarations,
OpenAPI, and route tests. Include middleware admission and errors.
OpenAPI alone does not describe all refusal behavior or release support.

Keep one review table in the delivery PR: source identity and revision, support
evidence, reference destination, and missing, obsolete, or corrected status.
Give a source-backed reason for each internal or unsupported exclusion.
Every supported entry needs reference coverage even when its comment is absent.
Every generated public entry needs useful text or an explicit omission reason.
An omission reason cannot excuse a missing supported interface.

For each entry, give accepted inputs and constraints, defaults, returned values,
errors, side effects, and applicable version/profile limits. Give exit codes
and output streams for commands, and status codes and headers for HTTP.
Link task instructions instead of embedding tutorials. Keep exact identifiers
searchable and distinguish canonical entries from re-export aliases.

Observed gaps make this comparison necessary:

- `docs/public/api/cli.rst` has no runtime section. Source registration and
  `raes --help` include `runtime`; `runtime store --help` lists `check`, `backup`,
  and `restore`.
- `raes` and `raes_runtime` use lazy exports. The runtime facade specifically
  avoids backend and state-owner initialization during package import.
- Autodoc defaults omit undocumented members, while some pages override that
  choice. Neither setting proves coverage or provides useful descriptions.
- `docs/public/conf.py` names `_templates`, but that directory is absent at
  this revision. Reuse the active autodoc/Napoleon/autosummary configuration;
  do not assume an existing custom API template or add a new generator.

## Cross-cutting layers and canonical owners

Paths below the Python package root are relative to
`implementations/python/packages/`.
Unqualified `control_plane*` paths are in `raes_runtime/`.

| Layer | Existing owner and required treatment |
| --- | --- |
| SDL input and validation | `raes/parser.py` and its source-loading helpers own parsing, import trust, and limits. `raes/validator/` owns semantic checks. Keep bytes-only parsing, path-aware loading, migration policy, and registry acquisition distinct. Do not imply that editor or offline calls fetch imports. |
| Contracts and DTOs | `contracts/schemas/` is the normative schema authority. `raes_contracts/contracts/`, its corpus loader, and existing validators provide typed bindings. Link these owners for field details. Do not create reference-only schemas, duplicate validation, or copy a DTO into an adapter. |
| Configuration shapes | `raes_runtime/control_plane_configuration.py` owns typed options and defaults. It also checks dispatcher shape and refused service combinations. `control_plane_profiles.py` owns profile capabilities. `control_plane_security.py` checks exact boolean/integer types and principal bindings. Examples must pass these checks. A string such as `"false"` is not a boolean. |
| Authentication and authorization | `control_plane_api/_auth.py` owns route authority and transport admission. P2 admits administrative service identities, not participant-limited credentials. Core policy still applies after transport admission. Keep strict defaults and empty built-in credential maps. Keep proxy-header trust disabled by default. Trusted proxy examples must explain how the proxy removes caller headers and supplies authenticated identity. |
| HTTP admission and exposure | `control_plane_api_guards.py` and `_install_request_guards` bound request bodies and seal the app. They also set no-store responses and redact errors. `control_plane_api/_offload.py` bounds call execution. Keep actual bounds, overload refusals, and admission order. Do not bypass these layers to extract docs. Do not claim ordinary FastAPI defaults. |
| Errors and diagnostics | `raes_contracts/errors.py`, `raes/_errors.py`, and `raes_contracts/diagnostics.py` own exception categories and portable diagnostics. `control_plane_api/_responses.py` maps runtime categories to fixed HTTP details. SDK exceptions, HTTP envelopes, operation diagnostics, and command failures are separate contracts. Do not invent a common envelope or hierarchy. |
| CLI results and logging | `raes_cli/_semantic_result.py` owns semantic command results and exit codes. Other command groups keep their own behavior. `raes_cli/entrypoint.py` and `raes_contracts/operational_logging.py` own application logs and unexpected failures. Keep result stdout and operational stderr separate. Keep value-free logs and redacted failures. Do not apply semantic exit codes to every command. |
| MCP boundary | `raes_mcp/server.py` owns registration, argument-error handling, and unexpected-error redaction. Source comments can become tool descriptions. Keep literal argument names and error behavior intact; do not add another argument validator or log raw tool inputs. |
| Secrets and OS exposure | `raes_contracts/secret_references.py` owns logical secret-reference shapes. Use synthetic placeholders and existing injection mechanisms. Do not put real tokens in examples, process argv, rendered output, tracebacks, or captured PR evidence. Do not invent environment bindings or imply environment strings satisfy typed constructors. |
| Persistence and host limits | `control_plane_store*.py` owns store compatibility and scoped records. `control_plane_store_lease.py` owns exclusive access and worker limits. `control_plane_store_maintenance.py` owns backup and restore. Check actual environment-variable names and parsing there. Give single-worker and reload limits beside local-store entries. Give replacement behavior too. Never execute maintenance examples against a real store to capture output. |
| Backend and runtime ownership | ADR-036 separates authoring, processing, runtime, and neutral contracts. ADR-115 assigns concrete realization, credentials, allocation, and teardown to external backend distributions, such as `OpenRAE/lilrae`. Name the actual artifact and owner for each task. Stub or fixture success does not prove a live deployment or installed capability. |

Examples must pass the same validators as consumer inputs.
Use existing inert fixtures or temporary local data when behavior needs checking.
Do not provision a backend, start a worker/server, acquire live credentials, or
change caller state merely to enumerate an interface. Import-time extraction
must respect lazy initialization rather than forcing eager runtime startup.

## Build, search, and verification boundaries

The canonical surfaces are `docs/public/conf.py`, `docs/Makefile`,
`.readthedocs.yaml`, `tools/nox_support/test_lanes.py`, and
`.github/workflows/canonical-verification.yml`. Reuse `docs-prose`, the existing
Sphinx HTML build, and public source/output checks. Run targeted local checks;
CI owns full verification. Relevant existing tests include
`test_public_docs_policy.py`, `test_issue_954_docs_publication_boundary.py`,
`test_semantic_cli.py`, `test_runtime_control_plane_api.py`, and the
`test_issue_1678_*` boundary tests. Add no tests that merely restate prose.
This preflight changes no behavior, so mutation testing has no changed code to
exercise. Preserve the existing behavioral and CI mutation gates.

`tools/check_public_docs.py` checks sources, routes, search documents, redirects,
and published assets. `tools/public_docs_guard.py` limits document dependencies.
Keep public sources inside `docs/public/`; link internal evidence through the
established repository links. Do not include private design records, add
symlinks, widen module roots, or put the repository root on the Sphinx import
path. Keep generated output disposable and edit its maintained sources.

The redirect map is checked against an exact established map. A move cannot
rely on an arbitrary new redirect passing by default. Prefer stable routes and
heading anchors. Build and inspect signatures, alias targets, source links,
heading order, descriptive links, diagram alternatives, and search results for
exact symbol and command names. Inspect the rendered view of repository prose.
Check keyboard access if navigation changes. Vale does not prove meaning,
coverage, accessibility, or STE conformance. Source comments need direct review
and rendered inspection because `docs-prose` selects Markdown and RST only.

Record commands, source revisions, and corrections in the implementation PR.
Include exclusions, unverified behavior, and rendered findings. Keep legal text, pinned evidence,
accepted ADRs, and release-owned version/changelog files unchanged.

## Extensibility and non-goals

The extension point is the existing source-to-reference configuration:
qualified entry names, module/member selection, and links to canonical contracts.
Keep version, contract ID, profile, and backend compatibility explicit per entry.
Use existing generator settings rather than duplicating signatures or defaults
in a second machine-readable inventory. The PR comparison is review evidence,
not a new support registry or authority.

Issue #1803 owns the Go documentation build and instruction migration.
Issue #1804 owns publication at the combined cutover.
The [runtime repository boundary](issue-1891-runtime-repository-boundary.md)
and `implementations/architecture.json` describe future ownership, not released
Python exports. Do not publish planned Go APIs or invent a runtime repository
installation route before that boundary takes effect.

This issue does not change APIs, parsers, validation, schemas, controllers,
services, stores, security policy, or runtime workflows. It adds no search
service, custom documentation tool, external processing, hosting, or build
migration. Keep the one implementation PR focused on reference accuracy and
the maintained source prose that generates it.

## Preflight checks

The file-local repo policy check passed before and after the note was added.
The explicit-path `docs-prose` check, `tools/check_public_docs.py`, and
`git diff --check` passed. Both CLI help commands cited above returned exit 0.
Local HTML rendering confirmed heading order, table structure, and both local
link targets. Chrome could not start under the host restrictions, so visual
browser review is unverified. No navigation, controls, or diagrams changed.
The public reference build and full coverage comparison remain issue acceptance
work. This preflight does not claim those results.
