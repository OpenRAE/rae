"""API-404 profile clauses and landed evidence for CP-11."""

from __future__ import annotations

import re
from pathlib import Path

from raes_runtime.control_plane_profiles import ControlPlaneProfile, profile_declaration
from tools.policy.repository_requirements import RepositoryRequirementClient

ROOT = Path(__file__).resolve().parents[3]
REQUIREMENT_PATH = ROOT / "docs/requirements/API-404/requirement.md"

COMMON_GUARANTEES = {
    "in-process-safety",
    "actor-scoped-idempotency",
    "target-run-isolation",
    "revision-cas",
    "atomic-audit",
}
DURABLE_GUARANTEES = {
    "durable-state",
    "retained-idempotency",
    "lease-admission",
    "startup-reconciliation",
}
TRANSPORT_GUARANTEES = {
    "authenticated-transport",
    "actor-bound-disclosure",
    "owner-serialized-mutation",
    "revision-carrying-reads",
}
EXPECTED_PROFILES = {
    ControlPlaneProfile.P0: ({"API-404-C1"}, COMMON_GUARANTEES),
    ControlPlaneProfile.P1: (
        {"API-404-C1", "API-404-C2"},
        COMMON_GUARANTEES | DURABLE_GUARANTEES,
    ),
    ControlPlaneProfile.P2: (
        {"API-404-C1", "API-404-C2", "API-404-C3"},
        COMMON_GUARANTEES | DURABLE_GUARANTEES | TRANSPORT_GUARANTEES,
    ),
    ControlPlaneProfile.P3: (set(), set()),
}


def _section(document: str, heading: str) -> str:
    marker = f"## {heading}"
    assert marker in document, f"API-404 is missing its {heading!r} section"
    return document.split(marker, 1)[1].split("\n## ", 1)[0]


def _profile_rows(document: str) -> dict[ControlPlaneProfile, tuple[set[str], set[str]]]:
    rows = {}
    for line in _section(document, "Profile-to-clause matrix").splitlines():
        if re.match(r"^\| P[0-3] \|", line) is None:
            continue
        profile_cell, clauses_cell, guarantees_cell, _ = [cell.strip() for cell in line.strip("|").split("|")]
        rows[ControlPlaneProfile(profile_cell)] = (
            set(re.findall(r"`(API-404-C[0-9]+)`", clauses_cell)),
            set(re.findall(r"`([a-z][a-z0-9-]+)`", guarantees_cell)),
        )
    return rows


def test_api_404_profile_clause_matrix_matches_canonical_declarations() -> None:
    document = REQUIREMENT_PATH.read_text()
    assert _profile_rows(document) == EXPECTED_PROFILES
    for profile, (_, expected_guarantees) in EXPECTED_PROFILES.items():
        declaration = profile_declaration(profile)
        assert {claim.identifier for claim in declaration.guarantees} == expected_guarantees


def test_api_404_scope_and_nonclaims_are_explicit() -> None:
    document = REQUIREMENT_PATH.read_text()
    clauses = _section(document, "Contract clauses")
    normalized_clauses = " ".join(clauses.split())
    assert all(f"### API-404-C{number}" in clauses for number in range(1, 5))
    assert "P0 process loss discards operation state, idempotency records, and audit" in normalized_clauses
    assert "P0 does not provide durability, restart recovery, or retained deduplication" in normalized_clauses
    assert "Only P2 authenticates transport callers" in normalized_clauses
    assert "P3 is unavailable and satisfies no API-404 clause" in normalized_clauses

    public_page = (ROOT / "docs/explain/sdl/runtime-architecture.md").read_text()
    public_profiles = _section(public_page, "Control-plane operating profiles")
    assert "| P3 | none | future-coordination |" in public_profiles
    assert "P3 is inspectable but unavailable" in public_profiles


def test_api_404_traceability_names_existing_local_evidence() -> None:
    client = RepositoryRequirementClient(ROOT)
    assert client.get_requirement("raes-sdl", "API-404")["status"] == "ACTIVE"
    links = client.get_traceability("API-404")
    triples = {(link["link_type"], link["artifact_type"], link["artifact_identifier"]) for link in links}
    assert (
        "IMPLEMENTS",
        "CODE_FILE",
        "implementations/python/packages/raes_runtime/control_plane_profiles.py",
    ) in triples
    assert (
        "TESTS",
        "TEST",
        "implementations/python/tests/test_issue_1189_control_plane_profile_declarations.py",
    ) in triples
    assert ("DOCUMENTS", "GITHUB_ISSUE", "1185") in triples
    assert {link["artifact_type"] for link in links if link["link_type"] == "IMPLEMENTS"} <= {"CODE_FILE", "SPEC"}
    assert {link["artifact_type"] for link in links if link["link_type"] == "TESTS"} == {"TEST"}

    local_artifact_types = {"CODE_FILE", "TEST", "SPEC", "DOCUMENTATION", "ADR"}
    missing = sorted(
        link["artifact_identifier"]
        for link in links
        if link["artifact_type"] in local_artifact_types and not (ROOT / str(link["artifact_identifier"])).is_file()
    )
    assert missing == []
