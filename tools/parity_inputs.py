"""CI-only pytest collector of inputs at the public parity boundaries (#1778).

Calls retain their original result and exceptions. No product implementation is
changed. This module is inert unless RAES_PARITY_INPUT_DIR is explicitly set.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import stat
import tempfile
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import pytest

from tools.parity_support import ARGUMENTS_FILE, Case, digest, encode, runtime_aliases

INPUT_PREFIX = "input/"


def capture_path(path: Path, base: Path) -> str:
    """Keep graph paths while removing pytest's generated run location."""
    relative = path.relative_to(base).as_posix()
    temporary = Path(tempfile.gettempdir())
    parts = path.relative_to(temporary).parts if path.is_relative_to(temporary) else ()
    if (
        len(parts) < 2
        or not re.fullmatch(r"pytest-of-[^/]+", parts[0])
        or not re.fullmatch(r"pytest-\d+", parts[1], flags=re.ASCII)
    ):
        return relative
    count = 3 if len(parts) >= 3 and re.fullmatch(r"popen-gw\d+", parts[2], flags=re.ASCII) else 2
    generated = temporary.joinpath(*parts[:count])
    if not generated.is_relative_to(base):
        return relative
    canonical = temporary / "pytest-user" / "pytest-session"
    if count == 3:
        canonical /= "pytest-worker"
    visible = generated.relative_to(base).parts
    prefix = canonical.parts[-len(visible) :] if visible else ()
    return Path(*prefix, *path.relative_to(generated).parts).as_posix()


def absolute_input(directory: Path, value: str) -> Path:
    return Path(os.path.abspath(directory / value))


def command_tokens(arguments: str | Sequence[object] | None) -> list[str]:
    supplied = shlex.split(arguments) if isinstance(arguments, str) else [str(value) for value in (arguments or [])]
    tokens: list[str] = []
    positional = False
    for argument in supplied:
        if not positional and argument.startswith("--") and "=" in argument:
            tokens.extend(argument.split("=", 1))
        else:
            tokens.append(argument)
        positional = positional or argument == "--"
    return tokens


def relocated_token(
    token: str,
    directory: Path,
    names: dict[Path, str],
    base: Path,
) -> str:
    resolved = absolute_input(directory, token)
    value = token
    if resolved in names:
        value = names[resolved]
    elif Path(token).is_absolute():
        relative = capture_path(resolved, base) if resolved.is_relative_to(base) else "output/" + resolved.name
        value = INPUT_PREFIX + relative
    return value


def source_names(originals: dict[Path, bytes], roots: list[Path]) -> tuple[Path, dict[Path, str]]:
    parents = [str(path.parent) for path in originals] + [str(root) for root in roots]
    base = Path(os.path.commonpath(parents)) if parents else Path.cwd()
    names = {path: INPUT_PREFIX + capture_path(path, base) for path in (*originals, *roots)}
    if len(set(names.values())) != len(names):
        raise ValueError("parity path normalization would merge distinct inputs")
    return base, names


def portable_files(
    originals: dict[Path, bytes],
    recipes: dict[Path, dict[str, str]],
    roots: list[Path],
    names: dict[Path, str],
) -> dict[str, bytes]:
    files = {names[path]: content for path, content in originals.items() if path not in recipes}
    if recipes:
        files["input-recipes.json"] = encode({names[path]: recipe for path, recipe in recipes.items()})
    if roots:
        files["setup.json"] = encode({"directories": [names[root] for root in roots]})
    return files


