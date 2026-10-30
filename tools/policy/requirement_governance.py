from __future__ import annotations

import http.client
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from raes_contracts.errors import InvalidInputError, OperationalError

from .common import PolicyFailure, load_yaml, path_matches_any

UID_RE = re.compile(r"\b([A-Z]{3}-\d{3})\b", re.IGNORECASE)
DEFAULT_HTTP_TIMEOUT_SECONDS = 5.0
HTTP_TIMEOUT_ENV = "GC_HTTP_TIMEOUT_SECONDS"
BASE_URL_ENV = "GC_BASE_URL"
_MALFORMED_RESPONSE = "malformed response"
# Name of the environment variable that carries the Ground Control bearer
# credential (matches the MCP server's own GROUND_CONTROL_API_TOKEN). This is an
# env-var name, not a credential value.
BEARER_ENV = "GROUND_CONTROL_API_TOKEN"


class GroundControlError(OperationalError):
    """Base class for Ground Control client failures.

    Ground Control is an external service, so its failures are operational
    failures. Callers that only distinguish "the governance gate could not be
    evaluated" catch this class, while callers that need to tell an auth
    rejection apart from a transport failure catch the specific subclasses
    below. Messages carry the HTTP status or the failure type only, never the
    response body or the text of the transport error.
    """


class GroundControlUnavailable(GroundControlError):
    """The endpoint could not be reached or returned a non-auth error.

    Covers connection refusal, DNS failure, read/connect timeout, and any HTTP
    status other than the auth-rejection codes. Governance was *not* evaluated.
    """


class GroundControlAuthRequired(GroundControlError):
    """The endpoint was reachable but rejected the request for missing/invalid auth.

    Distinct from :class:`GroundControlUnavailable` so a reachable-but-
    unauthenticated Ground Control (HTTP 401/403) is never reported as
    infrastructure downtime.
    """


def _transport_failure(reason: object) -> str:
    """Name a transport failure by its type only; the reason text can carry host details."""

    if isinstance(reason, BaseException):
        return f"connection failed ({type(reason).__name__})"
    return "connection failed"


