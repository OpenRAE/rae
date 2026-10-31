"""Consumer parse of caller-supplied SDL bytes admits only pinned, locked local imports (#1757, ADR-119).

``data/issue_1757/kit_pack`` is the verbatim ``sdl/`` output of ``raes-pack-kit add``
(env-packs revision 4589b28 with RAES 10.0.0): kit ``infrastructure.git-forge`` 1.2.0,
namespace ``forge``, target ``sdl/demo-pack.sdl.yaml``. Its bytes must not change.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml
from raes import (
    SDLError,
    SDLImportError,
    SDLImportErrorCode,
    SDLParseError,
    SDLParserLimits,
    parse_sdl_file,
    parse_sdl_sources,
)
from raes.module_registry import decode_lockfile, load_lockfile, resolve_lock_records
from raes.scenario import ExpandedScenario, Scenario
from raes_contracts.digests import sha256_digest
from raes_contracts.errors import InvalidInputError

Code = SDLImportErrorCode
_KIT_PACK = Path(__file__).parent / "data" / "issue_1757" / "kit_pack"
_KIT_ROOT = "sdl/demo-pack.sdl.yaml"
_HOST = {"type": "compute", "resources": {"ram": "1 GiB", "cpu": 1}}

# Audit events of host access (Python audit events table). ``os.stat``, ``os.getcwd`` and
# ``os.environ`` reads raise no audit event, so ``_host_access_trapped`` patches them.
_HOST_EVENTS = frozenset(
    {
        "open",
        "os.listdir",
        "os.scandir",
        "os.chdir",
        "os.putenv",
        "os.unsetenv",
        "os.system",
        "os.exec",
        "os.posix_spawn",
        "os.spawn",
        "os.fork",
        "subprocess.Popen",
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "urllib.Request",
    }
)
_TRAPPED: list[str] | None = None


def _audit(event: str, _args: tuple[object, ...]) -> None:
    if _TRAPPED is not None and event in _HOST_EVENTS:
        _TRAPPED.append(event)


sys.addaudithook(_audit)


class _GuardedEnvironment(dict[str, str]):
    def __init__(self, calls: list[str]) -> None:
        super().__init__()
        self._calls = calls

    def __getitem__(self, key: str) -> str:
        self._calls.append("os.environ")
        raise KeyError(key)

    def get(self, key: str, default: object = None) -> object:
        self._calls.append("os.environ")
        return default

    def __contains__(self, key: object) -> bool:
        self._calls.append("os.environ")
        return False


@contextmanager
def _host_access_trapped(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Record every filesystem, network, process and environment access inside the block."""

    global _TRAPPED
    calls: list[str] = []

    def denied(name: str):
        def call(*_args: object, **_kwargs: object) -> object:
            calls.append(name)
            raise PermissionError(name)

        return call

    with monkeypatch.context() as patch:
        for name in ("stat", "lstat", "getcwd", "readlink", "access"):
            patch.setattr(os, name, denied(f"os.{name}"))
        patch.setattr(os, "environ", _GuardedEnvironment(calls))
        _TRAPPED = calls
        try:
            yield calls
        finally:
            _TRAPPED = None


def _kit_sources() -> dict[str, bytes]:
    return {
        path.relative_to(_KIT_PACK).as_posix(): path.read_bytes()
        for path in sorted(_KIT_PACK.rglob("*"))
        if path.is_file()
    }


def _module(name: str, *, imports: list[dict] | None = None, version: str = "1.0.0") -> dict:
    document: dict = {
        "name": name,
        "module": {"id": f"example/{name}", "version": version, "exports": {"nodes": ["vm"]}},
        "nodes": {"vm": _HOST},
    }
    if imports:
        document["imports"] = imports
    return document


def _bytes(document: dict) -> bytes:
    return yaml.safe_dump(document, sort_keys=False).encode("utf-8")


def _import(target: str, namespace: str, target_bytes: bytes, *, version: str = "1.0.0") -> dict:
    return {
        "source": f"local:{target}",
        "namespace": namespace,
        "version": version,
        "digest": sha256_digest(target_bytes),
    }


