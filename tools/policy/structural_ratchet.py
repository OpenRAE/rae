"""ADR-117 structural ratchet: compare structural findings with exact, shrink-only baselines.

Each current finding must be in its baseline (I1), each baseline entry must be a
current finding (I2), and each baseline must be a subset of the baseline at the
base revision (I5). Structural failures cannot be waived (I9).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from raes_contracts.errors import InvalidInputError

from .class_ancestry import AncestryResult, analyze_class_ancestry
from .common import PolicyFailure
from .import_cycles import Components, cyclic_components, is_cyclic_import, layer_disagreements, parse_layers
from .import_graph import CONTRACT_BROKEN, CONTRACT_UNMATCHED_IGNORES, ImportAnalysis, analyze_imports
from .private_imports import PrivateImport, collect_private_imports
from .source_index import SourceIndex, build_source_index
from .structural_baseline import (
    CYCLES_CONTRACT_ID,
    IMPORT_CONTRACTS_PATH,
    LAYERS_CONTRACT_ID,
    STRUCTURAL_BASELINE_PATH,
    BaseRevision,
    GitBaseRevision,
    ImportContracts,
    StructuralBaseline,
    parse_import_contracts,
    parse_structural_baseline,
    read_artifact,
)

RULE_CONFIG = "policy-config-malformed"
RULE_ANALYSIS_FAILED = "structural-analysis-failed"
RULE_SCOPE = "structural-scope-mismatch"
RULE_LAYERS_DISAGREE = "import-layers-disagree"
RULE_CONTRACT_BROKEN = "import-contract-broken"
RULE_CYCLE_GROWN = "import-cycle-component-grown"
RULE_PRIVATE_IMPORT = "private-import-new"
RULE_DEEP_CLASS = "class-ancestry-too-deep"
RULE_UNRESOLVED_BASE = "class-ancestry-unresolved"
RULE_STALE = "structural-baseline-stale"
RULE_GROWN = "structural-baseline-grown"
RULE_BOOTSTRAP = "structural-baseline-bootstrap"
RULE_ANALYSIS_RECORD = "structural-baseline-analysis"
_REPORT_LIMIT = 50

ImportAnalyzer = Callable[..., ImportAnalysis]


@dataclass(frozen=True)
class _Settings:
    max_ancestors: int
    coverage_roots: tuple[str, ...]
    allowed_imports: Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class _Inputs:
    settings: _Settings
    contracts: ImportContracts
    baseline: StructuralBaseline
    index: SourceIndex
    private_imports: Counter[PrivateImport]
    ancestry: AncestryResult


def evaluate_structural_ratchet(
    repo_root: Path,
    policy: dict[str, object],
    *,
    base_rev: str | None = None,
    import_analyzer: ImportAnalyzer = analyze_imports,
    base_revision: BaseRevision | None = None,
) -> list[PolicyFailure]:
    """Run the ADR-117 checks and return their failures.

    ``base_rev`` is the revision whose baselines bound the current ones; it
    defaults to ``HEAD``. ``base_revision`` replaces the Git reader of that
    revision. A missing analyzer or an unreadable base revision raises
    ``OperationalError``.
    """

    inputs = _read_inputs(repo_root, policy)
    if isinstance(inputs, list):
        return inputs
    analysis = _analyze_imports(repo_root, inputs, import_analyzer)
    if isinstance(analysis, list):
        return analysis
    base = base_revision or GitBaseRevision(repo_root, base_rev or "HEAD")
    return _bounded(_comparison_failures(inputs, analysis, base))


def _read_inputs(repo_root: Path, policy: dict[str, object]) -> _Inputs | list[PolicyFailure]:
    """Read the configuration and baselines and analyze the source; return failures that stop the checks."""

    try:
        settings = _settings(policy)
        contracts = parse_import_contracts(read_artifact(repo_root, IMPORT_CONTRACTS_PATH), IMPORT_CONTRACTS_PATH)
        baseline = parse_structural_baseline(
            read_artifact(repo_root, STRUCTURAL_BASELINE_PATH), STRUCTURAL_BASELINE_PATH
        )
    except InvalidInputError as exc:
        return [_failure(RULE_CONFIG, str(exc))]
    try:
        index = build_source_index(repo_root, settings.coverage_roots)
        inputs = _Inputs(
            settings, contracts, baseline, index, collect_private_imports(index), analyze_class_ancestry(index)
        )
    except InvalidInputError as exc:
        return [_failure(RULE_ANALYSIS_FAILED, str(exc))]
    return _scope_failures(index, contracts) or inputs


def _analyze_imports(
    repo_root: Path, inputs: _Inputs, import_analyzer: ImportAnalyzer
) -> ImportAnalysis | list[PolicyFailure]:
    try:
        return import_analyzer(
            [repo_root / root for root in inputs.settings.coverage_roots],
            repo_root / IMPORT_CONTRACTS_PATH,
            root_packages=inputs.contracts.root_packages,
            exclude_type_checking_imports=inputs.contracts.exclude_type_checking_imports,
        )
    except InvalidInputError as exc:
        return [_failure(RULE_ANALYSIS_FAILED, str(exc))]


def _comparison_failures(inputs: _Inputs, analysis: ImportAnalysis, base: BaseRevision) -> list[PolicyFailure]:
    contracts, baseline, settings = inputs.contracts, inputs.baseline, inputs.settings
    components = cyclic_components(analysis.imports, depth=contracts.cycles_depth)
    return [
        *_layer_failures(contracts, settings),
        *_module_set_failures(inputs.index, analysis),
        *_analysis_record_failures(baseline, analysis, contracts, settings),
        *_contract_failures(analysis),
        *_cycle_failures(contracts, analysis, components, baseline),
        *_private_import_failures(inputs.index, inputs.private_imports, baseline),
        *_ancestry_failures(inputs.index, inputs.ancestry, baseline, settings.max_ancestors),
        *_base_failures(base, contracts, baseline, settings.coverage_roots),
    ]


def _settings(policy: dict[str, object]) -> _Settings:
    roots, allowed = _module_boundaries(policy.get("module_boundaries"))
    return _Settings(
        max_ancestors=_ancestor_limit(policy.get("structural_checks")),
        coverage_roots=roots,
        allowed_imports=allowed,
    )


def _ancestor_limit(block: object) -> int:
    if not isinstance(block, dict) or set(block) != {"adr", "max_repository_ancestors"}:
        raise InvalidInputError(
            "structural_checks block (ADR-117) is required with exactly the keys adr and max_repository_ancestors"
        )
    limit = block["max_repository_ancestors"]
    if not isinstance(block["adr"], str) or not block["adr"]:
        raise InvalidInputError("structural_checks.adr must be a non-empty string")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise InvalidInputError("structural_checks.max_repository_ancestors must be a positive integer")
    return limit


def _module_boundaries(boundaries: object) -> tuple[tuple[str, ...], dict[str, frozenset[str]]]:
    """Return the package coverage roots and the allowed top-level imports of each module (ADR-036)."""

    roots = boundaries.get("package_coverage_roots") if isinstance(boundaries, dict) else None
    modules = boundaries.get("modules") if isinstance(boundaries, dict) else None
    if not isinstance(roots, list) or not roots or not all(isinstance(root, str) for root in roots):
        raise InvalidInputError("module_boundaries.package_coverage_roots must be a non-empty list of strings")
    if not isinstance(modules, list) or not all(isinstance(module, dict) for module in modules):
        raise InvalidInputError("module_boundaries.modules must be a list of mappings")
    allowed = {
        str(module.get("id")): frozenset(str(name) for name in module.get("allowed_top_level_imports") or ())
        for module in modules
    }
    return tuple(roots), allowed


def _scope_failures(index: SourceIndex, contracts: ImportContracts) -> list[PolicyFailure]:
    packages = set(index.root_packages)
    failures: list[PolicyFailure] = []
    for label, declared in (("root_packages", contracts.root_packages), ("ancestors", contracts.cycles_ancestors)):
        if set(declared) != packages:
            failures.append(
                _failure(
                    RULE_SCOPE,
                    f"{label} must name every package of the module_boundaries coverage and no other: "
                    f"missing {sorted(packages - set(declared))}, extra {sorted(set(declared) - packages)}",
                    IMPORT_CONTRACTS_PATH,
                )
            )
    if index.max_package_depth > contracts.cycles_depth:
        failures.append(
            _failure(
                RULE_SCOPE,
                f"depth {contracts.cycles_depth} does not reach the deepest package (depth {index.max_package_depth}); "
                "raise depth so that every package is checked for cycles",
                IMPORT_CONTRACTS_PATH,
            )
        )
    return failures


def _layer_failures(contracts: ImportContracts, settings: _Settings) -> list[PolicyFailure]:
    try:
        layers = parse_layers(contracts.layers)
    except InvalidInputError as exc:
        return [_failure(RULE_CONFIG, f"{IMPORT_CONTRACTS_PATH}: {exc}", IMPORT_CONTRACTS_PATH)]
    return [
        _failure(RULE_LAYERS_DISAGREE, message, IMPORT_CONTRACTS_PATH)
        for message in layer_disagreements(layers, settings.allowed_imports)
    ]


def _module_set_failures(index: SourceIndex, analysis: ImportAnalysis) -> list[PolicyFailure]:
    indexed = set(index.modules)
    if analysis.modules == indexed:
        return []
    return [
        _failure(
            RULE_SCOPE,
            "the import graph and the source index disagree on the modules: "
            f"only in the graph {sorted(analysis.modules - indexed)[:5]}, "
            f"only in the index {sorted(indexed - analysis.modules)[:5]}",
        )
    ]


def _analysis_record_failures(
    baseline: StructuralBaseline, analysis: ImportAnalysis, contracts: ImportContracts, settings: _Settings
) -> list[PolicyFailure]:
    expected = {
        "exclude_type_checking_imports": contracts.exclude_type_checking_imports,
        "grimp": analysis.versions.get("grimp"),
        "import-linter": analysis.versions.get("import-linter"),
        "max_repository_ancestors": settings.max_ancestors,
        "sibling_depth": contracts.cycles_depth,
    }
    return [
        _failure(
            RULE_ANALYSIS_RECORD,
            f"analysis.{key} is {baseline.analysis.get(key)!r} but the analysis uses {value!r}; confirm the findings "
            "with the new analysis and update the record",
            STRUCTURAL_BASELINE_PATH,
        )
        for key, value in sorted(expected.items())
        if baseline.analysis.get(key) != value
    ]


def _contract_failures(analysis: ImportAnalysis) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for result in analysis.contracts:
        details = "; ".join(result.details)
        if result.status == CONTRACT_BROKEN:
            failures.append(
                _failure(
                    RULE_CONTRACT_BROKEN,
                    f"import contract {result.contract_id} is broken: {details}. Remove the new import; "
                    "do not add it to ignore_imports",
                )
            )
        elif result.status == CONTRACT_UNMATCHED_IGNORES:
            failures.append(
                _failure(
                    RULE_STALE,
                    f"import contract {result.contract_id} ignores imports that no longer exist: {details}. "
                    "Remove them from ignore_imports",
                    IMPORT_CONTRACTS_PATH,
                )
            )
    return failures


def _cycle_failures(
    contracts: ImportContracts, analysis: ImportAnalysis, components: Components, baseline: StructuralBaseline
) -> list[PolicyFailure]:
    failures = [
        _failure(
            RULE_STALE,
            f"ignored import '{importer} -> {imported}' is no longer on an import cycle; remove it from "
            f"{CYCLES_CONTRACT_ID} ignore_imports",
            IMPORT_CONTRACTS_PATH,
        )
        for importer, imported in sorted(contracts.ignores[CYCLES_CONTRACT_ID])
        if (importer, imported) in analysis.imports and not is_cyclic_import((importer, imported), components)
    ]
    for package in sorted(set(components) | set(baseline.cycle_components)):
        current = components.get(package, ())
        recorded = baseline.cycle_components.get(package, ())
        grown = [component for component in current if not _within_any(component, recorded)]
        for component in grown:
            failures.append(
                _failure(
                    RULE_CYCLE_GROWN,
                    f"new import cycle between children of {package}: {list(component)}. Remove the import that "
                    "closes the cycle",
                )
            )
        if not grown and current != recorded:
            failures.append(
                _failure(
                    RULE_STALE,
                    f"cycle_components[{package!r}] must be {[list(component) for component in current]}; "
                    "the cycles became smaller",
                    STRUCTURAL_BASELINE_PATH,
                )
            )
    return failures


def _private_import_failures(
    index: SourceIndex, current: Counter[PrivateImport], baseline: StructuralBaseline
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for finding, count in sorted(current.items()):
        allowed = baseline.private_imports.get((finding.importer, finding.target), 0)
        if count > allowed:
            failures.append(
                _failure(
                    RULE_PRIVATE_IMPORT,
                    f"{finding.importer} imports private {finding.target} {count} time(s); the baseline allows "
                    f"{allowed}. Import a public interface instead",
                    index.modules[finding.importer].rel_path,
                )
            )
    for (importer, target), allowed in sorted(baseline.private_imports.items()):
        count = current.get(PrivateImport(importer, target), 0)
        if count < allowed:
            failures.append(
                _failure(
                    RULE_STALE,
                    f"private_imports[{importer!r}][{target!r}] is {allowed} but the code has {count}; "
                    + ("remove the entry" if count == 0 else f"lower it to {count}"),
                    STRUCTURAL_BASELINE_PATH,
                )
            )
    return failures


def _ancestry_failures(
    index: SourceIndex, ancestry: AncestryResult, baseline: StructuralBaseline, limit: int
) -> list[PolicyFailure]:
    failures = [
        _failure(
            RULE_UNRESOLVED_BASE,
            f"base {item.base!r} of class {item.class_id} cannot be resolved: {item.reason}",
            item.rel_path,
        )
        for item in ancestry.unresolved
    ]
    for class_id, count in sorted(ancestry.counts.items()):
        if count <= limit:
            continue
        allowed = baseline.deep_classes.get(class_id)
        if allowed is None or count > allowed:
            bound = f"the baseline allows {allowed}" if allowed is not None else f"the limit is {limit}"
            failures.append(
                _failure(
                    RULE_DEEP_CLASS,
                    f"class {class_id} has {count} repository ancestors; {bound}. Use composition instead of "
                    "more inheritance",
                    index.modules[class_id.split(":", 1)[0]].rel_path,
                )
            )
    for class_id, allowed in sorted(baseline.deep_classes.items()):
        count = ancestry.counts.get(class_id)
        if count is None or count <= limit:
            failures.append(
                _failure(
                    RULE_STALE,
                    f"remove deep_classes[{class_id!r}]: the class is gone or within the limit",
                    STRUCTURAL_BASELINE_PATH,
                )
            )
        elif count < allowed:
            failures.append(
                _failure(
                    RULE_STALE, f"lower deep_classes[{class_id!r}] from {allowed} to {count}", STRUCTURAL_BASELINE_PATH
                )
            )
    return failures


def _base_failures(
    base: BaseRevision,
    contracts: ImportContracts,
    baseline: StructuralBaseline,
    coverage_roots: Sequence[str],
) -> list[PolicyFailure]:
    base_contracts_text = base.read(IMPORT_CONTRACTS_PATH)
    base_baseline_text = base.read(STRUCTURAL_BASELINE_PATH)
    if base_contracts_text is None or base_baseline_text is None:
        return _adoption_failures(base, coverage_roots)
    try:
        base_contracts = parse_import_contracts(base_contracts_text, f"{IMPORT_CONTRACTS_PATH} at {base.revision}")
        base_baseline = parse_structural_baseline(base_baseline_text, f"{STRUCTURAL_BASELINE_PATH} at {base.revision}")
    except InvalidInputError as exc:
        return [_failure(RULE_CONFIG, f"the base revision baselines cannot be read: {exc}")]
    return [
        *_grown_ignore_failures(contracts, base_contracts),
        *_grown_baseline_failures(baseline, base_baseline),
    ]


def _adoption_failures(base: BaseRevision, coverage_roots: Sequence[str]) -> list[PolicyFailure]:
    """Adoption (I6): a baseline new at the base revision needs the base revision's own package source.

    Then I1 and I2 make the new baseline equal to the findings of the base revision.
    """

    changed = base.sources_changed(coverage_roots)
    message = (
        "the structural baselines are new at the base revision, so this change must not change package "
        "source; adopt the baselines in a change of their own"
    )
    return [_failure(RULE_BOOTSTRAP, message, STRUCTURAL_BASELINE_PATH)] if changed else []


def _grown_ignore_failures(contracts: ImportContracts, base_contracts: ImportContracts) -> list[PolicyFailure]:
    return [
        _failure(
            RULE_GROWN,
            f"{contract_id} ignore_imports gained '{importer} -> {imported}'; import debt can only shrink",
            IMPORT_CONTRACTS_PATH,
        )
        for contract_id in (LAYERS_CONTRACT_ID, CYCLES_CONTRACT_ID)
        for importer, imported in sorted(contracts.ignores[contract_id] - base_contracts.ignores[contract_id])
    ]


def _grown_baseline_failures(baseline: StructuralBaseline, base_baseline: StructuralBaseline) -> list[PolicyFailure]:
    failures = [
        _failure(RULE_GROWN, f"private_imports[{importer!r}][{target!r}] grew to {count}", STRUCTURAL_BASELINE_PATH)
        for (importer, target), count in sorted(baseline.private_imports.items())
        if count > base_baseline.private_imports.get((importer, target), 0)
    ]
    failures.extend(
        _failure(RULE_GROWN, f"deep_classes[{class_id!r}] grew to {count}", STRUCTURAL_BASELINE_PATH)
        for class_id, count in sorted(baseline.deep_classes.items())
        if count > base_baseline.deep_classes.get(class_id, 0)
    )
    failures.extend(
        _failure(
            RULE_GROWN,
            f"cycle_components[{package!r}] gained {list(component)}; cycles can only become smaller",
            STRUCTURAL_BASELINE_PATH,
        )
        for package, components in sorted(baseline.cycle_components.items())
        for component in components
        if not _within_any(component, base_baseline.cycle_components.get(package, ()))
    )
    return failures


def _within_any(component: tuple[str, ...], recorded: Sequence[tuple[str, ...]]) -> bool:
    members = set(component)
    return any(members <= set(candidate) for candidate in recorded)


def _failure(rule_id: str, message: str, path: str | None = None) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path, waivable=False)


def _bounded(failures: list[PolicyFailure]) -> list[PolicyFailure]:
    """Keep at most ``_REPORT_LIMIT`` failures of each rule and count the rest."""

    kept: list[PolicyFailure] = []
    omitted: defaultdict[str, int] = defaultdict(int)
    shown: Counter[str] = Counter()
    for failure in failures:
        if shown[failure.rule_id] < _REPORT_LIMIT:
            shown[failure.rule_id] += 1
            kept.append(failure)
        else:
            omitted[failure.rule_id] += 1
    kept.extend(
        _failure(rule_id, f"{count} more {rule_id} failures are not shown")
        for rule_id, count in sorted(omitted.items())
    )
    return kept
