#!/usr/bin/env python3
"""Validate the ACT-611 autonomous behavior vocabulary source snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raes_contracts.contracts import (  # noqa: E402
    ActivityStreamsActivityTypesSourceModel,
    FipaCommunicativeActsSourceModel,
)

ACTIVITYSTREAMS_RELATIVE_PATH = "contracts/concept-authority/w3c-activitystreams-activity-types-source-v1.json"
ACTIVITYSTREAMS_AUTHORITY = "World Wide Web Consortium"
ACTIVITYSTREAMS_VERSION = "REC-activitystreams-vocabulary-20170523"
ACTIVITYSTREAMS_STATUS = "W3C Recommendation"
ACTIVITYSTREAMS_URL = "https://www.w3.org/TR/2017/REC-activitystreams-vocabulary-20170523/"
ACTIVITYSTREAMS_DIGEST = "sha256:1418443392160f4bb23dffb5727f5216d1f56d3430377dc67d364016521401db"
ACTIVITYSTREAMS_LATEST_URL = "https://www.w3.org/TR/activitystreams-vocabulary/"
ACTIVITYSTREAMS_CORE_URL = "https://www.w3.org/TR/2017/REC-activitystreams-core-20170523/"
ACTIVITYSTREAMS_LICENSE_URL = "https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document"
ACTIVITYSTREAMS_LICENSE_NOTICE = (
    "Copyright © 2017 Activity Streams Working Group, IBM & SAP SE; W3C permissive document license applies."
)
ACTIVITYSTREAMS_TYPES = (
    "Accept",
    "Add",
    "Announce",
    "Arrive",
    "Block",
    "Create",
    "Delete",
    "Dislike",
    "Flag",
    "Follow",
    "Ignore",
    "Invite",
    "Join",
    "Leave",
    "Like",
    "Listen",
    "Move",
    "Offer",
    "Question",
    "Reject",
    "Read",
    "Remove",
    "TentativeReject",
    "TentativeAccept",
    "Travel",
    "Undo",
    "Update",
    "View",
)

FIPA_RELATIVE_PATH = "contracts/concept-authority/fipa-communicative-acts-source-v1.json"
FIPA_AUTHORITY = "Foundation for Intelligent Physical Agents"
FIPA_VERSION = "SC00037J-2002-12-03"
FIPA_STATUS = "Standard"
FIPA_URL = "https://www.fipa.org/specs/fipa00037/SC00037J.html"
FIPA_ARTIFACT_URL = "https://www.fipa.org/specs/fipa00037/SC00037J.pdf"
FIPA_DIGEST = "sha256:90b3277247ef7e7f614ba4c0d58fb2b86aa53ff69036d27a731c09a26c605227"
FIPA_REPOSITORY_URL = "https://www.fipa.org/repository/aclspecs.html"
FIPA_LICENSE_NOTICE = (
    "Copyright © 1996-2002 Foundation for Intelligent Physical Agents. "
    "The specification notice grants no permission to use third-party intellectual property."
)
FIPA_ACTS = (
    "accept-proposal",
    "agree",
    "cancel",
    "cfp",
    "confirm",
    "disconfirm",
    "failure",
    "inform",
    "inform-if",
    "inform-ref",
    "not-understood",
    "propagate",
    "propose",
    "proxy",
    "query-if",
    "query-ref",
    "refuse",
    "reject-proposal",
    "request",
    "request-when",
    "request-whenever",
    "subscribe",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _metadata_failures(
    *,
    relative_path: str,
    source: ActivityStreamsActivityTypesSourceModel | FipaCommunicativeActsSourceModel,
    expected: dict[str, str],
    required_citations: tuple[str, ...],
) -> list[str]:
    failures: list[str] = []
    actual = source.model_dump()
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            failures.append(f"{relative_path}: {field} is {actual[field]!r}; expected {expected_value!r}")
    for citation in required_citations:
        if citation not in source.citation_urls:
            failures.append(f"{relative_path}: citation_urls must include {citation}")
    return failures


def _check_activitystreams_source(source: ActivityStreamsActivityTypesSourceModel) -> list[str]:
    failures = _metadata_failures(
        relative_path=ACTIVITYSTREAMS_RELATIVE_PATH,
        source=source,
        expected={
            "source_authority": ACTIVITYSTREAMS_AUTHORITY,
            "source_version": ACTIVITYSTREAMS_VERSION,
            "source_status": ACTIVITYSTREAMS_STATUS,
            "source_url": ACTIVITYSTREAMS_URL,
            "source_digest": ACTIVITYSTREAMS_DIGEST,
            "license_url": ACTIVITYSTREAMS_LICENSE_URL,
            "license_notice": ACTIVITYSTREAMS_LICENSE_NOTICE,
        },
        required_citations=(
            ACTIVITYSTREAMS_URL,
            ACTIVITYSTREAMS_LATEST_URL,
            ACTIVITYSTREAMS_CORE_URL,
            ACTIVITYSTREAMS_LICENSE_URL,
        ),
    )
    actual_types = [term.type_name for term in source.activity_types]
    if actual_types != list(ACTIVITYSTREAMS_TYPES):
        failures.append(
            f"{ACTIVITYSTREAMS_RELATIVE_PATH}: activity type order/content differs from the dated Recommendation"
        )
    expected_ids = [f"https://www.w3.org/ns/activitystreams#{name}" for name in ACTIVITYSTREAMS_TYPES]
    if [term.concept_id for term in source.activity_types] != expected_ids:
        failures.append(f"{ACTIVITYSTREAMS_RELATIVE_PATH}: concept ids differ from the normative Activity type IRIs")
    return failures


def _check_fipa_source(source: FipaCommunicativeActsSourceModel) -> list[str]:
    failures = _metadata_failures(
        relative_path=FIPA_RELATIVE_PATH,
        source=source,
        expected={
            "source_authority": FIPA_AUTHORITY,
            "source_version": FIPA_VERSION,
            "source_status": FIPA_STATUS,
            "source_url": FIPA_URL,
            "source_artifact_url": FIPA_ARTIFACT_URL,
            "source_digest": FIPA_DIGEST,
            "license_url": FIPA_URL,
            "license_notice": FIPA_LICENSE_NOTICE,
        },
        required_citations=(FIPA_URL, FIPA_ARTIFACT_URL, FIPA_REPOSITORY_URL),
    )
    if [act.concept_id for act in source.communicative_acts] != list(FIPA_ACTS):
        failures.append(f"{FIPA_RELATIVE_PATH}: communicative act order/content differs from SC00037J")
    return failures


def _validate_official_https_url(url: str, *, allowed_host: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != allowed_host:
        raise ValueError("remote verification URL is outside the allowlisted official HTTPS host")


class _OfficialHttpsRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_host: str) -> None:
        self._allowed_host = allowed_host

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        _validate_official_https_url(newurl, allowed_host=self._allowed_host)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _fetch_official_bytes(url: str, *, allowed_host: str) -> bytes:
    _validate_official_https_url(url, allowed_host=allowed_host)
    request = urllib.request.Request(url, headers={"User-Agent": "RAES-ACT-611-source-verifier/1"})  # noqa: S310
    opener = urllib.request.build_opener(_OfficialHttpsRedirectHandler(allowed_host))
    with opener.open(request, timeout=60) as response:  # noqa: S310
        return response.read()


def _prefixed_sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _extract_activitystreams_type_names(data: bytes) -> list[str]:
    document = data.decode("utf-8")
    start = document.index('<section id="activity-types"')
    list_start = document.index("<ul>", start)
    list_end = document.index("</ul>", list_start)
    source_list = document[list_start:list_end]
    return re.findall(r'data-link-type="dfn">([A-Za-z]+)</a>', source_list)


def _check_activitystreams_remote(
    source: ActivityStreamsActivityTypesSourceModel,
    selected_url: str,
    *,
    expected_size: int,
    expected_sha256: str,
) -> list[str]:
    if source.source_url != selected_url:
        return [f"{ACTIVITYSTREAMS_RELATIVE_PATH}: source URL differs from the reviewed lock selection"]
    data = _fetch_official_bytes(selected_url, allowed_host="www.w3.org")
    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_sha256:
        return [f"{ACTIVITYSTREAMS_RELATIVE_PATH}: retrieved bytes differ from the reviewed lock manifest"]
    failures: list[str] = []
    if _prefixed_sha256(data) != source.source_digest:
        failures.append(f"{ACTIVITYSTREAMS_RELATIVE_PATH}: retrieved Recommendation bytes differ from source_digest")
    if _extract_activitystreams_type_names(data) != list(ACTIVITYSTREAMS_TYPES):
        failures.append(f"{ACTIVITYSTREAMS_RELATIVE_PATH}: retrieved Activity type order/content differs from snapshot")
    return failures


def _check_fipa_remote(
    source: FipaCommunicativeActsSourceModel,
    selected_url: str,
    *,
    expected_size: int,
    expected_sha256: str,
) -> list[str]:
    if source.source_artifact_url != selected_url:
        return [f"{FIPA_RELATIVE_PATH}: source artifact URL differs from the reviewed lock selection"]
    data = _fetch_official_bytes(selected_url, allowed_host="www.fipa.org")
    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_sha256:
        return [f"{FIPA_RELATIVE_PATH}: retrieved bytes differ from the reviewed lock manifest"]
    failures: list[str] = []
    if _prefixed_sha256(data) != source.source_digest:
        failures.append(f"{FIPA_RELATIVE_PATH}: retrieved specification artifact bytes differ from source_digest")
    return failures


def _check_remote(
    activitystreams: ActivityStreamsActivityTypesSourceModel,
    fipa: FipaCommunicativeActsSourceModel,
) -> list[str]:
    from tools.tooling_policy_gate import load_tooling_artifact_selection

    activitystreams_selection = load_tooling_artifact_selection(
        artifact_id="w3c-activitystreams-activity-types-snapshot",
        version=ACTIVITYSTREAMS_VERSION,
        platform_id="source-any",
        profile_id="source-snapshot",
    )
    fipa_selection = load_tooling_artifact_selection(
        artifact_id="fipa-communicative-acts-snapshot",
        version=FIPA_VERSION,
        platform_id="source-any",
        profile_id="source-snapshot",
    )
    if len(activitystreams_selection.source_urls) != 1 or len(activitystreams_selection.raw_manifest) != 1:
        raise RuntimeError("ActivityStreams lock selection must contain one source and raw snapshot")
    if len(fipa_selection.source_urls) != 1 or len(fipa_selection.raw_manifest) != 1:
        raise RuntimeError("FIPA lock selection must contain one source and raw snapshot")
    activitystreams_failures = _check_activitystreams_remote(
        activitystreams,
        activitystreams_selection.source_urls[0],
        expected_size=activitystreams_selection.raw_manifest[0].size,
        expected_sha256=activitystreams_selection.raw_manifest[0].sha256,
    )
    if activitystreams_failures:
        return activitystreams_failures
    return _check_fipa_remote(
        fipa,
        fipa_selection.source_urls[0],
        expected_size=fipa_selection.raw_manifest[0].size,
        expected_sha256=fipa_selection.raw_manifest[0].sha256,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-remote",
        action="store_true",
        help="Fetch the two allowlisted official sources and verify their exact bytes and identifier sets.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    activitystreams = ActivityStreamsActivityTypesSourceModel.model_validate(
        _load_json(REPO_ROOT / ACTIVITYSTREAMS_RELATIVE_PATH)
    )
    fipa = FipaCommunicativeActsSourceModel.model_validate(_load_json(REPO_ROOT / FIPA_RELATIVE_PATH))
    failures = _check_activitystreams_source(activitystreams)
    failures.extend(_check_fipa_source(fipa))
    if args.verify_remote:
        failures.extend(_check_remote(activitystreams, fipa))
    for failure in failures:
        print(f"[autonomous-behavior-vocabularies] {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