def _locked(tmp_path: Path, sources: dict[str, bytes], importers: list[str]) -> dict[str, bytes]:
    """Add the lock that the authoring resolver writes beside each importing document."""

    for rel, data in sources.items():
        target = tmp_path.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    locked = dict(sources)
    for importer in importers:
        lock = resolve_lock_records(tmp_path.joinpath(*importer.split("/")))
        directory = importer.rpartition("/")[0]
        lock_path = f"{directory}/raes.lock.json" if directory else "raes.lock.json"
        locked[lock_path] = json.dumps(lock.model_dump(mode="python"), indent=2, sort_keys=True).encode("utf-8")
    return locked


def _simple_pack(tmp_path: Path, **import_overrides: object) -> dict[str, bytes]:
    module = _bytes(_module("web"))
    root = {"name": "pack", "imports": [_import("mods/web.sdl.yaml", "web", module)], "nodes": {"local": _HOST}}
    sources = _locked(tmp_path, {"main.sdl.yaml": _bytes(root), "mods/web.sdl.yaml": module}, ["main.sdl.yaml"])
    if import_overrides:
        root["imports"][0].update(import_overrides)
        root["imports"][0] = {key: value for key, value in root["imports"][0].items() if value is not None}
        sources["main.sdl.yaml"] = _bytes(root)
    return sources


def _lock_records(sources: Mapping[str, bytes], path: str = "raes.lock.json") -> list[dict]:
    return json.loads(sources[path])["imports"]


def _with_records(sources: dict[str, bytes], records: list[dict], path: str = "raes.lock.json") -> dict[str, bytes]:
    return {**sources, path: json.dumps({"schema_version": "raes-lock/v1", "imports": records}).encode("utf-8")}


def _refused(
    monkeypatch: pytest.MonkeyPatch, sources: Mapping[str, bytes], root: str = "main.sdl.yaml", **options: object
) -> SDLImportError:
    with _host_access_trapped(monkeypatch) as calls, pytest.raises(SDLImportError) as caught:
        parse_sdl_sources(sources, root, **options)
    assert calls == []
    return caught.value


@pytest.fixture(autouse=True, scope="module")
def _warm_imports() -> None:
    """Load every lazily imported module before a trap is active.

    A first import reads module files, and Pydantic reads ``PYDANTIC_DISABLE_PLUGINS``
    when it creates a model class. These are one-time effects of each process, not of a
    parse, so the traps apply after this warm-up.
    """

    parse_sdl_sources(_kit_sources(), _KIT_ROOT)
    parse_sdl_sources({"a.yaml": _bytes({"name": "plain", "nodes": {"vm": _HOST}})}, "a.yaml")
    with pytest.raises(SDLImportError):
        parse_sdl_sources(
            {"main.sdl.yaml": _bytes({"name": "x", "imports": [{"source": "oci:r.example/a/b", "namespace": "a"}]})},
            "main.sdl.yaml",
        )


def test_kit_pack_from_raes_pack_kit_add_parses_without_host_access(monkeypatch: pytest.MonkeyPatch) -> None:
    sources = _kit_sources()
    with _host_access_trapped(monkeypatch) as calls:
        scenario = parse_sdl_sources(sources, _KIT_ROOT, migration_policy="accept")
    assert calls == []
    assert isinstance(scenario, ExpandedScenario)
    assert scenario.semantic_validated
    assert "forge.forge" in scenario.nodes
    record = scenario.expansion_provenance.imports[0]
    assert record.resolved_source == "kits/forge/infrastructure.git-forge/1.2.0/module.sdl.yaml"
    assert record.content_digest == _lock_records(sources, "sdl/raes.lock.json")[0]["content_digest"]
    file_backed = parse_sdl_file(_KIT_PACK / _KIT_ROOT)
    assert scenario.model_dump(mode="json") == file_backed.model_dump(mode="json")


def test_root_without_imports_returns_a_validated_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    with _host_access_trapped(monkeypatch) as calls:
        scenario = parse_sdl_sources({"a.yaml": _bytes({"name": "plain", "nodes": {"vm": _HOST}})}, "a.yaml")
    assert calls == []
    assert type(scenario) is Scenario
    assert scenario.semantic_validated


def test_refusal_is_a_typed_sdl_parse_error_with_a_located_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = _refused(monkeypatch, _simple_pack(tmp_path, digest=None))
    assert isinstance(error, SDLParseError)
    assert isinstance(error, SDLError)
    assert isinstance(error, InvalidInputError)
    assert error.code is Code.DIGEST_MISSING
    assert [diagnostic.code for diagnostic in error.diagnostics] == ["sdl.import.digest-missing"]
    assert error.diagnostics[0].pointer == "/imports/0"
    assert error.path == Path("/main.sdl.yaml")