def resolve_timeout_seconds() -> float:
    """Resolve the HTTP timeout, allowing an env override of the 5s default."""
    raw = os.environ.get(HTTP_TIMEOUT_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_HTTP_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_HTTP_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_HTTP_TIMEOUT_SECONDS


def _mcp_ground_control_env(repo_root: Path) -> dict[str, str]:
    """Return the repo-local ``.mcp.json`` ground-control server env, or {}.

    Missing, unreadable, or malformed ``.mcp.json`` yields an empty mapping so
    resolution falls through to a clear "unset" state rather than raising.
    """
    try:
        data = json.loads((repo_root / ".mcp.json").read_text(encoding="utf-8"))
    # The try holds only the read and the decoder. ValueError covers text that is not UTF-8, malformed
    # JSON and an integer beyond the interpreter digit limit; RecursionError covers excessive nesting.
    except OSError, ValueError, RecursionError:
        return {}
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    server = servers.get("ground-control") if isinstance(servers, dict) else None
    env = server.get("env") if isinstance(server, dict) else None
    if not isinstance(env, dict):
        return {}
    return {str(key): value for key, value in env.items() if isinstance(value, str)}


def _resolve_from_env_or_mcp(repo_root: Path, name: str) -> str | None:
    explicit = os.environ.get(name)
    if explicit and explicit.strip():
        return explicit.strip()
    mcp_value = _mcp_ground_control_env(repo_root).get(name)
    if mcp_value and mcp_value.strip():
        return mcp_value.strip()
    return None


def resolve_base_url(repo_root: Path) -> str | None:
    """Resolve GC_BASE_URL from the environment, then the repo-local .mcp.json.

    There is deliberately no baked-in host default: a hardcoded fallback is
    what let this gate hang against decommissioned infrastructure. Returns None
    when unset so the caller can emit a clear configuration error.
    """
    return _resolve_from_env_or_mcp(repo_root, BASE_URL_ENV)


def resolve_token(repo_root: Path) -> str | None:
    """Resolve the Ground Control API bearer credential from env, then .mcp.json."""
    return _resolve_from_env_or_mcp(repo_root, BEARER_ENV)


_ORDER_POLICY = "tools/policy/requirement_order.yaml"


def load_policy(repo_root: Path) -> dict[str, object]:
    policy = load_yaml(repo_root / _ORDER_POLICY)
    _require_order_policy_shape(policy)
    return policy


def _is_text_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _require_phases_shape(phases: object) -> None:
    if not isinstance(phases, list) or not all(
        isinstance(phase, dict) and isinstance(phase.get("id"), str) for phase in phases
    ):
        raise InvalidInputError(f"{_ORDER_POLICY} phases must be a list of mappings with a text id")
    phase_ids = {phase["id"] for phase in phases}
    for index, phase in enumerate(phases):
        _require_phase_shape(index, phase, phase_ids)


def _require_phase_shape(index: int, phase: dict[str, object], phase_ids: set[str]) -> None:
    for field in ("requirements", "patterns", "blocked_until"):
        if field in phase and not _is_text_list(phase[field]):
            raise InvalidInputError(f"{_ORDER_POLICY} phases[{index}].{field} must be a list of text")
    if not set(phase.get("blocked_until", [])) <= phase_ids:
        raise InvalidInputError(f"{_ORDER_POLICY} phases[{index}].blocked_until names an unknown phase")
    for pattern in phase.get("patterns", []):
        try:
            re.compile(pattern)
        # re.compile reports a malformed pattern, a repetition count beyond its limit and
        # excessive group nesting with these exceptions.
        except (re.error, OverflowError, RecursionError) as exc:
            raise InvalidInputError(f"{_ORDER_POLICY} phases[{index}].patterns has an invalid pattern") from exc


def _require_order_policy_shape(policy: object) -> None:
    """Refuse a requirement order policy whose structure the governance gate cannot read."""

    if not isinstance(policy, dict) or not isinstance(policy.get("project"), str):
        raise InvalidInputError(f"{_ORDER_POLICY} must be a mapping with a text project")
    _require_phases_shape(policy.get("phases", []))
    ownership = policy.get("ownership", {})
    if not isinstance(ownership, dict) or not all(_is_text_list(roots) for roots in ownership.values()):
        raise InvalidInputError(f"{_ORDER_POLICY} ownership must map phases to lists of text")
    traceability = policy.get("traceability")
    if not isinstance(traceability, dict) or not all(
        _is_text_list(traceability.get(field)) for field in ("required_code_roots", "required_test_roots")
    ):
        raise InvalidInputError(f"{_ORDER_POLICY} traceability must have text lists of code and test roots")


class RequirementClient(Protocol):
    def get_requirement(self, project: str, uid: str) -> dict[str, object]: ...

    def get_traceability(self, requirement_id: str) -> list[dict[str, object]]: ...


class GroundControlHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    def _request(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, object] | list[object]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(url, headers={"X-Actor": "repo-policy"})  # noqa: S310 - explicit GC HTTP endpoint
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urlopen(  # noqa: S310 - explicit GC HTTP endpoint
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read()
        except HTTPError as exc:
            # The response body is remote content; only the status code is reported.
            if exc.code in {401, 403}:
                raise GroundControlAuthRequired(f"HTTP {exc.code}") from exc
            raise GroundControlUnavailable(f"HTTP {exc.code}") from exc
        except URLError as exc:
            # A socket read timeout raises TimeoutError, which is NOT a URLError
            # subclass, so it is handled separately below.
            raise GroundControlUnavailable(_transport_failure(exc.reason)) from exc
        except TimeoutError as exc:
            raise GroundControlUnavailable("request timed out") from exc
        except (OSError, http.client.HTTPException) as exc:
            # urlopen wraps only connection failures; a server that disconnects before or
            # while it sends the response raises the socket or HTTP error itself.
            raise GroundControlUnavailable(_transport_failure(exc)) from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError) as exc:
            # The try holds only the decoder. ValueError covers bytes that are not UTF-8, malformed JSON
            # and an integer beyond the interpreter digit limit; RecursionError covers excessive nesting.
            raise GroundControlUnavailable(_MALFORMED_RESPONSE) from exc

    def get_requirement(self, project: str, uid: str) -> dict[str, object]:
        requirement = self._request(f"/api/v1/requirements/uid/{uid}", params={"project": project})
        # The governance gate reads the id, the uid and the text status of each requirement.
        if (
            not isinstance(requirement, dict)
            or not isinstance(requirement.get("status"), str)
            or not {"id", "uid"} <= requirement.keys()
        ):
            raise GroundControlUnavailable(_MALFORMED_RESPONSE)
        return requirement

    def get_traceability(self, requirement_id: str) -> list[dict[str, object]]:
        traceability = self._request(f"/api/v1/requirements/{requirement_id}/traceability")
        if not isinstance(traceability, list) or not all(_is_traceability_link(link) for link in traceability):
            raise GroundControlUnavailable(_MALFORMED_RESPONSE)
        return traceability


# The link fields that the governance gate compares and collects into a set.
_TRACEABILITY_TEXT_FIELDS = (
    "link_type",
    "linkType",
    "artifact_type",
    "artifactType",
    "artifact_identifier",
    "artifactIdentifier",
)


def _is_traceability_link(link: object) -> bool:
    """Return whether a link is an object whose type and identifier fields are text when present."""

    return isinstance(link, dict) and all(
        link.get(field) is None or isinstance(link.get(field), str) for field in _TRACEABILITY_TEXT_FIELDS
    )


@dataclass(frozen=True)
class PhaseMatch:
    phase_id: str
    phase: dict[str, object]


def _traceability_value(link: dict[str, object], snake_case: str, camel_case: str) -> str | None:
    value = link.get(snake_case)
    if value is not None:
        return value
    raw_value = link.get(camel_case)
    return raw_value if isinstance(raw_value, str) else None


def detect_requirement_uid(branch_name: str | None) -> str | None:
    if not branch_name:
        return None
    match = UID_RE.search(branch_name)
    return match.group(1).upper() if match else None


def evaluate_requirement_governance(
    repo_root: Path,
    changed: list[str],
    *,
    client: RequirementClient,
    requirement_uid: str,
) -> list[PolicyFailure]:
    policy = load_policy(repo_root)
    project = policy["project"]
    failures: list[PolicyFailure] = []

    requirement = client.get_requirement(project, requirement_uid)
    status = requirement["status"]
    if status in {"ARCHIVED", "DEPRECATED"}:
        return [
            PolicyFailure(
                "requirement-invalid-status",
                f"{requirement_uid} is {status} and is not valid for implementation work",
            )
        ]

    phase_match = match_phase(policy, requirement_uid)
    if phase_match is None:
        return [
            PolicyFailure(
                "requirement-policy-missing",
                f"{requirement_uid} is not mapped in tools/policy/requirement_order.yaml",
            )
        ]

    failures.extend(_check_phase_predecessors(policy, client, phase_match))
    failures.extend(_check_path_ownership(policy, phase_match, changed, requirement_uid=requirement_uid))
    failures.extend(_check_traceability(client, requirement, policy, changed))

    return failures


def match_phase(policy: dict[str, object], requirement_uid: str) -> PhaseMatch | None:
    for phase in policy.get("phases", []):
        if requirement_uid in phase.get("requirements", []):
            return PhaseMatch(phase["id"], phase)
        for pattern in phase.get("patterns", []):
            if re.match(pattern, requirement_uid):
                return PhaseMatch(phase["id"], phase)
    return None


def _check_phase_predecessors(
    policy: dict[str, object],
    client: RequirementClient,
    match: PhaseMatch,
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    blocked_until = match.phase.get("blocked_until", [])
    project = policy["project"]
    for phase_id in blocked_until:
        phase = next(phase for phase in policy["phases"] if phase["id"] == phase_id)
        if phase.get("manual_release"):
            failures.append(
                PolicyFailure(
                    "requirement-order-blocked",
                    f"{match.phase_id} remains deferred until {phase_id} is explicitly released",
                )
            )
            continue
        incomplete: list[str] = []
        for uid in phase.get("requirements", []):
            status = client.get_requirement(project, uid)["status"]
            if status != "ACTIVE":
                incomplete.append(f"{uid} ({status})")
        if incomplete:
            failures.append(
                PolicyFailure(
                    "requirement-order-blocked",
                    f"{match.phase_id} is blocked until {phase_id} is complete; "
                    f"incomplete prerequisites: {', '.join(incomplete)}",
                )
            )
    return failures


def _check_path_ownership(
    policy: dict[str, object],
    match: PhaseMatch,
    changed: list[str],
    *,
    requirement_uid: str | None = None,
) -> list[PolicyFailure]:
    allowed = policy.get("ownership", {}).get(match.phase_id, [])
    if not allowed:
        return []
    # Contract owners must maintain their traceability in the same change;
    # this grants only the evaluated owner's exact record, never a directory.
    owner_record = f"docs/requirements/{requirement_uid}/requirement.md" if requirement_uid else None
    failures: list[PolicyFailure] = []
    relevant = [path for path in changed if path.startswith(("implementations/", "contracts/", "specs/", "docs/"))]
    for path in relevant:
        if path != owner_record and not path_matches_any(path, allowed):
            failures.append(
                PolicyFailure(
                    "requirement-ownership-mismatch",
                    f"{match.phase_id} changes must stay within the mapped ownership roots for that phase",
                    path,
                )
            )
    return failures


def _linked_artifacts(
    traceability: list[dict[str, object]],
    artifact_type: str,
    link_type: str,
) -> set[str]:
    return {
        artifact_identifier
        for link in traceability
        if _traceability_value(link, "artifact_type", "artifactType") == artifact_type
        and _traceability_value(link, "link_type", "linkType") == link_type
        and (artifact_identifier := _traceability_value(link, "artifact_identifier", "artifactIdentifier")) is not None
    }


def _check_traceability(
    client: RequirementClient,
    requirement: dict[str, object],
    policy: dict[str, object],
    changed: list[str],
) -> list[PolicyFailure]:
    traceability = client.get_traceability(requirement["id"])
    checks = (
        (
            _linked_artifacts(traceability, "CODE_FILE", "IMPLEMENTS"),
            policy["traceability"]["required_code_roots"],
            "traceability-missing-implements",
            f"{requirement['uid']} is missing an IMPLEMENTS traceability link for this code file",
        ),
        (
            _linked_artifacts(traceability, "TEST", "TESTS"),
            policy["traceability"]["required_test_roots"],
            "traceability-missing-tests",
            f"{requirement['uid']} is missing a TESTS traceability link for this test file",
        ),
    )
    failures: list[PolicyFailure] = []
    for path in changed:
        for linked, roots, failure_code, message in checks:
            if path_matches_any(path, roots) and path.endswith(".py") and path not in linked:
                failures.append(PolicyFailure(failure_code, message, path))
    return failures


def requirement_uid_from_context(branch_name: str | None, explicit_uid: str | None) -> str | None:
    return explicit_uid or os.environ.get("RAES_REQUIREMENT_UID") or detect_requirement_uid(branch_name)
