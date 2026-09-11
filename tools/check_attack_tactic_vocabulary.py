#!/usr/bin/env python3
"""Validate the ACT-609 offensive behavior vocabulary against pinned ATT&CK data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raes_contracts.contracts import (  # noqa: E402
    AttackEnterpriseTacticsSourceModel,
    ControlledVocabularyCatalogModel,
)

VOCABULARY_ID = "participant-offensive-behavior-activities"
CATALOG_RELATIVE_PATH = "contracts/concept-authority/controlled-vocabularies-v1.json"
SOURCE_RELATIVE_PATH = "contracts/concept-authority/attack-enterprise-tactics-source-v1.json"
SOURCE_AUTHORITY = "MITRE ATT&CK"
SOURCE_DOMAIN = "enterprise-attack"
SOURCE_VERSION = "v19.1"
SOURCE_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/"
    "v19.1/enterprise-attack/enterprise-attack-19.1.json"
)
SOURCE_DIGEST = "sha256:bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3"
LICENSE_URL = "https://attack.mitre.org/resources/legal-and-branding/terms-of-use/"
LICENSE_NOTICE = (
    "\u00a9 2026 The MITRE Corporation. This work is reproduced and distributed with the permission "
    "of The MITRE Corporation."
)
MATRIX_NAME = "Enterprise ATT&CK"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _mitre_reference(stix_object: dict[str, Any]) -> dict[str, Any]:
    for reference in stix_object.get("external_references", []):
        if reference.get("source_name") == "mitre-attack":
            return reference
    raise ValueError(f"STIX object {stix_object.get('id')} is missing a mitre-attack external reference")


def _extract_enterprise_tactics(stix_payload: dict[str, Any]) -> list[dict[str, str]]:
    objects = stix_payload.get("objects", [])
    tactics_by_stix_id = {
        item["id"]: item
        for item in objects
        if item.get("type") == "x-mitre-tactic"
        and not item.get("revoked", False)
        and not item.get("x_mitre_deprecated", False)
    }
    matrix = next(
        (item for item in objects if item.get("type") == "x-mitre-matrix" and item.get("name") == MATRIX_NAME),
        None,
    )
    if matrix is None:
        raise ValueError(f"STIX payload is missing matrix {MATRIX_NAME!r}")

    extracted: list[dict[str, str]] = []
    for tactic_ref in matrix.get("tactic_refs", []):
        tactic = tactics_by_stix_id.get(tactic_ref)
        if tactic is None:
            raise ValueError(f"matrix references missing active tactic {tactic_ref!r}")
        reference = _mitre_reference(tactic)
        extracted.append(
            {
                "tactic_id": str(reference["external_id"]),
                "shortname": str(tactic["x_mitre_shortname"]),
                "name": str(tactic["name"]),
                "description": str(tactic["description"]),
                "url": str(reference["url"]),
                "stix_id": str(tactic["id"]),
            }
        )
    return extracted


def _source_tactics(source: AttackEnterpriseTacticsSourceModel) -> list[dict[str, str]]:
    return [
        {
            "tactic_id": tactic.tactic_id,
            "shortname": tactic.shortname,
            "name": tactic.name,
            "description": tactic.description,
            "url": tactic.url,
            "stix_id": tactic.stix_id,
        }
        for tactic in source.tactics
    ]


def _check_source_metadata(source: AttackEnterpriseTacticsSourceModel) -> list[str]:
    failures: list[str] = []
    expected = {
        "source_authority": SOURCE_AUTHORITY,
        "source_domain": SOURCE_DOMAIN,
        "source_version": SOURCE_VERSION,
        "source_url": SOURCE_URL,
        "source_digest": SOURCE_DIGEST,
        "license_url": LICENSE_URL,
        "license_notice": LICENSE_NOTICE,
    }
    actual = source.model_dump()
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            failures.append(f"{SOURCE_RELATIVE_PATH}: {field} is {actual[field]!r}; expected {expected_value!r}")
    if SOURCE_URL not in source.citation_urls:
        failures.append(f"{SOURCE_RELATIVE_PATH}: citation_urls must include the pinned STIX bundle URL")
    if LICENSE_URL not in source.citation_urls:
        failures.append(f"{SOURCE_RELATIVE_PATH}: citation_urls must include the MITRE terms URL")
    return failures


def _check_catalog(
    catalog: ControlledVocabularyCatalogModel,
    source: AttackEnterpriseTacticsSourceModel,
) -> list[str]:
    failures: list[str] = []
    vocabulary = catalog.vocabularies.get(VOCABULARY_ID)
    if vocabulary is None:
        return [f"{CATALOG_RELATIVE_PATH}: missing vocabulary {VOCABULARY_ID!r}"]

    if vocabulary.source is None:
        failures.append(f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID} must declare adopted ATT&CK source metadata")
    else:
        source_fields = {
            "provenance": "adopted",
            "authority": "MITRE ATT&CK Enterprise",
            "authority_version": SOURCE_VERSION,
            "source_artifact_ref": SOURCE_RELATIVE_PATH,
            "source_url": SOURCE_URL,
            "source_digest": SOURCE_DIGEST,
            "license_url": LICENSE_URL,
            "license_notice": LICENSE_NOTICE,
        }
        actual_source = vocabulary.source.model_dump()
        for field, expected_value in source_fields.items():
            if actual_source[field] != expected_value:
                failures.append(
                    f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID}.source.{field} is "
                    f"{actual_source[field]!r}; expected {expected_value!r}"
                )
        if SOURCE_URL not in vocabulary.source.citation_urls:
            failures.append(f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID}.source.citation_urls omits STIX URL")
        if LICENSE_URL not in vocabulary.source.citation_urls:
            failures.append(f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID}.source.citation_urls omits terms URL")

    if vocabulary.governed_scopes != []:
        failures.append(
            f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID}.governed_scopes is "
            f"{vocabulary.governed_scopes!r}; expected {[]!r}"
        )
    if vocabulary.extension_policy != "closed":
        failures.append(f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID} must remain a closed optional source catalog")

    source_terms = _source_tactics(source)
    expected_shortnames = [term["shortname"] for term in source_terms]
    actual_shortnames = list(vocabulary.terms)
    if actual_shortnames != expected_shortnames:
        failures.append(
            f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID} term order/content differs from pinned ATT&CK matrix "
            f"order; actual={actual_shortnames!r} expected={expected_shortnames!r}"
        )

    for source_term in source_terms:
        term = vocabulary.terms.get(source_term["shortname"])
        if term is None:
            failures.append(f"{CATALOG_RELATIVE_PATH}: missing ATT&CK tactic {source_term['shortname']!r}")
            continue
        if term.title != source_term["name"]:
            failures.append(
                f"{CATALOG_RELATIVE_PATH}: {source_term['shortname']}.title is {term.title!r}; "
                f"expected {source_term['name']!r}"
            )
        if term.description != source_term["description"]:
            failures.append(
                f"{CATALOG_RELATIVE_PATH}: {source_term['shortname']}.description differs from pinned ATT&CK text"
            )
        if term.source_id != source_term["tactic_id"]:
            failures.append(
                f"{CATALOG_RELATIVE_PATH}: {source_term['shortname']}.source_id is {term.source_id!r}; "
                f"expected {source_term['tactic_id']!r}"
            )
        if term.source_url != source_term["url"]:
            failures.append(
                f"{CATALOG_RELATIVE_PATH}: {source_term['shortname']}.source_url is {term.source_url!r}; "
                f"expected {source_term['url']!r}"
            )
    return failures


def _remote_url_failure(source: AttackEnterpriseTacticsSourceModel, selected_url: str) -> str | None:
    failure = None
    if source.source_url != selected_url:
        failure = f"{SOURCE_RELATIVE_PATH}: source URL differs from the reviewed lock selection"
    else:
        parsed = urllib.parse.urlparse(selected_url)
        if parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com":
            failure = (
                f"{SOURCE_RELATIVE_PATH}: remote verification URL must stay pinned to raw.githubusercontent.com HTTPS"
            )
    return failure


def _remote_bytes_failure(data: bytes, *, size: int, sha256: str) -> str | None:
    digest = _sha256_digest(data)
    if len(data) != size or digest != f"sha256:{sha256}":
        return f"{SOURCE_RELATIVE_PATH}: retrieved bytes differ from the reviewed lock manifest"
    return None


def _check_remote(source: AttackEnterpriseTacticsSourceModel) -> list[str]:
    from tools.tooling_policy_gate import load_tooling_artifact_selection

    selection = load_tooling_artifact_selection(
        artifact_id="attack-enterprise-tactics-snapshot",
        version=SOURCE_VERSION,
        platform_id="source-any",
        profile_id="source-snapshot",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1:
        raise RuntimeError("ATT&CK lock selection must contain one source and raw snapshot")
    raw = selection.raw_manifest[0]
    url_failure = _remote_url_failure(source, selection.source_urls[0])
    if url_failure is not None:
        return [url_failure]
    with urllib.request.urlopen(selection.source_urls[0], timeout=60) as response:  # noqa: S310
        data = response.read()
    digest = _sha256_digest(data)
    bytes_failure = _remote_bytes_failure(data, size=raw.size, sha256=raw.sha256)
    if bytes_failure is not None:
        return [bytes_failure]
    failures: list[str] = []
    if digest != source.source_digest:
        failures.append(f"{SOURCE_RELATIVE_PATH}: source_digest differs from the reviewed lock manifest")
    remote_tactics = _extract_enterprise_tactics(json.loads(data.decode("utf-8")))
    if remote_tactics != _source_tactics(source):
        failures.append(f"{SOURCE_RELATIVE_PATH}: tactic snapshot differs from pinned upstream STIX bundle")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-remote",
        action="store_true",
        help="Fetch the pinned upstream STIX bundle and verify digest plus tactic extraction.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = AttackEnterpriseTacticsSourceModel.model_validate(_load_json(REPO_ROOT / SOURCE_RELATIVE_PATH))
    catalog = ControlledVocabularyCatalogModel.model_validate(_load_json(REPO_ROOT / CATALOG_RELATIVE_PATH))

    failures = _check_source_metadata(source)
    failures.extend(_check_catalog(catalog, source))
    if args.verify_remote:
        failures.extend(_check_remote(source))

    for failure in failures:
        print(f"[attack-tactic-vocabulary] {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