@pytest.mark.parametrize(
    "source",
    [
        "oci:registry.example/acme/hosts",
        "locked:web",
        "https://registry.example/acme/hosts",
        "file:/etc/passwd",
    ],
)
def test_non_local_root_imports_are_refused_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    from raes import module_registry

    def no_request(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("registry request")

    monkeypatch.setattr(module_registry, "_json_request", no_request)
    monkeypatch.setattr(module_registry, "_bytes_request", no_request)
    sources = _simple_pack(tmp_path, source=source)
    sources["raes-trust.yaml"] = b"registries:\n  registry.example:\n    require_signatures: false\n"
    assert _refused(monkeypatch, sources).code is Code.SOURCE_REFUSED


def test_locked_import_that_names_a_local_record_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = _simple_pack(tmp_path, source="locked:local:mods/web.sdl.yaml")
    assert _refused(monkeypatch, sources).code is Code.SOURCE_REFUSED


def test_nested_registry_import_is_refused_at_its_depth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inner = _module(
        "inner", imports=[{"source": "oci:registry.example/acme/x", "namespace": "x", "digest": "sha256:" + "0" * 64}]
    )
    inner_bytes = _bytes(inner)
    root = {"name": "pack", "imports": [_import("mods/inner.sdl.yaml", "inner", inner_bytes)]}
    sources = {"main.sdl.yaml": _bytes(root), "mods/inner.sdl.yaml": inner_bytes}
    record = {
        "source": "local:mods/inner.sdl.yaml",
        "namespace": "inner",
        "requested_version": "1.0.0",
        "resolved_source": "mods/inner.sdl.yaml",
        "module_id": "example/inner",
        "module_version": "1.0.0",
        "manifest_digest": "",
        "content_digest": sha256_digest(inner_bytes),
        "export_hash": _export_hash(tmp_path),
    }
    sources = _with_records(sources, [record])
    error = _refused(monkeypatch, sources)
    assert error.code is Code.SOURCE_REFUSED
    assert error.path == Path("/mods/inner.sdl.yaml")
    assert error.diagnostics[0].pointer == "/imports/0"


def _export_hash(tmp_path: Path) -> str:
    sources = _simple_pack(tmp_path / "export")
    return _lock_records(sources)[0]["export_hash"]


@pytest.mark.parametrize(
    ("digest", "code"),
    [
        (None, Code.DIGEST_MISSING),
        ("", Code.DIGEST_MISSING),
        ("sha256:abc", Code.DIGEST_INVALID),
        ("sha256:" + "A" * 64, Code.DIGEST_INVALID),
        ("0" * 64, Code.DIGEST_INVALID),
        ("sha256:" + "0" * 64, Code.DIGEST_MISMATCH),
    ],
)
def test_root_import_pin_is_mandatory_and_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, digest: str | None, code: SDLImportErrorCode
) -> None:
    assert _refused(monkeypatch, _simple_pack(tmp_path, digest=digest)).code is code


def test_missing_lock_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = _simple_pack(tmp_path)
    del sources["raes.lock.json"]
    assert _refused(monkeypatch, sources).code is Code.LOCK_MISSING


@pytest.mark.parametrize(
    "lock_bytes",
    [
        b"not json",
        b'{"imports": [], "imports": []}',
        b'{"schema_version": "raes-lock/v2", "imports": []}',
        b'{"imports": [{"source": "local:x"}]}',
        b'{"imports": [], "extra": 1}',
        b"[]",
    ],
    ids=["syntax", "duplicate-member", "version", "record-shape", "closed-keys", "not-object"],
)
def test_invalid_lock_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lock_bytes: bytes) -> None:
    sources = {**_simple_pack(tmp_path), "raes.lock.json": lock_bytes}
    assert _refused(monkeypatch, sources).code is Code.LOCK_INVALID


