#!/usr/bin/env python3
"""Validate the ACT-610 defensive vocabulary against the pinned NIST CSF 2.0 Core."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from defusedxml import ElementTree

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raes_contracts.contracts import (  # noqa: E402
    ControlledVocabularyCatalogModel,
    NistCsfDefensiveCategorySourceModel,
)

VOCABULARY_ID = "participant-defensive-behavior-activities"
CATALOG_RELATIVE_PATH = "contracts/concept-authority/controlled-vocabularies-v1.json"
SOURCE_RELATIVE_PATH = "contracts/concept-authority/nist-csf-defensive-categories-source-v1.json"
SOURCE_AUTHORITY = "NIST Cybersecurity Framework"
SOURCE_VERSION = "2.0"
SOURCE_URL = "https://csrc.nist.gov/extensions/nudp/services/json/csf/download?"
SOURCE_DIGEST = "sha256:014492980e87f8ce2c98d80ea040540392de96a08980c2f9901114ad4108b2c3"
PUBLICATION_URL = "https://www.nist.gov/publications/nist-cybersecurity-framework-csf-20"
PUBLICATION_DOI = "https://doi.org/10.6028/NIST.CSWP.29"
LICENSE_URL = "https://www.nist.gov/copyrights-disclaimers"
LICENSE_NOTICE = (
    "Adapted from NIST CSF 2.0. Except for material marked as copyrighted, NIST site information is public "
    "information that may be distributed or copied; appropriate source credit is requested."
)
_CATEGORY_TERM_IDS = {
    "DE.CM": "continuous-monitoring",
    "DE.AE": "adverse-event-analysis",
    "RS.MA": "incident-management",
    "RS.AN": "incident-analysis",
    "RS.CO": "incident-response-reporting-and-communication",
    "RS.MI": "incident-mitigation",
    "RC.RP": "incident-recovery-plan-execution",
    "RC.CO": "incident-recovery-communication",
}
_CATEGORY_RE = re.compile(r"^(.+) \(((?:DE|RS|RC)\.[A-Z]{2})\): (.+)$")
_SPREADSHEET_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_digest(categories: list[dict[str, str]]) -> str:
    payload = json.dumps(categories, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _xlsx_rows(data: bytes) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as workbook:
        shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        shared = [
            "".join(text.text or "" for text in item.findall(".//x:t", _SPREADSHEET_NS))
            for item in shared_root.findall("x:si", _SPREADSHEET_NS)
        ]
        sheet_root = ElementTree.fromstring(workbook.read("xl/worksheets/sheet2.xml"))

    rows: list[dict[str, str]] = []
    for row in sheet_root.findall(".//x:row", _SPREADSHEET_NS):
        values: dict[str, str] = {}
        for cell in row.findall("x:c", _SPREADSHEET_NS):
            coordinate = cell.get("r", "")
            value_node = cell.find("x:v", _SPREADSHEET_NS)
            value = "" if value_node is None else value_node.text or ""
            if cell.get("t") == "s" and value:
                value = shared[int(value)]
            if coordinate:
                values[coordinate[0]] = value
        rows.append(values)
    return rows


def _extract_defensive_categories(data: bytes) -> list[dict[str, str]]:
    function = ""
    categories: list[dict[str, str]] = []
    for row in _xlsx_rows(data):
        if row.get("A"):
            function = row["A"].split(" (", 1)[0].title()
        match = _CATEGORY_RE.fullmatch(row.get("B", ""))
        if match is None or match.group(2) not in _CATEGORY_TERM_IDS:
            continue
        categories.append(
            {
                "category_id": match.group(2),
                "term_id": _CATEGORY_TERM_IDS[match.group(2)],
                "title": match.group(1),
                "description": match.group(3),
                "function": function,
            }
        )
    return categories


def _source_categories(
    source: NistCsfDefensiveCategorySourceModel,
) -> list[dict[str, str]]:
    return [category.model_dump() for category in source.categories]


def _check_source_metadata(source: NistCsfDefensiveCategorySourceModel) -> list[str]:
    failures: list[str] = []
    expected = {
        "source_authority": SOURCE_AUTHORITY,
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
    for citation in (SOURCE_URL, PUBLICATION_URL, PUBLICATION_DOI, LICENSE_URL):
        if citation not in source.citation_urls:
            failures.append(f"{SOURCE_RELATIVE_PATH}: citation_urls must include {citation}")
    if _canonical_digest(_source_categories(source)) != source.source_digest:
        failures.append(f"{SOURCE_RELATIVE_PATH}: source_digest does not match the canonical category snapshot")
    return failures


def _check_catalog(
    catalog: ControlledVocabularyCatalogModel,
    source: NistCsfDefensiveCategorySourceModel,
) -> list[str]:
    failures: list[str] = []
    vocabulary = catalog.vocabularies.get(VOCABULARY_ID)
    if vocabulary is None:
        return [f"{CATALOG_RELATIVE_PATH}: missing vocabulary {VOCABULARY_ID!r}"]
    if vocabulary.source is None:
        failures.append(f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID} must declare adapted NIST source metadata")
    else:
        expected_source = {
            "provenance": "adapted",
            "authority": SOURCE_AUTHORITY,
            "authority_version": SOURCE_VERSION,
            "source_artifact_ref": SOURCE_RELATIVE_PATH,
            "source_url": SOURCE_URL,
            "source_digest": SOURCE_DIGEST,
            "license_url": LICENSE_URL,
            "license_notice": LICENSE_NOTICE,
        }
        actual_source = vocabulary.source.model_dump()
        for field, expected_value in expected_source.items():
            if actual_source[field] != expected_value:
                failures.append(
                    f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID}.source.{field} is "
                    f"{actual_source[field]!r}; expected {expected_value!r}"
                )
    if vocabulary.governed_scopes != []:
        failures.append(
            f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID}.governed_scopes is "
            f"{vocabulary.governed_scopes!r}; expected {[]!r}"
        )
    if vocabulary.extension_policy != "closed":
        failures.append(f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID} must remain a closed optional source catalog")

    expected_term_ids = [category.term_id for category in source.categories]
    if list(vocabulary.terms) != expected_term_ids:
        failures.append(f"{CATALOG_RELATIVE_PATH}: {VOCABULARY_ID} term order/content differs from NIST source")
    for category in source.categories:
        term = vocabulary.terms.get(category.term_id)
        if term is None:
            continue
        if term.title != category.title or term.source_id != category.category_id:
            failures.append(f"{CATALOG_RELATIVE_PATH}: {category.term_id} title or source_id differs from NIST source")
        if term.source_url != PUBLICATION_DOI:
            failures.append(f"{CATALOG_RELATIVE_PATH}: {category.term_id}.source_url must cite NIST CSWP 29")
    return failures


def _remote_url_failure(source: NistCsfDefensiveCategorySourceModel, selected_url: str) -> str | None:
    failure = None
    if source.source_url != selected_url:
        failure = f"{SOURCE_RELATIVE_PATH}: source URL differs from the reviewed lock selection"
    else:
        parsed = urllib.parse.urlparse(selected_url)
        if parsed.scheme != "https" or parsed.netloc != "csrc.nist.gov":
            failure = f"{SOURCE_RELATIVE_PATH}: remote verification URL must stay on csrc.nist.gov HTTPS"
    return failure


def _remote_bytes_failure(data: bytes, *, size: int, sha256: str) -> str | None:
    if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
        return f"{SOURCE_RELATIVE_PATH}: retrieved bytes differ from the reviewed lock manifest"
    return None


def _check_remote(source: NistCsfDefensiveCategorySourceModel) -> list[str]:
    from tools.tooling_policy_gate import load_tooling_artifact_selection

    selection = load_tooling_artifact_selection(
        artifact_id="nist-csf-defensive-categories-snapshot",
        version=SOURCE_VERSION,
        platform_id="source-any",
        profile_id="source-snapshot",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1:
        raise RuntimeError("NIST CSF lock selection must contain one source and raw snapshot")
    raw = selection.raw_manifest[0]
    url_failure = _remote_url_failure(source, selection.source_urls[0])
    if url_failure is not None:
        return [url_failure]
    request = urllib.request.Request(  # noqa: S310 - allowlisted NIST HTTPS endpoint above
        selection.source_urls[0],
        headers={"User-Agent": "RAES-NIST-CSF-verifier/1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        data = response.read()
    bytes_failure = _remote_bytes_failure(data, size=raw.size, sha256=raw.sha256)
    if bytes_failure is not None:
        return [bytes_failure]
    categories = _extract_defensive_categories(data)
    failures: list[str] = []
    if categories != _source_categories(source):
        failures.append(f"{SOURCE_RELATIVE_PATH}: category snapshot differs from the current NIST CSF 2.0 Core export")
    if _canonical_digest(categories) != source.source_digest:
        failures.append(f"{SOURCE_RELATIVE_PATH}: canonical remote digest differs from source_digest")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-remote",
        action="store_true",
        help="Fetch the official NIST CSF 2.0 Core export and verify the canonical defensive-category snapshot.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = NistCsfDefensiveCategorySourceModel.model_validate(_load_json(REPO_ROOT / SOURCE_RELATIVE_PATH))
    catalog = ControlledVocabularyCatalogModel.model_validate(_load_json(REPO_ROOT / CATALOG_RELATIVE_PATH))
    failures = _check_source_metadata(source)
    failures.extend(_check_catalog(catalog, source))
    if args.verify_remote:
        failures.extend(_check_remote(source))
    for failure in failures:
        print(f"[nist-csf-defensive-vocabulary] {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
