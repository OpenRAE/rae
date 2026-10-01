#!/usr/bin/env python3
"""Derive the validated publisher handoff for one admitted release (#1227).

Evidence admission (`release_evidence_admission`) decides whether a release's
declared subjects are present and byte-exact. This module answers the separate
question a credentialed publisher needs answered: *which two files may be
published, and what are their digests*.

Keeping it apart from admission matters because the consumers differ. Admission
runs against the evidence bundle; these values cross a job boundary into a job
that holds publication credentials and no repository checkout. The expected
version therefore comes from the trusted release tag rather than from the
record being read, so an index that correctly describes a different release
cannot name itself into this one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from tools.release_evidence_admission import (
    SDIST_SUFFIX,
    WHEEL_SUFFIX,
    AdmissionError,
)

# The published distribution name. Only a stable SemVer release is publishable,
# so the tag maps to exactly one PEP 440 release version with no normalization
# ambiguity to resolve at the publication boundary.
_PROJECT_NAME = "raes"
_STABLE_RELEASE_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

# The roles a publisher consumes, and the scalars it receives for each, in a
# fixed order. A publisher gets these validated values and nothing else: it
# must not read the evidence index, because it holds publication credentials
# and the index travels with the artifact it describes.
_PUBLISHED_ROLES = ("wheel", "sdist")
_PUBLICATION_OUTPUTS = ("wheel_name", "wheel_sha256", "sdist_name", "sdist_sha256")


def release_version(expected_tag: str) -> str:
    """Return the release version the tag names, refusing anything unstable."""

    if not _STABLE_RELEASE_TAG.match(expected_tag):
        raise AdmissionError(
            "admission-release-tag-malformed",
            "expected a stable SemVer release tag such as v1.0.0",
        )
    return expected_tag[1:]


def _subjects_by_role(index: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Return the one declared subject per published role."""

    declared = index.get("subjects")
    if not isinstance(declared, Sequence) or isinstance(declared, (str, bytes)):
        raise AdmissionError("admission-index-unsupported", "evidence index has no subject set")

    by_role: dict[str, Mapping[str, Any]] = {}
    for item in declared:
        if not isinstance(item, Mapping):
            raise AdmissionError("admission-index-unsupported", "evidence index has a malformed subject")
        role = item.get("role")
        if not isinstance(role, str):
            continue
        if role in by_role:
            raise AdmissionError(
                "admission-subject-cardinality",
                f"evidence index declares more than one {role} subject",
            )
        by_role[role] = item

    for role in _PUBLISHED_ROLES:
        if role not in by_role:
            raise AdmissionError(
                "admission-subject-cardinality",
                f"evidence index does not declare a published {role}",
            )
    return by_role


def _subject_identity(role: str, subject: Mapping[str, Any]) -> tuple[str, str]:
    filename = subject.get("filename")
    digest = subject.get("sha256")
    if not isinstance(filename, str) or not isinstance(digest, str):
        raise AdmissionError("admission-index-unsupported", f"admitted {role} has no name and digest")
    return filename, digest


def _require_release_name(role: str, filename: str, version: str) -> None:
    """Refuse an admitted name that is not this release's distribution.

    A wheel carries build tags after the version, so its version field is
    delimited rather than terminal. Matching the delimiter keeps `1.2.30` from
    satisfying a `1.2.3` release.
    """

    if role == "sdist":
        correct = filename == f"{_PROJECT_NAME}-{version}{SDIST_SUFFIX}"
    else:
        correct = filename.startswith(f"{_PROJECT_NAME}-{version}-") and filename.endswith(WHEEL_SUFFIX)
    if not correct:
        raise AdmissionError(
            "admission-subject-version-mismatch",
            f"admitted {role} {filename!r} is not a {_PROJECT_NAME} {version} distribution",
        )


def admitted_publication_subjects(index: Mapping[str, Any] | Any, *, expected_tag: str) -> dict[str, str]:
    """Return the validated publisher handoff for one admitted release.

    Size and digest equality against the files themselves belongs to
    admission's subject verification; this decides that the admitted *names*
    belong to the release being published, which no other check does.
    """

    if not isinstance(index, Mapping):
        raise AdmissionError("admission-index-unsupported", "evidence index is not a JSON object")

    version = release_version(expected_tag)
    by_role = _subjects_by_role(index)

    subjects: dict[str, str] = {}
    for role in _PUBLISHED_ROLES:
        filename, digest = _subject_identity(role, by_role[role])
        _require_release_name(role, filename, version)
        subjects[f"{role}_name"] = filename
        subjects[f"{role}_sha256"] = digest
    return {key: subjects[key] for key in _PUBLICATION_OUTPUTS}


def render_publication_outputs(subjects: Mapping[str, str]) -> str:
    """Render the handoff as fixed `KEY=value` lines for a workflow output.

    Each value lands in a line-delimited Actions output file, so a newline in
    one scalar would let it declare another. The values are already validated
    names and hex digests; refusing a control character here keeps that
    guarantee at the sink rather than relying on it holding upstream.
    """

    lines = []
    for key in _PUBLICATION_OUTPUTS:
        value = subjects[key]
        if not value or any(character in value for character in "\r\n="):
            raise AdmissionError(
                "admission-publication-output-unsafe",
                f"admitted {key} is not representable as a workflow output",
            )
        lines.append(f"{key}={value}")
    return "\n".join(lines)


__all__ = [
    "admitted_publication_subjects",
    "release_version",
    "render_publication_outputs",
]
