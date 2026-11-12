#!/usr/bin/env python3
"""Validate the ACT-609 AI offensive behavior vocabulary against pinned ATLAS data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.contracts import (  # noqa: E402
    AtlasTacticsSourceModel,
    ControlledVocabularyCatalogModel,
)
from raes_contracts.errors import InvalidInputError, OperationalError  # noqa: E402
from raes_contracts.operational_logging import run_application  # noqa: E402

VOCABULARY_ID = "participant-ai-offensive-behavior-activities"
CATALOG_RELATIVE_PATH = "contracts/concept-authority/controlled-vocabularies-v1.json"
SOURCE_RELATIVE_PATH = "contracts/concept-authority/atlas-tactics-source-v1.json"
SOURCE_AUTHORITY = "MITRE ATLAS"
SOURCE_VERSION = "2026.06"
SOURCE_FORMAT_VERSION = "6.0.0"
SOURCE_URL = "https://github.com/mitre-atlas/atlas-data/releases/download/v2026.06/ATLAS-2026.06.yaml"
SOURCE_DIGEST = "sha256:b771de8b1489564b2838a709c7429849a9575dbd94073928817fe1a21661e70a"
RELEASE_URL = "https://github.com/mitre-atlas/atlas-data/releases/tag/v2026.06"
README_URL = "https://github.com/mitre-atlas/atlas-data/blob/main/README.md"
LICENSE_URL = "https://github.com/mitre-atlas/atlas-data/blob/main/LICENSE"
ATLAS_HOME_URL = "https://atlas.mitre.org/"
LICENSE_NOTICE = (
    "Copyright 2021-2026 MITRE. Licensed under the Apache License, Version 2.0. Public Release Case Number 26-1162."
)
COLLECTION_ID = "ATLAS-collection"
MATRIX_ID = "ATLAS-matrix"


def _load_json(path: Path) -> Any:
    def bounded_integer(literal: str) -> int:
        # The decoder passes only JSON integer literals, so int() fails only beyond the interpreter digit limit.
        try:
            return int(literal)
        except ValueError as exc:
            raise InvalidInputError(f"{path.name} contains an integer beyond the digit limit") from exc

    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_int=bounded_integer)
    except RecursionError as exc:
        # Without a depth limit, the recursive decoder stops at the interpreter recursion limit.
        raise InvalidInputError(f"{path.name} nests beyond the JSON decoder depth") from exc


def _sha256_digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def _tactic_url(tactic_id: str) -> str:
    return f"https://atlas.mitre.org/tactics/{tactic_id}/"


def _extract_atlas_tactics(atlas_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if atlas_payload.get("format-version") != SOURCE_FORMAT_VERSION:
        raise InvalidInputError(
            f"ATLAS payload format-version is {atlas_payload.get('format-version')!r}; "
            f"expected {SOURCE_FORMAT_VERSION!r}"
        )
    collection = atlas_payload.get("collection", {})
    if collection.get("id") != COLLECTION_ID or collection.get("version") != SOURCE_VERSION:
        raise InvalidInputError("ATLAS payload collection id/version does not match the pinned source metadata")
    matrix = atlas_payload.get("matrix", {})
    if matrix.get("id") != MATRIX_ID:
        raise InvalidInputError(f"ATLAS payload matrix id is {matrix.get('id')!r}; expected {MATRIX_ID!r}")

    tactics = atlas_payload.get("tactics", {})
    sequences = atlas_payload.get("relationships", {}).get(MATRIX_ID, {}).get("sequences", [])
    extracted: list[dict[str, Any]] = []
    for sequence in sorted(sequences, key=lambda item: item["position"]):
        if sequence.get("source") != MATRIX_ID or sequence.get("relationship-type") != "sequences":
            raise InvalidInputError(f"ATLAS matrix sequence has unexpected shape: {sequence!r}")
        tactic_id = str(sequence["target"])
        tactic = tactics.get(tactic_id)
        if tactic is None:
            raise InvalidInputError(f"ATLAS matrix references missing tactic {tactic_id!r}")
        if tactic.get("object-type") != "tactic" or tactic.get("id") != tactic_id:
            raise InvalidInputError(f"ATLAS tactic {tactic_id!r} has unexpected object-type/id")
        attack_reference = tactic.get("attack-reference") or {}
        extracted.append(
            {
                "tactic_id": tactic_id,
                "shortname": _slug(str(tactic["name"])),
                "name": str(tactic["name"]),
                "description": str(tactic["description"]),
                "url": _tactic_url(tactic_id),
                "position": int(sequence["position"]),
                "uuid": str(tactic["uuid"]),
                "created_date": str(tactic["created-date"]),
                "modified_date": str(tactic["modified-date"]),
                "attack_reference_id": attack_reference.get("id"),
                "attack_reference_url": attack_reference.get("url"),
            }
        )
    return extracted


def _source_tactics(source: AtlasTacticsSourceModel) -> list[dict[str, Any]]:
    return [
        {
            "tactic_id": tactic.tactic_id,
            "shortname": tactic.shortname,
            "name": tactic.name,
            "description": tactic.description,
            "url": tactic.url,
            "position": tactic.position,
            "uuid": tactic.uuid,
            "created_date": tactic.created_date,
            "modified_date": tactic.modified_date,
            "attack_reference_id": tactic.attack_reference_id,
            "attack_reference_url": tactic.attack_reference_url,
        }
        for tactic in source.tactics
    ]


def _check_source_metadata(source: AtlasTacticsSourceModel) -> list[str]:
    failures: list[str] = []
    expected = {
        "source_authority": SOURCE_AUTHORITY,
        "source_version": SOURCE_VERSION,
        "source_format_version": SOURCE_FORMAT_VERSION,
        "source_url": SOURCE_URL,
        "source_digest": SOURCE_DIGEST,
        "license_url": LICENSE_URL,
        "license_notice": LICENSE_NOTICE,
        "collection_id": COLLECTION_ID,
        "matrix_id": MATRIX_ID,
    }
    actual = source.model_dump()
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            failures.append(f"{SOURCE_RELATIVE_PATH}: {field} is {actual[field]!r}; expected {expected_value!r}")
    for required_url in (
        SOURCE_URL,
        RELEASE_URL,
        README_URL,
        LICENSE_URL,
        ATLAS_HOME_URL,
    ):
        if required_url not in source.citation_urls:
            failures.append(f"{SOURCE_RELATIVE_PATH}: citation_urls must include {required_url}")
    return failures


def _check_catalog(catalog: ControlledVocabularyCatalogModel, source: AtlasTacticsSourceModel) -> list[str]:
    failures: list[str] = []
    vocabulary = catalog.vocabularies.get(VOCABULARY_ID)
    if vocabulary is None:
        return [f"{CATALOG_RELATIVE_PATH}: missing vocabulary {VOCABULARY_ID!r}"]

    if vocabulary.source is None:
        failures.append(f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID} must declare adopted ATLAS source metadata")
    else:
        source_fields = {
            "provenance": "adopted",
            "authority": "MITRE ATLAS",
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
        for required_url in (
            SOURCE_URL,
            RELEASE_URL,
            README_URL,
            LICENSE_URL,
            ATLAS_HOME_URL,
        ):
            if required_url not in vocabulary.source.citation_urls:
                failures.append(
                    f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID}.source.citation_urls must include {required_url}"
                )

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
            f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID} term order/content differs from pinned ATLAS matrix "
            f"order; actual={actual_shortnames!r} expected={expected_shortnames!r}"
        )

    for source_term in source_terms:
        term = vocabulary.terms.get(source_term["shortname"])
        if term is None:
            failures.append(f"{CATALOG_RELATIVE_PATH}: missing ATLAS tactic {source_term['shortname']!r}")
            continue
        if term.title != source_term["name"]:
            failures.append(
                f"{CATALOG_RELATIVE_PATH}: {source_term['shortname']}.title is {term.title!r}; "
                f"expected {source_term['name']!r}"
            )
        if term.description != source_term["description"]:
            failures.append(
                f"{CATALOG_RELATIVE_PATH}: {source_term['shortname']}.description differs from pinned ATLAS text"
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


def _remote_url_failure(source: AtlasTacticsSourceModel, selected_url: str) -> str | None:
    expected_path = "/mitre-atlas/atlas-data/releases/download/v2026.06/ATLAS-2026.06.yaml"
    failure = None
    if source.source_url != selected_url:
        failure = f"{SOURCE_RELATIVE_PATH}: source URL differs from the reviewed lock selection"
    else:
        try:
            parsed = urllib.parse.urlparse(selected_url)
        except ValueError:
            # urlparse refuses a malformed authority, such as an unclosed IPv6 bracket.
            parsed = None
        if parsed is None or parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.path != expected_path:
            failure = (
                f"{SOURCE_RELATIVE_PATH}: remote verification URL must stay pinned to the v2026.06 GitHub release asset"
            )
    return failure


def _check_remote(
    source: AtlasTacticsSourceModel,
    *,
    local_input: Path | None = None,
) -> list[str]:
    from tools.maintained_client_acquisition import ArtifactAcquisitionError, acquire_locked_bytes
    from tools.tooling_policy_gate import ArtifactPolicyError, load_tooling_artifact_selection

    selection = load_tooling_artifact_selection(
        artifact_id="atlas-tactics-snapshot",
        version=SOURCE_VERSION,
        platform_id="source-any",
        profile_id="source-snapshot",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1:
        raise ArtifactPolicyError("ATLAS lock selection must contain one source and raw snapshot")
    url_failure = _remote_url_failure(source, selection.source_urls[0])
    if url_failure is not None:
        return [url_failure]
    try:
        data = acquire_locked_bytes(
            artifact_id="atlas-tactics-snapshot",
            source_url=selection.source_urls[0],
            expected=selection.raw_manifest[0],
            local_input=local_input,
        )
    except ArtifactAcquisitionError as error:
        return [f"{SOURCE_RELATIVE_PATH}: {error}"]
    failures: list[str] = []
    if _sha256_digest(data) != source.source_digest:
        failures.append(f"{SOURCE_RELATIVE_PATH}: source_digest differs from the reviewed lock manifest")
    remote_tactics = _extract_atlas_tactics(yaml.safe_load(data))
    if remote_tactics != _source_tactics(source):
        failures.append(f"{SOURCE_RELATIVE_PATH}: tactic snapshot differs from pinned upstream ATLAS YAML")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-remote",
        action="store_true",
        help="Fetch the pinned upstream ATLAS YAML and verify digest plus tactic extraction.",
    )
    parser.add_argument(
        "--local-input",
        type=Path,
        default=None,
        help="Admit an approved local raw object instead of a fresh network transfer (no network fallback).",
    )
    args = parser.parse_args()
    if args.local_input is not None and not args.verify_remote:
        parser.error("--local-input requires --verify-remote")
    return args


def _failures(args: argparse.Namespace) -> list[str]:
    source = AtlasTacticsSourceModel.model_validate(_load_json(REPO_ROOT / SOURCE_RELATIVE_PATH))
    catalog = ControlledVocabularyCatalogModel.model_validate(_load_json(REPO_ROOT / CATALOG_RELATIVE_PATH))

    failures = _check_source_metadata(source)
    failures.extend(_check_catalog(catalog, source))
    if args.verify_remote:
        failures.extend(_check_remote(source, local_input=args.local_input))
    return failures


def main() -> int:
    args = parse_args()
    try:
        failures = _failures(args)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        yaml.YAMLError,
        ValidationError,
        InvalidInputError,
        OperationalError,
    ) as exc:
        print(f"[atlas-tactic-vocabulary] {exc}", file=sys.stderr)
        return 1

    for failure in failures:
        print(f"[atlas-tactic-vocabulary] {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
