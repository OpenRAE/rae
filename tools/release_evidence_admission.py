#!/usr/bin/env python3
"""Admit one release's exact output subjects and their authenticated evidence.

ADR-107 binds the complete release identity to the exact bytes a publisher will
consume. This module builds that binding and, at each publisher handoff, refuses
it before any usable output is produced. Absent or rejected evidence is a
failure, never an optional report.

Every document read here is untrusted parser input even after transfer, so
reads are size-bounded and structurally checked. Signature, certificate and
issuer verification belong to the maintained verifier (`gh attestation
verify`); this module consumes the producer identity that verifier established
and decides release association against reviewed policy.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

# Parsed JSON is an untyped document tree; naming it is clearer than `Any`.
JsonValue: TypeAlias = "str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]"

SCHEMA_VERSION = "raes-release-evidence/v1"
BUILD_INVENTORY_SCHEMA_VERSION = "raes-build-inventory/v1"

# The evidence index travels with the evidence it describes, so candidate build
# code could rewrite both before they are uploaded. The required evidence set is
# therefore fixed here rather than read out of the index: an index naming fewer
# sidecars must not discharge the obligation to carry them.
INDEX_FILENAME = "release-evidence-index.json"
REQUIRED_EVIDENCE = ("build-inventory.json", "sdist.cdx.json", "wheel.cdx.json")

# Evidence documents are small structured records. The bound keeps a malformed
# or hostile sidecar from being parsed unbounded at a publication boundary.
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
_READ_CHUNK = 1024 * 1024

_WHEEL_SUFFIX = ".whl"
_SDIST_SUFFIX = ".tar.gz"
_DERIVED_DIRECTORY = "from-sdist"

# The published distribution name. The release tag is the only accepted source
# of the expected version, and only a stable SemVer release is publishable, so
# the tag maps to exactly one PEP 440 release version with no normalization
# ambiguity to resolve at the publication boundary.
_PROJECT_NAME = "raes"
_STABLE_RELEASE_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

# The scalars a credentialed publisher needs, in a fixed order. A publisher
# gets these validated values and nothing else: it must not read the evidence
# index, because it holds publication credentials and the index travels with
# the artifact it describes.
_PUBLICATION_OUTPUTS = ("wheel_name", "wheel_sha256", "sdist_name", "sdist_sha256")


class AdmissionError(Exception):
    """An admission failure carrying a stable, publishable failure code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReleaseIdentity:
    """The run that produced a release, as one value.

    These six fields are always produced, recorded and checked together, so
    passing them as a group keeps a caller from supplying five of six or
    transposing two strings of the same shape.
    """

    repository: str
    source_sha: str
    workflow_ref: str
    # The producer workflow's own revision. ADR-107 keeps this distinct from the
    # candidate source revision; they are different identities.
    workflow_sha: str
    run_id: str
    run_attempt: str
    tag: str


@dataclass(frozen=True)
class ProducerIdentity:
    """The producer a maintained verifier established for an attestation."""

    issuer: str
    repository: str
    workflow_ref: str


def digest_file(path: Path) -> tuple[int, str]:
    """Return the exact size and SHA-256 of one regular file."""

    if not path.is_file() or path.is_symlink():
        raise AdmissionError("admission-subject-missing", f"{path.name} is not a regular file")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_READ_CHUNK):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _single(paths: Sequence[Path], role: str) -> Path:
    if len(paths) != 1:
        raise AdmissionError(
            "admission-subject-cardinality",
            f"expected exactly one {role}, found {len(paths)}",
        )
    return paths[0]


def _distribution_files(distribution_dir: Path) -> tuple[Path, Path, Path]:
    wheels = sorted(p for p in distribution_dir.glob("*.whl") if p.is_file())
    sdists = sorted(p for p in distribution_dir.glob(f"*{_SDIST_SUFFIX}") if p.is_file())
    derived = sorted(p for p in (distribution_dir / _DERIVED_DIRECTORY).glob("*.whl") if p.is_file())
    return (
        _single(wheels, "release wheel"),
        _single(sdists, "source distribution"),
        _single(derived, "sdist-built wheel"),
    )


