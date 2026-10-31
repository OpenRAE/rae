"""Bind a reproduction review record to GitHub server records before retention.

Offline admission checks retained bytes and joins. This check runs when a
capture is retained: each review reference must name an existing server record
that binds the reviewed digests, the qualified run, and its artifact. The
records come from one repository account; separation is between runs only.
"""

import re
import urllib.request
from collections.abc import Callable
from datetime import datetime

from raes_contracts.errors import EvidenceIntegrityError, InvalidInputError, OperationalError
from raes_contracts.json_ingress import parse_bounded_json_object

from .export import digest

API = "https://api.github.com/repos/OpenRAE/rae/"
MAX_RESPONSE_BYTES = 1024 * 1024
_ISSUE_REF = re.compile(r"https://github\.com/OpenRAE/rae/issues/([1-9][0-9]{0,6})")
_COMMENT_REF = re.compile(r"https://github\.com/OpenRAE/rae/issues/([1-9][0-9]{0,6})#issuecomment-([1-9][0-9]{0,19})")
_RUN_REF = re.compile(r"https://github\.com/OpenRAE/rae/actions/runs/([1-9][0-9]{0,19})")

Fetch = Callable[[str], dict]


def github_fetch(path: str) -> dict:
    """Read one public repository record; ``path`` contains only validated integers or digests."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/OpenRAE/rae/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "raes-participant-crossing-reproduction",
        },
    )
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler())
        with opener.open(request, timeout=20) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        return parse_bounded_json_object(payload, max_bytes=MAX_RESPONSE_BYTES, max_depth=16)
    except OSError, InvalidInputError:
        raise OperationalError("GitHub record lookup failed") from None


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise EvidenceIntegrityError("invalid GitHub record time")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise EvidenceIntegrityError("invalid GitHub record time") from None


def _comment(reference: str, fetch: Fetch) -> tuple[str, datetime, str]:
    match = _COMMENT_REF.fullmatch(reference)
    if match is None:
        raise EvidenceIntegrityError("review reference is not an issue comment")
    record = fetch(f"issues/comments/{match[2]}")
    body = record.get("body")
    if (
        record.get("html_url") != reference
        or record.get("issue_url") != API + "issues/" + match[1]
        or not isinstance(body, str)
    ):
        raise EvidenceIntegrityError("review reference does not match its GitHub record")
    return match[1], _time(record.get("created_at")), body


def _producer_time(reference: str, fetch: Fetch) -> datetime:
    if _COMMENT_REF.fullmatch(reference):
        return _comment(reference, fetch)[1]
    match = _ISSUE_REF.fullmatch(reference)
    if match is None:
        raise EvidenceIntegrityError("invalid producer reference")
    record = fetch(f"issues/{match[1]}")
    if record.get("html_url") != reference:
        raise EvidenceIntegrityError("producer reference does not match its GitHub record")
    return _time(record.get("created_at"))


def _verify_run(review: dict, fetch: Fetch) -> None:
    run = review["qualified_run"]
    match = _RUN_REF.fullmatch(run["url"])
    if (
        match is None
        or type(run["artifact_id"]) is not int
        or run["artifact_id"] < 1
        or not isinstance(review["source_revision"], str)
        or re.fullmatch(r"[0-9a-f]{40}", review["source_revision"]) is None
    ):
        raise EvidenceIntegrityError("invalid qualified run reference")
    record = fetch(f"actions/runs/{match[1]}")
    jobs = fetch(f"actions/runs/{match[1]}/jobs?per_page=100").get("jobs")
    artifact = fetch(f"actions/artifacts/{run['artifact_id']}")
    commit = fetch(f"git/commits/{review['source_revision']}")
    parents = commit.get("parents")
    workflow_run = artifact.get("workflow_run")
    if (
        record.get("html_url") != run["url"]
        or record.get("head_sha") != run["feature_sha"]
        or not isinstance(jobs, list)
        or not any(
            isinstance(job, dict)
            and str(job.get("name", "")).endswith("model-check")
            and job.get("conclusion") == "success"
            for job in jobs
        )
        or artifact.get("name") != run["artifact_name"]
        or artifact.get("digest") != run["artifact_digest"]
        or not isinstance(workflow_run, dict)
        or workflow_run.get("id") != int(match[1])
        or not isinstance(parents, list)
        or [parent.get("sha") if isinstance(parent, dict) else None for parent in parents] != run["source_parents"]
    ):
        raise EvidenceIntegrityError("qualified run does not match its GitHub records")


def verify_review_records(
    review: dict, measurement: bytes, execution: bytes, subject: str, fetch: Fetch = github_fetch
) -> None:
    """Refuse a review whose references do not resolve to binding server records."""
    produced = _producer_time(review["producer_ref"], fetch)
    reviewer_issue, reviewed, _ = _comment(review["reviewer_ref"], fetch)
    acceptance_issue, accepted, body = _comment(review["acceptance_record_ref"], fetch)
    required = (
        digest(measurement),
        digest(execution),
        review["claim_digest"],
        subject,
        review["qualified_run"]["url"],
    )
    if reviewer_issue != acceptance_issue or not produced < reviewed < accepted:
        raise EvidenceIntegrityError("review records are not ordered after the producer record")
    if any(value not in body for value in required):
        raise EvidenceIntegrityError("acceptance record does not bind the reviewed evidence")
    _verify_run(review, fetch)