class InputCollector:
    """Own one pytest worker's observed inputs and their source test identities."""

    def __init__(self, root: Path, repo: Path) -> None:
        self.root = root
        self.repo = repo
        self.nodeid = "collection"
        self.tests: set[str] = set()
        self.collected_tests: set[str] = set()
        self.expected_tests: set[str] = set()
        self.non_protocol_tests: set[str] = set()
        self.records: dict[str, dict[str, object]] = {}
        self.blobs: dict[str, bytes] = {}
        self.lock = RLock()
        self.patches = pytest.MonkeyPatch()
        self.id_counts: dict[str, int] = {}
        self.key_counts: dict[str, int] = {}
        self.key_seeds: dict[bytes, str] = {}
        self.aliases_to_restore: list[tuple[object, object]] = []

    def add(self, case: Case) -> None:
        if self.nodeid == "collection":
            return
        files = {name: "sha256:" + digest(content) for name, content in sorted(case.files.items())}
        record = {
            "surface": case.surface,
            "command": case.command,
            "args": list(case.args),
            "files": files,
        }
        identity = digest(encode(record))
        with self.lock:
            stored = self.records.setdefault(identity, {**record, "tests": set()})
            stored["tests"].add(self.nodeid)
            for content in case.files.values():
                self.blobs[digest(content)] = content

    def source(self, content: str, **options: object) -> None:
        arguments = {
            "sdl_content": content,
            "semantic_validation": not options.get("skip_semantic_validation", False),
        }
        arguments["accept_migration_syntax"] = str(options.get("migration_policy", "reject")) in {
            "accept",
            "SDLMigrationPolicy.ACCEPT",
        }
        try:
            content = encode(arguments)
        except ValueError:
            self.non_protocol_tests.add(self.nodeid)
            return
        self.add(Case("mcp", "sdl_parse", "", (), {ARGUMENTS_FILE: content}))

    def allowed_input(self, path: Path) -> bool:
        return path.is_relative_to(self.repo) or path.is_relative_to(Path(tempfile.gettempdir()))

    def regular_input(self, path: Path) -> Path | None:
        absolute = Path(os.path.abspath(path))
        if not self.allowed_input(absolute):
            return None
        try:
            for candidate in reversed((absolute, *absolute.parents)):
                if candidate.is_symlink():
                    raise ValueError("parity input collection refuses symbolic links")
            mode = absolute.lstat().st_mode
        except OSError:
            return None
        return absolute if stat.S_ISREG(mode) else None

    def key_recipe(self, content: bytes) -> dict[str, str]:
        from cryptography.exceptions import UnsupportedAlgorithm
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        try:
            key = serialization.load_pem_private_key(content, password=None)
        except ValueError, TypeError, UnsupportedAlgorithm:
            key = None
        recipe = {"kind": "invalid-key"}
        if isinstance(key, Ed25519PrivateKey):
            public = key.public_key().public_bytes_raw()
            if public not in self.key_seeds:
                raise ValueError("a signing key was not generated by the deterministic CI fixture")
            recipe = {"kind": "public-test-ed25519", "seed_id": self.key_seeds[public]}
        return recipe

    def candidate_input(self, path: Path) -> tuple[bytes | None, dict[str, str] | None]:
        """Inspect only regular files under explicitly allowed CI input roots."""
        absolute = self.regular_input(path)
        if absolute is None:
            return None, None
        content = absolute.read_bytes()
        if b"PRIVATE KEY-----" in content:
            return b"", self.key_recipe(content)
        return content, None

    @staticmethod
    def directory_inputs(root: Path) -> list[Path]:
        files = []
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("parity input collection refuses symbolic links")
            if path.suffix in {".json", ".yaml", ".yml"}:
                files.append(path)
        return files

    def conformance_inputs(self, command: str, tokens: list[str], directory: Path) -> tuple[list[Path], list[Path]]:
        roots, files = [], []
        if command != "conformance backend":
            return roots, files
        for option, default in (
            ("--fixtures-root", self.repo / "contracts/fixtures"),
            ("--profiles-root", self.repo / "contracts/profiles/backend"),
        ):
            if option not in tokens:
                tokens.extend([option, str(default)])
            position = tokens.index(option) + 1
            if position >= len(tokens):
                continue
            root = absolute_input(directory, tokens[position])
            if self.allowed_input(root):
                self.candidate_input(root)
                if root.is_dir():
                    roots.append(root)
                    files.extend(self.directory_inputs(root))
        return roots, files

    def input_graph(self, pending: list[Path]) -> tuple[dict[Path, bytes], dict[Path, dict[str, str]]]:
        from tools.parity_surfaces import local_dependencies

        originals: dict[Path, bytes] = {}
        recipes = {}
        while pending:
            path = pending.pop()
            if path in originals:
                continue
            content, recipe = self.candidate_input(path)
            if content is not None:
                originals[path] = content
                if recipe is not None:
                    recipes[path] = recipe
                if path.suffix in {".yaml", ".yml"}:
                    pending.extend(local_dependencies(path, content))
        return originals, recipes

    def cli(
        self,
        arguments: str | Sequence[object] | None,
        kwargs: dict[str, object],
        *,
        working_directory: str | bytes | os.PathLike[str] | None = None,
    ) -> None:
        directory = Path(os.fsdecode(working_directory)) if working_directory is not None else Path.cwd()
        tokens = command_tokens(arguments)
        command = self.command(tokens)
        roots, directory_files = self.conformance_inputs(command, tokens, directory)
        pending = [absolute_input(directory, token) for token in tokens if not token.startswith("-")] + directory_files
        originals, recipes = self.input_graph(pending)
        base, names = source_names(originals, roots)
        files = portable_files(originals, recipes, roots, names)
        rewritten = [relocated_token(token, directory, names, base) for token in tokens]
        supplied = kwargs.get("input")
        if supplied is not None:
            files["stdin.bin"] = supplied.encode() if isinstance(supplied, str) else bytes(supplied)
        if command:
            self.add(Case("cli", command, "", tuple(rewritten), files))

    @staticmethod
    def command(tokens: list[str]) -> str:
        from tools.parity_surfaces import cli_registry

        registry = cli_registry()
        root_options = {option: parameter for parameter in registry[""] for option in parameter.get("opts", [])}
        start = 0
        while start < len(tokens) and tokens[start].startswith("-"):
            parameter = root_options.get(tokens[start])
            if parameter is None or parameter["name"] == "version":
                return "root"
            start += 1 + (0 if parameter.get("is_flag") else parameter.get("nargs", 1))
        matches = [name for name in registry if name and tokens[start : start + len(name.split())] == name.split()]
        return max(matches, key=len, default="root")

    def install(self) -> None:
        # FastMCP configures the root logger during registry discovery. Discovery
        # must not change the handlers or levels that the tests are verifying.
        root = logging.root
        handlers, level = root.handlers[:], root.level
        try:
            self._install()
        finally:
            root.handlers[:] = handlers
            root.setLevel(level)

    def close(self) -> None:
        from hypothesis import settings

        self.patches.undo()
        for replacement, original in self.aliases_to_restore:
            for module, attribute in runtime_aliases(replacement):
                setattr(module, attribute, original)
        settings.load_profile(self.previous_profile)

    def patch_aliases(self, original: Callable[..., object], replacement: Callable[..., object]) -> None:
        for module, attribute in runtime_aliases(original):
            self.patches.setattr(module, attribute, replacement)
        self.aliases_to_restore.append((replacement, original))

    def fixture_uuid(self) -> uuid.UUID:
        with self.lock:
            serial = self.id_counts.get(self.nodeid, 0)
            self.id_counts[self.nodeid] = serial + 1
        return uuid.UUID(hex=digest(f"parity/{self.nodeid}/{serial}".encode())[:32], version=4)

    def fixture_key(self) -> Ed25519PrivateKey:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        with self.lock:
            serial = self.key_counts.get(self.nodeid, 0)
            self.key_counts[self.nodeid] = serial + 1
        seed_id = f"public-parity-fixture/{self.nodeid}/{serial}"
        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(digest(seed_id.encode())))
        self.key_seeds[key.public_key().public_bytes_raw()] = seed_id
        return key

    def _install(self) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from hypothesis import settings

        from tools import parity_observers as observers
        from tools.parity_surfaces import (
            cli_registry,
            http_registry,
            http_schema,
            mcp_registry,
        )

        self.previous_profile = settings.get_current_profile_name()
        settings.register_profile("parity-capture", derandomize=True, database=None)
        settings.load_profile("parity-capture")
        # Discover registries before tests can mock them, or observers can record them.
        cli_registry()
        tools = set(mcp_registry())
        routes = http_registry(http_schema())
        models = observers.published_models(self)
        original_uuid = uuid.uuid4
        fixture_uuid = self.fixture_uuid
        observers.install_parsing(self)
        self.patch_aliases(original_uuid, fixture_uuid)
        observers.install_models(self, models)
        observers.install_schema_validation(self, models)
        self.patches.setattr(uuid, "uuid4", fixture_uuid)
        self.patches.setattr(Ed25519PrivateKey, "generate", staticmethod(self.fixture_key))
        observers.install_cli(self)
        observers.install_mcp(self, tools)
        observers.install_http(self, routes)

    def write(self, worker: str) -> None:
        from tools.parity_regressions import source_identity

        with self.lock:
            records = {key: {**value, "tests": sorted(value["tests"])} for key, value in sorted(self.records.items())}
            document = {
                "schema": "raes-parity-inputs/v1",
                "worker": worker,
                "tests": sorted(self.tests),
                "collected_tests": sorted(self.collected_tests),
                "expected_tests": sorted(self.expected_tests or self.collected_tests),
                "non_protocol_tests": sorted(self.non_protocol_tests),
                "source_identity": source_identity(self.repo),
                "inputs": records,
            }
            self.root.mkdir(parents=True, exist_ok=True)
            for identity, content in self.blobs.items():
                path = self.root / "blobs" / identity
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            (self.root / (worker + ".json")).write_bytes(encode(document))


def pytest_configure(config: pytest.Config) -> None:
    output = os.environ.get("RAES_PARITY_INPUT_DIR")
    if not output:
        return
    repo = Path(__file__).resolve().parents[1]
    collector = InputCollector(Path(output), repo)
    collector.install()
    config._parity_input_collector = collector


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    collector = getattr(item.config, "_parity_input_collector", None)
    if collector is not None:
        collector.nodeid = item.nodeid
        collector.tests.add(item.nodeid)


def pytest_sessionfinish(session: pytest.Session) -> None:
    collector = getattr(session.config, "_parity_input_collector", None)
    if collector is not None:
        worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
        shard = os.environ.get("RAES_PARITY_SHARD_INDEX", "0")
        collector.write("shard-" + shard + "-" + worker)
        collector.close()


def pytest_collection_finish(session: pytest.Session) -> None:
    collector = getattr(session.config, "_parity_input_collector", None)
    if collector is not None:
        collector.collected_tests.update(item.nodeid for item in session.items)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    collector = getattr(config, "_parity_input_collector", None)
    if collector is not None:
        collector.expected_tests.update(item.nodeid for item in items)
