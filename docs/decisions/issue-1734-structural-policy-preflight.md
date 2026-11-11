# Issue #1734: structural policy preflight

Inspection: 2026-10-29, `dea4d1bed2cc4a5919627e9682bcf22b62b85a12`.
Scope: issue #1734, chunk 00, governed by **MOD-001**. This note records design
guardrails, not an implementation plan or completed acceptance. The supplied
requirement still states 600 lines; accepted ADR-015 and policy currently say
500, while this issue requests 1,000. Treat that as an explicit policy evolution,
preserve the one-way SDL/processor invariant, and reconcile requirement wording
through the existing governance workflow before claiming MOD-001 satisfaction.
The shared exception/logging change associated with #1678 is present in history
as `e6c1f008` / PR #1716, including ADR-116. Baselines must describe the actual
implementation base after that change, not the issue's older `0ab5bf57` counts.

## Ownership and canonical incumbents

Structural analysis belongs in `tools/policy/`, integrated through
`evaluate_repo_policy()` in `tools/policy/repo_policy.py` and the existing
`tools/check_repo_policy.py` command. Keep `PolicyFailure`, its stable rule IDs,
repo-relative paths, `render()` and `failures_to_json()` as the reporting
contract. An expected structural finding is a failure record, not an exception.
No runtime controller, service, repository, public DTO or published schema is
needed. Keep focused policy helpers separate from RAES package behavior.

The repository surfaces that consume or constrain this change are:

