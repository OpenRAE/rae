"""Tracked-source acquisition and lock-selection discovery."""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from tools.tooling_artifact_policy_common import TOML_SUFFIX, YAML_SUFFIXES, safe_text

ACQUISITION_COMMAND_RE = re.compile(
    r"(?:^|[;&|('\"\n]\s*)(?:command\s+)?(?:sudo\s+)?(?:curl|wget)\b"
    r"|(?:^|[;&|('\"\n]\s*)(?:command\s+)?(?:gh\s+release\s+download|git\s+clone)\b"
    r"|(?:^|[;&|('\"\n]\s*)(?:command\s+)?(?:uv\s+(?:tool|pip)\s+install|pip(?:3)?\s+install)\b"
    r"|(?:^|[;&|('\"\n]\s*)(?:command\s+)?(?:docker|podman)\s+pull\b"
    r"|(?:^|[;&|('\"\n]\s*)(?:command\s+)?skopeo\s+copy\b",
    re.MULTILINE,
)
SCANNED_SUFFIXES = frozenset({".py", ".sh", ".bash", ".ps1", *YAML_SUFFIXES, TOML_SUFFIX})
SCANNED_NAMES = frozenset({"Dockerfile", "Makefile"})
NETWORK_CALLS = frozenset(
    {
        "http.client.HTTPConnection",
        "http.client.HTTPSConnection",
        "tools.http_download.download_bytes",
        "urllib.request.urlopen",
    }
)
REQUEST_CALLS = frozenset(
    {
        "aiohttp.request",
        "httpx.get",
        "httpx.request",
        "httpx.stream",
        "requests.get",
        "requests.request",
    }
)
SELECTION_CALL = "tools.tooling_policy_gate.load_tooling_artifact_selection"
REQUIRED_SELECTION_KEYWORDS = frozenset({"artifact_id", "version", "platform_id", "profile_id"})


@dataclass(frozen=True)
class PythonScan:
    selected_artifact_ids: frozenset[str]
    selection_calls_valid: bool
    acquisition_count: int
    parsed: bool
    unknown_executable_count: int


def ast_name(node: ast.AST) -> str | None:
    name = None
    if isinstance(node, ast.Name):
        name = node.id
    elif isinstance(node, ast.Attribute):
        parent = ast_name(node.value)
        name = f"{parent}.{node.attr}" if parent else node.attr
    return name