def test_lock_record_must_exist_and_be_unique(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = _simple_pack(tmp_path)
    record = _lock_records(sources)[0]
    other = {**record, "namespace": "other"}
    assert _refused(monkeypatch, _with_records(sources, [other])).code is Code.LOCK_RECORD_MISSING
    assert _refused(monkeypatch, _with_records(sources, [record, dict(record)])).code is Code.LOCK_AMBIGUOUS


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_digest", "sha256:" + "1" * 64),
        ("resolved_source", "mods/other.sdl.yaml"),
        ("module_id", "example/other"),
        ("module_version", "9.9.9"),
        ("export_hash", "0" * 64),
        ("manifest_digest", "sha256:" + "2" * 64),
        ("signer_id", "signer"),
    ],
)
def test_lock_record_must_agree_with_the_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    sources = _simple_pack(tmp_path)
    record = {**_lock_records(sources)[0], field: value}
    assert _refused(monkeypatch, _with_records(sources, [record])).code is Code.LOCK_MISMATCH


def _nested_pack(tmp_path: Path) -> dict[str, bytes]:
    leaf = _bytes(_module("leaf"))
    middle = _bytes(_module("middle", imports=[_import("leaf/leaf.sdl.yaml", "leaf", leaf)]))
    root = {"name": "pack", "imports": [_import("mods/middle.sdl.yaml", "middle", middle)]}
    return _locked(
        tmp_path,
        {"main.sdl.yaml": _bytes(root), "mods/middle.sdl.yaml": middle, "mods/leaf/leaf.sdl.yaml": leaf},
        ["main.sdl.yaml", "mods/middle.sdl.yaml"],
    )


def test_nested_imports_use_the_lock_beside_their_importing_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = _nested_pack(tmp_path)
    with _host_access_trapped(monkeypatch) as calls:
        scenario = parse_sdl_sources(sources, "main.sdl.yaml")
    assert calls == []
    # The middle module exports only its own node, so the admitted leaf node composes as private.
    assert set(scenario.nodes) == {"middle.vm", "middle.__private.leaf.vm"}


def test_nested_import_does_not_inherit_the_root_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = _nested_pack(tmp_path)
    merged = _lock_records(sources) + _lock_records(sources, "mods/raes.lock.json")
    sources = _with_records(sources, merged)
    del sources["mods/raes.lock.json"]
    error = _refused(monkeypatch, sources)
    assert error.code is Code.LOCK_MISSING
    assert error.path == Path("/mods/middle.sdl.yaml")


def test_nested_import_pin_is_mandatory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    leaf = _bytes(_module("leaf"))
    middle = _bytes(_module("middle", imports=[{"source": "local:leaf/leaf.sdl.yaml", "namespace": "leaf"}]))
    root = {"name": "pack", "imports": [_import("mods/middle.sdl.yaml", "middle", middle)]}
    sources = _locked(
        tmp_path,
        {"main.sdl.yaml": _bytes(root), "mods/middle.sdl.yaml": middle, "mods/leaf/leaf.sdl.yaml": leaf},
        ["main.sdl.yaml", "mods/middle.sdl.yaml"],
    )
    error = _refused(monkeypatch, sources)
    assert error.code is Code.DIGEST_MISSING
    assert error.path == Path("/mods/middle.sdl.yaml")


def test_shared_dependency_is_not_a_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _bytes(_module("web"))
    root = {
        "name": "pack",
        "imports": [_import("web.sdl.yaml", "first", module), _import("web.sdl.yaml", "second", module)],
    }
    sources = _locked(tmp_path, {"main.sdl.yaml": _bytes(root), "web.sdl.yaml": module}, ["main.sdl.yaml"])
    with _host_access_trapped(monkeypatch) as calls:
        assert {"first.vm", "second.vm"} <= set(parse_sdl_sources(sources, "main.sdl.yaml").nodes)
    assert calls == []


def test_import_cycle_has_a_code(tmp_path: Path) -> None:
    # A digest pin cannot cover a document that contains its own pin, so cycles occur only without pins.
    for name, other in (("a", "b"), ("b", "a")):
        module = _module(name, imports=[{"source": f"local:{other}.yaml", "namespace": other}])
        (tmp_path / f"{name}.yaml").write_bytes(_bytes(module))
    (tmp_path / "main.yaml").write_bytes(
        _bytes({"name": "root", "imports": [{"source": "local:a.yaml", "namespace": "a"}]})
    )
    with pytest.raises(SDLImportError) as caught:
        parse_sdl_file(tmp_path / "main.yaml")
    assert caught.value.code is Code.CYCLE


