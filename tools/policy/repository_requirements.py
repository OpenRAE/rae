"""Read the repository's specs-as-code requirements for the existing policy gate."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import yaml
from raes_contracts.errors import InvalidInputError
from yaml.constructor import ConstructorError, SafeConstructor

_UID = re.compile(r"[A-Z]{3}-\d{3,}")
_TRACE = re.compile(r"- ([A-Z][A-Z_]*) → ([A-Z][A-Z_]*) `([^`\n]+)`(?: \([^\n]*\))?")
_MAX_REQUIREMENT_BYTES = 512 * 1024
_GOVERNED_STATUSES = frozenset({"DRAFT", "ACTIVE", "DEPRECATED", "ARCHIVED"})


class RepositoryRequirementError(InvalidInputError):
    """Required local authority was missing, unsafe or malformed."""


class _RequirementLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[object, object]:
        keys = [key.value for key, _ in node.value if isinstance(key, yaml.ScalarNode)]
        if len(keys) != len(node.value) or len(keys) != len(set(keys)):
            raise yaml.YAMLError("Requirement metadata keys must be unique scalars.")
        return super().construct_mapping(node, deep=deep)


# The safe scalar constructors raise these built-in exceptions, not a YAMLError, for a value
# that they cannot build: an integer beyond the interpreter digit limit, an impossible date,
# an empty tagged number, an unknown !!bool word or a !!timestamp value that is not a timestamp.
_SCALAR_CONSTRUCTION_FAILURES: tuple[tuple[str, Callable[..., object], tuple[type[Exception], ...]], ...] = (
    ("tag:yaml.org,2002:int", SafeConstructor.construct_yaml_int, (ValueError, IndexError)),
    ("tag:yaml.org,2002:float", SafeConstructor.construct_yaml_float, (ValueError, IndexError)),
    ("tag:yaml.org,2002:bool", SafeConstructor.construct_yaml_bool, (KeyError,)),
    ("tag:yaml.org,2002:timestamp", SafeConstructor.construct_yaml_timestamp, (ValueError, AttributeError)),
)


def _refusing_scalar_constructor(
    constructor: Callable[..., object],
    construction_failures: tuple[type[Exception], ...],
) -> Callable[[_RequirementLoader, yaml.Node], object]:
    """Report a scalar that the safe constructor cannot build as a constructor error."""

    def construct(loader: _RequirementLoader, node: yaml.Node) -> object:
        try:
            return constructor(loader, node)
        except construction_failures as exc:
            raise ConstructorError(None, None, "scalar value cannot be constructed", node.start_mark) from exc

    return construct


for _tag, _constructor, _failures in _SCALAR_CONSTRUCTION_FAILURES:
    _RequirementLoader.add_constructor(_tag, _refusing_scalar_constructor(_constructor, _failures))


def _metadata(frontmatter: str) -> object:
    depth = 0
    for event in yaml.parse(frontmatter, Loader=yaml.SafeLoader):
        if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
            depth += 1
        elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
            depth -= 1
        if depth > 64 or isinstance(event, yaml.AliasEvent):
            raise yaml.YAMLError("Requirement metadata exceeds its structural bounds.")
    loader = _RequirementLoader(frontmatter)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _governed_requirement(metadata: object, uid: str) -> dict[str, object]:
    """Admit one requirement's identity and governed status from its frontmatter."""

    if not isinstance(metadata, dict) or metadata.get("id") != uid:
        raise RepositoryRequirementError("Requirement metadata does not match its canonical identity.")
    status = metadata.get("status")
    if not isinstance(status, str) or status not in _GOVERNED_STATUSES:
        raise RepositoryRequirementError("Requirement metadata has no valid governed status.")
    return {"id": uid, "uid": uid, "status": status}


class RepositoryRequirementClient:
    """Adapt pinned local records, without weakening any governance predicate."""

    def __init__(self, repo_root: Path) -> None:
        self.root = repo_root.resolve() / "docs" / "requirements"
        self._records: dict[str, tuple[dict[str, object], list[dict[str, object]]]] = {}

    def _load(self, uid: str) -> tuple[dict[str, object], list[dict[str, object]]]:
        if not isinstance(uid, str) or _UID.fullmatch(uid) is None:
            raise RepositoryRequirementError("Requirement identity is not a canonical UID.")
        if uid in self._records:
            return self._records[uid]
        path = self.root / uid / "requirement.md"
        try:
            # Do not follow a substituted directory or file outside its exact
            # authority location, including a symlink to otherwise readable data.
            if path.resolve() != path or path.stat().st_size > _MAX_REQUIREMENT_BYTES:
                raise RepositoryRequirementError("Requirement source is not its bounded canonical file.")
            with path.open("rb") as source:
                raw = source.read(_MAX_REQUIREMENT_BYTES + 1)
            if len(raw) > _MAX_REQUIREMENT_BYTES:
                raise RepositoryRequirementError("Requirement source exceeds its bounded file size.")
            frontmatter, body = self._split(raw.decode("utf-8"))
            requirement = _governed_requirement(_metadata(frontmatter), uid)
            traceability = self._traceability(body)
        except (OSError, UnicodeError, yaml.YAMLError, RecursionError) as exc:
            raise RepositoryRequirementError("Requirement authority cannot be read and validated.") from exc
        self._records[uid] = requirement, traceability
        return requirement, traceability

    @staticmethod
    def _split(document: str) -> tuple[str, str]:
        lines = document.splitlines()
        if not lines or lines[0] != "---":
            raise RepositoryRequirementError("Requirement source has no YAML frontmatter.")
        try:
            end = lines.index("---", 1)
        except ValueError as exc:
            raise RepositoryRequirementError("Requirement frontmatter is not terminated.") from exc
        return "\n".join(lines[1:end]), "\n".join(lines[end + 1 :])

    @staticmethod
    def _traceability(body: str) -> list[dict[str, object]]:
        links = []
        in_traceability = False
        for line in body.splitlines():
            if line.startswith("## "):
                in_traceability = line == "## Traceability"
            if not in_traceability or not line.startswith("- "):
                continue
            match = _TRACE.fullmatch(line)
            if match is None:
                raise RepositoryRequirementError("Requirement traceability contains an invalid link record.")
            link_type, artifact_type, artifact_identifier = match.groups()
            links.append(
                {
                    "link_type": link_type,
                    "artifact_type": artifact_type,
                    "artifact_identifier": artifact_identifier,
                }
            )
        return links

    def get_requirement(self, _project: str, uid: str) -> dict[str, object]:
        # Repository location, not a retired remote project alias, owns this UID.
        return dict(self._load(uid)[0])

    def get_traceability(self, requirement_id: str) -> list[dict[str, object]]:
        return [dict(link) for link in self._load(requirement_id)[1]]
