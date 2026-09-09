#!/usr/bin/env python3
# ruff: noqa: E402
"""Offline integrity gate for the revision-pinned SDL lineage ledger."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import ValidationError
from raes._runtime_service_families import RUNTIME_SERVICE_FAMILIES
from raes_contracts.provenance import LineageDisposition, SDLLineageLedgerModel

from tools.check_schema_publication import load_schema_publication_catalog
from tools.policy.common import PolicyFailure, safe_repo_path

LEDGER_PATH = "contracts/provenance/sdl-lineage-ledger-v1.json"
AUTHORING_SCHEMA_PATH = "contracts/schemas/sdl/sdl-authoring-input-v1.json"
CONCEPT_FAMILIES_PATH = "contracts/concept-authority/concept-families-v1.json"
REFERENCE_MODELS_PATH = "contracts/concept-authority/reference-models-v1.json"
SCHEMA_PUBLICATION_MANIFEST_PATH = "contracts/schema-publication-manifest.json"
CURRENT_PROSE_PATHS = (
    "docs/explain/sdl/precedents.md",
    "docs/explain/sdl/lineage.md",
    "docs/explain/sdl/related-work-comparison.md",
    "docs/explain/sdl/validation.md",
    "implementations/python/packages/raes/__init__.py",
)
_HISTORICAL_BOUNDARIES_KEY = "a" + "ces_boundaries"
_HISTORICAL_NATIVE_CLASSIFICATION = "a" + "ces_native"
_HISTORICAL_COMPATIBILITY_DIRECTION = "a" + "ces_relative_to_source"
DOI_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(https://doi\.org/(10\.\d{4,9}/[^)\s]+)\)",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?:18|19|20|21)\d{2}\b")


def _failure(rule: str, message: str, path: str = LEDGER_PATH) -> PolicyFailure:
    return PolicyFailure(rule, message, path)


def _load_json(repo_root: Path, rel_path: str) -> object:
    path = safe_repo_path(repo_root, rel_path)
    if path is None or not path.is_file():
        raise ValueError(f"missing or unsafe repository artifact {rel_path!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def project_historical_ledger_to_current_contract(payload: object) -> object:
    """Project the exact pre-cutover ledger structure into the current contract.

    This policy-only projection is used solely for the immutable artifact at
    ``LEDGER_PATH``. It does not add aliases to the published model or any
    runtime parser.
    """

    if isinstance(payload, list):
        return [project_historical_ledger_to_current_contract(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    projected: dict[str, object] = {}
    for key, value in payload.items():
        current_key = "raes_boundaries" if key == _HISTORICAL_BOUNDARIES_KEY else key
        if value == _HISTORICAL_NATIVE_CLASSIFICATION:
            current_value: object = "raes_native"
        elif value == _HISTORICAL_COMPATIBILITY_DIRECTION:
            current_value = "raes_relative_to_source"
        else:
            current_value = project_historical_ledger_to_current_contract(value)
        projected[current_key] = current_value
    # Preserve the pre-cutover ledger bytes; project the explicitly retired
    # subject through its current removal authority (issue #989).
    if (
        projected.get("subject_id") == "sdl-field:vulnerabilities"
        and projected.get("disposition") == "current"
        and projected.get("authority")
        == {
            "artifact": AUTHORING_SCHEMA_PATH,
            "pointer": "#/properties/vulnerabilities",
            "contract_id": "sdl-authoring-input-v1",
        }
    ):
        projected["disposition"] = "removed"
        projected["authority"] = {
            "artifact": "specs/concept-authority/classification-migration.md",
            "pointer": "#inventory-and-disposition",
        }
    return projected


def _canonical_subjects(repo_root: Path) -> set[str]:
    schema = _load_json(repo_root, AUTHORING_SCHEMA_PATH)
    concepts = _load_json(repo_root, CONCEPT_FAMILIES_PATH)
    references = _load_json(repo_root, REFERENCE_MODELS_PATH)
    if not isinstance(schema, dict) or not isinstance(schema.get("properties"), dict):
        raise ValueError("authoring schema has no properties catalog")
    if not isinstance(concepts, dict) or not isinstance(concepts.get("families"), dict):
        raise ValueError("concept-family catalog has no families")
    if not isinstance(references, dict) or not isinstance(references.get("models"), dict):
        raise ValueError("reference-model catalog has no models")
    subjects = {f"sdl-field:{name}" for name in schema["properties"]}
    subjects.update(f"runtime-family:{family.collection_name}" for family in RUNTIME_SERVICE_FAMILIES)
    subjects.update(f"concept-family:{name}" for name in concepts["families"])
    subjects.update(f"reference-model:{name}" for name in references["models"])
    return subjects


def _resolve_json_pointer(document: object, pointer: str) -> bool:
    if pointer == "#":
        return True
    if not pointer.startswith("#/"):
        return False
    current = document
    for raw_part in pointer[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False
    return True


def _validate_authorities(repo_root: Path, ledger: SDLLineageLedgerModel) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    cache: dict[str, object] = {}
    try:
        manifest = load_schema_publication_catalog(repo_root)
    except ValueError:
        manifest = None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("schemas"), list):
        return [
            _failure(
                "lineage-schema-publication-manifest-invalid",
                "schema publication manifest has no schemas catalog",
                SCHEMA_PUBLICATION_MANIFEST_PATH,
            )
        ]
    published_paths = {
        entry["contract_id"]: entry["schema_path"]
        for entry in manifest["schemas"]
        if isinstance(entry, dict)
        and isinstance(entry.get("contract_id"), str)
        and isinstance(entry.get("schema_path"), str)
    }
    for subject in ledger.subjects:
        artifact = subject.authority.artifact
        contract_id = subject.authority.contract_id
        if contract_id is not None and published_paths.get(contract_id) != artifact:
            failures.append(
                _failure(
                    "lineage-authority-contract-mismatch",
                    f"{subject.subject_id}: contract {contract_id!r} is not published at {artifact!r}",
                )
            )
        path = safe_repo_path(repo_root, artifact)
        if path is None or not path.is_file():
            failures.append(
                _failure(
                    "lineage-authority-missing",
                    f"{subject.subject_id}: missing {artifact!r}",
                )
            )
            continue
        if subject.disposition is not LineageDisposition.CURRENT:
            continue
        if path.suffix != ".json":
            failures.append(
                _failure(
                    "lineage-current-authority-not-json",
                    f"{subject.subject_id}: current authority must be JSON",
                )
            )
            continue
        try:
            document = cache.setdefault(artifact, json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            failures.append(
                _failure(
                    "lineage-authority-invalid",
                    f"{subject.subject_id}: invalid JSON authority",
                )
            )
            continue
        if not _resolve_json_pointer(document, subject.authority.pointer):
            failures.append(
                _failure(
                    "lineage-authority-pointer-missing",
                    f"{subject.subject_id}: pointer {subject.authority.pointer!r} does not resolve in {artifact}",
                )
            )
    return failures


def _validate_internal_paths(repo_root: Path, ledger: SDLLineageLedgerModel) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    refs: set[str] = set()
    for citation in ledger.citations:
        refs.add(citation.verification_evidence.split("#", 1)[0])
    for subject in ledger.subjects:
        refs.add(subject.authority.artifact)
        for claim in subject.claims:
            refs.update(boundary.artifact for boundary in claim.raes_boundaries)
            refs.update(ref.split("#", 1)[0] for ref in claim.internal_authority_refs)
    for disposition in ledger.third_party_dispositions:
        refs.update(ref.split("#", 1)[0] for ref in disposition.evidence_refs if not ref.startswith("git:"))
        if disposition.notice_artifact:
            refs.add(disposition.notice_artifact)
        refs.update(boundary.artifact for boundary in disposition.derivation_scope)
    for ref in sorted(refs):
        path = safe_repo_path(repo_root, ref)
        if path is None or not path.is_file():
            failures.append(
                _failure(
                    "lineage-internal-artifact-missing",
                    f"internal artifact {ref!r} is missing or unsafe",
                )
            )
    return failures


def _validate_bibliography(ledger: SDLLineageLedgerModel) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    doi_identity: dict[str, tuple[str, int]] = {}
    for citation in ledger.citations:
        if citation.doi is None:
            continue
        doi = citation.doi.casefold()
        identity = (citation.title.casefold(), citation.year)
        previous = doi_identity.setdefault(doi, identity)
        if previous != identity:
            failures.append(
                _failure(
                    "lineage-doi-identity-conflict",
                    f"DOI {doi!r} has conflicting title/year",
                )
            )
        if citation.canonical_url.casefold() != f"https://doi.org/{doi}":
            failures.append(
                _failure(
                    "lineage-doi-url-mismatch",
                    f"{citation.citation_id}: DOI URL does not match DOI",
                )
            )
    return failures


def _validate_current_prose(
    repo_root: Path,
    ledger: SDLLineageLedgerModel,
    prose_paths: tuple[str, ...] = CURRENT_PROSE_PATHS,
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    doi_years = {citation.doi.casefold(): citation.year for citation in ledger.citations if citation.doi is not None}
    for rel_path in prose_paths:
        path = safe_repo_path(repo_root, rel_path)
        if path is None or not path.is_file():
            failures.append(
                _failure(
                    "lineage-prose-missing",
                    f"governed current prose {rel_path!r} is missing",
                    rel_path,
                )
            )
            continue
        prose = path.read_text(encoding="utf-8")
        folded_prose = prose.casefold()
        if "direct port" in folded_prose or "ported from" in folded_prose:
            failures.append(
                _failure(
                    "lineage-ambiguous-port-claim",
                    "replace ambiguous port wording with revision-, plane-, boundary-, and compatibility-qualified terms",
                    rel_path,
                )
            )
        for label, doi in DOI_LINK_RE.findall(prose):
            expected_year = doi_years.get(doi.casefold())
            label_years = {int(year) for year in YEAR_RE.findall(label)}
            if expected_year is not None and label_years and expected_year not in label_years:
                failures.append(
                    _failure(
                        "lineage-doi-label-year-mismatch",
                        f"DOI {doi!r} is verified as {expected_year}, but its link label says {sorted(label_years)}",
                        rel_path,
                    )
                )
    return failures


def evaluate(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    try:
        payload = _load_json(repo_root, LEDGER_PATH)
        payload = project_historical_ledger_to_current_contract(payload)
        ledger = SDLLineageLedgerModel.model_validate(payload)
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        return [_failure("lineage-ledger-invalid", f"ledger validation failed: {exc}")]
    failures: list[PolicyFailure] = []
    try:
        expected = _canonical_subjects(repo_root)
    except (ValueError, json.JSONDecodeError) as exc:
        return [_failure("lineage-canonical-catalog-invalid", str(exc))]
    actual = {subject.subject_id for subject in ledger.subjects if subject.disposition is LineageDisposition.CURRENT}
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        failures.append(
            _failure(
                "lineage-current-subjects-missing",
                f"missing canonical subjects: {missing}",
            )
        )
    if unexpected:
        failures.append(
            _failure(
                "lineage-current-subjects-unexpected",
                f"unexpected current subjects: {unexpected}",
            )
        )
    failures.extend(_validate_authorities(repo_root, ledger))
    failures.extend(_validate_internal_paths(repo_root, ledger))
    failures.extend(_validate_bibliography(ledger))
    failures.extend(_validate_current_prose(repo_root, ledger))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    failures = evaluate()
    if args.json:
        print(json.dumps([failure.__dict__ for failure in failures], indent=2))
    else:
        for failure in failures:
            print(failure.render())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