@pytest.mark.parametrize(
    ("target", "code"),
    [
        ("../outside.sdl.yaml", Code.PATH_INVALID),
        ("/etc/passwd", Code.PATH_INVALID),
        ("C:/windows/system.ini", Code.PATH_INVALID),
        ("mods/absent.sdl.yaml", Code.SOURCE_MISSING),
    ],
)
def test_import_paths_stay_inside_the_supplied_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, code: SDLImportErrorCode
) -> None:
    sources = _simple_pack(tmp_path, source=f"local:{target}")
    assert _refused(monkeypatch, sources).code is code


@pytest.mark.parametrize(
    "key", ["./main.sdl.yaml", "a//main.sdl.yaml", "/main.sdl.yaml", "a/../main.sdl.yaml", "a\\b", "", "a/"]
)
def test_source_keys_must_be_canonical_relative_paths(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    sources = {key: _bytes({"name": "plain"}), "main.sdl.yaml": _bytes({"name": "plain"})}
    assert _refused(monkeypatch, sources).code is Code.PATH_INVALID


def test_missing_root_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _refused(monkeypatch, {"a.yaml": b"name: a\n"}, "b.yaml").code is Code.SOURCE_MISSING


def test_non_bytes_source_is_a_programming_error() -> None:
    with pytest.raises(TypeError):
        parse_sdl_sources({"a.yaml": "name: a\n"}, "a.yaml")  # type: ignore[dict-item]


def test_sources_are_captured_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = _simple_pack(tmp_path)

    class Shifting(Mapping[str, bytes]):
        reads: dict[str, int] = {}

        def __getitem__(self, key: str) -> bytes:
            self.reads[key] = self.reads.get(key, 0) + 1
            return sources[key] if self.reads[key] == 1 else b"name: replaced\n"

        def __iter__(self) -> Iterator[str]:
            return iter(sources)

        def __len__(self) -> int:
            return len(sources)

    shifting = Shifting()
    with _host_access_trapped(monkeypatch) as calls:
        scenario = parse_sdl_sources(shifting, "main.sdl.yaml")
    assert calls == []
    assert "web.vm" in scenario.nodes
    assert set(shifting.reads.values()) == {1}


def test_materialized_root_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    root = {"name": "m", "materialization_provenance": {}}
    assert _refused(monkeypatch, {"m.yaml": _bytes(root)}, "m.yaml").code is Code.PHASE_REFUSED


def test_import_and_byte_budgets_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _bytes(_module("web"))
    root = {"name": "pack", "imports": [_import("web.sdl.yaml", "a", module), _import("web.sdl.yaml", "b", module)]}
    sources = _locked(tmp_path, {"main.sdl.yaml": _bytes(root), "web.sdl.yaml": module}, ["main.sdl.yaml"])
    limits = SDLParserLimits(max_imports=1)
    assert _refused(monkeypatch, sources, limits=limits).code is Code.BUDGET_EXCEEDED

    padded = {**_simple_pack(tmp_path / "padded")}
    padded["raes.lock.json"] = padded["raes.lock.json"] + b" " * 20_000
    small = SDLParserLimits(max_composed_bytes=10_000)
    assert _refused(monkeypatch, padded, limits=small).code is Code.BUDGET_EXCEEDED


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"version": "2.0.0"}, Code.VERSION_MISMATCH),
        ({"parameters": {"unknown": 1}}, Code.PARAMETER_REFUSED),
    ],
)
def test_ordinary_import_checks_are_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overrides: dict, code: SDLImportErrorCode
) -> None:
    sources = _simple_pack(tmp_path, **overrides)
    record = {**_lock_records(sources)[0]}
    if "version" in overrides:
        record["requested_version"] = overrides["version"]
    assert _refused(monkeypatch, _with_records(sources, [record])).code is code


def test_refusal_messages_do_not_echo_authored_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "SYNTHETIC-SECRET"
    error = _refused(monkeypatch, _simple_pack(tmp_path, source=f"oci:user:{secret}@registry.example/a/b"))
    assert secret not in str(error)
    assert all(secret not in diagnostic.message for diagnostic in error.diagnostics)

    sources = _simple_pack(tmp_path / "lock")
    record = {**_lock_records(sources)[0], "module_id": f"example/{secret}"}
    error = _refused(monkeypatch, _with_records(sources, [record]))
    assert secret not in str(error)