def build_evidence_index(
    *,
    distribution_dir: Path,
    evidence_dir: Path,
    identity: ReleaseIdentity,
    profile_id: str,
    policy_hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Bind every output subject and evidence document to one release identity."""

    wheel, sdist, derived = _distribution_files(distribution_dir)

    def _record(role: str, path: Path, derived_from: str | None = None) -> dict[str, Any]:
        size, sha256 = digest_file(path)
        record: dict[str, Any] = {
            "role": role,
            "path": path.relative_to(distribution_dir).as_posix(),
            "filename": path.name,
            "size": size,
            "sha256": sha256,
        }
        if derived_from is not None:
            record["derived_from"] = derived_from
        return record

    # `subjects` is the published set the publishers actually consume. The
    # sdist-built wheel is a build-time test subject that is never uploaded, so
    # it keeps its own digest-bound identity in `test_subjects` rather than
    # joining a set the publisher is then expected to produce.
    subjects = [_record("wheel", wheel), _record("sdist", sdist)]
    test_subjects = [_record("derived-test-wheel", derived, sdist.name)]

    evidence = []
    for path in sorted(evidence_dir.iterdir()):
        if not path.is_file() or path.is_symlink():
            continue
        size, sha256 = digest_file(path)
        evidence.append({"filename": path.name, "size": size, "sha256": sha256})

    return {
        "schema_version": SCHEMA_VERSION,
        "release": {
            "repository": identity.repository,
            "source_sha": identity.source_sha,
            "workflow_ref": identity.workflow_ref,
            "workflow_sha": identity.workflow_sha,
            "run_id": identity.run_id,
            "run_attempt": identity.run_attempt,
            "tag": identity.tag,
        },
        "profile": {"python_closure_profile_id": profile_id},
        "policy": dict(policy_hashes),
        "subjects": subjects,
        "test_subjects": test_subjects,
        "evidence": evidence,
    }


def _load_bounded_json(path: Path, declared_sha256: str) -> JsonValue:
    size, sha256 = digest_file(path)
    if sha256 != declared_sha256:
        raise AdmissionError(
            "admission-evidence-digest-mismatch",
            f"{path.name} does not match its recorded digest",
        )
    if size > MAX_EVIDENCE_BYTES:
        raise AdmissionError(
            "admission-evidence-oversized",
            f"{path.name} exceeds the evidence size bound",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, ValueError) as exc:
        raise AdmissionError("admission-evidence-unparsable", f"{path.name} could not be parsed") from exc


def _reject_duplicate_keys(pairs: Sequence[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    seen: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def _sbom_subject_digest(document: JsonValue) -> str | None:
    """Return the SHA-256 the document binds itself to, if it binds one."""

    metadata = document.get("metadata") if isinstance(document, Mapping) else None
    component = metadata.get("component") if isinstance(metadata, Mapping) else None
    hashes = component.get("hashes") if isinstance(component, Mapping) else None
    return next(
        (
            entry["content"]
            for entry in (hashes or ())
            if isinstance(entry, Mapping) and entry.get("alg") == "SHA-256" and isinstance(entry.get("content"), str)
        ),
        None,
    )


def _verify_subjects(distribution_dir: Path, index: Mapping[str, Any]) -> dict[str, str]:
    """Match the distribution directory exactly against the admitted subject set.

    Subjects are keyed by relative path: the sdist-built wheel shares a basename
    with the directly built release wheel, so a basename key would let one stand
    in for the other.
    """

    declared = {item["path"]: item for item in index["subjects"]}
    present: dict[str, Path] = {}
    unexpected: list[str] = []
    for entry in sorted(distribution_dir.iterdir()):
        relative = entry.name
        if entry.is_file() and not entry.is_symlink():
            present[relative] = entry
        else:
            # A publisher consumes the downloaded distribution set only. A
            # nested directory here (a build-time `from-sdist/` tree, say) is
            # not part of that set and must not be published alongside it.
            unexpected.append(relative)
    unexpected.extend(sorted(set(present) - set(declared)))
    if unexpected:
        raise AdmissionError(
            "admission-unexpected-distribution",
            f"distribution directory carries undeclared entries: {sorted(unexpected)}",
        )
    digests: dict[str, str] = {}
    for relative, record in declared.items():
        path = present.get(relative)
        if path is None:
            raise AdmissionError("admission-subject-missing", f"declared subject {relative} is absent")
        size, sha256 = digest_file(path)
        if size != record["size"] or sha256 != record["sha256"]:
            raise AdmissionError(
                "admission-subject-digest-mismatch",
                f"{relative} does not match its admitted bytes",
            )
        digests[relative] = sha256
    return digests


def _require_declared_set(evidence_dir: Path, declared: Mapping[str, Any]) -> None:
    """The directory must hold exactly the declared documents, plus the index.

    The required set is fixed here rather than read from the index, so an index
    naming fewer sidecars cannot discharge the obligation to carry them. An
    undeclared sidecar is refused before handoff: the signer and the GitHub
    publisher both consume `evidence/*.json`, so an extra file would otherwise be
    attested and retained without ever being semantically admitted.
    """

    missing_required = sorted(set(REQUIRED_EVIDENCE) - set(declared))
    if missing_required:
        raise AdmissionError(
            "admission-required-evidence-missing",
            f"evidence index does not declare required documents: {missing_required}",
        )
    present = {path.name for path in sorted(evidence_dir.iterdir()) if path.is_file() and not path.is_symlink()}
    unexpected = sorted(present - set(declared) - {INDEX_FILENAME})
    if unexpected:
        raise AdmissionError(
            "admission-unexpected-evidence",
            f"evidence directory carries undeclared documents: {unexpected}",
        )


def _load_declared(evidence_dir: Path, declared: Mapping[str, Any]) -> dict[str, Any]:
    """Read every declared document at the digest the index recorded for it."""

    documents: dict[str, Any] = {}
    for filename, record in declared.items():
        path = evidence_dir / filename
        if not path.is_file() or path.is_symlink():
            raise AdmissionError(
                "admission-evidence-missing",
                f"declared evidence {filename} is absent",
            )
        documents[filename] = _load_bounded_json(path, record["sha256"])
    return documents


def _check_document_subjects(filename: str, document: JsonValue, admitted: set[str]) -> None:
    """Every document must describe bytes that were actually admitted."""

    if filename.endswith(".cdx.json"):
        subject = _sbom_subject_digest(document)
        if subject is None or subject not in admitted:
            raise AdmissionError(
                "admission-sbom-foreign-subject",
                f"{filename} does not bind an admitted output subject",
            )
        return
    if isinstance(document, Mapping) and document.get("schema_version") == BUILD_INVENTORY_SCHEMA_VERSION:
        recorded = {item.get("sha256") for item in document.get("subjects", []) or () if isinstance(item, Mapping)}
        if not recorded or not recorded <= admitted:
            raise AdmissionError(
                "admission-inventory-subject-mismatch",
                f"{filename} records a subject that was not admitted",
            )


def _verify_evidence(
    evidence_dir: Path,
    index: Mapping[str, Any],
    subject_digests: Mapping[str, str],
) -> dict[str, str]:
    """Admit the evidence directory against a fixed contract, not the index alone."""

    declared = {record["filename"]: record for record in index["evidence"]}
    _require_declared_set(evidence_dir, declared)
    documents = _load_declared(evidence_dir, declared)

    admitted = set(subject_digests.values())
    for filename, document in documents.items():
        _check_document_subjects(filename, document, admitted)

    digests = {filename: record["sha256"] for filename, record in declared.items()}

    # The index is evidence too. It is not listed in its own `evidence` array,
    # so bind it explicitly and require its attestation alongside the rest.
    index_path = evidence_dir / INDEX_FILENAME
    if not index_path.is_file() or index_path.is_symlink():
        raise AdmissionError(
            "admission-evidence-missing",
            f"{INDEX_FILENAME} is absent from the evidence directory",
        )
    digests[INDEX_FILENAME] = digest_file(index_path)[1]
    return digests


def _verify_attestations(
    digests: Iterable[str],
    attestations: Mapping[str, ProducerIdentity],
    approved_producers: Sequence[ProducerIdentity],
) -> None:
    approved = set(approved_producers)
    for digest in digests:
        producer = attestations.get(digest)
        if producer is None:
            raise AdmissionError(
                "admission-attestation-missing",
                "an admitted artifact has no verified attestation",
            )
        if producer not in approved:
            raise AdmissionError(
                "admission-attestation-foreign-producer",
                "an attestation was produced by an identity that is not approved",
            )


def release_version(expected_tag: str) -> str:
    """Return the release version the tag names, refusing anything unstable."""

    if not _STABLE_RELEASE_TAG.match(expected_tag):
        raise AdmissionError(
            "admission-release-tag-malformed",
            "expected a stable SemVer release tag such as v1.0.0",
        )
    return expected_tag[1:]


def admitted_publication_subjects(index: Mapping[str, Any] | Any, *, expected_tag: str) -> dict[str, str]:
    """Return the validated publisher handoff for one admitted release.

    The expected version comes from the trusted tag rather than from the record
    being read, so an index that correctly describes a different release cannot
    name itself into this one. Size and digest equality is checked against the
    files themselves by `_verify_subjects`; this decides that the admitted
    *names* belong to the release being published, which no other check does.
    """

    if not isinstance(index, Mapping):
        raise AdmissionError("admission-index-unsupported", "evidence index is not a JSON object")
    version = release_version(expected_tag)

    declared = index.get("subjects")
    if not isinstance(declared, Sequence) or isinstance(declared, (str, bytes)):
        raise AdmissionError("admission-index-unsupported", "evidence index has no subject set")
    by_role: dict[str, Mapping[str, Any]] = {}
    for item in declared:
        if not isinstance(item, Mapping):
            raise AdmissionError("admission-index-unsupported", "evidence index has a malformed subject")
        role = item.get("role")
        if role in by_role:
            raise AdmissionError(
                "admission-subject-cardinality",
                f"evidence index declares more than one {role} subject",
            )
        if isinstance(role, str):
            by_role[role] = item
    missing = [role for role in ("wheel", "sdist") if role not in by_role]
    if missing:
        raise AdmissionError(
            "admission-subject-cardinality",
            f"evidence index does not declare a published {missing[0]}",
        )

    expected_sdist = f"{_PROJECT_NAME}-{version}{_SDIST_SUFFIX}"
    # A wheel carries build tags after the version, so its version field is
    # delimited rather than terminal. Matching the delimiter keeps `1.2.30`
    # from satisfying a `1.2.3` release.
    wheel_prefix = f"{_PROJECT_NAME}-{version}-"

    subjects: dict[str, str] = {}
    for role, item in (("wheel", by_role["wheel"]), ("sdist", by_role["sdist"])):
        filename = item.get("filename")
        digest = item.get("sha256")
        if not isinstance(filename, str) or not isinstance(digest, str):
            raise AdmissionError("admission-index-unsupported", f"admitted {role} has no name and digest")
        correct_name = (
            filename == expected_sdist
            if role == "sdist"
            else filename.startswith(wheel_prefix) and filename.endswith(_WHEEL_SUFFIX)
        )
        if not correct_name:
            raise AdmissionError(
                "admission-subject-version-mismatch",
                f"admitted {role} {filename!r} is not a {_PROJECT_NAME} {version} distribution",
            )
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


def verify_admission(
    *,
    distribution_dir: Path,
    evidence_dir: Path,
    index: Mapping[str, Any],
    attestations: Mapping[str, ProducerIdentity],
    approved_producers: Sequence[ProducerIdentity],
    expected: ReleaseIdentity,
    policy_hashes: Mapping[str, str],
) -> None:
    """Refuse the release unless every subject and sidecar is admissible.

    Expected identities come from the trusted verifying context, never from the
    evidence being verified, so a replayed or foreign bundle cannot describe
    itself into acceptance.
    """

    if index.get("schema_version") != SCHEMA_VERSION:
        raise AdmissionError(
            "admission-index-unsupported",
            "evidence index schema version is not supported",
        )

    release = index.get("release")
    if not isinstance(release, Mapping):
        raise AdmissionError("admission-index-unsupported", "evidence index has no release identity")
    if (
        release.get("repository") != expected.repository
        or release.get("run_id") != expected.run_id
        or release.get("run_attempt") != expected.run_attempt
        or release.get("source_sha") != expected.source_sha
        or release.get("tag") != expected.tag
    ):
        raise AdmissionError(
            "admission-run-identity-mismatch",
            "evidence was produced by a different repository, run, attempt or source revision",
        )

    recorded_policy = index.get("policy")
    if not isinstance(recorded_policy, Mapping) or dict(recorded_policy) != dict(policy_hashes):
        raise AdmissionError(
            "admission-policy-hash-mismatch",
            "evidence records policy hashes that differ from the verifying tree",
        )

    # Names are checked against the trusted tag before the bytes are read, so a
    # foreign-version artifact is refused even when its own record is internally
    # consistent.
    admitted_publication_subjects(index, expected_tag=expected.tag)

    subject_digests = _verify_subjects(distribution_dir, index)
    evidence_digests = _verify_evidence(evidence_dir, index, subject_digests)
    _verify_attestations(
        [*subject_digests.values(), *evidence_digests.values()],
        attestations,
        approved_producers,
    )


__all__ = [
    "BUILD_INVENTORY_SCHEMA_VERSION",
    "ReleaseIdentity",
    "INDEX_FILENAME",
    "REQUIRED_EVIDENCE",
    "MAX_EVIDENCE_BYTES",
    "SCHEMA_VERSION",
    "AdmissionError",
    "ProducerIdentity",
    "admitted_publication_subjects",
    "build_evidence_index",
    "digest_file",
    "release_version",
    "render_publication_outputs",
    "verify_admission",
]
