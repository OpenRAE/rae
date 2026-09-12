"""Read issue lifecycle facts and the delivery workflow's requirement scope."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class IssueFacts:
    """Issue identity, lifecycle and authoritative requirement scope."""

    exists: bool
    is_open: bool
    requirement_uids: tuple[str, ...] = ()


def _requirement_lines(body: str) -> Iterator[str]:
    """Select the first level 2–4 Requirements section, including subheadings."""
    level: int | None = None
    for line in body.splitlines():
        heading = re.fullmatch(r"(#{1,6})\s(.+)", line)
        if heading:
            depth = len(heading[1])
            if level is not None and depth <= level:
                break
            if level is None and 2 <= depth <= 4 and heading[2].strip().casefold() == "requirements":
                level = depth
            continue
        if level is not None:
            yield line


def _leading_uids(line: str) -> Iterator[str]:
    bullet = re.fullmatch(r"\s*[-*+]\s+(\S.*)", line)
    if not bullet:
        return
    for token in re.split(r"[\s,;]+", bullet[1]):
        uid = token.lstrip("`[(").rstrip("`)].:")
        if len(uid) > 50 or not re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[A-Z0-9]*\d", uid, re.ASCII):
            break
        yield uid


def requirement_uids(body: str) -> tuple[str, ...]:
    """Read authoritative issue scope using the delivery workflow convention.

    A same-or-higher heading ends the first Requirements section; only the
    leading UID run of each bullet declares scope. This is not a PR claim.
    """
    return tuple(dict.fromkeys(uid for line in _requirement_lines(body) for uid in _leading_uids(line)))


class GitHubIssueLookup:
    """Read-only lookup for issues in exactly one GitHub repository."""

    def __init__(self, repository: str, token: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("GITHUB_REPOSITORY must have owner/repository form")
        if not token:
            raise ValueError("GH_TOKEN is required to verify closing issues")
        self._repository = repository
        self._token = token

    def __call__(self, number: int) -> IssueFacts:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{self._repository}/issues/{number}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "OpenRAE-pr-body-guard",
            },
        )
        try:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler())
            with opener.open(request, timeout=15) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return IssueFacts(False, False)
            raise RuntimeError(f"GitHub returned HTTP {exc.code}") from exc
        if (
            not isinstance(payload, dict)
            or "body" not in payload
            or payload["body"] is not None
            and not isinstance(payload["body"], str)
        ):
            raise RuntimeError("GitHub returned a malformed issue response")
        # Pull requests also appear through the issues endpoint and cannot be
        # used to satisfy an issue-closing requirement.
        exists = "pull_request" not in payload
        return IssueFacts(
            exists,
            exists and payload.get("state") == "open",
            requirement_uids(payload["body"] or ""),
        )
