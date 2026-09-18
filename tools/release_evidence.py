#!/usr/bin/env python3
# ruff: noqa: E402
"""Generate and admit output-bound release evidence (issue #1226).

`generate` runs in the read-only build job and writes the runtime SBOMs, the
build/tool/native input inventory and the evidence index into a directory kept
separate from the distribution directory: the corpus check rejects unexpected
files beside the distributions, and the publishers consume that directory.

`verify` runs at each publisher handoff and refuses the release unless every
declared subject and sidecar is present, byte-exact, bound to this run, and
attested by an approved producer. It has no partial-success path.

Release identity is read from explicitly named `GITHUB_*` environment fields
rather than assembled from free-form input, and no credential-bearing value is
read or recorded.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_tooling_artifact_policy import tooling_policy_sha256
from tools.generate_python_closures import reviewed_python_full_version
from tools.generate_python_closures_locks import target_environment
from tools.python_closure_profiles import load_python_closure_profile
from tools.python_closure_wheelhouse import operator_path
from tools.release_evidence_admission import (
    INDEX_FILENAME,
    AdmissionError,
    ProducerIdentity,
    ReleaseIdentity,
    build_evidence_index,
    digest_file,
    verify_admission,
)
from tools.release_evidence_documents import (
    BuildInputs,
    EvidenceDocumentError,
    render_build_inventory,
    render_runtime_sbom,
)
from tools.release_evidence_publication import (
    admitted_publication_subjects,
    render_publication_outputs,
)
from tools.release_evidence_sbom import (
    RuntimeClosureError,
    observed_installation,
    reconcile_runtime_closure,
    wheel_metadata,
)
from tools.release_evidence_verifier import (
    VerifierError,
    build_verify_command,
    parse_verifier_output,
)
from tools.release_evidence_workflows import WorkflowInputError, workflow_actions

INVENTORY_FILENAME = "build-inventory.json"
_VERIFIER_TIMEOUT_SECONDS = 120

_REQUIRED_ENVIRONMENT = (
    "GITHUB_REPOSITORY",
    "GITHUB_SHA",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_WORKFLOW_SHA",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
)


class ReleaseEvidenceError(Exception):
    """A CLI-boundary failure carrying a stable, publishable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def release_identity(environment: Mapping[str, str]) -> dict[str, str]:
    """Read the run's identity from explicitly named environment fields."""

    missing = [name for name in _REQUIRED_ENVIRONMENT if not environment.get(name)]
    if missing:
        raise ReleaseEvidenceError(
            "release-identity-incomplete",
            f"release identity environment is incomplete: {missing}",
        )
    return {
        "repository": environment["GITHUB_REPOSITORY"],
        "source_sha": environment["GITHUB_SHA"],
        "workflow_ref": environment["GITHUB_WORKFLOW_REF"],
        "workflow_sha": environment["GITHUB_WORKFLOW_SHA"],
        "run_id": environment["GITHUB_RUN_ID"],
        "run_attempt": environment["GITHUB_RUN_ATTEMPT"],
    }


def _distribution_paths(distribution_dir: Path) -> tuple[Path, Path, Path]:
    wheels = sorted(p for p in distribution_dir.glob("*.whl") if p.is_file())
    sdists = sorted(p for p in distribution_dir.glob("*.tar.gz") if p.is_file())
    derived = sorted(p for p in (distribution_dir / "from-sdist").glob("*.whl") if p.is_file())
    if len(wheels) != 1 or len(sdists) != 1 or len(derived) != 1:
        raise ReleaseEvidenceError(
            "distribution-set-unexpected",
            "expected exactly one wheel, one sdist and one sdist-built wheel",
        )
    return wheels[0], sdists[0], derived[0]


def _lock_hashes(repo_root: Path) -> dict[str, str]:
    paths = {
        "project_lock_sha256": "implementations/python/uv.lock",
        "tool_lock_sha256": "implementations/tooling/python/uv.lock",
        "build_constraints_sha256": "implementations/tooling/python/build-constraints.txt",
    }
    return {key: digest_file(repo_root / value)[1] for key, value in paths.items()}