def _node_aliases(node: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    if isinstance(node, ast.Import):
        aliases = {
            alias.asname or alias.name.split(".", maxsplit=1)[0]: (
                alias.name if alias.asname else alias.name.split(".", maxsplit=1)[0]
            )
            for alias in node.names
        }
    elif isinstance(node, ast.ImportFrom) and node.module:
        aliases = {alias.asname or alias.name: f"{node.module}.{alias.name}" for alias in node.names}
    return aliases


def _aliases(nodes: Sequence[ast.AST]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in nodes:
        aliases.update(_node_aliases(node))
    return aliases


def _resolved_name(name: str, aliases: Mapping[str, str]) -> str:
    first, separator, remainder = name.partition(".")
    return f"{aliases[first]}.{remainder}" if separator and first in aliases else aliases.get(first, name)


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {target.id for target in targets if isinstance(target, ast.Name)}


def _assigned_selection_names(node: ast.AST, aliases: Mapping[str, str]) -> set[str]:
    assigned: set[str] = set()
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        value_name = ast_name(node.value) if node.value is not None else None
        if value_name is not None and _resolved_name(value_name, aliases) == SELECTION_CALL:
            assigned = _assigned_names(node)
    return assigned


def _selection_aliases(nodes: Sequence[ast.AST], aliases: Mapping[str, str]) -> set[str]:
    selection_aliases: set[str] = set()
    for node in nodes:
        selection_aliases.update(_assigned_selection_names(node, aliases))
    return selection_aliases


def _is_selection_call(
    node: ast.AST,
    aliases: Mapping[str, str],
    selection_aliases: set[str],
) -> bool:
    if not isinstance(node, ast.Call) or (call_name := ast_name(node.func)) is None:
        return False
    return _resolved_name(call_name, aliases) == SELECTION_CALL or call_name in {
        "load_tooling_artifact_selection",
        *selection_aliases,
    }


def _selection_call_observation(
    node: ast.AST,
    aliases: Mapping[str, str],
    selection_aliases: set[str],
) -> tuple[str | None, bool] | None:
    if not _is_selection_call(node, aliases, selection_aliases):
        return None
    assert isinstance(node, ast.Call)
    keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg is not None}
    artifact_node = keywords.get("artifact_id")
    complete = keywords.keys() >= REQUIRED_SELECTION_KEYWORDS and "policy_root" not in keywords
    literal = isinstance(artifact_node, ast.Constant) and isinstance(artifact_node.value, str)
    artifact_id = artifact_node.value if complete and literal else None
    return artifact_id, complete and literal


def _selection_observation(
    nodes: Sequence[ast.AST],
    aliases: Mapping[str, str],
) -> tuple[frozenset[str], bool]:
    artifact_ids: set[str] = set()
    valid = True
    selection_aliases = _selection_aliases(nodes, aliases)
    for node in nodes:
        observation = _selection_call_observation(node, aliases, selection_aliases)
        if observation is None:
            continue
        artifact_id, call_is_valid = observation
        valid = valid and call_is_valid
        if artifact_id is not None:
            artifact_ids.add(artifact_id)
    return frozenset(artifact_ids), valid


def is_command_executor(call_name: str) -> bool:
    fixed = call_name in {
        "os.system",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.run",
    }
    receiver, separator, method = call_name.rpartition(".")
    session_run = (
        separator == "." and method == "run" and receiver.rsplit(".", maxsplit=1)[-1] in {"nox_session", "session"}
    )
    return fixed or session_run


def _callable_aliases(nodes: Sequence[ast.AST], aliases: Mapping[str, str]) -> dict[str, str]:
    callable_aliases: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value_name = ast_name(node.value) if node.value is not None else None
        resolved = _resolved_name(value_name, aliases) if value_name is not None else ""
        if is_command_executor(resolved) or resolved in NETWORK_CALLS:
            callable_aliases.update(dict.fromkeys(_assigned_names(node), resolved))
    return callable_aliases


def _url_openers(nodes: Sequence[ast.AST], aliases: Mapping[str, str]) -> set[str]:
    openers: set[str] = set()
    for node in nodes:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(node.value, ast.Call):
            continue
        factory_name = ast_name(node.value.func)
        if factory_name is not None and _resolved_name(factory_name, aliases) == "urllib.request.build_opener":
            openers.update(_assigned_names(node))
    return openers


def command_tokens(call: ast.Call) -> list[str | None]:
    arguments: Sequence[ast.AST] = (
        call.args[0].elts if call.args and isinstance(call.args[0], (ast.List, ast.Tuple)) else call.args
    )
    tokens: list[str | None] = []
    for argument in arguments:
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            tokens.append(argument.value)
        elif ast_name(argument) == "sys.executable":
            tokens.append("python")
        else:
            tokens.append(None)
    return tokens


def _normalized_command_tokens(tokens: Sequence[str | None]) -> list[str | None]:
    literals = [token.lower() if token is not None else None for token in tokens]
    while literals and literals[0] in {"command", "sudo"}:
        literals.pop(0)
    if literals and literals[0] is not None:
        literals[0] = literals[0].rsplit("/", maxsplit=1)[-1]
    return literals


def tokens_are_acquisition(tokens: Sequence[str | None]) -> bool:
    literals = _normalized_command_tokens(tokens)
    sequences = (
        ("gh", "release", "download"),
        ("git", "clone"),
        ("uv", "tool", "install"),
        ("uv", "pip", "install"),
        ("pip", "install"),
        ("pip3", "install"),
        ("docker", "pull"),
        ("podman", "pull"),
        ("skopeo", "copy"),
    )
    direct = bool(literals) and (literals[0] in {"curl", "wget"} or len(literals) >= 2 and literals[1] == "pull")
    return direct or any(tuple(literals[: len(sequence)]) == sequence for sequence in sequences)


def tokens_have_unknown_acquisition(tokens: Sequence[str | None]) -> bool:
    literals = _normalized_command_tokens(tokens)
    required_prefixes = {
        "docker": 1,
        "gh": 2,
        "git": 1,
        "pip": 1,
        "pip3": 1,
        "podman": 1,
        "skopeo": 1,
        "uv": 2,
    }
    executable = literals[0] if literals else None
    prefix_length = required_prefixes.get(executable) if executable is not None else None
    return (
        not literals
        or executable is None
        or prefix_length is not None
        and (len(literals) <= prefix_length or any(token is None for token in literals[1 : prefix_length + 1]))
    )


def _is_nested_opener_call(node: ast.Call, aliases: Mapping[str, str]) -> bool:
    if (
        not isinstance(node.func, ast.Attribute)
        or node.func.attr != "open"
        or not isinstance(node.func.value, ast.Call)
    ):
        return False
    factory_name = ast_name(node.func.value.func)
    return factory_name is not None and _resolved_name(factory_name, aliases) == "urllib.request.build_opener"


def _is_network_call(call_name: str, resolved_name: str, aliases: Mapping[str, str], openers: set[str]) -> bool:
    return bool(
        resolved_name in NETWORK_CALLS
        or resolved_name.endswith(".open")
        and resolved_name.removesuffix(".open") in openers
        or call_name.partition(".")[0] in aliases
        and resolved_name in REQUEST_CALLS
    )


def _command_observation(node: ast.Call, resolved_name: str) -> tuple[int, int]:
    if not is_command_executor(resolved_name):
        return 0, 0
    tokens = command_tokens(node)
    literal_command = tokens[0] if len(tokens) == 1 else None
    acquisition = tokens_are_acquisition(tokens) or bool(
        literal_command is not None and ACQUISITION_COMMAND_RE.search(literal_command)
    )
    return int(acquisition), int(not acquisition and tokens_have_unknown_acquisition(tokens))


def _acquisition_observation(nodes: Sequence[ast.AST], aliases: dict[str, str]) -> tuple[int, int]:
    aliases.update(_callable_aliases(nodes, aliases))
    openers = _url_openers(nodes, aliases)
    acquisition_count = 0
    unknown_count = 0
    for node in nodes:
        if not isinstance(node, ast.Call) or (call_name := ast_name(node.func)) is None:
            continue
        resolved_name = _resolved_name(call_name, aliases)
        if _is_nested_opener_call(node, aliases) or _is_network_call(call_name, resolved_name, aliases, openers):
            acquisition_count += 1
            continue
        acquisitions, unknown = _command_observation(node, resolved_name)
        acquisition_count += acquisitions
        unknown_count += unknown
    return acquisition_count, unknown_count


def python_scan(text: str) -> PythonScan:
    """Parse one Python source once and derive every discovery projection."""

    try:
        nodes = tuple(ast.walk(ast.parse(text)))
    except (SyntaxError, ValueError):
        return PythonScan(frozenset(), False, 0, False, 0)
    aliases = _aliases(nodes)
    artifact_ids, selection_valid = _selection_observation(nodes, aliases)
    acquisition_count, unknown_count = _acquisition_observation(nodes, aliases)
    return PythonScan(artifact_ids, selection_valid, acquisition_count, True, unknown_count)


def structured_acquisition(text: str, path: str) -> tuple[int, bool, int]:
    suffix = Path(path).suffix
    parsed = True
    if suffix == ".py":
        scan = python_scan(text)
        return scan.acquisition_count, scan.parsed, scan.unknown_executable_count
    try:
        if suffix in YAML_SUFFIXES:
            yaml.safe_load(text)
        elif suffix == TOML_SUFFIX:
            tomllib.loads(text)
    except (yaml.YAMLError, tomllib.TOMLDecodeError):
        parsed = False
    return len(ACQUISITION_COMMAND_RE.findall(text)) if parsed else 0, parsed, 0


def tracked_python_scans(repo_root: Path, tracked_paths: Sequence[str]) -> dict[str, PythonScan | None]:
    scans: dict[str, PythonScan | None] = {}
    for path in tracked_paths:
        if Path(path).suffix != ".py":
            continue
        text = safe_text(repo_root, path)
        scans[path] = None if text is None else python_scan(text)
    return scans


def is_acquisition_scan_candidate(path: str) -> bool:
    candidate = Path(path)
    if candidate.suffix in YAML_SUFFIXES:
        return (
            path.startswith(".github/workflows/")
            or candidate.name in {"action.yaml", "action.yml", ".pre-commit-config.yaml"}
            or path == ".ground-control.yaml"
        )
    return candidate.suffix in SCANNED_SUFFIXES or candidate.name in SCANNED_NAMES
