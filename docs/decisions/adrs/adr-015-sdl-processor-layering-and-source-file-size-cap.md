# ADR-015: SDL-Processor Layering and Source-File Size Cap

## Status

accepted

## Date

2026-05-10

## Context

Two structural problems in the `aces-sdl` Python tree, surfaced by the
modularity audit ([issue #3](https://github.com/autarchy-ai/aces/issues/3)):

1. **Circular dependency.** `aces_sdl/validator.py` imported
   `analyze_objective_window` and workflow helpers from
   `aces_processor.semantics.{objectives,workflow}`, while
   `aces_processor/{compiler,manager,planner,models}.py` imported runtime
   types and helpers from `aces_sdl.{instantiate,scenario,nodes,_base,
   infrastructure,entities,orchestration}`. Conceptually the SDL defines
   the language; the processor compiles and runs it. The dependency must
   be one-way (processor → SDL), but imports ran both directions.

2. **Oversized modules.** Fourteen non-test, non-generated source files
   under `implementations/python/packages/` exceeded 600 lines, four of
   them by 50–270%. These files attract further growth and mix multiple
   subdomains. Splitting them is tracked by the 14 child issues of #3,
   but the splits need an enforced cap to keep working: a file dropped
   below 600 lines that can silently grow back has not been split, just
   shuffled.

Neither is enforceable by reviewer attention alone. Both need structural
CI gates.

## Decision

### 1. SDL-processor layering

`aces_sdl` shall not import `aces_processor` — directly or via the
`aces_processor.semantics.*` re-export path.

The cycle is broken by relocating the two SDL-language modules
`objectives.py` and `workflow.py` from `aces_processor/semantics/` to
`aces_sdl/semantics/`. Their contents — objective-window analysis, the
workflow step-type contract and `branch_closure`, and a pure workflow
step-result validator — are SDL-language semantics; they import only the
standard library and have no import-time coupling to `aces_processor`;
`aces_sdl/validator.py` is their primary consumer. Each module moves as a
unit. In particular `validate_workflow_step_result` (which checks a
backend's *reported* execution state against the step-type contract) moves
with the rest of `workflow.py`: it is pure, so moving it does not violate
the layering rule, and keeping the module intact avoids fragmenting the
`aces.core.semantics.workflow` compatibility surface for what would be a
marginal conceptual gain. (A reasonable alternative — pulling that
validator into a processor-owned module — was considered and rejected on
that basis.)

`semantics/planner.py` stays at `aces_processor/semantics/planner.py`.
Although it also has stdlib-only imports, its content — resource-action
reconciliation between compiled resources and runtime snapshots,
dependency-graph construction over compiled-resource addresses,
topological ordering of processor-domain resources — operates on
*compiled resources*, a processor artifact, so it is processor-runtime
logic rather than SDL-language semantics. Moving it would put processor
logic into the SDL package solely to satisfy a "stdlib-only imports"
heuristic, which would not improve the layering.

The owning-package import paths `aces_processor.semantics.{objectives,
workflow}` are removed, not preserved with re-export shims. Per ADR-009
and ADR-010 the *stable* public surface is the `aces.*` namespace, not
the owning packages; the compatibility model is exactly one shim layer
(`aces.*`), and the `aces.core.semantics.{objectives,workflow}` wrappers
retarget to `aces_sdl.semantics.*` so that surface is unchanged.
`aces.core.semantics.planner` continues to target
`aces_processor.semantics.planner` (which did not move). Adding a second
shim layer at the owning-package level would introduce a pattern the
repository does not otherwise use and blur which location is canonical.

Enforcement: a `layering_rules` block in `tools/policy/adr_policy.yaml`
and a `_check_layering` checker in `tools/policy/repo_policy.py`. The
checker walks the AST of every changed `.py` file under each rule's
`scope_root` and emits `layering-rule-violation` for any `import` or
`from … import` of the forbidden top-level package or its submodules.

### 2. 1,000-line cap on non-test source files

No non-test, non-generated `.py` file under `implementations/python/packages/`
shall exceed 1,000 lines, except for paths listed in
`tools/policy/oversized_allowlist.yaml`.

The cap is a backstop. ADR-117 checks the module structure directly: import
cycles, private imports across modules and class ancestry. A file length does
not show whether a module is cohesive.

SonarCloud S104 allows the same files. The project uses its own quality
profile, which inherits the organization profile and sets the S104 maximum to
1001. SonarCloud counts the empty line after the final newline, so a
1,000-line file has 1,001 SonarCloud lines. (The cap was originally 600 and
then 500; see Amendments.)

The allowlist is the inverse of the goal: each entry is technical debt to
be drained. A split PR splits its file and removes the entry. The
modularity tracker closes when the allowlist is empty.

The fixed reference set is the set of paths over the cap when the current cap
was adopted. It is a *code constant*, `_ADR015_INITIAL_OVERSIZED_FILES` in
`tools/policy/repo_policy.py`, **not** config in `adr_policy.yaml`. If the
locked set were PR-editable config, one PR could edit the allowlist and the
locked set together and still satisfy "the allowlist only shrinks". In the
policy module, a new entry needs a diff to the checker code, and PR review
examines that diff as policy, not as data. The allowlist must be a subset of
that constant, so it cannot gain an entry. A file over the cap that is not in
the reference set must be split. A change of the cap re-baselines the constant
and the allowlist to the files over the new cap at that time. That change is a
code-constant diff, and PR review examines it the same way. The shrink-only
rule then continues from the new baseline. No file was over 1,000 lines when
that cap was adopted, so the constant and the allowlist are empty.
Enforcement:

- `_check_oversized` — emits `oversized-source-file` for an over-cap,
  non-allowlisted changed file.
- `_check_drain` — emits `oversized-allowlist-locked` for an allowlist
  entry not in `_ADR015_INITIAL_OVERSIZED_FILES` (the allowlist may only
  shrink).
- `_check_allowlist_entries_still_oversized` — emits
  `oversized-allowlist-stale-entry` for an allowlist entry (one of the
  initial set) that no longer resolves to a regular file over the cap. A
  split PR deletes the original file, so `git diff` never lists it as
  "changed"; without this config-wide check a forgotten drain would leave
  the path permanently exempt and free to grow back. This is the
  structural gate that makes the drain step non-optional.

The `layering_rules` and `oversized_source_files` blocks are *required*
policy. An absent block surfaces as `policy-config-malformed`, not as a silent
opt-out, so a deleted block cannot disable a gate. Malformed config surfaces
the same way, not as a traceback. This covers these conditions:

- `adr_policy.yaml` does not parse or does not have a mapping root.
  (`evaluate_repo_policy` loads it through a guard before any checker runs.)
- The ADR-015 blocks have wrong types or empty required lists.
- The allowlist YAML does not parse or does not have a mapping root.

Path safety has a single chokepoint. `evaluate_repo_policy` checks that each
path in the PR's changed-file list resolves inside the repository. It drops
each path that escapes the root *before any checker reads a file*. Thus the
layering scan, the size cap, and the import-direction and compat-wrapper
checks all receive an already-validated list. The same check applies to the
allowlist file path (`oversized_source_files.allowlist_path`) and to each
allowlist entry that the drain check reads. An absolute path, a `..` segment,
or a symlink that resolves outside the tree surfaces as `policy-path-unsafe`,
and the gate never opens the target. (This is defense-in-depth for the in-repo
trust model below. It does not claim to withstand an adversarial author who
edits the policy itself.)

Test files under `implementations/python/tests/` and generated files
under `contracts/schemas/` are excluded from the cap — tests grow as a
function of the surface they cover, and generated files are not authored.

### Trust model

These gates catch unintentional regressions in normal source-code
contributions: a developer who accidentally types `import aces_processor`
in `aces_sdl/`, or one who pushes a 700-line file, or a split PR that
forgets to drain its allowlist entry. The policy code and its YAML config
are in the repository and are PR-mutable; PR review is responsible for
catching deliberate weakening of the policy itself. Defending against an
adversarial commit author who rewrites `repo_policy.py` is out of scope —
if that level of enforcement is ever required, the right answer is to move
the policy into immutable CI workflow code, not to harden in-repo code
defensively. That would be a separate ADR.

### Out of scope

- Splitting any of the 14 oversized files. Each has its own child issue
  under #3.
- Behavioral changes. The cycle break and policy gates are pure
  refactoring + tooling; semantics, public dataclass shapes, and runtime
  algorithms are unchanged.

## Consequences

### Positive

- The dependency between `aces_sdl` and `aces_processor` is a DAG,
  enforced by CI.
- Each subsequent file split inherits the layering invariant for free.
- The cap creates a forcing function: a file that wants to grow past 1,000
  lines must be split.
- The allowlist is self-documenting debt; its size measures remaining
  modularity work.

### Negative

- A subsequent PR is needed to drain each allowlist entry.
- `docs/api/processor-semantics.rst` is rescoped to planner only; a new
  `docs/api/sdl-semantics.rst` documents the moved modules. Bookmarks to
  the processor-semantics page still resolve, to a smaller page.

### Risks

- A new top-level package introduced later (e.g. `aces_runtime`) could
  re-introduce a layering bug the current rule doesn't capture. Mitigation:
  each new package introduction should consider whether it needs its own
  `layering_rules` entry.
- A cap alone rewards splits that keep facades and private names. ADR-117
  checks the structure that such splits damage.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-07-12 | #561 | Lowered the non-test source-file cap from 600 to 500 lines to align with SonarCloud's S104 threshold, closing the 500–599 band where a file was repo-compliant but failed the Sonar quality gate at the `dev → main` integration PR (#545). Re-baselined `_ADR015_INITIAL_OVERSIZED_FILES` and `tools/policy/oversized_allowlist.yaml` to the files over the 500-line cap as of this amendment; the shrink-only rule continues from that new baseline. |
| 2026-10-30 | #1734 | Raised the cap from 500 to 1,000 lines as a backstop to the structural checks of ADR-117. Set the SonarCloud S104 maximum to 1001 in a project profile that inherits the organization profile. Re-baselined `_ADR015_INITIAL_OVERSIZED_FILES` to the files over 1,000 lines: none. |