| Surface | Reuse and boundary |
| --- | --- |
| Policy configuration | `tools/policy/adr_policy.yaml`, its guarded loader and block validators, and `tools/policy/conftest/repo_policy.rego`. Keep the existing Rego authority checks; do not move Python source analysis into a second policy engine. |
| Package ownership | ADR-036 and `module_boundaries`, including package coverage, allowed imports, forbidden prefixes, public prefixes and backend protocol annotations. These remain enforced without a new debt exemption. |
| Size debt | ADR-015, `_ADR015_INITIAL_OVERSIZED_FILES`, `oversized_allowlist.yaml`, `_check_drain()` and `_check_oversized_debt_consistency()`. Preserve locked membership and mandatory stale-entry removal. The current size allowlist is empty. |
| Command graph | `Makefile`, `noxfile.py`, `tools/nox_support/policy_lanes.py`, `runner.py`, `graph.py`, `.pre-commit-config.yaml` and test selection in `tools/verification_plan.py`. One policy implementation serves these callers. |
| Required CI | `.github/workflows/ci.yml` and `canonical-verification.yml`: the required static lane invokes policy with a verified base revision. Advisory fast feedback alone is insufficient. Preserve exact-commit binding and failure aggregation. |
| Tool supply chain | `implementations/tooling/python/{pyproject.toml,uv.lock}`, `tools/python_closure_profiles.py`, `tools/tooling_artifact_policy_python*.py`, `tools/generate_python_closures*.py`, the development profiles and generated closure projections. |
| Governance and Sonar | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/requirement_context.py`, ADR-059, `tools/check_adr_immutability.py`, both ADR indexes, `sonar-project.properties` and the project's external SonarCloud quality profile. |
| Evidence | Existing temporary-repository fixtures and policy/CLI tests in `implementations/python/tests/test_repo_policy_tools.py`, tooling-lock tests in `test_tooling_artifact_policy.py`, and nox/shard/fast-feedback wiring tests. |

## Structural meaning and ratchets

- Use import-linter's `acyclic_siblings` for sibling-module/package cycles,
  including function-local imports. Cover every first-party package under
  `implementations/python/packages/`, not only the four review samples. Declare
  ancestor/depth coverage explicitly: `depth = 1` checks children and
  grandchildren, not every nested sibling group. New deeper packages must not
  silently escape the check. Make the type-checking choice explicit; exclude
  `TYPE_CHECKING` imports for runtime-cycle analysis as in the issue's review.
  That choice must not disable the existing ADR-036 rules or private-import
  checks. Conditional and function-local runtime imports remain graph edges.
- Use `layers` where a dependency order exists and `forbidden` for specific
  disallowed directions between packages/subpackages. Derive or verify their
  agreement with the canonical `module_boundaries` data rather than maintaining
  an independent ownership matrix. In particular, `raes` and `raes_contracts`
  currently permit imports in both directions; declaring the entire repository
  a strict layered DAG would change policy. Existing direction debt may be
  recorded only where the new contracts require it; do not weaken ADR-036.
  Distinguish direct-import ownership rules from import-linter's transitive
  dependency rules. Public-prefix restrictions still need the incumbent checks.
- Private imports are a module boundary concern even within one top-level
  package. The current `_check_module_imports()` skips same-package imports and
  `_imported_names()` skips relative imports, so neither alone supplies this
  check. Resolve absolute and relative source-module identities, including
  `__init__.py`, and inspect original imported names/private path components
  before aliases. A leading underscore remains private when renamed locally.
  Specify Python language exceptions explicitly: `from __future__ import ...`
  is a language directive, not a private-interface violation. Distinguish
  documented special names from single-underscore implementation names; an
  export in `__all__` alone must not bless a private name. Inspect function bodies
  and type-checking guards. Limit scanned importers to the package source root;
  inspecting a dependency's import spelling does not require reading its code.
  Own-module names are not cross-module imports. A module-import check is not
  a general checker of attribute access or dynamically constructed imports.
- Interpret "more than seven ancestors" as the number of distinct transitive
  repository-defined ancestor classes, excluding the class itself, builtins
  and dependency-defined classes. It is neither direct-base count nor longest
  inheritance path. Prefer a focused static policy check over adding general
  pylint solely for this rule. Resolve qualified identities, relative imports,
  aliases, re-exports, same-name classes and subscripted generic bases; visit a
  diamond ancestor once and bound traversal of malformed cyclic definitions.
  If pylint is chosen, its default ancestor count is insufficient: filter by
  repository ownership, rather than an ever-growing list of external classes.
  The #1678 exception-hierarchy test is useful precedent but its simple-name
  heuristic is not a production ancestor resolver. Do not import/instantiate
  package classes or inspect live MROs. Unresolvable repository bases must not
  silently count as zero; report a bounded analysis failure. Do not reject
  ordinary external bases or count PyYAML's ancestors against `SafeLoader`.

For every check, baseline **finding identities**, not aggregate counts,
files, line numbers or whole-class waivers. A fixed violation cannot buy room
for a different violation. An over-limit class must also retain its observed
ancestor bound so existing debt cannot deepen under the same identity; decreases
must lower that bound in the same PR. New classes must meet seven. If repeated
private-import sites share an identity, retain an occurrence ceiling so a new
site cannot borrow the old exemption. Removal of debt requires entry removal.

Record baseline provenance as an exact base SHA plus analysis version/options.
Every initial exemption must be reproducible on that base. Later baselines
must be subsets of the accepted base baseline, and every retained exemption
must still describe a current finding. Preserve this across deletions, renames,
reintroductions and base synchronization. Reuse existing git/base plumbing;
do not fetch a moving branch or derive the base from candidate baseline data.
For initial adoption, absence of a baseline on the base is not permission to
take arbitrary findings from the candidate. No wildcard debt, automatic
re-baselining, or restoration of previously drained entries. Review remains
responsible for deliberate edits to the in-repository policy itself, as ADR-015
already states; this is not a tamper-proof enforcement system.

The base revision currently reaches `check_repo_policy.py` only to select
changed paths; `evaluate_repo_policy()` receives no base context. The ratchet
needs that trusted revision at its comparison boundary. Keep policy, source
graph and baseline from the same snapshot, including staged versus working-tree
invocations. A missing base or changed analyzer/options must not silently reset
debt; use an explicit, reviewed compatibility or adoption rule. Historical source
is parser input, never executable code or an authority for subprocess commands.

Import-linter's `ignore_imports` plus `unmatched_ignore_imports_alerting = error`
can record exact legacy edges and force removal when an import disappears.
They do **not** alone prove the required ratchet: a still-present ignored import
may cease to be cycle debt, and suppressing it can hide a new cycle that uses
that legacy edge. Retain the unfiltered graph when validating baseline currency
and new cyclic dependencies, using the same import-linter/Grimp graph rather
than a second import parser/cycle engine. Require a regression where a new
return path closes a cycle through an ignored edge. A passing ignored graph or
an unchanged minimum-edge-removal count is insufficient evidence.
Keep finding order deterministic and analysis bounded; do not enumerate every
possible simple cycle to describe debt.

Full policy must scan the complete source graph and reconcile debt even when
the changed list is empty, deletion-only, documentation-only or baseline-only.
`evaluate_repo_policy()` currently has an early empty-change return; new global
checks cannot live solely below it. File-local feedback can remain cheaper,
but must not be represented as the global ratchet. Do not confuse the existing
`structural_runner` seam (the Rego runner) with the new Python graph checks.

## Security, shape checks and process boundaries

| Layer touched | Required behavior |
| --- | --- |
| Filesystem and source parsing | Reuse `safe_repo_path`, `_read_repository_text()` and `_parse_python_source()`. Check containment for every discovered source/config/baseline path, not only changed paths: the incumbent full-tree enumeration does not itself enforce that. Refuse escaping symlinks/traversal before reading or handing roots to another analyzer. Analyze repository source statically; never execute source from the candidate or historical base to collect findings. |
| Policy and baseline input shapes | Extend the guarded policy/block validation with required nonempty scope, supported versions/options, positive limits, exact unique finding identities and bounded collections. Missing, unreadable, malformed, unknown-version or inconsistent data fails closed. Reuse `load_yaml` and its parser-failure handling; if JSON is selected, reuse `load_bounded_json_object` for bounds and duplicate-key rejection. Do not introduce a published schema or duplicate the tooling schemas. |
| Tool environment and host processes | Pin import-linter and its closure in the tooling project, with Python 3.14 compatibility. Run through the existing frozen tooling environment with fixed argv, repository cwd and explicit config/source roots. `frozen_tool_command()` currently rejects unlisted executables: deliberately admit `lint-imports` if using its console command, or use the reviewed interpreter. `_run_project_python()` uses the application environment, and the CLI's current relaunch checks only for `filelock`; neither proves the new analyzer is importable. Preserve closure-profile/context validation and the `closure_environment` shape at acquisition boundaries; do not add arbitrary env maps, shell interpolation, ambient module-path discovery or a separate tool installer. Tool absence, timeout or parser failure is an operational failure, never an empty finding set. |
| Lock admission and projections | A `pyproject.toml`/`uv.lock` edit alone is insufficient: direct pins, profile/lock hashes, generated projections and wheel availability are validated by `check_tooling_artifact_policy.py`. Regenerate affected projections with the incumbent generator; keep runtime dependency declarations unchanged. Policy execution must not install packages or require credentials/network access to analyze imports. |
| Exceptions and error envelopes | Reuse `raes_contracts.errors.InvalidInputError` for invalid external/config data and `OperationalError` for an unavailable/failed analyzer, translated once at the owning boundary. Preserve `check_repo_policy.py`'s text/JSON result contract and `run_application()`. Do not catch programming defects as valid findings, swallow cancellation, parse unstable colored terminal output as a schema, or leak a traceback into JSON stdout. |
| Logging and diagnostic output | ADR-116 and `docs/develop/exceptions-and-logging.md` apply to tooling too. Keep `SessionReporter` stage reporting and shared logging; configure no second logger. Identifiers/counts and useful source locations belong in bounded diagnostics; raw source, environment maps, command lines, credentials and subprocess dumps do not belong in logs. Existing policy exceptions are not a replacement for exact structural debt or a reason to turn failed/skipped analysis into success. |
| Authentication and external state | Local analysis has no application authentication, credential binding or runtime authorization surface. Do not involve SDL secret/config validators or runtime stores. Preserve CI checkout permissions and Sonar's existing secret-bearing job boundary; never pass tokens in argv or URLs. Changing the external S104 profile needs a SonarCloud administrator, not a new credential flow in policy. |

The existing OSV lane selects the application `uv.lock` via
`tools/nox_support/config.py::OSV_LOCKFILE_PATH`; it does not prove the new
tooling closure has been vulnerability-scanned. Reuse `tools/osv_scanner_tool.py`
and the established dependency-review process for that concern, rather than
equating exact pins with security review or adding a new scanning service.

New persistent state is only reviewed repository baseline/configuration data.
Analyzer caches are disposable, not authority; their presence or corruption
cannot change findings or let base/head graphs contaminate one another.
No runtime database, migration, evidence/audit schema or remote service is needed.

## Cap, governance and extension seams

The implementation must amend ADR-015 to 1,000 lines and preserve the source
scope/counting semantics and shrink-only debt rules. Its empty allowlist must
stay empty. Raising the cap does not authorize a new size-debt baseline.
Under ADR-059, editing accepted decision text also needs the in-band amendment
row and matching amendment entry/new canonical pin in `adr-index.yaml`; a cap
config edit or bare pin bump is insufficient. Use the incumbent pin checker.

SonarCloud S104's effective quality-profile threshold must permit the same
1,000-line boundary. Record administrator confirmation and the relevant project
analysis before claiming acceptance. A local scanner property, broader file
exclusion, new `NOSONAR` marker or disabled quality gate is not that change.
No external setting is changed by this preflight.

The extension seam is validated policy data: package roots derived from existing
ownership coverage, sibling ancestor/depth settings, directional contracts,
the seven-ancestor limit and versioned exact baseline records. Adding a package
must require coverage, not edits to several hard-coded sample-package lists.
Keep one finding identity/normalization definition shared by collection,
baseline comparison and reporting. Do not expose switches that disable required
checks or widen debt. Avoid a new plugin framework, graph service or schema DSL.

The eventual `.gc/plan-rules.md` change must require each plan to name the module
owning new code and the public interface used by other modules. Reuse the
existing plan workflow and requirement resolver. The current branch name has
no UID, so set `RAES_REQUIREMENT_UID=MOD-001` for requirement-aware checks;
do not skip governance or create a parallel plan validator.

## Verification boundaries and non-goals

Implementation evidence must exercise actual policy entry points, not only
mocked import-linter success: new/function-local/deep sibling cycles, the ignored
legacy-edge case, direction restrictions, relative/aliased private imports,
seven versus eight unique local ancestors, diamond/re-export/generic resolution,
external-only ancestors, worsening existing debt, new-for-fixed substitution,
stale/removal/reintroduction cases and unsafe/malformed inputs. Include no-change
and deletion-only invocation, language-directive exceptions, snapshot consistency,
clean/cache-independent results, unavailable tools in the actual entry-point
environments, and required CI wiring. Extend existing fixtures; retain old tests.
Use targeted local modules/cases; full, integration, fuzz and completion suites
remain CI-only. Verify that the package-source diff is empty.

No package edits, cycle repairs, interface migrations, inheritance refactoring,
runtime functionality changes or bulk file splits belong to chunk 00. Do not
manufacture facades/private aliases to satisfy metrics, equate a cohesive module
with a file length, or move checks into runtime validation. The cap is a backstop;
module ownership and public interfaces remain the design decision. This note
does not implement the checks, baseline, cap amendment or plan rule.

Official-source basis: import-linter's [acyclic siblings contract](https://import-linter.readthedocs.io/en/latest/contract_types/acyclic_siblings/)
defines generation depth; its [shared contract options](https://import-linter.readthedocs.io/en/stable/contract_types/)
define exact import ignores and unmatched-ignore errors; [layers](https://import-linter.readthedocs.io/en/stable/contract_types/layers/)
and [forbidden contracts](https://import-linter.readthedocs.io/en/stable/contract_types/forbidden/)
include dependency-direction semantics. Verify these against the version pinned
by implementation; the issue reviewed 2.15. These references support design,
not a claim that the new checks have been run here.
Python's [future-statement reference](https://docs.python.org/3/reference/simple_stmts.html#future-statements)
and [PEP 8 naming conventions](https://peps.python.org/pep-0008/#descriptive-naming-styles)
inform the language exceptions to the private-import rule.
