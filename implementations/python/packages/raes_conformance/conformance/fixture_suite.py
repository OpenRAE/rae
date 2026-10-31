"""Fixture-corpus conformance suite runner."""

from __future__ import annotations

import json
from pathlib import Path

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import schema_bundle
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.digests import sha256_digest
from raes_contracts.errors import OperationalError

from raes_conformance.conformance.diagnostics import _diagnostic, sanitized_failure_message
from raes_conformance.conformance.profiles import (
    BackendProfileSelector,
    _fixture_contract_root,
    _resolve_required_contracts,
    _to_profile_id,
    fixtures_root,
)
from raes_conformance.conformance.report import (
    BackendConformanceReport,
    ConformanceCaseResult,
    _bounded_conformance_claim,
    conformance_tool_version,
    contract_content_digests,
)
from raes_conformance.conformance.semantics import _fixture_case_diagnostics
from raes_conformance.conformance.validators import _SCHEMA_INVALID_DIAGNOSTIC_CODE

_FIXTURE_UNREADABLE = "conformance fixture could not be read"


def _read_fixture(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        # An unreadable file is a corpus or host failure, not a rejected payload, so the whole run fails.
        raise OperationalError(_FIXTURE_UNREADABLE) from exc


def _payload_invalid(contract_name: str, reason: str) -> Diagnostic:
    """Return the refusal that a fixture payload which fails contract validation gets."""

    return _diagnostic(
        _SCHEMA_INVALID_DIAGNOSTIC_CODE,
        contract_name,
        f"{contract_name} failed contract validation: {reason}",
    )


def _fixture_case(contract_name: str, path: Path, *, valid: bool) -> ConformanceCaseResult:
    """Check one fixture file; a file that does not decode as JSON is an invalid payload, like any other.

    Raise ``OperationalError`` when the file cannot be read.
    """

    raw = _read_fixture(path)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        case_diagnostics = [_payload_invalid(contract_name, sanitized_failure_message(exc))]
    except ValueError, RecursionError:
        # The decoder raises a plain ValueError beyond the integer digit limit and RecursionError beyond its depth.
        case_diagnostics = [_payload_invalid(contract_name, "payload exceeds the JSON decoder limits")]
    else:
        case_diagnostics = _fixture_case_diagnostics(contract_name, payload)
    return ConformanceCaseResult(
        name=path.stem,
        contract_name=contract_name,
        valid=valid,
        passed=not case_diagnostics if valid else bool(case_diagnostics),
        diagnostics=tuple(case_diagnostics),
        probe_digest=sha256_digest(raw),
        evidence_refs=(f"fixture:{contract_name}:{'valid' if valid else 'invalid'}:{path.stem}:{sha256_digest(raw)}",),
    )


def run_fixture_suite(
    *,
    profile: BackendProfileSelector,
    root: Path | None = None,
    profiles_root: Path | None = None,
) -> BackendConformanceReport:
    """Run the checked-in fixture corpus for a backend profile.

    ``root`` overrides the fixtures tree (defaults to ``contracts/fixtures``);
    ``profiles_root`` overrides the backend profile tree (defaults to
    ``contracts/profiles/backend``). Both default to the canonical
    ``contracts/`` paths so the published artifacts remain the authority.
    A fixture file that cannot be read raises ``OperationalError``, so a
    broken corpus fails the whole run instead of producing a report.
    """

    root = fixtures_root() if root is None else root
    bundle = schema_bundle()
    profile_evidence: dict[str, object] = {}
    required, profile_diagnostics = _resolve_required_contracts(
        profile, profiles_root=profiles_root, evidence=profile_evidence
    )
    cases: list[ConformanceCaseResult] = []
    diagnostics: list[Diagnostic] = list(profile_diagnostics)

    for contract_name in sorted(required):
        contract_root = _fixture_contract_root(root, contract_name)
        valid_dir = contract_root / "valid"
        invalid_dir = contract_root / "invalid"
        valid_paths = sorted(valid_dir.glob("*.json"))
        if not valid_paths:
            diagnostics.append(
                _diagnostic(
                    "conformance.fixture-missing",
                    contract_name,
                    f"Missing valid fixture directory for {contract_name}.",
                )
            )

        cases.extend(_fixture_case(contract_name, path, valid=True) for path in valid_paths)
        if invalid_dir.exists():
            cases.extend(_fixture_case(contract_name, path, valid=False) for path in sorted(invalid_dir.glob("*.json")))

    profile_id = _to_profile_id(profile)
    case_tuple = tuple(cases)
    return BackendConformanceReport(
        profile=profile_id,
        passed=not diagnostics and all(case.passed for case in cases),
        claim=_bounded_conformance_claim(
            profile=profile_id,
            cases=case_tuple,
            left_carrier_ref=f"conformance-fixture-suite:{profile_id}",
        ),
        cases=case_tuple,
        contract_versions={name: str(schema.get("title", name)) for name, schema in bundle.items() if name in required},
        diagnostics=tuple(diagnostics),
        profile_version=profile_evidence.get("version"),
        profile_digest=profile_evidence.get("digest"),
        tool_version=conformance_tool_version(),
        contract_digests=contract_content_digests(
            {name: schema for name, schema in bundle.items() if name in required}
        ),
        required_case_refs=tuple(f"conformance-case:{case.contract_name}:{case.name}" for case in case_tuple),
        provenance={
            "fixture_origin": "unknown",
            "fixture_set_digest": canonical_json_digest([case.probe_digest for case in case_tuple]),
        },
    )
