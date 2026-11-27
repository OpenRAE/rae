# ADR-117: Ratcheted Structural Checks for Package Modules

## Status

accepted

## Date

2026-10-30

## Classification

Classification: FM1
Required artifacts: ADR invariant list (Decision §3), unit tests (private imports, class ancestry, cyclic components, baselines, base comparison), integration tests (import-linter contracts in the tooling environment)
Waivers: none

The checks resolve references between modules and find import cycles.
They read repository source and change no RAES behavior.

## Context

ADR-015 caps each package source file and ADR-036 limits the imports between packages.
No other gate checks the module structure.
A review of `dev` for issue #1734 found three problems:

- Sibling modules import each other in cycles, also through imports inside functions.
- Modules import private names from other modules about 1,400 times. Ruff `PLC2701` ignores imports in the same top-level package, and the repository does not enable it.
- Three classes have 27 to 33 ancestors that the packages define.

The file cap caused splits that keep facades and private names only to meet the cap.
The Engineering Quality Refactor milestone removes this debt in 22 ordered changes.
Each change needs a gate that stops new debt while it removes old debt.

## Decision

### 1. Checks

The full repository policy check (`tools/check_repo_policy.py`) runs six structural checks.
The scope is every directory with `__init__.py` under `module_boundaries.package_coverage_roots`.

1. **Import structure.** import-linter runs the contracts in `tools/policy/import_contracts.toml`.
   Its grimp graph includes imports inside functions and conditional imports.
   It excludes imports under `TYPE_CHECKING`, because they do not run.
   - `raes-package-layers` is a `layers` contract that orders the packages.
     The gate verifies that the order agrees with `module_boundaries` (ADR-036).
     The order can forbid an import that ADR-036 allows only when ADR-036 also allows the reverse import.
     In that case, acyclicity requires one direction.
   - `raes-sibling-cycles` is an `acyclic_siblings` contract.
     It forbids cycles between the children of each package, at each depth.
   - No `forbidden` contract is used.
     ADR-036 forbidden prefixes are direct-import rules.
     A direct-only `forbidden` contract repeats the ADR-036 check.
     A transitive one fails on chains through permitted imports, for example `raes_mcp` → `raes_backend_stubs.stubs` → `raes_runtime.registry`.
2. **Private imports.** An import of a private name from another module is a finding.
   A name that starts with `_` is private.
   A special name of the form `__name__` is not private, as PEP 8 states.
   A private module, such as `a.b._c`, is private to its parent package `a.b`.
   A module in that package can import it.
   The check resolves relative imports and uses the original name before `as`.
   An entry in `__all__` does not make a private name public.
   Imports inside functions and under `TYPE_CHECKING` count.
3. **Class ancestry.** A class has at most `structural_checks.max_repository_ancestors` (7) ancestors from the packages.
   The count is the number of distinct package classes among all its bases.
   The check does not count external and builtin classes.
   A static resolver follows relative imports, aliases, re-exports, star imports, nested classes and subscripted bases.
4. **Private members.** An access to a private attribute of another object is a finding.
   The rule is Ruff `SLF001`. For example, `obj._x` is a finding, and `self._x`, `cls._x` and `super()._x` are not.
   The check runs Ruff from the locked tooling environment with only this rule selected.
   The identity of a finding is the module and the attribute name.
5. **Imports inside functions.** A first-party import inside a function is a finding.
   An import inside a module-level `__getattr__` (PEP 562) is not a finding.
   The identity of a finding is the importing module and the imported module.
6. **Hidden imports.** A first-party call of `importlib.import_module`, `__import__` or `importlib.util.find_spec` must name its target.
   The check resolves each name through the imports and simple assignments of its scope, also across first-party modules.
   A name can have more than one value, for example after a deletion. The check keeps each possible value.
   A string literal names a target. A relative target also needs a literal package or level.
   In a module-level `__getattr__`, a `for` loop over the literal `_LAZY_EXPORTS` mapping of that module names each key as a target.
   This applies only when the module only reads the mapping and no other module reaches it.
   Each target is an edge of the import graph. The layer, module-boundary and cycle checks apply to it as to a static import.
   The cycle contract applies to the graph with these edges, after the ignored imports are removed.
   `structural_checks.dynamic_import_allowlist` names each other call, with its reason.
   Any other call fails the gate. Any other use that passes on one of these callables or modules also fails the gate.
   This check has no baseline.

The checks in this ADR and in ADR-036 enforce these rules:

| Rule | Check |
| --- | --- |
| A package imports only lower packages. | `module_boundaries` (ADR-036) and `raes-package-layers` |
| A package uses another package only through its public prefixes. | `module_boundaries` `public_import_prefixes` (ADR-036) |
| A module does not import a private module or name of another module. | `module_boundaries` (ADR-036) and check 2 |
| Code does not access a private member of another object. | Check 4 |
| An import inside a function needs a reason other than a cycle. | Check 5 |
| A dynamic import does not hide an edge. | Check 6 |
| No import cycle exists between sibling modules or packages. | `raes-sibling-cycles` and `raes-package-layers` |

### 2. Baselines

Each check records the current findings as exact identities:

- Each import contract keeps its debt in `ignore_imports` as importer and imported module pairs.
  `unmatched_ignore_imports_alerting` is `error`.
  The cycle debt is the set of cycle breakers that grimp nominates and that are on a cycle.
- `tools/policy/structural_baseline.json` keeps the cyclic components of each package, each private import with its occurrence count, and each deep class with its ancestor count.
  It also keeps each private member access and each import inside a function, with its occurrence count.
  It also records the adoption commit, the analyzer versions and the analysis options.

### 3. Invariants

- **I1** Each current finding is in its baseline, with a count that is not more than the baseline count.
- **I2** Each baseline entry is a current finding with the same count. A change that removes debt removes or lowers the entry.
- **I3** Each ignored `raes-sibling-cycles` import is on a cycle in the graph without ignored imports.
- **I4** Each cyclic component of each package equals one baseline component. Thus a new cycle through an ignored import fails.
- **I5** Under `--base-rev`, each baseline is a subset of the baseline at the base revision, and no count increases. Without it, the comparison uses `HEAD`. CI supplies the base revision.
- **I6** When a baseline is absent at the base revision, the adoption commit bounds it as in I5. The adoption commit is the newest commit in the history of `HEAD` that adds the baseline and changes no file under the package roots.
  Without an adoption commit, the gate accepts the baseline only if no file under the package roots changed. Then I1 and I2 make it equal to the findings of the base revision.
- **I7** The analysis record in the baseline equals the installed analyzer versions and the configured options.
- **I8** A missing analyzer, unreadable or unsafe source, or an unresolved package base class fails the gate. It never gives an empty set of findings.
- **I9** `tools/policy/exceptions.yaml` cannot waive a structural finding.
- **I10** A counted family that the baseline at the base revision does not record is adopted when its total is not more than the total of the same check on the source at the base revision. A move gives a finding a new identity, so the bound uses totals.

The cycle debt counts the imports to remove, not every import in a cycle.
An import that keeps the current direction inside a component does not add to that count.
Thus normal work continues in large components, such as the 120-module component in `raes_runtime`.

### 4. Analysis boundary

The checks parse source.
They never import or run the analyzed code.
grimp builds the graph without a cache.
import-linter and grimp are pinned in the locked tooling environment, and `check_repo_policy.py` runs in that environment.

### 5. Trust model

The ADR-015 trust model applies.
The policy code, its configuration and the baselines are in the repository.
Pull request review defends against a deliberate change to them.

## Alternatives Considered

- **pylint `too-many-ancestors`.** It counts external ancestors, for example nine for a PyYAML `SafeLoader` subclass. A filter needs a list of external classes that grows. It adds a large dependency for one rule.
- **Live MRO inspection.** It gives exact counts, but the policy gate must import and run the package code.
- **A baseline of every import in a cycle.** It blocks new imports inside large components until the refactor breaks them.
- **`ignore_imports` alone.** A new cycle through an ignored import passes, and an ignored import can stay after it stops being on a cycle.
- **Aggregate counts.** A removed finding can make room for a new finding.
- **`forbidden` contracts.** Decision §1 gives the reason.

## Consequences

### Positive

- CI fails on a new import cycle, private import, private member access, import inside a function, hidden import or deep class.
- Debt can only decrease, and each refactor change shows its progress as baseline removals.
- One structural gate serves CI, `make policy` and the local nox sessions.

### Negative

- A moved module that is on a cycle, or a moved class with debt, gets a new identity. The move must remove the debt.
- A baseline edit is manual. The failure message names the exact entry.
- An analyzer upgrade needs an update of the analysis record.

### Risks

- The checks do not see an attribute access through `getattr` with a computed name.
- grimp can nominate an import that is not on a cycle. I3 keeps such imports out of the baseline.

## Amendments

| Date | Commit/PR | Summary |
| --- | --- | --- |
| 2026-10-30 | #1752 | I6: the adoption commit bounds a baseline that is absent at the base revision. Thus a dev to main promotion can pass. |
| 2026-10-31 | #1711 | Checks 4 to 6: private members, imports inside functions and hidden imports. Check 6 applies the layer and module-boundary rules to each dynamic edge. I10 adopts a new counted family. A table names the check for each structural rule. |
