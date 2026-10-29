"""Every RAES exception class descends from RaesError through one base (issue #1678)."""

import ast
import builtins
from pathlib import Path

from raes_contracts import errors

REPO_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_PATTERNS = (
    "implementations/python/packages/**/*.py",
    "implementations/python/tests/**/*.py",
    "implementations/python/research/*.py",
    "implementations/python/hatch_build.py",
    "implementations/formal/**/*.py",
    "implementations/tooling/*.py",
    "tools/**/*.py",
    "noxfile.py",
    "docs/public/conf.py",
    "docs/research/language-extensibility/*.py",
    "docs/research/modular-participant-control/*.py",
)
_BUILTIN_EXCEPTIONS = frozenset(
    name for name, value in vars(builtins).items() if isinstance(value, type) and issubclass(value, BaseException)
)
# Test doubles that simulate a foreign failure, an interruption or test control flow.
_FOREIGN_TEST_DOUBLES = frozenset(
    {
        ("implementations/python/tests/test_asr_535_participant_flow_assurance.py", "_Boom"),
        ("implementations/python/tests/test_issue_1226_release_evidence_cli.py", "_StopAfterProfile"),
        ("implementations/python/tests/test_issue_1355_mixed_mapping_time.py", "Interrupted"),
        ("implementations/python/tests/test_issue_1678_contracts_policy.py", "ProducerOnlyError"),
        ("implementations/python/tests/test_issue_1678_sweep_c.py", "ObservationRuntimeOnlyError"),
        ("implementations/python/tests/test_issue_1678_cycle2_pointers.py", "ArchiveAdapterOnlyError"),
        ("implementations/python/tests/test_issue_1678_sweep_t.py", "_GuardWarning"),
    }
)
_CATEGORIES = (
    errors.InvalidInputError,
    errors.ConflictError,
    errors.NotFoundError,
    errors.AuthorizationError,
    errors.OperationalError,
    errors.EvidenceIntegrityError,
)


def _source_files() -> list[Path]:
    files = set()
    for pattern in _SOURCE_PATTERNS:
        files.update(path for path in REPO_ROOT.glob(pattern) if path.is_file())
    return sorted(files)


def _class_definitions(paths: list[Path], root: Path) -> list[tuple[str, str, list[str]]]:
    definitions = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        relative = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [ast.unparse(base) for base in node.bases]
                definitions.append((relative, node.name, bases))
    return definitions


def _exception_classes(
    definitions: list[tuple[str, str, list[str]]],
) -> tuple[list[tuple[str, str, list[str]]], dict[str, list[list[str]]]]:
    bases_by_name: dict[str, list[list[str]]] = {}
    for _, name, bases in definitions:
        bases_by_name.setdefault(name, []).append(bases)

    def is_exception(base: str, seen: frozenset[str] = frozenset()) -> bool:
        name = base.rsplit(".", 1)[-1]
        if name in _BUILTIN_EXCEPTIONS:
            return True
        if name in seen:
            return False
        if name in bases_by_name:
            return any(is_exception(item, seen | {name}) for bases in bases_by_name[name] for item in bases)
        return name.endswith(("Error", "Exception"))

    exceptions = [definition for definition in definitions if any(is_exception(base) for base in definition[2])]
    return exceptions, bases_by_name


def _descends_from_root(name: str, bases_by_name: dict[str, list[list[str]]], seen: frozenset[str]) -> bool:
    if name == "RaesError":
        return True
    if name in seen or name not in bases_by_name:
        return False
    return all(
        len(bases) == 1 and _descends_from_root(bases[0].rsplit(".", 1)[-1], bases_by_name, seen | {name})
        for bases in bases_by_name[name]
    )


def _violations(definitions: list[tuple[str, str, list[str]]], allowed: frozenset[tuple[str, str]]) -> list[str]:
    exceptions, bases_by_name = _exception_classes(definitions)
    violations = []
    for path, name, bases in exceptions:
        if (path, name) in allowed:
            continue
        if len(bases) != 1:
            violations.append(f"{path}:{name} has {len(bases)} base classes")
        elif not _descends_from_root(bases[0].rsplit(".", 1)[-1], bases_by_name, frozenset({name})):
            violations.append(f"{path}:{name} does not descend from RaesError")
    return violations


def test_root_and_categories_use_single_inheritance():
    assert errors.RaesError.__bases__ == (Exception,)
    for category in _CATEGORIES:
        assert category.__bases__ == (errors.RaesError,)


def test_every_exception_class_descends_from_the_root_through_one_base():
    allowed = _FOREIGN_TEST_DOUBLES | {("implementations/python/packages/raes_contracts/errors.py", "RaesError")}

    assert _violations(_class_definitions(_source_files(), REPO_ROOT), allowed) == []


def test_the_scan_reports_classes_outside_the_root(tmp_path):
    source = tmp_path / "module.py"
    source.write_text(
        "from raes_contracts.errors import ConflictError, RaesError\n"
        "class Defined(RaesError): pass\n"
        "class Family(ConflictError): pass\n"
        "class Member(Family): pass\n"
        "class Builtin(ValueError): pass\n"
        "class Mixed(Family, ValueError): pass\n"
        "class Foreign(yaml.YAMLError): pass\n",
        encoding="utf-8",
    )
    definitions = _class_definitions([source], tmp_path)
    definitions.append(("raes_contracts/errors.py", "RaesError", ["Exception"]))
    definitions.append(("raes_contracts/errors.py", "ConflictError", ["RaesError"]))

    assert _violations(definitions, frozenset({("raes_contracts/errors.py", "RaesError")})) == [
        "module.py:Builtin does not descend from RaesError",
        "module.py:Mixed has 2 base classes",
        "module.py:Foreign does not descend from RaesError",
    ]


def test_listed_test_doubles_still_exist():
    exceptions, _ = _exception_classes(_class_definitions(_source_files(), REPO_ROOT))
    found = {(path, name) for path, name, _ in exceptions}

    assert found >= _FOREIGN_TEST_DOUBLES
