"""#1227: the publication boundary consumes only the admitted tested bytes.

Admission already binds one wheel and one sdist to a release by size and
SHA-256. Two gaps remain at the boundary where a credentialed publisher acts:
a subject filename is never checked against the resolved tag version, and the
validated identity is never handed to the publisher jobs. These cases drive
both, so a publisher cannot be pointed at a correctly-shaped artifact that
belongs to a different version, and cannot publish a file the admission job
did not validate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tools.release_evidence_admission import (
    AdmissionError,
    ReleaseIdentity,
    admitted_publication_subjects,
    build_evidence_index,
)

_IDENTITY = ReleaseIdentity(
    repository="OpenRAE/rae",
    source_sha="a" * 40,
    workflow_ref="OpenRAE/rae/.github/workflows/release-please.yml@refs/heads/main",
    workflow_sha="e" * 40,
    run_id="1234567890",
    run_attempt="1",
    tag="v1.2.3",
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _index(
    tmp_path: Path,
    *,
    wheel_name: str = "raes-1.2.3-py3-none-any.whl",
    sdist_name: str = "raes-1.2.3.tar.gz",
) -> dict[str, object]:
    """Build one evidence index over a named wheel/sdist pair.

    Only the index is needed here: filename correspondence and the publisher
    handoff are decided from the admitted record, not from a second scan of
    the directory.
    """

    dist = tmp_path / "dist"
    evidence = tmp_path / "evidence"
    _write(dist / wheel_name, b"wheel-bytes")
    _write(dist / sdist_name, b"sdist-bytes")
    _write(dist / "from-sdist" / wheel_name, b"derived-bytes")
    _write(evidence / "build-inventory.json", b"{}")
    return build_evidence_index(
        distribution_dir=dist,
        evidence_dir=evidence,
        identity=_IDENTITY,
        profile_id="public-linux-x86_64-cp312-all-extras",
        policy_hashes={"tooling_policy_sha256": "b" * 64},
    )


def test_admitted_subjects_are_the_wheel_and_sdist_digests(tmp_path: Path) -> None:
    """The handoff carries exactly the two published basenames and digests."""

    subjects = admitted_publication_subjects(index=_index(tmp_path), expected_tag="v1.2.3")

    assert subjects == {
        "wheel_name": "raes-1.2.3-py3-none-any.whl",
        "wheel_sha256": _sha256(b"wheel-bytes"),
        "sdist_name": "raes-1.2.3.tar.gz",
        "sdist_sha256": _sha256(b"sdist-bytes"),
    }


def test_sdist_named_for_another_version_is_refused(tmp_path: Path) -> None:
    """A correctly-shaped sdist from a different version is not this release."""

    index = _index(tmp_path, sdist_name="raes-9.9.9.tar.gz")

    with pytest.raises(AdmissionError) as excinfo:
        admitted_publication_subjects(index=index, expected_tag="v1.2.3")
    assert excinfo.value.code == "admission-subject-version-mismatch"


def test_wheel_named_for_another_version_is_refused(tmp_path: Path) -> None:
    index = _index(tmp_path, wheel_name="raes-9.9.9-py3-none-any.whl")

    with pytest.raises(AdmissionError) as excinfo:
        admitted_publication_subjects(index=index, expected_tag="v1.2.3")
    assert excinfo.value.code == "admission-subject-version-mismatch"


def test_wheel_version_prefix_must_be_a_whole_version_field(tmp_path: Path) -> None:
    """`raes-1.2.30-...` does not satisfy a `1.2.3` release."""

    index = _index(tmp_path, wheel_name="raes-1.2.30-py3-none-any.whl")

    with pytest.raises(AdmissionError) as excinfo:
        admitted_publication_subjects(index=index, expected_tag="v1.2.3")
    assert excinfo.value.code == "admission-subject-version-mismatch"


def test_foreign_project_name_is_refused(tmp_path: Path) -> None:
    """Only the release's own distribution is a publication candidate."""

    index = _index(tmp_path, wheel_name="other-1.2.3-py3-none-any.whl")

    with pytest.raises(AdmissionError) as excinfo:
        admitted_publication_subjects(index=index, expected_tag="v1.2.3")
    assert excinfo.value.code == "admission-subject-version-mismatch"