def test_authoring_refusals_carry_codes_with_their_existing_messages(tmp_path: Path) -> None:
    (tmp_path / "main.yaml").write_text(
        yaml.safe_dump({"name": "root", "imports": [{"source": "local:../escape.yaml", "namespace": "x"}]}),
        encoding="utf-8",
    )
    with pytest.raises(SDLImportError, match="escapes base directory") as caught:
        parse_sdl_file(tmp_path / "main.yaml")
    assert caught.value.code is Code.PATH_INVALID


def test_lock_decoder_is_strict_on_the_authoring_path(tmp_path: Path) -> None:
    (tmp_path / "raes.lock.json").write_bytes(b'{"imports": [], "imports": []}')
    with pytest.raises(SDLImportError) as caught:
        load_lockfile(tmp_path)
    assert caught.value.code is Code.LOCK_INVALID
    assert caught.value.path == tmp_path / "raes.lock.json"
    assert decode_lockfile(b'{"imports": []}', path=Path("raes.lock.json")).imports == []


def test_source_context_copies_mutable_bytes_and_refuses_non_virtual_bases() -> None:
    from raes._supplied_sources import SuppliedSources

    buffer = bytearray(b"name: first\n")
    sources = SuppliedSources.capture({"a.yaml": buffer, "b/c.yaml": memoryview(b"name: c\n")})
    buffer[:] = b"name: changed"
    assert sources.root("a.yaml") == (Path("/a.yaml"), b"name: first\n")
    assert sources.resolve(base_dir=Path("/b"), relative="c.yaml") == (Path("/b/c.yaml"), b"name: c\n")
    assert sources.companion(Path("/"), "a.yaml") == b"name: first\n"
    for base_dir in (Path("relative"), Path("/b/../b")):
        with pytest.raises(SDLImportError) as caught:
            sources.resolve(base_dir=base_dir, relative="c.yaml")
        assert caught.value.code is Code.PATH_INVALID
    with pytest.raises(SDLImportError) as caught:
        sources.root("../a.yaml")
    assert caught.value.code is Code.PATH_INVALID


def test_revision_mismatch_on_load_is_typed_and_located(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from raes._source_profile import PROGRESSIVE_SDL_REVISION

    untagged = _bytes(_module("web"))
    root = {
        "name": "pack",
        "semantic_revision": PROGRESSIVE_SDL_REVISION,
        "imports": [_import("mods/web.sdl.yaml", "web", untagged)],
    }
    sources = _locked(tmp_path / "root", {"main.sdl.yaml": _bytes(root), "mods/web.sdl.yaml": untagged}, [])
    error = _refused(monkeypatch, sources)
    assert error.code is Code.REVISION_MISMATCH
    assert (error.path, error.diagnostics[0].pointer) == (Path("/main.sdl.yaml"), "/imports/0")

    leaf = _bytes(_module("leaf"))
    middle_document = {**_module("middle", imports=[_import("leaf/leaf.sdl.yaml", "leaf", leaf)])}
    middle_document["semantic_revision"] = PROGRESSIVE_SDL_REVISION
    middle = _bytes(middle_document)
    root = {
        "name": "pack",
        "semantic_revision": PROGRESSIVE_SDL_REVISION,
        "imports": [_import("mods/middle.sdl.yaml", "middle", middle)],
    }
    files = {"main.sdl.yaml": _bytes(root), "mods/middle.sdl.yaml": middle, "mods/leaf/leaf.sdl.yaml": leaf}
    error = _refused(monkeypatch, _locked(tmp_path / "nested", files, ["main.sdl.yaml"]))
    assert error.code is Code.REVISION_MISMATCH
    assert (error.path, error.diagnostics[0].pointer) == (Path("/mods/middle.sdl.yaml"), "/imports/0")


def test_malformed_lock_is_located_at_its_importing_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = {**_simple_pack(tmp_path / "root"), "raes.lock.json": b"{"}
    error = _refused(monkeypatch, sources)
    assert error.code is Code.LOCK_INVALID
    assert (error.path, error.diagnostics[0].pointer) == (Path("/main.sdl.yaml"), "/imports")

    nested = {**_nested_pack(tmp_path / "nested"), "mods/raes.lock.json": b'{"imports": [], "imports": []}'}
    error = _refused(monkeypatch, nested)
    assert error.code is Code.LOCK_INVALID
    assert (error.path, error.diagnostics[0].pointer) == (Path("/mods/middle.sdl.yaml"), "/imports")
    assert "raes.lock.json" in str(error)