@dataclass(frozen=True)
class GeneratePaths:
    """The four admitted directories one generation reads and writes."""

    repo_root: Path
    distribution_dir: Path
    evidence_dir: Path
    environment_dir: Path
    sdist_environment_dir: Path


def generate(
    *,
    paths: GeneratePaths,
    profile_id: str,
    release_tag: str,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    """Write every evidence document for one built release."""

    repo_root = paths.repo_root
    distribution_dir = paths.distribution_dir
    evidence_dir = paths.evidence_dir
    environment_dir = paths.environment_dir
    sdist_environment_dir = paths.sdist_environment_dir

    wheel, sdist, derived = _distribution_paths(distribution_dir)
    identity = release_identity(environment)
    profile = load_python_closure_profile(profile_id)
    markers = target_environment(
        profile.python_version,
        profile.platform,
        full_version=reviewed_python_full_version(profile.python_version, repo_root=repo_root),
    )
    lock = tomllib.loads((repo_root / "implementations" / "python" / "uv.lock").read_text(encoding="utf-8"))

    evidence_dir.mkdir(parents=True, exist_ok=True)
    subject_digests: dict[str, str] = {}

    # The sdist declares the same requirements it builds into; its runtime
    # closure is read from the wheel built out of it, while the SBOM subject
    # stays the original archive. The derived wheel is recorded as the metadata
    # source so the relationship is explicit rather than implied.
    for role, subject_path, metadata_path, target_venv in (
        ("wheel", wheel, wheel, environment_dir),
        ("sdist", sdist, derived, sdist_environment_dir),
    ):
        metadata = wheel_metadata(metadata_path)
        closure = reconcile_runtime_closure(
            metadata,
            lock=lock,
            installed_versions=observed_installation(target_venv),
            environment=markers,
            extras=(),
        )
        _size, subject_digest = digest_file(subject_path)
        subject_digests[role] = subject_digest
        document = render_runtime_sbom(
            closure=closure,
            subject_name=str(metadata.name),
            subject_version=str(metadata.version),
            subject_filename=subject_path.name,
            subject_digest=subject_digest,
            subject_role=role,
        )
        if role == "sdist":
            document["metadata"]["component"]["properties"].append(
                {
                    "name": "raes:metadata-source-digest",
                    "value": digest_file(derived)[1],
                }
            )
        _write_json(evidence_dir / f"{role}.cdx.json", document)

    policy_hashes = {"tooling_policy_sha256": tooling_policy_sha256(repo_root)}
    inventory = render_build_inventory(
        subjects=[
            {
                "role": "wheel",
                "filename": wheel.name,
                "sha256": subject_digests["wheel"],
            },
            {
                "role": "sdist",
                "filename": sdist.name,
                "sha256": subject_digests["sdist"],
            },
            {
                "role": "derived-test-wheel",
                "filename": derived.name,
                "sha256": digest_file(derived)[1],
            },
        ],
        inputs=BuildInputs(
            interpreter={
                "implementation": "cpython",
                "version": markers["python_full_version"],
                "abi": profile.abi,
                "platform": profile.platform,
            },
            build_backend=_build_backend(repo_root),
            tool_inputs=_tool_inputs(repo_root),
            native_inputs=[],
            actions=_workflow_actions(repo_root),
            runner={
                "image": environment.get("ImageOS", "unknown"),
                "architecture": profile.platform,
                "observed": False,
            },
        ),
        lock_hashes=_lock_hashes(repo_root),
        policy_hashes=policy_hashes,
        release={**identity, "tag": release_tag},
        profile_id=profile_id,
    )
    _write_json(evidence_dir / INVENTORY_FILENAME, inventory)

    index = build_evidence_index(
        distribution_dir=distribution_dir,
        evidence_dir=evidence_dir,
        identity=ReleaseIdentity(**identity, tag=release_tag),
        profile_id=profile_id,
        policy_hashes=policy_hashes,
    )
    _write_json(evidence_dir / INDEX_FILENAME, index)
    return index


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_backend(repo_root: Path) -> dict[str, str]:
    project = tomllib.loads((repo_root / "implementations" / "python" / "pyproject.toml").read_text(encoding="utf-8"))
    requires = project.get("build-system", {}).get("requires", [])
    name, _, version = str(requires[0]).partition("==") if requires else ("", "", "")
    return {"name": name, "version": version}


def _tool_inputs(repo_root: Path) -> list[dict[str, str]]:
    tool_project = tomllib.loads(
        (repo_root / "implementations" / "tooling" / "python" / "pyproject.toml").read_text(encoding="utf-8")
    )
    inputs = []
    for value in tool_project.get("project", {}).get("dependencies", []):
        name, _, version = str(value).partition("==")
        inputs.append({"name": name, "version": version})
    return inputs


def _workflow_actions(repo_root: Path) -> list[dict[str, str]]:
    """Record pinned actions from the release workflow and its reusable calls."""
    try:
        return workflow_actions(repo_root)
    except WorkflowInputError as exc:
        raise ReleaseEvidenceError("workflow-input-invalid", str(exc)) from exc


def _run_verifier(command: Sequence[str]) -> str:
    try:
        # Fixed argv, no shell, closed stdin.
        completed = subprocess.run(  # noqa: S603
            list(command),
            capture_output=True,
            text=True,
            timeout=_VERIFIER_TIMEOUT_SECONDS,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerifierError("verifier-unavailable", "attestation verifier could not be executed") from exc
    if completed.returncode != 0:
        raise VerifierError("verifier-rejected", "attestation verifier did not return a clean verdict")
    return completed.stdout


def collect_attestations(
    *,
    distribution_dir: Path,
    evidence_dir: Path,
    index: Mapping[str, Any],
    repository: str,
    signer_workflow: str,
    runner: Callable[[Sequence[str]], str] = _run_verifier,
) -> dict[str, ProducerIdentity]:
    """Verify every admitted artifact through the maintained verifier."""

    attestations: dict[str, ProducerIdentity] = {}
    for record in index["subjects"]:
        path = distribution_dir / record["path"]
        attestations[record["sha256"]] = parse_verifier_output(
            runner(
                build_verify_command(
                    artifact_path=str(path),
                    repository=repository,
                    signer_workflow=signer_workflow,
                )
            )
        )
    evidence_files = [record["filename"] for record in index["evidence"]]
    # The index describes the other sidecars but never itself, so verify it
    # explicitly. Admitting an index whose own attestation was never checked
    # would let candidate-written evidence govern publication.
    evidence_files.append(INDEX_FILENAME)
    for filename in evidence_files:
        path = evidence_dir / filename
        attestations[digest_file(path)[1]] = parse_verifier_output(
            runner(
                build_verify_command(
                    artifact_path=str(path),
                    repository=repository,
                    signer_workflow=signer_workflow,
                )
            )
        )
    return attestations


def approved_producers(repo_root: Path) -> tuple[ProducerIdentity, ...]:
    """Load the reviewed producer identities a release may be attested by.

    These come from `implementations/tooling/admission-policy.json`, which is
    reviewed by Release and Security and covered by the tooling policy hash.
    Deriving them from the bundle being verified would let any valid signature
    approve itself, so the policy is the only source.
    """

    policy = json.loads(
        (repo_root / "implementations" / "tooling" / "admission-policy.json").read_text(encoding="utf-8")
    )
    producers = tuple(
        ProducerIdentity(
            issuer=str(item["issuer"]),
            repository=str(item["repository"]),
            workflow_ref=str(item["workflow_ref"]),
        )
        for item in policy.get("release_producers", [])
        if isinstance(item, Mapping)
    )
    if not producers:
        raise ReleaseEvidenceError(
            "approved-producers-absent",
            "admission policy declares no approved release producer",
        )
    return producers


def _load_index(evidence_dir: Path) -> dict[str, Any]:
    path = evidence_dir / INDEX_FILENAME
    if not path.is_file() or path.is_symlink():
        raise ReleaseEvidenceError("evidence-index-absent", "release evidence index is absent")
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--distribution-dir", required=True, type=Path)
    generate_parser.add_argument("--evidence-dir", required=True, type=Path)
    generate_parser.add_argument("--environment", required=True, type=Path)
    generate_parser.add_argument("--sdist-environment", required=True, type=Path)
    generate_parser.add_argument("--profile", required=True)
    generate_parser.add_argument("--release-tag", required=True)
    generate_parser.add_argument("--repo-root", default=REPO_ROOT, type=Path)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--distribution-dir", required=True, type=Path)
    verify_parser.add_argument("--evidence-dir", required=True, type=Path)
    verify_parser.add_argument("--signer-workflow", required=True)
    # The tag is expected identity, so it comes from the trusted workflow
    # context rather than from the index being verified.
    verify_parser.add_argument("--release-tag", required=True)
    verify_parser.add_argument("--repo-root", default=REPO_ROOT, type=Path)
    # The admission job is the trust bridge to the credentialed publishers: it
    # writes the validated wheel/sdist identity here, and they publish nothing
    # that does not match it.
    verify_parser.add_argument("--emit-subjects", type=Path)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        # Canonicalize and admit operator input before it reaches a filesystem
        # sink, so no `..` component survives into a read or write.
        for name, purpose in (
            ("repo_root", "repository root"),
            ("distribution_dir", "distribution directory"),
            ("evidence_dir", "evidence directory"),
            ("environment", "smoke environment"),
            ("sdist_environment", "sdist smoke environment"),
            ("emit_subjects", "publication handoff sink"),
        ):
            value = getattr(args, name, None)
            if value is not None:
                setattr(args, name, operator_path(Path(value), purpose=purpose))
        if args.command == "generate":
            generate(
                paths=GeneratePaths(
                    repo_root=args.repo_root,
                    distribution_dir=args.distribution_dir,
                    evidence_dir=args.evidence_dir,
                    environment_dir=args.environment,
                    sdist_environment_dir=args.sdist_environment,
                ),
                profile_id=args.profile,
                release_tag=args.release_tag,
                environment=os.environ,
            )
            print("release evidence generated")
            return 0

        index = _load_index(args.evidence_dir)
        identity = release_identity(os.environ)
        policy_hashes = {"tooling_policy_sha256": tooling_policy_sha256(args.repo_root)}
        approved = approved_producers(args.repo_root)
        attestations = collect_attestations(
            distribution_dir=args.distribution_dir,
            evidence_dir=args.evidence_dir,
            index=index,
            repository=identity["repository"],
            signer_workflow=args.signer_workflow,
        )
        verify_admission(
            distribution_dir=args.distribution_dir,
            evidence_dir=args.evidence_dir,
            index=index,
            attestations=attestations,
            approved_producers=approved,
            expected=ReleaseIdentity(**identity, tag=args.release_tag),
            policy_hashes=policy_hashes,
        )
        # Unconditional: the admitted subject names must correspond to the
        # release being published on every admission, not only when a caller
        # asks for the handoff to be written out.
        subjects = admitted_publication_subjects(index, expected_tag=args.release_tag)
        if args.emit_subjects is not None:
            # Written only here, after admission accepted the release, so a
            # refused release leaves no scalars a publisher could act on.
            args.emit_subjects.write_text(
                render_publication_outputs(subjects) + "\n",
                encoding="utf-8",
            )
        print("release evidence admitted")
        return 0
    except (
        AdmissionError,
        EvidenceDocumentError,
        ReleaseEvidenceError,
        RuntimeClosureError,
        VerifierError,
    ) as exc:
        print(f"release evidence refused [{exc.code}]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
