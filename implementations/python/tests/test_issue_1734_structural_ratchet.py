"""Issue #1734 / ADR-117: the structural ratchet compares exact findings with shrink-only baselines."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import tools.check_repo_policy as check_repo_policy
from raes_contracts.errors import InvalidInputError, OperationalError
from tools.policy import import_graph, repo_policy
from tools.policy.common import PolicyFailure, apply_exceptions
from tools.policy.import_graph import (
    CONTRACT_BROKEN,
    CONTRACT_KEPT,
    CONTRACT_UNMATCHED_IGNORES,
    ContractResult,
    ImportAnalysis,
)
from tools.policy.source_index import build_source_index
from tools.policy.structural_baseline import (
    IMPORT_CONTRACTS_PATH,
    STRUCTURAL_BASELINE_PATH,
    validate_git_revision,
)
from tools.policy.structural_ratchet import evaluate_structural_ratchet

PACKAGES = "implementations/python/packages"
VERSIONS = {"grimp": "3.18", "import-linter": "2.15"}
COMMIT = "0" * 40


def _policy(**structural: object) -> dict[str, Any]:
    return {
        "module_boundaries": {
            "package_coverage_roots": [PACKAGES],
            "modules": [
                {"id": "alpha", "allowed_top_level_imports": ["beta"]},
                {"id": "beta", "allowed_top_level_imports": []},
            ],
        },
        "structural_checks": {"adr": "ADR-117", "max_repository_ancestors": 7, **structural},
    }


def _contracts(
    *,
    layer_ignores: Iterable[str] = (),
    cycle_ignores: Iterable[str] = (),
    layers: Sequence[str] = ("alpha", "beta"),
    roots: Sequence[str] = ("alpha", "beta"),
    depth: int = 10,
    extra: str = "",
) -> str:
    def toml_list(items: Iterable[str]) -> str:
        return "[" + ", ".join(json.dumps(item) for item in items) + "]"

    return (
        "[tool.importlinter]\n"
        f"root_packages = {toml_list(roots)}\n"
        "include_external_packages = false\n"
        "exclude_type_checking_imports = true\n\n"
        "[[tool.importlinter.contracts]]\n"
        'id = "raes-package-layers"\nname = "layers"\ntype = "layers"\n'
        f"layers = {toml_list(layers)}\n"
        'unmatched_ignore_imports_alerting = "error"\n'
        f"ignore_imports = {toml_list(layer_ignores)}\n\n"
        "[[tool.importlinter.contracts]]\n"
        'id = "raes-sibling-cycles"\nname = "cycles"\ntype = "acyclic_siblings"\n'
        f"ancestors = {toml_list(roots)}\ndepth = {depth}\n"
        'unmatched_ignore_imports_alerting = "error"\n'
        f"ignore_imports = {toml_list(cycle_ignores)}\n" + extra
    )


def _baseline(
    *,
    components: dict[str, list[list[str]]] | None = None,
    private: dict[str, dict[str, int]] | None = None,
    deep: dict[str, int] | None = None,
    **analysis: object,
) -> str:
    record = {
        "exclude_type_checking_imports": True,
        "grimp": VERSIONS["grimp"],
        "import-linter": VERSIONS["import-linter"],
        "max_repository_ancestors": 7,
        "sibling_depth": 10,
        **analysis,
    }
    document = {
        "schema": "raes.structural-baseline/v1",
        "adopted_commit": COMMIT,
        "analysis": record,
        "cycle_components": components or {},
        "private_imports": private or {},
        "deep_classes": deep or {},
    }
    return json.dumps(document, indent=2)


def _write(repo: Path, rel_path: str, text: str) -> None:
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(tmp_path: Path, files: dict[str, str], *, contracts: str | None = None, baseline: str | None = None) -> Path:
    for rel_path, text in {"alpha/__init__.py": "", "beta/__init__.py": "", **files}.items():
        _write(tmp_path, f"{PACKAGES}/{rel_path}", text)
    _write(tmp_path, IMPORT_CONTRACTS_PATH, contracts if contracts is not None else _contracts())
    _write(tmp_path, STRUCTURAL_BASELINE_PATH, baseline if baseline is not None else _baseline())
    return tmp_path


@dataclass
class FakeAnalyzer:
    repo: Path
    imports: set[tuple[str, str]] = field(default_factory=set)
    contracts: tuple[ContractResult, ...] = (
        ContractResult("raes-package-layers", CONTRACT_KEPT, ()),
        ContractResult("raes-sibling-cycles", CONTRACT_KEPT, ()),
    )
    versions: dict[str, str] = field(default_factory=lambda: dict(VERSIONS))
    modules: frozenset[str] | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    def __call__(
        self, roots: Sequence[Path], config: Path, *, root_packages: Sequence[str], exclude_type_checking_imports: bool
    ) -> ImportAnalysis:
        self.calls.append({"roots": list(roots), "config": config, "root_packages": tuple(root_packages)})
        modules = self.modules or frozenset(build_source_index(self.repo, [PACKAGES]).modules)
        return ImportAnalysis(modules, frozenset(self.imports), self.contracts, self.versions)


@dataclass
class FakeBase:
    texts: dict[str, str | None]
    changed: bool = False
    revision: str = "base"

    def read(self, rel_path: str) -> str | None:
        return self.texts.get(rel_path)

    def sources_changed(self, roots: Sequence[str]) -> bool:
        return self.changed


def _same_base(repo: Path) -> FakeBase:
    return FakeBase(
        {
            IMPORT_CONTRACTS_PATH: (repo / IMPORT_CONTRACTS_PATH).read_text(encoding="utf-8"),
            STRUCTURAL_BASELINE_PATH: (repo / STRUCTURAL_BASELINE_PATH).read_text(encoding="utf-8"),
        }
    )


def _run(repo: Path, analyzer: FakeAnalyzer | None = None, base: FakeBase | None = None, **policy: object):
    return evaluate_structural_ratchet(
        repo,
        _policy(**policy),
        import_analyzer=analyzer or FakeAnalyzer(repo),
        base_revision=base or _same_base(repo),
    )


def _rules(failures: list[PolicyFailure]) -> list[str]:
    return [failure.rule_id for failure in failures]


CYCLE_FILES = {"alpha/a.py": "from alpha import b\n", "alpha/b.py": "from alpha import a\n_x = 1\n_y = 2\n"}
CYCLE_IMPORTS = {("alpha.a", "alpha.b"), ("alpha.b", "alpha.a")}


def _cyclic_repo(tmp_path: Path, files: dict[str, str] | None = None, **baseline: Any) -> Path:
    return _repo(
        tmp_path,
        {**CYCLE_FILES, **(files or {})},
        contracts=_contracts(cycle_ignores=["alpha.a -> alpha.b"]),
        baseline=_baseline(components={"alpha": [["alpha.a", "alpha.b"]]}, **baseline),
    )


def test_findings_equal_to_their_baselines_pass_and_the_analyzer_gets_the_package_scope(tmp_path: Path) -> None:
    repo = _cyclic_repo(
        tmp_path,
        {"alpha/a.py": "from alpha import b\nfrom alpha.b import _x\n"},
        private={"alpha.a": {"alpha.b._x": 1}},
    )
    analyzer = FakeAnalyzer(repo, CYCLE_IMPORTS)

    assert _run(repo, analyzer) == []
    assert analyzer.calls == [
        {
            "roots": [repo / PACKAGES],
            "config": repo / IMPORT_CONTRACTS_PATH,
            "root_packages": ("alpha", "beta"),
        }
    ]


def test_a_new_private_import_fails_and_a_replacement_cannot_reuse_a_fixed_entry(tmp_path: Path) -> None:
    repo = _cyclic_repo(
        tmp_path,
        {"alpha/a.py": "from alpha import b\nfrom alpha.b import _y\n"},
        private={"alpha.a": {"alpha.b._x": 1}},
    )

    failures = _run(repo, FakeAnalyzer(repo, CYCLE_IMPORTS))

    assert _rules(failures) == ["private-import-new", "structural-baseline-stale"]
    assert failures[0].path == f"{PACKAGES}/alpha/a.py"
    assert "alpha.b._y" in failures[0].message
    assert all(not failure.waivable for failure in failures)


def test_a_second_site_of_a_baselined_private_import_exceeds_its_occurrence_count(tmp_path: Path) -> None:
    repo = _cyclic_repo(
        tmp_path,
        {"alpha/a.py": "from alpha import b\nfrom alpha.b import _x\ndef f():\n    from alpha.b import _x\n"},
        private={"alpha.a": {"alpha.b._x": 1}},
    )

    assert _rules(_run(repo, FakeAnalyzer(repo, CYCLE_IMPORTS))) == ["private-import-new"]


def test_a_removed_private_import_requires_removing_its_entry(tmp_path: Path) -> None:
    repo = _cyclic_repo(tmp_path, private={"alpha.a": {"alpha.b._x": 1}})

    failures = _run(repo, FakeAnalyzer(repo, CYCLE_IMPORTS))

    assert _rules(failures) == ["structural-baseline-stale"]
    assert "remove the entry" in failures[0].message


def _chain(length: int) -> str:
    return "class C0:\n    pass\n" + "".join(f"class C{i}(C{i - 1}):\n    pass\n" for i in range(1, length + 1))


def test_a_new_deep_class_fails_and_a_baselined_one_cannot_deepen(tmp_path: Path) -> None:
    new_class = _repo(tmp_path / "new", {"alpha/deep.py": _chain(8)})
    deepened = _repo(tmp_path / "deeper", {"alpha/deep.py": _chain(9)}, baseline=_baseline(deep={"alpha.deep:C8": 8}))

    assert _rules(_run(new_class)) == ["class-ancestry-too-deep"]
    assert _rules(_run(deepened)) == ["class-ancestry-too-deep"]
    assert "alpha.deep:C9" in _run(deepened)[0].message


def test_a_shallower_or_removed_deep_class_requires_a_baseline_update(tmp_path: Path) -> None:
    shallower = _repo(tmp_path / "s", {"alpha/deep.py": _chain(8)}, baseline=_baseline(deep={"alpha.deep:C8": 9}))
    removed = _repo(tmp_path / "r", {"alpha/deep.py": _chain(7)}, baseline=_baseline(deep={"alpha.deep:C8": 8}))

    assert [f.message for f in _run(shallower)] == ["lower deep_classes['alpha.deep:C8'] from 9 to 8"]
    assert _rules(_run(removed)) == ["structural-baseline-stale"]


def test_an_unresolved_package_base_fails_the_gate(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"alpha/odd.py": "from alpha.missing import Base\nclass Odd(Base):\n    pass\n"})

    failures = _run(repo)

    assert _rules(failures) == ["class-ancestry-unresolved"]
    assert failures[0].path == f"{PACKAGES}/alpha/odd.py"


def test_broken_and_stale_contracts_are_reported(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {})
    analyzer = FakeAnalyzer(
        repo,
        contracts=(
            ContractResult("raes-package-layers", CONTRACT_BROKEN, ("beta is not allowed to import alpha:",)),
            ContractResult(
                "raes-sibling-cycles", CONTRACT_UNMATCHED_IGNORES, ("No matches for ignored import x -> y.",)
            ),
        ),
    )

    failures = _run(repo, analyzer)

    assert _rules(failures) == ["import-contract-broken", "structural-baseline-stale"]
    assert "beta is not allowed to import alpha" in failures[0].message


def test_a_new_return_path_through_an_ignored_import_fails_even_when_the_contract_is_kept(tmp_path: Path) -> None:
    files = {
        "alpha/a.py": "from alpha import b\n",
        "alpha/b.py": "from alpha import c\n",
        "alpha/c.py": "from alpha import a\n",
    }
    repo = _repo(
        tmp_path,
        files,
        contracts=_contracts(cycle_ignores=["alpha.a -> alpha.b"]),
        baseline=_baseline(components={"alpha": [["alpha.a", "alpha.b"]]}),
    )
    analyzer = FakeAnalyzer(repo, {("alpha.a", "alpha.b"), ("alpha.b", "alpha.c"), ("alpha.c", "alpha.a")})

    failures = _run(repo, analyzer)

    assert _rules(failures) == ["import-cycle-component-grown"]
    assert "['alpha.a', 'alpha.b', 'alpha.c']" in failures[0].message


def test_an_ignored_import_that_left_its_cycle_and_a_smaller_component_are_stale(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {"alpha/a.py": "", "alpha/b.py": "", "alpha/c.py": ""},
        contracts=_contracts(cycle_ignores=["alpha.c -> alpha.a"]),
        baseline=_baseline(components={"alpha": [["alpha.a", "alpha.b", "alpha.c"]]}),
    )
    analyzer = FakeAnalyzer(repo, {("alpha.a", "alpha.b"), ("alpha.b", "alpha.a"), ("alpha.c", "alpha.a")})

    messages = [failure.message for failure in _run(repo, analyzer)]

    assert messages == [
        "ignored import 'alpha.c -> alpha.a' is no longer on an import cycle; remove it from raes-sibling-cycles "
        "ignore_imports",
        "cycle_components['alpha'] must be [['alpha.a', 'alpha.b']]; the cycles became smaller",
    ]


def test_the_baselines_cannot_grow_against_the_base_revision(tmp_path: Path) -> None:
    repo = _cyclic_repo(tmp_path, {"alpha/a.py": "from alpha import b\nfrom alpha.b import _x\n"})
    base = _same_base(repo)
    _write(repo, IMPORT_CONTRACTS_PATH, _contracts(cycle_ignores=["alpha.a -> alpha.b", "alpha.b -> alpha.a"]))
    _write(
        repo,
        STRUCTURAL_BASELINE_PATH,
        _baseline(
            components={"alpha": [["alpha.a", "alpha.b"]], "beta": [["beta.x", "beta.y"]]},
            private={"alpha.a": {"alpha.b._x": 1}},
            deep={"alpha.a:Ghost": 9},
        ),
    )

    grown = [
        failure for failure in _run(repo, FakeAnalyzer(repo, CYCLE_IMPORTS), base) if failure.rule_id.endswith("grown")
    ]

    assert [failure.message for failure in grown] == [
        "raes-sibling-cycles ignore_imports gained 'alpha.b -> alpha.a'; import debt can only shrink",
        "private_imports['alpha.a']['alpha.b._x'] grew to 1",
        "deep_classes['alpha.a:Ghost'] grew to 9",
        "cycle_components['beta'] gained ['beta.x', 'beta.y']; cycles can only become smaller",
    ]


def test_a_baseline_new_at_the_base_is_accepted_only_with_unchanged_package_source(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {})

    assert _run(repo, base=FakeBase({}, changed=False)) == []
    assert _rules(_run(repo, base=FakeBase({}, changed=True))) == ["structural-baseline-bootstrap"]


def test_a_malformed_base_baseline_fails_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {})
    base = _same_base(repo)
    base.texts[STRUCTURAL_BASELINE_PATH] = "{}"

    assert _rules(_run(repo, base=base)) == ["policy-config-malformed"]


def test_the_analysis_record_must_match_the_analyzers_and_options(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {})
    analyzer = FakeAnalyzer(repo, versions={"grimp": "3.19", "import-linter": "2.15"})

    failures = _run(repo, analyzer, max_repository_ancestors=8)

    assert _rules(failures) == ["structural-baseline-analysis", "structural-baseline-analysis"]
    assert "analysis.grimp is '3.18' but the analysis uses '3.19'" in failures[0].message


@pytest.mark.parametrize(
    ("contracts", "baseline", "policy", "fragment"),
    [
        (None, None, {"adr": ""}, "structural_checks.adr"),
        (None, None, {"max_repository_ancestors": 0}, "max_repository_ancestors"),
        (None, None, {"extra": 1}, "exactly the keys"),
        (None, "{}", {}, "keys must be"),
        (None, '{"schema": 1, "schema": 2}', {}, "duplicate JSON key"),
        (None, _baseline().replace("raes.structural-baseline/v1", "v0"), {}, "schema must be"),
        (None, _baseline(private={"alpha.a": {"alpha.b._x": 0}}), {}, "positive count"),
        (None, _baseline(components={"alpha": [["alpha.b", "alpha.a"]]}), {}, "sorted list"),
        (None, _baseline(deep={"alpha.a": 9}), {}, "positive ancestor count"),
        (_contracts(cycle_ignores=["alpha.* -> alpha.b"]), None, {}, "exact 'importer -> imported'"),
        (_contracts(cycle_ignores=["alpha.a -> alpha.b", "alpha.a -> alpha.b"]), None, {}, "must not repeat"),
        (_contracts(extra='\n[[tool.importlinter.contracts]]\nid = "x"\n'), None, {}, "contracts must be exactly"),
        (_contracts().replace('"error"', '"warn"', 1), None, {}, "must be 'error'"),
        (
            _contracts().replace("include_external_packages = false", "include_external_packages = true"),
            None,
            {},
            "false",
        ),
        (_contracts().replace("depth = 10", "depth = -1"), None, {}, "non-negative"),
        ("not = [toml", None, {}, "not valid TOML"),
        ("[tool]\nother = 1\n", None, {}, "only a [tool.importlinter] table"),
        ("[tool.importlinter]\nroot_packages = ['alpha']\n", None, {}, "keys must be"),
        (
            _contracts().replace('root_packages = ["alpha", "beta"]', 'root_packages = ["alpha", "alpha"]'),
            None,
            {},
            "repeat",
        ),
        (_contracts().replace('root_packages = ["alpha", "beta"]', 'root_packages = ["1bad"]'), None, {}, "dotted"),
        (
            _contracts().replace("exclude_type_checking_imports = true", 'exclude_type_checking_imports = "yes"'),
            None,
            {},
            "boolean",
        ),
        (_contracts().replace('layers = ["alpha", "beta"]', "layers = []"), None, {}, "layers must be"),
        (_contracts().replace('type = "layers"', 'type = "forbidden"'), None, {}, "must have type"),
        (_contracts().replace("ignore_imports = []", 'ignore_imports = "x"', 1), None, {}, "must be a list"),
        (None, _baseline().replace(COMMIT, "abc"), {}, "40-character"),
        (None, _baseline().replace(',\n    "sibling_depth": 10', ""), {}, "analysis keys"),
        (None, _baseline().replace('"cycle_components": {}', '"cycle_components": []'), {}, "must be an object"),
        (None, _baseline(components={"alpha": []}), {}, "non-empty list"),
        (None, _baseline(components={"alpha": [["alpha.a", "beta.b"]]}), {}, "children of the package"),
        (None, _baseline(private={"alpha.a": {}}), {}, "non-empty object"),
        (None, _baseline().replace('"private_imports": {}', '"private_imports": []'), {}, "must be an object"),
        (None, _baseline().replace('"deep_classes": {}', '"deep_classes": []'), {}, "must be an object"),
    ],
)
def test_malformed_policy_contracts_and_baselines_fail_closed(
    tmp_path: Path, contracts: str | None, baseline: str | None, policy: dict[str, object], fragment: str
) -> None:
    repo = _repo(tmp_path, {}, contracts=contracts, baseline=baseline)

    failures = _run(repo, **policy)

    assert _rules(failures) == ["policy-config-malformed"]
    assert fragment in failures[0].message


def test_a_missing_baseline_file_fails_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {})
    base = _same_base(repo)
    (repo / STRUCTURAL_BASELINE_PATH).unlink()

    assert _rules(_run(repo, base=base)) == ["policy-config-malformed"]


def test_the_contracts_must_cover_every_package_at_every_depth(tmp_path: Path) -> None:
    missing = _repo(tmp_path / "m", {}, contracts=_contracts(roots=("alpha",)))
    shallow = _repo(
        tmp_path / "s", {"alpha/sub/__init__.py": "", "alpha/sub/deep/__init__.py": ""}, contracts=_contracts(depth=1)
    )

    assert _rules(_run(missing)) == ["structural-scope-mismatch", "structural-scope-mismatch"]
    assert _rules(_run(shallow)) == ["structural-scope-mismatch"]


def test_the_layer_order_must_agree_with_module_boundaries(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {}, contracts=_contracts(layers=("beta", "alpha")))

    failures = _run(repo)

    assert _rules(failures) == ["import-layers-disagree"]
    assert "ADR-036 allows 'alpha' to import 'beta'" in failures[0].message


def test_the_graph_and_the_index_must_name_the_same_modules(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {})

    failures = _run(repo, FakeAnalyzer(repo, modules=frozenset({"alpha", "beta", "alpha.ghost"})))

    assert _rules(failures) == ["structural-scope-mismatch"]


def test_source_that_cannot_be_analyzed_fails_the_gate(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"alpha/broken.py": "def broken(:\n"})

    failures = _run(repo)

    assert _rules(failures) == ["structural-analysis-failed"]


def test_an_analyzer_refusal_fails_the_gate(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {})

    def refusing(*_args: object, **_kwargs: object) -> ImportAnalysis:
        raise InvalidInputError("grimp could not build the import graph: SourceSyntaxError")

    failures = evaluate_structural_ratchet(repo, _policy(), import_analyzer=refusing, base_revision=_same_base(repo))

    assert _rules(failures) == ["structural-analysis-failed"]


def test_reports_are_bounded_for_each_rule(tmp_path: Path) -> None:
    importer = "".join(f"from alpha.owner import _n{index}\n" for index in range(60))
    repo = _repo(tmp_path, {"alpha/owner.py": "", "alpha/user.py": importer})

    failures = _run(repo)

    assert _rules(failures).count("private-import-new") == 51
    assert failures[-1].message == "10 more private-import-new failures are not shown"


def test_structural_failures_cannot_be_waived_by_policy_exceptions() -> None:
    structural = PolicyFailure("private-import-new", "new", "a.py", waivable=False)
    ordinary = PolicyFailure("private-import-new", "new", "a.py")
    exceptions = [{"rule_id": "private-import-new", "paths": ["a.py"]}]

    assert apply_exceptions([structural, ordinary], exceptions) == [structural]


def test_repo_policy_runs_the_ratchet_for_every_full_check_with_the_base_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []
    sentinel = PolicyFailure("private-import-new", "new", waivable=False)

    def ratchet(repo_root: Path, policy: dict, *, base_rev: str | None = None) -> list[PolicyFailure]:
        calls.append({"repo_root": repo_root, "base_rev": base_rev, "has_block": "structural_checks" in policy})
        return [sentinel]

    monkeypatch.setattr(repo_policy, "evaluate_structural_ratchet", ratchet)
    repo_root = Path(__file__).resolve().parents[3]

    full = repo_policy.evaluate_repo_policy(repo_root, [], base_rev="abc123")
    local = repo_policy.evaluate_repo_policy(
        repo_root, ["README.md"], check_set="file-local", structural_runner=lambda _: []
    )

    assert sentinel in full
    assert sentinel not in local
    assert calls == [{"repo_root": repo_root, "base_rev": "abc123", "has_block": True}]


def test_missing_analyzers_are_an_operational_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> object:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(import_graph.importlib, "import_module", missing)

    with pytest.raises(OperationalError, match="locked tooling environment"):
        import_graph.analyze_imports(
            [Path(".")], Path("x.toml"), root_packages=["alpha"], exclude_type_checking_imports=True
        )


def test_repo_policy_relaunches_when_the_structural_analyzers_are_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tooling_python = tmp_path / "implementations" / "tooling" / "python" / ".venv" / "bin" / "python"
    tooling_python.parent.mkdir(parents=True)
    tooling_python.write_bytes(b"python")
    present = {"filelock"}
    monkeypatch.setattr(
        check_repo_policy.importlib.util, "find_spec", lambda name: object() if name in present else None
    )
    monkeypatch.setattr(check_repo_policy, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        check_repo_policy.subprocess, "run", lambda args, **_kwargs: subprocess.CompletedProcess(args, returncode=3)
    )

    assert check_repo_policy._run_from_frozen_tooling_environment() == 3


def test_repo_policy_command_refuses_a_base_revision_that_git_could_read_as_an_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check_repo_policy.sys, "argv", ["check_repo_policy.py", "--base-rev", "--output=/tmp/x"])

    with pytest.raises(SystemExit):
        check_repo_policy.parse_args()


@pytest.mark.parametrize("value", ["", "-x", "--output=/tmp/x", "a b", "a;b"])
def test_git_revisions_that_git_could_read_as_options_are_refused(value: str) -> None:
    with pytest.raises(InvalidInputError):
        validate_git_revision(value)


@pytest.mark.parametrize("value", ["HEAD", "origin/dev", "dea4d1be", "HEAD~1", "v1.2.3"])
def test_ordinary_git_revisions_are_accepted(value: str) -> None:
    assert validate_git_revision(value) == value