@pytest.mark.parametrize("tag", ["1.2.3", "v1.2", "v1.2.3-rc1", "vx.y.z", "", "v01.2.3"])
def test_unstable_or_malformed_tags_are_refused(tmp_path: Path, tag: str) -> None:
    """The expected version comes from a strict stable-SemVer release tag."""

    index = _index(tmp_path)

    with pytest.raises(AdmissionError) as excinfo:
        admitted_publication_subjects(index=index, expected_tag=tag)
    assert excinfo.value.code == "admission-release-tag-malformed"


def test_index_without_both_published_subjects_is_refused(tmp_path: Path) -> None:
    """A truncated subject set never yields a partial publisher handoff."""

    index = _index(tmp_path)
    index["subjects"] = [item for item in index["subjects"] if item["role"] != "sdist"]

    with pytest.raises(AdmissionError) as excinfo:
        admitted_publication_subjects(index=index, expected_tag="v1.2.3")
    assert excinfo.value.code == "admission-subject-cardinality"


def test_derived_test_wheel_is_not_a_publication_candidate(tmp_path: Path) -> None:
    """The sdist-built wheel shares a basename but is never published."""

    index = _index(tmp_path)
    derived = next(item for item in index["test_subjects"] if item["role"] == "derived-test-wheel")
    subjects = admitted_publication_subjects(index=index, expected_tag="v1.2.3")

    assert derived["filename"] == subjects["wheel_name"]
    assert derived["sha256"] != subjects["wheel_sha256"]
    assert _sha256(b"derived-bytes") not in set(subjects.values())


def test_emitted_scalars_are_shell_safe_key_values(tmp_path: Path) -> None:
    """The handoff is written as fixed `KEY=value` lines for a job output."""

    from tools.release_evidence_admission import render_publication_outputs

    rendered = render_publication_outputs(
        admitted_publication_subjects(index=_index(tmp_path), expected_tag="v1.2.3")
    )

    assert rendered.splitlines() == [
        "wheel_name=raes-1.2.3-py3-none-any.whl",
        f"wheel_sha256={_sha256(b'wheel-bytes')}",
        "sdist_name=raes-1.2.3.tar.gz",
        f"sdist_sha256={_sha256(b'sdist-bytes')}",
    ]
    # A GitHub Actions output line is terminated per value; an injected newline
    # or a stray `=` in a name would let one scalar declare another.
    for line in rendered.splitlines():
        key, _, value = line.partition("=")
        assert key.isidentifier()
        assert "\n" not in value and "\r" not in value


def test_publication_subjects_reject_a_non_mapping_index() -> None:
    with pytest.raises(AdmissionError) as excinfo:
        admitted_publication_subjects(index=json.loads("[]"), expected_tag="v1.2.3")
    assert excinfo.value.code == "admission-index-unsupported"


def test_cli_verify_accepts_an_emit_subjects_sink() -> None:
    """The admission job writes the handoff through the existing verify command."""

    from tools import release_evidence

    args = release_evidence._parse_args(
        [
            "verify",
            "--distribution-dir",
            "dist",
            "--evidence-dir",
            "evidence",
            "--signer-workflow",
            "OpenRAE/rae/.github/workflows/release-please.yml",
            "--release-tag",
            "v1.2.3",
            "--emit-subjects",
            "subjects.env",
        ]
    )

    assert args.emit_subjects == Path("subjects.env")


def test_cli_canonicalizes_the_emit_subjects_sink() -> None:
    """The handoff sink is operator input reaching a filesystem write.

    Every other path this command accepts is canonicalized before use so no
    unresolved `..` component survives into a read or write; a write sink is
    the case where that matters most.
    """

    import ast
    import inspect

    from tools import release_evidence

    main = next(
        node
        for node in ast.walk(ast.parse(inspect.getsource(release_evidence)))
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    canonicalized = {
        element.value
        for node in ast.walk(main)
        if isinstance(node, ast.Tuple)
        for element in node.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }

    assert "emit_subjects" in canonicalized


def test_cli_emits_the_handoff_only_after_admission_succeeds() -> None:
    """A rejected release must never leave publishable scalars behind.

    The scalars authorize a credentialed publisher, so emitting them before or
    independently of `verify_admission` would hand a publisher an identity the
    admission boundary had not accepted.
    """

    import ast
    import inspect

    from tools import release_evidence

    main = next(
        node
        for node in ast.walk(ast.parse(inspect.getsource(release_evidence)))
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    def _position(needle: str) -> int:
        return next(
            index
            for index, statement in enumerate(ast.walk(main))
            if isinstance(statement, ast.Call)
            and isinstance(statement.func, ast.Name)
            and statement.func.id == needle
        )

    assert _position("verify_admission") < _position("render_publication_outputs")
