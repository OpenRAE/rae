"""ADR-117 structural ratchet: compare structural findings with exact, shrink-only baselines.

Each current finding must be in its baseline (I1), each baseline entry must be a
current finding (I2), and each baseline must be a subset of the baseline at the
base revision (I5). When the base revision has no baselines, the adoption
commit bounds them (I6). Structural failures cannot be waived (I9).
"""

from __future__ import annotations

import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from raes_contracts.errors import InvalidInputError

from .class_ancestry import AncestryResult, analyze_class_ancestry
from .common import PolicyFailure
from .function_imports import collect_function_imports
from .hidden_imports import (
    DynamicImportAllowance,
    HiddenImportAnalysis,
    analyze_hidden_imports,
    parse_dynamic_import_allowlist,
)
from .import_boundaries import boundary_violation
from .import_cycles import Components, cyclic_components, is_cyclic_import, layer_disagreements, parse_layers
from .import_graph import CONTRACT_BROKEN, CONTRACT_UNMATCHED_IGNORES, ImportAnalysis, analyze_imports
from .private_imports import PrivateImport, collect_private_imports
from .private_members import PrivateMemberAnalysis, analyze_private_members
from .source_index import SourceIndex, build_source_index
from .structural_baseline import (
    CYCLES_CONTRACT_ID,
    FAMILY_KEYS,
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
RULE_PRIVATE_MEMBER = "private-member-access-new"
RULE_FUNCTION_IMPORT = "function-import-new"
RULE_HIDDEN_IMPORT = "dynamic-import-hidden"
RULE_HIDDEN_BOUNDARY = "dynamic-import-boundary"
RULE_HIDDEN_CYCLE = "dynamic-import-cycle"
_PRIVATE_MEMBERS, _FUNCTION_IMPORTS = FAMILY_KEYS
_FAMILY_RULES = {
    _PRIVATE_MEMBERS: (RULE_PRIVATE_MEMBER, "accesses private member", "Use a public interface of the object"),
    _FUNCTION_IMPORTS: (RULE_FUNCTION_IMPORT, "imports inside a function", "Move the import to module level"),
}
_REPORT_LIMIT = 50

ImportAnalyzer = Callable[..., ImportAnalysis]
MemberAnalyzer = Callable[[Path, SourceIndex], PrivateMemberAnalysis]


@dataclass(frozen=True)
class _Settings:
    max_ancestors: int
    coverage_roots: tuple[str, ...]
    allowed_imports: Mapping[str, frozenset[str]]
    boundary_rules: Mapping[str, Mapping[str, object]]
    dynamic_import_allowlist: tuple[DynamicImportAllowance, ...]


@dataclass(frozen=True)
class _Inputs:
    settings: _Settings
    contracts: ImportContracts
    baseline: StructuralBaseline
    index: SourceIndex
    private_imports: Counter[PrivateImport]
    ancestry: AncestryResult
    families: Mapping[str, Counter[tuple[str, str]]]
    hidden: HiddenImportAnalysis
    member_version: str


def evaluate_structural_ratchet(
    repo_root: Path,
    policy: dict[str, object],
    *,
    base_rev: str | None = None,
    import_analyzer: ImportAnalyzer = analyze_imports,
    member_analyzer: MemberAnalyzer = analyze_private_members,
    base_revision: BaseRevision | None = None,
) -> list[PolicyFailure]:
    """Run the ADR-117 checks and return their failures.

    ``base_rev`` is the revision whose baselines bound the current ones; it
    defaults to ``HEAD``. ``base_revision`` replaces the Git reader of that
    revision. ``member_analyzer`` counts the private member accesses (Ruff
    ``SLF001``). A missing analyzer or an unreadable base revision raises
    ``OperationalError``.
    """

    inputs = _read_inputs(repo_root, policy, member_analyzer)
    if isinstance(inputs, list):
        return inputs
    analysis = _analyze_imports(repo_root, inputs, import_analyzer)
    if isinstance(analysis, list):
        return analysis
    base = base_revision or GitBaseRevision(repo_root, base_rev or "HEAD")
    return _bounded(_comparison_failures(inputs, analysis, base, member_analyzer))


def _read_inputs(
    repo_root: Path, policy: dict[str, object], member_analyzer: MemberAnalyzer
) -> _Inputs | list[PolicyFailure]:
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
        members = member_analyzer(repo_root, index)
        inputs = _Inputs(
            settings,
            contracts,
            baseline,
            index,
            collect_private_imports(index),
            analyze_class_ancestry(index),
            _family_counts(index, members),
            analyze_hidden_imports(index, settings.dynamic_import_allowlist),
            members.version,
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


def _comparison_failures(
    inputs: _Inputs, analysis: ImportAnalysis, base: BaseRevision, member_analyzer: MemberAnalyzer
) -> list[PolicyFailure]:
    contracts, baseline, settings = inputs.contracts, inputs.baseline, inputs.settings
    # Check 6: the named targets of dynamic imports are edges of the graph for the cycle check.
    components = cyclic_components(analysis.imports | inputs.hidden.edges, depth=contracts.cycles_depth)
    return [
        *_layer_failures(contracts, settings),
        *_module_set_failures(inputs.index, analysis),
        *_analysis_record_failures(baseline, analysis, contracts, settings, inputs.member_version),
        *_contract_failures(analysis),
        *_cycle_failures(contracts, analysis, components, baseline),
        *_dynamic_cycle_failures(contracts, analysis, inputs.hidden.edges, baseline),
        *_private_import_failures(inputs.index, inputs.private_imports, baseline),
        *_ancestry_failures(inputs.index, inputs.ancestry, baseline, settings.max_ancestors),
        *(failure for key in FAMILY_KEYS for failure in _family_failures(inputs, key)),
        *_hidden_import_failures(inputs),
        *_base_failures(base, inputs, member_analyzer),
    ]


def _family_counts(index: SourceIndex, members: PrivateMemberAnalysis) -> dict[str, Counter[tuple[str, str]]]:
    return {
        _PRIVATE_MEMBERS: Counter({(item.module, item.member): count for item, count in members.counts.items()}),
        _FUNCTION_IMPORTS: Counter(
            {(item.importer, item.imported): count for item, count in collect_function_imports(index).items()}
        ),
    }


def _family_failures(inputs: _Inputs, key: str) -> list[PolicyFailure]:
    """I1 and I2 for one counted family: each finding within the baseline, each entry still found."""

    recorded = inputs.baseline.families[key]
    if recorded is None:
        return [
            _failure(RULE_CONFIG, f"the baseline must record {key} (ADR-117 check {key})", STRUCTURAL_BASELINE_PATH)
        ]
    rule_id, verb, remedy = _FAMILY_RULES[key]
    current = inputs.families[key]
    failures = [
        _failure(
            rule_id,
            f"{owner} {verb} {name} {count} time(s); the baseline allows {recorded.get((owner, name), 0)}. {remedy}",
            inputs.index.modules[owner].rel_path,
        )
        for (owner, name), count in sorted(current.items())
        if count > recorded.get((owner, name), 0)
    ]
    for (owner, name), allowed in sorted(recorded.items()):
        count = current.get((owner, name), 0)
        if count < allowed:
            failures.append(
                _failure(
                    RULE_STALE,
                    f"{key}[{owner!r}][{name!r}] is {allowed} but the code has {count}; "
                    + ("remove the entry" if count == 0 else f"lower it to {count}"),
                    STRUCTURAL_BASELINE_PATH,
                )
            )
    return failures


def _hidden_import_failures(inputs: _Inputs) -> list[PolicyFailure]:
    """Check 6: each dynamic import names its target, and each named target respects the module boundaries."""

    hidden = inputs.hidden
    failures = [
        _failure(
            RULE_HIDDEN_IMPORT,
            f"{item.module}.{item.function} line {item.line} imports a module that it does not name with a string "
            "literal or a literal _LAZY_EXPORTS mapping; name the module or add a reasoned "
            "structural_checks.dynamic_import_allowlist entry",
            inputs.index.modules[item.module].rel_path,
        )
        for item in hidden.unresolved
    ]
    failures.extend(
        _failure(
            RULE_STALE,
            f"dynamic_import_allowlist entry {item.module}.{item.function} matches no dynamic import; remove it",
        )
        for item in hidden.unused_allowances
    )
    failures.extend(_hidden_edge_failures(inputs))
    return failures


def _hidden_edge_failures(inputs: _Inputs) -> list[PolicyFailure]:
    """Check each dynamic edge as a static import: the module boundaries and the package layer order."""

    rules = inputs.settings.boundary_rules
    known = frozenset(rules)
    positions = _layer_positions(inputs.contracts)
    failures: list[PolicyFailure] = []
    for importer, imported in sorted(inputs.hidden.edges):
        source, target = importer.split(".", 1)[0], imported.split(".", 1)[0]
        path = inputs.index.modules[importer].rel_path
        rule = rules.get(source)
        violation = boundary_violation(rule, known, imported) if rule is not None else None
        if violation is not None:
            failures.append(
                _failure(RULE_HIDDEN_BOUNDARY, f"{importer} loads {imported} dynamically: {violation[1]}", path)
            )
        elif source != target and not _layer_allows(positions, source, target):
            failures.append(
                _failure(
                    RULE_HIDDEN_BOUNDARY,
                    f"{importer} loads {imported} dynamically, but the package layers do not let {source} import "
                    f"{target}",
                    path,
                )
            )
    return failures


def _layer_positions(contracts: ImportContracts) -> dict[str, tuple[int, bool]]:
    """Map each package of the layer order to its position and whether its layer siblings are independent."""

    try:
        layers = parse_layers(contracts.layers)
    except InvalidInputError:
        return {}
    return {package: (index, layer.independent) for index, layer in enumerate(layers) for package in layer.packages}


def _layer_allows(positions: Mapping[str, tuple[int, bool]], source: str, target: str) -> bool:
    if source not in positions or target not in positions:
        return False
    (source_index, independent), (target_index, _) = positions[source], positions[target]
    return target_index > source_index or (target_index == source_index and not independent)


def _settings(policy: dict[str, object]) -> _Settings:
    roots, rules = _module_boundaries(policy.get("module_boundaries"))
    block = policy.get("structural_checks")
    return _Settings(
        max_ancestors=_ancestor_limit(block),
        coverage_roots=roots,
        allowed_imports={module: rule["allowed_top_level_imports"] for module, rule in rules.items()},  # type: ignore[misc]
        boundary_rules=rules,
        dynamic_import_allowlist=parse_dynamic_import_allowlist(
            block.get("dynamic_import_allowlist") if isinstance(block, dict) else None
        ),
    )


def _ancestor_limit(block: object) -> int:
    required = {"adr", "max_repository_ancestors"}
    if not isinstance(block, dict) or not required <= set(block) <= {*required, "dynamic_import_allowlist"}:
        raise InvalidInputError(
            "structural_checks block (ADR-117) is required with the keys adr and max_repository_ancestors and "
            "optionally dynamic_import_allowlist"
        )
    limit = block["max_repository_ancestors"]
    if not isinstance(block["adr"], str) or not block["adr"]:
        raise InvalidInputError("structural_checks.adr must be a non-empty string")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise InvalidInputError("structural_checks.max_repository_ancestors must be a positive integer")
    return limit


def _module_boundaries(boundaries: object) -> tuple[tuple[str, ...], dict[str, dict[str, object]]]:
    """Return the package coverage roots and the import rules of each module (ADR-036)."""

    roots = boundaries.get("package_coverage_roots") if isinstance(boundaries, dict) else None
    modules = boundaries.get("modules") if isinstance(boundaries, dict) else None
    if not isinstance(roots, list) or not roots or not all(isinstance(root, str) for root in roots):
        raise InvalidInputError("module_boundaries.package_coverage_roots must be a non-empty list of strings")
    if not isinstance(modules, list) or not all(isinstance(module, dict) for module in modules):
        raise InvalidInputError("module_boundaries.modules must be a list of mappings")
    rules = {
        str(module.get("id")): {
            "id": str(module.get("id")),
            "allowed_top_level_imports": frozenset(str(name) for name in module.get("allowed_top_level_imports") or ()),
            "forbidden_import_prefixes": tuple(str(item) for item in module.get("forbidden_import_prefixes") or ()),
            "public_import_prefixes": {
                str(key): tuple(str(prefix) for prefix in value)
                for key, value in (module.get("public_import_prefixes") or {}).items()
            },
        }
        for module in modules
    }
    return tuple(roots), rules


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
    baseline: StructuralBaseline,
    analysis: ImportAnalysis,
    contracts: ImportContracts,
    settings: _Settings,
    member_version: str,
) -> list[PolicyFailure]:
    expected = {
        "exclude_type_checking_imports": contracts.exclude_type_checking_imports,
        "grimp": analysis.versions.get("grimp"),
        "import-linter": analysis.versions.get("import-linter"),
        "max_repository_ancestors": settings.max_ancestors,
        "ruff": member_version,
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


def _dynamic_cycle_failures(
    contracts: ImportContracts,
    analysis: ImportAnalysis,
    hidden: frozenset[tuple[str, str]],
    baseline: StructuralBaseline,
) -> list[PolicyFailure]:
    """Apply the cycle contract to the graph with the dynamic edges, as import-linter applies it to the static graph.

    Without its ignored imports, the static graph has no sibling cycle. So each cycle that the dynamic edges add is a
    failure. This check reports a cycle inside a baselined component; ``_cycle_failures`` reports a grown component.
    """

    if not hidden:
        return []
    ignored = contracts.ignores[CYCLES_CONTRACT_ID]
    static = cyclic_components(analysis.imports - ignored, depth=contracts.cycles_depth)
    combined = cyclic_components((analysis.imports | hidden) - ignored, depth=contracts.cycles_depth)
    return [
        _failure(
            RULE_HIDDEN_CYCLE,
            f"dynamic imports close an import cycle between children of {package}: {list(component)}. Remove the "
            "dynamic import that closes the cycle",
        )
        for package, components in sorted(combined.items())
        for component in components
        if not _within_any(component, static.get(package, ()))
        and _within_any(component, baseline.cycle_components.get(package, ()))
    ]


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


def _base_failures(base: BaseRevision, inputs: _Inputs, member_analyzer: MemberAnalyzer) -> list[PolicyFailure]:
    contracts, baseline, coverage_roots = inputs.contracts, inputs.baseline, inputs.settings.coverage_roots
    bound, texts = base, _baseline_texts(base)
    if texts is None:
        adoption = base.adoption(coverage_roots)
        if adoption is None or (texts := _baseline_texts(adoption)) is None:
            return _adoption_failures(base, coverage_roots)
        bound = adoption
    base_contracts_text, base_baseline_text = texts
    try:
        base_contracts = parse_import_contracts(base_contracts_text, f"{IMPORT_CONTRACTS_PATH} at {bound.revision}")
        base_baseline = parse_structural_baseline(base_baseline_text, f"{STRUCTURAL_BASELINE_PATH} at {bound.revision}")
    except InvalidInputError as exc:
        return [_failure(RULE_CONFIG, f"the base revision baselines cannot be read: {exc}")]
    return [
        *_grown_ignore_failures(contracts, base_contracts),
        *_grown_baseline_failures(baseline, base_baseline),
        *_grown_family_failures(bound, inputs, base_baseline, member_analyzer),
    ]


def _grown_family_failures(
    bound: BaseRevision, inputs: _Inputs, base_baseline: StructuralBaseline, member_analyzer: MemberAnalyzer
) -> list[PolicyFailure]:
    """I5 for the counted families, and I10 for a family that the base revision does not record yet.

    I10 adopts such a family. A move gives a finding a new identity, so the bound
    is the total count of the family's findings in the base revision source.
    """

    failures: list[PolicyFailure] = []
    unrecorded = [key for key in FAMILY_KEYS if base_baseline.families[key] is None]
    for key in FAMILY_KEYS:
        recorded, base_recorded = inputs.baseline.families[key], base_baseline.families[key]
        if recorded is None or base_recorded is None:
            continue
        failures.extend(
            _failure(RULE_GROWN, f"{key}[{owner!r}][{name!r}] grew to {count}", STRUCTURAL_BASELINE_PATH)
            for (owner, name), count in sorted(recorded.items())
            if count > base_recorded.get((owner, name), 0)
        )
    if unrecorded:
        base_counts = _base_family_counts(bound, inputs.settings.coverage_roots, member_analyzer)
        for key in unrecorded:
            recorded = inputs.baseline.families[key] or {}
            total, base_total = sum(recorded.values()), sum(base_counts[key].values())
            if total > base_total:
                failures.append(
                    _failure(
                        RULE_GROWN,
                        f"{key} adopts {total} findings, but the base revision source has {base_total}; adoption "
                        "must not add findings (ADR-117 I10)",
                        STRUCTURAL_BASELINE_PATH,
                    )
                )
    return failures


def _base_family_counts(
    bound: BaseRevision, coverage_roots: Sequence[str], member_analyzer: MemberAnalyzer
) -> dict[str, Counter[tuple[str, str]]]:
    with tempfile.TemporaryDirectory(prefix="raes-structural-base-") as directory:
        root = Path(directory)
        bound.extract(coverage_roots, root)
        index = build_source_index(root, coverage_roots)
        return _family_counts(index, member_analyzer(root, index))


def _baseline_texts(revision: BaseRevision) -> tuple[str, str] | None:
    contracts_text = revision.read(IMPORT_CONTRACTS_PATH)
    baseline_text = revision.read(STRUCTURAL_BASELINE_PATH)
    return None if contracts_text is None or baseline_text is None else (contracts_text, baseline_text)


def _adoption_failures(base: BaseRevision, coverage_roots: Sequence[str]) -> list[PolicyFailure]:
    """Adoption (I6): without an adoption commit, a baseline new at the base revision needs its package source.

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
