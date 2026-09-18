"""Policy tests for the exact-SHA release verification graph (#1125, GOV-928)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CANONICAL_PATH = WORKFLOWS / "canonical-verification.yml"
CI_PATH = WORKFLOWS / "ci.yml"
RELEASE_PATH = WORKFLOWS / "release-please.yml"
RELEASE_CONFIG_PATH = REPO_ROOT / "release-please-config.json"
DOCKER_INTEGRATION_PATH = (
    REPO_ROOT / "implementations" / "python" / "tests" / "test_reference_backend_docker_integration.py"
)

LOCAL_CANONICAL_WORKFLOW = "./.github/workflows/canonical-verification.yml"

# The `gh` calls a fresh attachment makes. Each distribution is probed for an
# existing asset, uploaded only when absent, and read back (#1227); the
# evidence set is then uploaded once and each document read back (#1226).
_FRESH_ATTACHMENT_CALLS = [
    "upload",  # wheel
    "download",  # wheel readback
    "upload",  # sdist
    "download",  # sdist readback
    "upload",  # build-inventory.json
    "download",
    "upload",  # release-evidence-index.json
    "download",
]
FULL_SHA_USE = re.compile(r"^[^@]+@[0-9a-f]{40}$")
DRAFT_RELEASE_STATE = re.compile(r"(?:\bisDraft\b|\.(?:isDraft|draft)\b|-F\s+draft=)")


def _load(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    # PyYAML follows YAML 1.1 and treats the top-level GitHub key ``on`` as the
    # boolean True. Normalize only that known key after using the safe loader.
    if True in payload and "on" not in payload:
        payload["on"] = payload.pop(True)
    return payload


def _named_step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [step for step in job["steps"] if step.get("name") == name]
    assert len(matches) == 1, f"expected one step named {name!r}, found {len(matches)}"
    return matches[0]


def _uses(workflow: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for job in workflow["jobs"].values():
        if "uses" in job:
            refs.append(job["uses"])
        refs.extend(step["uses"] for step in job.get("steps", []) if "uses" in step)
    return refs


def _run_pypi_identity_revalidation(
    tmp_path: Path,
    *,
    release_json: str,
    ref_json: str,
    tag_json: str = "",
) -> subprocess.CompletedProcess[str]:
    if shutil.which("bash") is None or shutil.which("jq") is None:
        pytest.skip("the release identity shell policy requires bash and jq")
    script = _named_step(
        _load(RELEASE_PATH)["jobs"]["publish-pypi"],
        "Revalidate release identity immediately before PyPI",
    )["run"]
    gh_stub = tmp_path / "gh"
    gh_stub.write_text(
        """#!/bin/sh
set -eu
case "$1" in
  release)
    printf '%s\n' "$RELEASE_JSON"
    ;;
  api)
    case "$*" in
      */git/ref/tags/*) printf '%s\n' "$REF_JSON" ;;
      */git/tags/*) printf '%s\n' "$TAG_JSON" ;;
      *) echo "unexpected gh api request: $*" >&2; exit 64 ;;
    esac
    ;;
  *) echo "unexpected gh request: $*" >&2; exit 64 ;;
esac
""",
        encoding="utf-8",
    )
    gh_stub.chmod(0o700)
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "GH_TOKEN": "test-token",
        "GITHUB_REPOSITORY": "OpenRAE/rae",
        "EXPECTED_SHA": "a" * 40,
        "EXPECTED_TAG": "v3.4.5",
        "EXPECTED_RELEASE_ID": "1234",
        "EXPECTED_DRAFT": "true",
        "RELEASE_JSON": release_json,
        "REF_JSON": ref_json,
        "TAG_JSON": tag_json,
    }
    return subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _run_github_finalization(
    tmp_path: Path,
    *,
    release_states: list[str],
    mismatched_download: bool = False,
    tampered_evidence_readback: bool = False,
    moved_tag: bool = False,
    published_assets: bool = False,
    published_evidence: bool = False,
    conflicting_evidence: bool = False,
    asset_list_fails: bool = False,
    finalization_json: str = '{"id":1234,"tag_name":"v3.4.5","draft":false}',
) -> subprocess.CompletedProcess[str]:
    if shutil.which("bash") is None or shutil.which("jq") is None:
        pytest.skip("the release finalization shell policy requires bash and jq")

    script = _named_step(
        _load(RELEASE_PATH)["jobs"]["publish-github"],
        "Revalidate, attach, and publish the GitHub Release",
    )["run"]
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "raes-3.4.5-py3-none-any.whl").write_bytes(b"tested wheel")
    (dist / "raes-3.4.5.tar.gz").write_bytes(b"tested sdist")
    # The finalization step also attaches the release evidence to the durable
    # Release and digest-compares it on readback (#1226).
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "release-evidence-index.json").write_bytes(b'{"schema_version":"raes-release-evidence/v1"}')
    (evidence / "build-inventory.json").write_bytes(b'{"schema_version":"raes-build-inventory/v1"}')

    # The assets the GitHub Release already holds. Uploads land here and
    # downloads are served from here, so "already attached" and "not yet
    # attached" are distinguishable the way they are against the real API.
    release_store = tmp_path / "release-assets"
    release_store.mkdir()
    if published_assets:
        for already in dist.iterdir():
            shutil.copy(already, release_store / already.name)
    if published_evidence or conflicting_evidence:
        for already in evidence.iterdir():
            if conflicting_evidence:
                (release_store / already.name).write_bytes(b"divergent evidence")
            else:
                shutil.copy(already, release_store / already.name)

    state_file = tmp_path / "release-states.jsonl"
    state_file.write_text("\n".join(release_states) + "\n", encoding="utf-8")
    state_counter = tmp_path / "release-state-counter"
    state_counter.write_text("0\n", encoding="utf-8")
    call_log = tmp_path / "gh-calls.log"
    # Created up front so a run that makes no asset call is still readable.
    call_log.write_text("", encoding="utf-8")

    gh_stub = tmp_path / "gh"
    gh_stub.write_text(
        """#!/bin/sh
set -eu
case "${1-}:${2-}" in
  release:view)
    case "$*" in
      *"--json assets"*)
        if [ "$ASSET_LIST_FAILS" = "1" ]; then
          echo "gh: could not list release assets" >&2
          exit 1
        fi
        ls -1 "$RELEASE_STORE" 2>/dev/null | jq -R . | jq -s '{assets: [.[] | {name: .}]}'
        ;;
      *)
        index="$(cat "$STATE_COUNTER")"
        index=$((index + 1))
        printf '%s\n' "$index" > "$STATE_COUNTER"
        sed -n "${index}p" "$STATE_FILE"
        ;;
    esac
    ;;
  release:upload)
    printf '%s\n' upload >> "$CALL_LOG"
    shift 3
    for uploaded in "$@"; do
      case "$uploaded" in
        --*) ;;
        *)
          if [ -f "$uploaded" ]; then
            cp "$uploaded" "$RELEASE_STORE"/
          fi
          ;;
      esac
    done
    ;;
  release:download)
    printf '%s\n' download >> "$CALL_LOG"
    shift 2
    destination=""
    patterns=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --dir) destination="$2"; shift 2 ;;
        --pattern) patterns="$patterns $2"; shift 2 ;;
        *) shift ;;
      esac
    done
    test -n "$destination"
    mkdir -p "$destination"
    # Serve only what the Release actually holds, so a pre-upload existence
    # probe reports absence rather than handing back the local copy.
    served=0
    for pattern in $patterns; do
      if [ -f "$RELEASE_STORE/$pattern" ]; then
        cp "$RELEASE_STORE/$pattern" "$destination"/
        served=1
      fi
    done
    if [ "$served" = "0" ]; then
      echo "release asset not found" >&2
      exit 1
    fi
    if [ "$MISMATCH_DOWNLOAD" = "1" ] && [ -f "$destination/raes-3.4.5-py3-none-any.whl" ]; then
      printf '%s\n' tampered > "$destination/raes-3.4.5-py3-none-any.whl"
    fi
    if [ "$TAMPER_EVIDENCE_READBACK" = "1" ]; then
      # An unmatched glob must not leak a non-zero status out of the stub.
      for served_file in "$destination"/*.json; do
        if [ -f "$served_file" ]; then
          printf '%s\n' tampered > "$served_file"
        fi
      done
    fi
    ;;
  api:*)
    case "$*" in
      */git/ref/tags/*) printf '%s\n' "$REF_JSON" ;;
      */git/tags/*) printf '%s\n' "$TAG_JSON" ;;
      *)
        printf '%s\n' patch >> "$CALL_LOG"
        printf '%s\n' "$FINALIZATION_JSON"
        ;;
    esac
    ;;
  *)
    echo "unexpected gh request: $*" >&2
    exit 64
    ;;
esac
""",
        encoding="utf-8",
    )
    gh_stub.chmod(0o700)

    # The finalization job holds `contents: write` and checks out nothing, so
    # it must not shell out to git at all (#1227). A stub that always fails
    # turns any reintroduced git call into a test failure.
    git_stub = tmp_path / "git"
    git_stub.write_text(
        """#!/bin/sh
echo "the credentialed publisher must not invoke git: $*" >&2
exit 64
""",
        encoding="utf-8",
    )
    git_stub.chmod(0o700)

    environment = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "GH_TOKEN": "test-token",
        "GITHUB_REPOSITORY": "OpenRAE/rae",
        "RUNNER_TEMP": str(tmp_path),
        "EXPECTED_SHA": "a" * 40,
        "EXPECTED_TAG": "v3.4.5",
        "EXPECTED_RELEASE_ID": "1234",
        "EXPECTED_DRAFT": "true",
        "WHEEL_NAME": "raes-3.4.5-py3-none-any.whl",
        "SDIST_NAME": "raes-3.4.5.tar.gz",
        # The tag now resolves over the API rather than from a working tree.
        "REF_JSON": json.dumps(
            {
                "ref": "refs/tags/v3.4.5",
                "object": {"type": "commit", "sha": ("c" if moved_tag else "a") * 40},
            }
        ),
        "TAG_JSON": "",
        "STATE_FILE": str(state_file),
        "STATE_COUNTER": str(state_counter),
        "CALL_LOG": str(call_log),
        "TEST_DIST_SOURCE": str(dist),
        "TEST_EVIDENCE_SOURCE": str(evidence),
        "RELEASE_STORE": str(release_store),
        "ASSET_LIST_FAILS": "1" if asset_list_fails else "0",
        "MISMATCH_DOWNLOAD": "1" if mismatched_download else "0",
        "TAMPER_EVIDENCE_READBACK": "1" if tampered_evidence_readback else "0",
        "FINALIZATION_JSON": finalization_json,
    }
    return subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=environment,
    )


def test_canonical_verifier_requires_and_checks_out_an_exact_commit_sha() -> None:
    workflow = _load(CANONICAL_PATH)
    inputs = workflow["on"]["workflow_call"]["inputs"]
    assert inputs["ref"]["required"] is True
    assert inputs["ref"]["type"] == "string"
    assert workflow["permissions"] == {"contents": "read"}

    job = workflow["jobs"]["checks"]
    checkout = job["steps"][0]
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["ref"] == "${{ inputs.ref }}"

    binding = _named_step(job, "Bind verification to the exact commit and resolve policy base")
    script = binding["run"]
    assert "^[0-9a-f]{40}$" in script
    assert 'actual_sha="$(git rev-parse HEAD)"' in script
    assert '"${actual_sha}" != "${EXPECTED_SHA}"' in script
    assert 'git cat-file -e "${base_sha}^{commit}"' in script
    assert 'git rev-parse "${EXPECTED_SHA}^"' in script


def test_canonical_verifier_preserves_proof_install_and_full_verify_graph() -> None:
    workflow = _load(CANONICAL_PATH)
    # The monolithic verify job is now distributed across deterministic shards and
    # parallel lanes (#935); the reusable graph remains the single full-gate owner.
    assert set(workflow["jobs"]) == {
        "generic-tool-local-inputs",
        "test-shard",
        "integration",
        "checks",
        "proof",
        "coverage-reduce",
        "sonar",
        "gate",
    }

    # Deterministic concurrent shards of the default-marker suite.
    shard = workflow["jobs"]["test-shard"]
    assert shard["strategy"]["matrix"]["shard"] == [0, 1, 2, 3]
    assert shard["strategy"]["fail-fast"] is False
    shard_run = _named_step(shard, "Run deterministic test shard")
    assert "nox -f noxfile.py -s verify-shard" in shard_run["run"]
    assert shard_run["env"]["RAES_SHARD_INDEX"] == "${{ matrix.shard }}"
    assert shard_run["env"]["RAES_SHARD_COUNT"] == "${{ env.RAES_CI_SHARD_COUNT }}"

    # The proof-bearing lane stays on Ubuntu 22.04 with the Bubblewrap sandbox.
    proof = workflow["jobs"]["proof"]
    assert proof["needs"] == "generic-tool-local-inputs"
    assert proof["runs-on"] == "ubuntu-22.04"
    step_names = [step.get("name") for step in proof["steps"]]
    assert "Install proof sandbox" in step_names
    assert "Admit the carried Isabelle archive with egress denied" in step_names
    assert step_names.index("Install proof sandbox") < step_names.index(
        "Admit the carried Isabelle archive with egress denied"
    )
    assert not any(str(step.get("uses", "")).startswith("actions/cache/") for step in proof["steps"])

    carrier = _named_step(
        workflow["jobs"]["generic-tool-local-inputs"], "Fetch the locked proof archive with the qualified client"
    )
    assert "fetch-inputs" in carrier["run"]
    assert "proof-ubuntu-22.04-x86_64 .canonical-tool-inputs --artifact-id isabelle" in carrier["run"]
    acquire = _named_step(proof, "Admit the carried Isabelle archive with egress denied")["run"]
    assert acquire.startswith("bwrap --dev-bind / / --unshare-net --die-with-parent ")
    assert "implementations/tooling/python/.venv/bin/python -m tools.isabelle_tool acquire" in acquire
    assert "--local-input .canonical-tool-inputs/archives/isabelle/Isabelle2025-2_linux.tar.gz" in acquire
    replay = _named_step(proof, "Replay the pinned participant-opacity proof")["run"]
    assert "nox -f noxfile.py -s participant-opacity-proof" in replay
    harness = _named_step(proof, "Qualify proof-input installation slices")["run"]
    assert "nox -f noxfile.py -s proof-input-qualification -- --real-installation" in harness
    assert "--output proof-input-qualification.json" in harness
    assert step_names.index("Qualify proof-input installation slices") < step_names.index(
        "Retain proof-input installation results"
    )
    evidence = _named_step(proof, "Retain proof-input installation results")
    assert evidence["with"]["path"] == "proof-input-qualification.json"
    assert evidence["with"]["if-no-files-found"] == "error"
    sandbox = _named_step(proof, "Install proof sandbox")["run"]
    assert "bubblewrap fontconfig fonts-dejavu-core" in sandbox
    assert "fc-list" in sandbox
    assert "test -d /etc/fonts" in sandbox
    assert "test -d /usr/share/fonts" in sandbox

    # Coverage is combined once, after a completeness proof, gated on both producers.
    reduce = workflow["jobs"]["coverage-reduce"]
    assert reduce["needs"] == ["test-shard", "integration"]
    reduce_run = _named_step(reduce, "Prove completeness and combine coverage")["run"]
    assert "nox -f noxfile.py -s verify-coverage-reduce" in reduce_run
    coverage = _named_step(reduce, "Upload combined coverage report")
    assert coverage["if"] == "always()"
    assert coverage["with"]["path"].splitlines() == [
        "implementations/python/coverage.xml",
        "implementations/python/coverage.json",
    ]

    # The full gate is an explicit fail-closed aggregate that distinguishes skips.
    gate = workflow["jobs"]["gate"]
    assert gate["if"] == "always()"
    assert set(gate["needs"]) == {"test-shard", "integration", "checks", "proof", "coverage-reduce"}


def test_ci_uses_the_same_canonical_verifier_for_github_sha() -> None:
    workflow = _load(CI_PATH)
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["on"]["push"]["branches"] == ["main", "dev"]
    assert workflow["on"]["pull_request"]["branches"] == ["main", "dev"]
    assert "continue-on-error" not in workflow["jobs"]["supply-chain"]
    canonical = workflow["jobs"]["canonical"]
    assert canonical["uses"] == LOCAL_CANONICAL_WORKFLOW
    assert canonical["with"]["ref"] == "${{ github.sha }}"
    assert "github.event.pull_request.base.sha" in canonical["with"]["base-rev"]
    assert canonical["with"]["requirement-branch"] == "${{ github.head_ref || github.ref_name }}"
    assert canonical["with"]["sonar-enabled"] is True
    assert canonical["secrets"]["sonar_token"] == "${{ secrets.SONAR_TOKEN }}"

    # dev/main branch protection requires the `verify` and `sonar` contexts. Both
    # are now decoupled joins over the reusable graph's outcomes (#935).
    verify = workflow["jobs"]["verify"]
    assert verify["needs"] == "canonical"
    assert verify["if"] == "always()"
    verify_join = _named_step(verify, "Preserve the required canonical verification status")
    assert verify_join["env"]["GATE_OUTCOME"] == "${{ needs.canonical.outputs.gate-outcome }}"
    assert '"${GATE_OUTCOME}" != "success"' in verify_join["run"]

    sonar = workflow["jobs"]["sonar"]
    assert sonar["needs"] == "canonical"
    assert sonar["if"] == "always()"
    sonar_join = _named_step(sonar, "Preserve the required SonarCloud quality-gate status")
    assert sonar_join["env"]["SONAR_OUTCOME"] == "${{ needs.canonical.outputs.sonar-outcome }}"

    # The quality gate itself runs inside the reusable graph, trust-gated there so
    # the token is never exposed to fork or Dependabot contexts.
    reusable_sonar = _load(CANONICAL_PATH)["jobs"]["sonar"]
    assert "inputs.sonar-enabled" in reusable_sonar["if"]
    assert "github.event.pull_request.head.repo.full_name == github.repository" in reusable_sonar["if"]
    assert "github.actor != 'dependabot[bot]'" in reusable_sonar["if"]
    assert reusable_sonar["needs"] == "coverage-reduce"

    interpreters = workflow["jobs"]["interpreters"]
    assert interpreters["strategy"]["matrix"]["python"] == [
        {"feature": "3.11", "payload": "3.11.16", "closure": "public-linux-x86_64-cp311-all-extras"},
        {"feature": "3.12", "payload": "3.12.14", "closure": "public-linux-x86_64-cp312-all-extras"},
        {"feature": "3.13", "payload": "3.13.15", "closure": "public-linux-x86_64-cp313-all-extras"},
        {"feature": "3.14", "payload": "3.14.7", "closure": "public-linux-x86_64-cp314-all-extras"},
    ]
    assert interpreters["env"] == {
        "UV_PYTHON": "${{ matrix.python.payload }}",
        "RAES_EXPECTED_PYTHON": "${{ matrix.python.feature }}",
        "RAES_PYTHON_CLOSURE_PROFILE": "${{ matrix.python.closure }}",
    }
    compatibility = _named_step(interpreters, "Test exact interpreter and clean distribution")
    assert "nox -f noxfile.py -s python-compatibility" in compatibility["run"]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("required", "outcome", "exit_code"),
    [
        ("true", "success", 0),
        ("true", "", 1),  # required but no verdict: scanner setup failed -> fail closed
        ("true", "failure", 1),  # quality gate red
        ("false", "", 0),  # fork / Dependabot: intentionally skipped
        ("false", "failure", 1),  # defensive: a recorded failure still fails
    ],
)
def test_sonar_join_requires_a_verdict_when_analysis_is_required(
    tmp_path: Path,
    required: str,
    outcome: str,
    exit_code: int,
) -> None:
    if shutil.which("bash") is None:
        pytest.skip("the sonar join gate requires bash")
    step = _named_step(_load(CI_PATH)["jobs"]["sonar"], "Preserve the required SonarCloud quality-gate status")
    completed = subprocess.run(
        ["bash", "-c", step["run"]],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "SONAR_REQUIRED": required, "SONAR_OUTCOME": outcome},
    )
    assert completed.returncode == exit_code, completed.stderr


def test_release_resolves_and_verifies_one_immutable_release_commit() -> None:
    workflow = _load(RELEASE_PATH)
    jobs = workflow["jobs"]
    release_config = _load(RELEASE_CONFIG_PATH)
    assert release_config["draft"] is True
    assert release_config["force-tag-creation"] is True
    assert jobs["release-please"]["outputs"]["sha"] == "${{ steps.rp.outputs.sha }}"

    resolve = jobs["resolve-release"]
    assert resolve["needs"] == "release-please"
    assert "github.event_name == 'push'" in resolve["if"]
    assert "github.event_name == 'workflow_dispatch'" in resolve["if"]
    assert "github.ref == 'refs/heads/main'" in resolve["if"]
    assert "needs.release-please.result == 'success'" in resolve["if"]
    assert "needs.release-please.outputs.release_created == 'true'" in resolve["if"]
    assert resolve["permissions"] == {"contents": "write"}
    resolution = _named_step(resolve, "Resolve and bind the immutable release commit")["run"]
    assert 'if [ "${EVENT_NAME}" = "workflow_dispatch" ]' in resolution
    assert 'tag="${INPUT_TAG}"' in resolution
    assert 'expected_sha="${RELEASE_PLEASE_SHA}"' in resolution
    assert 'tag_sha="$(git rev-parse --verify "${tag}^{commit}")"' in resolution
    assert '"${tag_sha}" != "${expected_sha}"' in resolution
    assert 'git merge-base --is-ancestor "${tag_sha}" origin/main' in resolution
    assert '"${release_is_draft}" != "true"' in resolution
    assert "release_sha=${tag_sha}" in resolution
    assert "release_id=${release_id}" in resolution
    assert "release_is_draft=${release_is_draft}" in resolution

    verify = jobs["verify-release"]
    assert verify["needs"] == "resolve-release"
    assert verify["uses"] == LOCAL_CANONICAL_WORKFLOW
    assert verify["with"]["ref"] == "${{ needs.resolve-release.outputs.release_sha }}"
    assert verify["with"]["base-rev"] == "${{ needs.resolve-release.outputs.base_sha }}"


def test_every_shell_draft_release_inspection_has_push_capable_token() -> None:
    workflow = _load(RELEASE_PATH)
    assert workflow["permissions"] == {"contents": "read"}

    draft_inspection_jobs = {
        name
        for name, job in workflow["jobs"].items()
        if any(DRAFT_RELEASE_STATE.search(step.get("run", "")) for step in job.get("steps", []))
    }
    assert draft_inspection_jobs
    insufficient_permissions = {
        name
        for name in draft_inspection_jobs
        if workflow["jobs"][name].get("permissions", {}).get("contents") != "write"
    }
    assert not insufficient_permissions, (
        f"draft GitHub Releases require push-capable contents permission: {sorted(insufficient_permissions)}"
    )

    for name, job in workflow["jobs"].items():
        if job.get("permissions", {}).get("contents") != "write":
            continue
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step.get("with", {}).get("persist-credentials") is False, (
                    f"{name} must not persist its write-scoped checkout credential"
                )


def test_release_builds_and_smokes_the_verified_sha_before_publish() -> None:
    workflow = _load(RELEASE_PATH)
    jobs = workflow["jobs"]
    build = jobs["build-release"]
    assert set(build["needs"]) == {"resolve-release", "verify-release", "integration-docker-release"}
    assert "needs.verify-release.result == 'success'" in build["if"]
    assert "needs.integration-docker-release.result == 'success'" in build["if"]
    assert build["permissions"] == {"contents": "read"}

    checkout = build["steps"][0]
    assert checkout["with"]["ref"] == "${{ needs.resolve-release.outputs.release_sha }}"
    binding = _named_step(build, "Reconfirm the exact verified release checkout")["run"]
    assert 'actual_sha="$(git rev-parse HEAD)"' in binding
    assert '"${actual_sha}" != "${EXPECTED_SHA}"' in binding

    names = [step.get("name") for step in build["steps"]]
    corpus_index = names.index("Verify the contract corpus is bundled in both distributions (#537)")
    wheel_smoke_index = names.index("Smoke-test the installed release wheel (#537)")
    sdist_smoke_index = names.index("Smoke-test the installed release sdist (#537)")
    upload_index = names.index("Upload the tested release distributions")
    assert corpus_index < wheel_smoke_index < sdist_smoke_index < upload_index

    corpus = build["steps"][corpus_index]["run"]
    assert "tarfile.open(sdists[0]" in corpus
    assert "sdist is missing corpus payload" in corpus

    build_script = _named_step(build, "Build constrained release distributions")["run"]
    assert "tools.python_closure build" in build_script
    assert "--profile public-linux-x86_64-cp312-all-extras" in build_script
    assert "uv build" not in build_script

    for smoke_index, distribution in ((wheel_smoke_index, "wheel"), (sdist_smoke_index, "sdist")):
        smoke = build["steps"][smoke_index]["run"]
        assert "tools.python_closure smoke" in smoke
        assert "--wheelhouse" in smoke
        assert "--offline" in smoke
        assert "uv pip install" not in smoke
        assert "env -u PYTHONPATH -u PYTHONHOME" in smoke
        assert "conformance backend --profile provisioning-only" in smoke
        assert 'installed_version = version("raes")' in smoke
        assert 'installed_version != os.environ["EXPECTED_VERSION"]' in smoke
        assert 'report.get("passed") is not True' in smoke
        assert 'not report.get("cases")' in smoke
        assert f"installed release {distribution}" in smoke


def test_release_requires_skip_free_real_docker_tests_at_the_exact_sha() -> None:
    release = _load(RELEASE_PATH)
    docker = release["jobs"]["integration-docker-release"]
    assert set(docker["needs"]) == {"resolve-release", "verify-release"}
    assert "needs.verify-release.result == 'success'" in docker["if"]
    assert docker["permissions"] == {"contents": "read"}
    assert "continue-on-error" not in docker

    checkout = docker["steps"][0]
    assert checkout["with"]["ref"] == "${{ needs.resolve-release.outputs.release_sha }}"
    binding = _named_step(docker, "Bind real-container testing to the exact release commit")["run"]
    assert 'actual_sha="$(git rev-parse HEAD)"' in binding
    assert '"${actual_sha}" != "${EXPECTED_SHA}"' in binding

    required = _named_step(docker, "Require real-container release integration")
    assert required["env"]["RAES_DOCKER_INTEGRATION_REQUIRED"] == "1"
    required_script = required["run"]
    assert "-s integration_docker -- --junitxml=" in required_script
    assert "if not cases:" in required_script
    assert "if skipped:" in required_script
    assert "collected zero tests" in required_script
    assert "skipped tests" in required_script

    fixture = DOCKER_INTEGRATION_PATH.read_text(encoding="utf-8")
    assert "RAES_DOCKER_INTEGRATION_REQUIRED" in fixture
    assert "pytest.fail" in fixture
    # The reviewed image identity is lock data, not a literal in the harness.
    assert "sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc" not in fixture
    assert "oci_release_image.locked_platform_graphs()" in fixture

    optional = _load(CI_PATH)["jobs"]["integration-docker"]
    assert optional["continue-on-error"] is True
    assert "RAES_DOCKER_INTEGRATION_REQUIRED" not in str(optional)


def test_publication_is_split_retry_safe_and_finalizes_the_same_release() -> None:
    workflow = _load(RELEASE_PATH)
    jobs = workflow["jobs"]
    publish_pypi = jobs["publish-pypi"]
    assert set(publish_pypi["needs"]) == {
        "resolve-release",
        "verify-release",
        "integration-docker-release",
        "build-release",
        # Absent or rejected evidence must block the handoff, so admission is a
        # predecessor of publication rather than an optional report (#1226).
        "admit-release",
    }
    assert "needs.verify-release.result == 'success'" in publish_pypi["if"]
    assert "needs.integration-docker-release.result == 'success'" in publish_pypi["if"]
    assert "needs.build-release.result == 'success'" in publish_pypi["if"]
    assert "github.ref == 'refs/heads/main'" in publish_pypi["if"]
    assert publish_pypi["environment"] == "pypi"
    assert publish_pypi["permissions"] == {"contents": "write", "id-token": "write"}

    # OIDC is held by exactly two reviewed boundaries: the publisher, and the
    # signer. They are separate jobs so an attestation credential never carries
    # publication capability, and vice versa (#1226).
    oidc_jobs = {name for name, job in jobs.items() if job.get("permissions", {}).get("id-token") == "write"}
    assert oidc_jobs == {"publish-pypi", "attest-release"}

    for name, job in jobs.items():
        if name == "publish-pypi":
            continue
        assert job.get("environment") != "pypi"

    attest = jobs["attest-release"]
    assert attest["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }
    assert attest.get("environment") is None
    # A protected script launched inside a candidate checkout can still import
    # or execute candidate code, so the signer checks out nothing.
    assert all(not step.get("uses", "").startswith("actions/checkout@") for step in attest["steps"])
    # Only the signer may write attestations.
    assert {name for name, job in jobs.items() if job.get("permissions", {}).get("attestations") == "write"} == {
        "attest-release"
    }

    upload = _named_step(jobs["build-release"], "Upload the tested release distributions")
    pypi_download = _named_step(publish_pypi, "Download the tested release distributions")
    assert upload["with"]["name"] == pypi_download["with"]["name"]
    assert pypi_download["with"]["path"] == "dist/"
    pypi_names = [step.get("name") for step in publish_pypi["steps"]]
    revalidate_index = pypi_names.index("Revalidate release identity immediately before PyPI")
    publish_index = pypi_names.index("Publish to PyPI (OIDC trusted publishing)")
    # Nothing but the read-only destination reconciliation may sit between
    # identity revalidation and the upload, so no unvetted work can intervene
    # once the release identity has been proven (#1227).
    assert pypi_names[revalidate_index + 1 : publish_index] == ["Reconcile the PyPI destination"]
    assert all(not step.get("uses", "").startswith("actions/checkout@") for step in publish_pypi["steps"])
    revalidation = publish_pypi["steps"][revalidate_index]
    assert revalidation["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "EXPECTED_SHA": "${{ needs.resolve-release.outputs.release_sha }}",
        "EXPECTED_TAG": "${{ needs.resolve-release.outputs.tag }}",
        "EXPECTED_RELEASE_ID": "${{ needs.resolve-release.outputs.release_id }}",
        "EXPECTED_DRAFT": "${{ needs.resolve-release.outputs.release_is_draft }}",
    }
    revalidation_script = revalidation["run"]
    assert 'gh release view "${EXPECTED_TAG}"' in revalidation_script
    assert '"${current_release_id}" != "${EXPECTED_RELEASE_ID}"' in revalidation_script
    assert '"${current_draft}" != "${EXPECTED_DRAFT}"' in revalidation_script
    assert '"${current_ref}" != "refs/tags/${EXPECTED_TAG}"' in revalidation_script
    assert 'while [ "${current_type}" = "tag" ]' in revalidation_script
    assert '"${current_sha}" != "${EXPECTED_SHA}"' in revalidation_script

    publish_github = jobs["publish-github"]
    assert set(publish_github["needs"]) == {
        "resolve-release",
        "verify-release",
        "build-release",
        "admit-release",
        "publish-pypi",
    }
    assert "needs.publish-pypi.result == 'success'" in publish_github["if"]
    assert "github.ref == 'refs/heads/main'" in publish_github["if"]
    assert publish_github["permissions"] == {"contents": "write"}
    github_download = _named_step(publish_github, "Download the tested release distributions")
    assert github_download["with"]["name"] == upload["with"]["name"]
    finalization = _named_step(publish_github, "Revalidate, attach, and publish the GitHub Release")["run"]
    assert '"${current_release_id}" != "${EXPECTED_RELEASE_ID}"' in finalization
    assert '"${current_tag_sha}" != "${EXPECTED_SHA}"' in finalization
    assert finalization.index("gh release upload") < finalization.index("prepublish_json")
    assert finalization.index("prepublish_json") < finalization.index("--method PATCH")
    assert '"repos/${GITHUB_REPOSITORY}/releases/${EXPECTED_RELEASE_ID}"' in finalization
    assert "-F draft=false" in finalization
    assert "Already-public Release assets do not match the tested distributions" in finalization
    assert 'gh release download "${EXPECTED_TAG}"' in finalization
    # The retry proves the already-public assets against the admitted names,
    # not against whatever a glob selected from the artifact (#1227).
    assert 'cmp -s "${wheel}" "${retry_dir}/${WHEEL_NAME}"' in finalization
    assert 'cmp -s "${sdist}" "${retry_dir}/${SDIST_NAME}"' in finalization

    sync = jobs["sync-dev"]
    assert set(sync["needs"]) == {"release-please", "publish-github"}
    assert "needs.publish-github.result == 'success'" in sync["if"]
    assert "github.ref == 'refs/heads/main'" in sync["if"]


@pytest.mark.integration
def test_pre_pypi_identity_revalidation_dereferences_annotated_tag(tmp_path: Path) -> None:
    result = _run_pypi_identity_revalidation(
        tmp_path,
        release_json='{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
        ref_json='{"ref":"refs/tags/v3.4.5","object":{"type":"tag","sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}',
        tag_json='{"object":{"type":"commit","sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}',
    )

    assert result.returncode == 0, result.stderr
    assert "Revalidated Release 1234, v3.4.5" in result.stdout


@pytest.mark.integration
def test_pre_pypi_identity_revalidation_rejects_replaced_release(tmp_path: Path) -> None:
    result = _run_pypi_identity_revalidation(
        tmp_path,
        release_json='{"databaseId":9999,"isDraft":true,"tagName":"v3.4.5"}',
        ref_json='{"ref":"refs/tags/v3.4.5","object":{"type":"commit","sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}',
    )

    assert result.returncode != 0
    assert "Release object changed: expected id 1234, got 9999" in result.stderr


@pytest.mark.integration
def test_pre_pypi_identity_revalidation_rejects_moved_tag(tmp_path: Path) -> None:
    result = _run_pypi_identity_revalidation(
        tmp_path,
        release_json='{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
        ref_json='{"ref":"refs/tags/v3.4.5","object":{"type":"commit","sha":"cccccccccccccccccccccccccccccccccccccccc"}}',
    )

    assert result.returncode != 0
    assert f"Release tag moved: expected {'a' * 40}, got {'c' * 40}" in result.stderr


@pytest.mark.integration
def test_github_finalization_revalidates_release_object_after_attachment(tmp_path: Path) -> None:
    result = _run_github_finalization(
        tmp_path,
        release_states=[
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":9999,"isDraft":true,"tagName":"v3.4.5"}',
        ],
    )

    assert result.returncode != 0
    assert "Release identity changed during attachment; refusing public finalization" in result.stderr
    # Attachment and evidence retention complete, then the re-read of the
    # Release object rejects the identity change before public finalization.
    assert (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines() == _FRESH_ATTACHMENT_CALLS


@pytest.mark.integration
def test_github_finalization_rejects_moved_tag_before_attachment(tmp_path: Path) -> None:
    result = _run_github_finalization(
        tmp_path,
        release_states=['{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}'],
        moved_tag=True,
    )

    assert result.returncode != 0
    assert f"Release tag moved: expected {'a' * 40}, got {'c' * 40}" in result.stderr
    assert (tmp_path / "gh-calls.log").read_text(encoding="utf-8") == ""


@pytest.mark.integration
def test_github_finalization_rejects_tampered_finalization_response(tmp_path: Path) -> None:
    result = _run_github_finalization(
        tmp_path,
        release_states=[
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
        ],
        finalization_json='{"id":9999,"tag_name":"v3.4.5","draft":false}',
    )

    assert result.returncode != 0
    assert "GitHub Release finalization response changed the verified identity" in result.stderr
    assert (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines() == [
        *_FRESH_ATTACHMENT_CALLS,
        "patch",
    ]


@pytest.mark.integration
def test_github_finalization_uses_bound_id_and_accepts_verified_response(tmp_path: Path) -> None:
    result = _run_github_finalization(
        tmp_path,
        release_states=[
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":false,"tagName":"v3.4.5"}',
        ],
    )

    assert result.returncode == 0, result.stderr
    assert "Retained 2 evidence documents with verified readback digests" in result.stdout
    assert (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines() == [
        *_FRESH_ATTACHMENT_CALLS,
        "patch",
    ]


@pytest.mark.integration
def test_github_finalization_rejects_tampered_retained_evidence(tmp_path: Path) -> None:
    """Retention rests on observed stored bytes, not on a successful upload call."""

    result = _run_github_finalization(
        tmp_path,
        release_states=[
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":false,"tagName":"v3.4.5"}',
        ],
        tampered_evidence_readback=True,
    )

    assert result.returncode != 0
    assert "does not match the admitted bytes" in result.stderr
    # The Release is never finalized public when the retained bytes disagree.
    assert "patch" not in (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines()


@pytest.mark.integration
def test_github_finalization_accepts_matching_already_public_retry(tmp_path: Path) -> None:
    result = _run_github_finalization(
        tmp_path,
        release_states=[
            '{"databaseId":1234,"isDraft":false,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":false,"tagName":"v3.4.5"}',
        ],
        published_assets=True,
    )

    assert result.returncode == 0, result.stderr
    assert "was already public with the tested distributions" in result.stdout
    assert (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines() == ["download"]


@pytest.mark.integration
def test_github_finalization_rejects_mismatched_already_public_assets(tmp_path: Path) -> None:
    result = _run_github_finalization(
        tmp_path,
        release_states=['{"databaseId":1234,"isDraft":false,"tagName":"v3.4.5"}'],
        mismatched_download=True,
        published_assets=True,
    )

    assert result.returncode != 0
    assert "Already-public Release assets do not match the tested distributions" in result.stderr
    assert (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines() == ["download"]


def test_every_always_job_gates_on_each_dependency_result() -> None:
    """`needs:` membership alone gates nothing once a job uses `always()`.

    With `if: always() && ...` GitHub runs the job even when a dependency
    failed, so the only thing that actually blocks it is an explicit
    `needs.<job>.result` clause. A test that asserts `needs:` membership without
    that clause stays green while the real gate is deleted, which is how a
    failed evidence admission could stop blocking publication (#1226).
    """

    workflow = _load(RELEASE_PATH)
    ungated: dict[str, list[str]] = {}
    for name, job in workflow["jobs"].items():
        condition = str(job.get("if", ""))
        if "always()" not in condition:
            continue
        needs = job.get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        missing = [dependency for dependency in needs if f"needs.{dependency}.result" not in condition]
        if missing:
            ungated[name] = missing
    assert ungated == {}, f"always()-conditioned jobs ignore a dependency result: {ungated}"


def test_publication_requires_successful_evidence_admission() -> None:
    """Rejected release evidence must block both publishers (#1226)."""

    jobs = _load(RELEASE_PATH)["jobs"]
    for publisher in ("publish-pypi", "publish-github"):
        condition = str(jobs[publisher]["if"])
        assert "needs.admit-release.result == 'success'" in condition, publisher
    # And admission itself cannot run ahead of a successful signing boundary.
    assert "needs.attest-release.result == 'success'" in str(jobs["admit-release"]["if"])
    assert "needs.build-release.result == 'success'" in str(jobs["attest-release"]["if"])


def test_release_gate_does_not_poll_mutable_check_or_branch_status() -> None:
    release_text = RELEASE_PATH.read_text(encoding="utf-8").lower()
    forbidden = ("gh run list", "check-runs", "/statuses/", "workflow_run")
    assert all(token not in release_text for token in forbidden)


def _workflow_paths() -> list[Path]:
    paths = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    assert {CANONICAL_PATH, CI_PATH, RELEASE_PATH} <= set(paths)
    return paths


def test_every_workflow_pins_every_third_party_action_to_a_full_sha() -> None:
    for path in _workflow_paths():
        for action_ref in _uses(_load(path)):
            if action_ref.startswith("./"):
                continue
            assert FULL_SHA_USE.fullmatch(action_ref), f"{path.name}: unpinned action {action_ref!r}"


# Every write-capable token grant is a reviewed publication, Pages, code-scanning,
# or release-bookkeeping boundary. Any other job or workflow stays read-only.
_REVIEWED_JOB_WRITE_SCOPES = {
    ("docs.yml", "deploy"): {"pages", "id-token"},
    ("release-please.yml", "release-please"): {"contents", "pull-requests"},
    ("release-please.yml", "resolve-release"): {"contents"},
    # Signing holds an OIDC and attestation identity only. It has no `contents`
    # write and no PyPI environment, so an attestation credential cannot
    # authorize publication (#1226).
    ("release-please.yml", "attest-release"): {"attestations", "id-token"},
    ("release-please.yml", "publish-pypi"): {"contents", "id-token"},
    ("release-please.yml", "publish-github"): {"contents"},
    ("release-please.yml", "sync-dev"): {"pull-requests"},
    ("scorecard.yml", "analysis"): {"security-events", "id-token"},
}


def _write_scopes(permissions: object, location: str) -> set[str]:
    assert permissions is None or isinstance(permissions, dict), f"{location}: permissions must be an explicit mapping"
    scopes = permissions or {}
    assert set(scopes.values()) <= {"read", "write", "none"}, f"{location}: unknown permission level"
    return {scope for scope, level in scopes.items() if level == "write"}


def test_every_workflow_and_job_token_is_read_only_except_reviewed_write_boundaries() -> None:
    observed: dict[tuple[str, str], set[str]] = {}
    for path in _workflow_paths():
        workflow = _load(path)
        assert "permissions" in workflow, f"{path.name}: missing workflow-level token permissions"
        assert not _write_scopes(workflow["permissions"], path.name), f"{path.name}: workflow default grants write"
        for job_name, job in workflow["jobs"].items():
            scopes = _write_scopes(job.get("permissions"), f"{path.name}:{job_name}")
            if scopes:
                observed[(path.name, job_name)] = scopes
    assert observed == _REVIEWED_JOB_WRITE_SCOPES


def _release_managed_paths() -> list[str]:
    package = _load(RELEASE_CONFIG_PATH)["packages"]["."]
    (release_please,) = [
        step for step in _load(RELEASE_PATH)["jobs"]["release-please"]["steps"] if step.get("id") == "rp"
    ]
    manifest = release_please["with"]["manifest-file"]
    return sorted([package["changelog-path"], manifest, *(item["path"] for item in package["extra-files"])])


# Events that must still run when only release-managed files change: Release
# Please itself publishes, and the main Docs push redeploys the release version.
_RELEASE_BOOKKEEPING_RUNS = {("release-please.yml", "push"), ("docs.yml", "push")}


def test_release_bookkeeping_changes_do_not_retrigger_check_workflows() -> None:
    expected = _release_managed_paths()
    assert expected == [
        ".release-please-manifest.json",
        "CHANGELOG.md",
        "implementations/python/packages/raes/_version.py",
    ]

    filtered: set[tuple[str, str]] = set()
    unfiltered: set[tuple[str, str]] = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        triggers = _load(path)["on"]
        if isinstance(triggers, str):
            triggers = {triggers: None}
        elif isinstance(triggers, list):
            triggers = dict.fromkeys(triggers)
        for event in ("push", "pull_request"):
            if event not in triggers:
                continue
            config = triggers[event] or {}
            if path.name == "bootstrap-qualification.yml":
                assert config.get("paths")
                assert "workflow_dispatch" in triggers
                continue
            assert "paths" not in config, f"{path.name} {event}: positive path filters would hide real changes"
            if "paths-ignore" in config:
                assert sorted(config["paths-ignore"]) == expected, f"{path.name} {event}: ignored paths drifted"
                assert len(config["paths-ignore"]) == len(set(config["paths-ignore"]))
                filtered.add((path.name, event))
            else:
                unfiltered.add((path.name, event))

    assert unfiltered == _RELEASE_BOOKKEEPING_RUNS
    assert filtered == {
        ("ci.yml", "pull_request"),
        ("ci.yml", "push"),
        ("docs.yml", "pull_request"),
        ("post-merge-closing-issue-audit.yml", "pull_request"),
        ("pr-body-policy.yml", "pull_request"),
        ("pr-title-lint.yml", "pull_request"),
        ("scorecard.yml", "push"),
    }


_EXACT = "a" * 40
_PARENT = "b" * 40
_OTHER = "c" * 40
_GIT_STUB = """#!/bin/sh
set -eu
case "$*" in
  "rev-parse HEAD") printf '%s\\n' "$STUB_HEAD" ;;
  "rev-parse --verify "*) printf '%s\\n' "$STUB_TAG_SHA" ;;
  "rev-parse "*"^") printf '%s\\n' "$STUB_PARENT" ;;
  "cat-file -e "*) exit "${STUB_CAT_FILE_STATUS:-0}" ;;
  "fetch "*) exit 0 ;;
  "merge-base --is-ancestor "*) exit "${STUB_ANCESTOR_STATUS:-0}" ;;
  *) echo "unexpected git request: $*" >&2; exit 64 ;;
esac
"""
_GH_STUB = """#!/bin/sh
set -eu
case "${1-}:${2-}" in
  release:view) printf '%s\\n' "$STUB_RELEASE_JSON" ;;
  *) echo "unexpected gh request: $*" >&2; exit 64 ;;
esac
"""


def _run_exact_commit_gate(
    tmp_path: Path,
    workflow_path: Path,
    job_name: str,
    step_name: str,
    environment: dict[str, str],
) -> tuple[subprocess.CompletedProcess[str], str]:
    if shutil.which("bash") is None or shutil.which("jq") is None:
        pytest.skip("the exact-commit shell gates require bash and jq")
    script = _named_step(_load(workflow_path)["jobs"][job_name], step_name)["run"]
    for name, body in (("git", _GIT_STUB), ("gh", _GH_STUB)):
        stub = tmp_path / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o700)
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    completed = subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": "OpenRAE/rae",
            "STUB_PARENT": _PARENT,
            **environment,
        },
    )
    return completed, output.read_text(encoding="utf-8")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("head", "expected", "exit_code", "message"),
    [
        (_EXACT, _EXACT, 0, "Verified exact commit"),
        (_OTHER, _EXACT, 1, "Checkout mismatch"),
        (_EXACT, "A" * 40, 1, "full lowercase commit SHA"),
    ],
)
def test_canonical_exact_commit_gate_executes_and_rejects_a_different_checkout(
    tmp_path: Path,
    head: str,
    expected: str,
    exit_code: int,
    message: str,
) -> None:
    completed, output = _run_exact_commit_gate(
        tmp_path,
        CANONICAL_PATH,
        "checks",
        "Bind verification to the exact commit and resolve policy base",
        {"STUB_HEAD": head, "EXPECTED_SHA": expected, "REQUESTED_BASE_SHA": ""},
    )

    assert completed.returncode == exit_code, completed.stderr
    assert message in completed.stdout + completed.stderr
    assert ("base_rev=" + _PARENT in output) is (exit_code == 0)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("job_name", "step_name", "mismatch_message"),
    [
        ("integration-docker-release", "Bind real-container testing to the exact release commit", "checkout mismatch"),
        ("build-release", "Reconfirm the exact verified release checkout", "Publish checkout mismatch"),
    ],
)
@pytest.mark.parametrize("head", [_EXACT, _OTHER])
def test_release_checkout_gates_execute_and_reject_a_different_checkout(
    tmp_path: Path,
    job_name: str,
    step_name: str,
    mismatch_message: str,
    head: str,
) -> None:
    completed, _output = _run_exact_commit_gate(
        tmp_path,
        RELEASE_PATH,
        job_name,
        step_name,
        {"STUB_HEAD": head, "EXPECTED_SHA": _EXACT},
    )

    if head == _EXACT:
        assert completed.returncode == 0, completed.stderr
    else:
        assert completed.returncode == 1
        assert mismatch_message in completed.stderr


@pytest.mark.integration
@pytest.mark.parametrize(
    ("tag_sha", "ancestor_status", "exit_code", "message"),
    [
        (_EXACT, "0", 0, "Resolved v3.4.5 to immutable release commit"),
        (_OTHER, "0", 1, "Release Please SHA/tag mismatch"),
        (_EXACT, "1", 1, "is not reachable from origin/main"),
    ],
)
def test_release_resolution_executes_and_binds_the_exact_release_commit(
    tmp_path: Path,
    tag_sha: str,
    ancestor_status: str,
    exit_code: int,
    message: str,
) -> None:
    completed, output = _run_exact_commit_gate(
        tmp_path,
        RELEASE_PATH,
        "resolve-release",
        "Resolve and bind the immutable release commit",
        {
            "EVENT_NAME": "push",
            "INPUT_TAG": "",
            "RELEASE_PLEASE_TAG": "v3.4.5",
            "RELEASE_PLEASE_SHA": _EXACT,
            "STUB_RELEASE_JSON": '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            "STUB_TAG_SHA": tag_sha,
            "STUB_ANCESTOR_STATUS": ancestor_status,
        },
    )

    assert completed.returncode == exit_code, completed.stderr
    assert message in completed.stdout + completed.stderr
    assert (f"release_sha={_EXACT}" in output) is (exit_code == 0)


# --- #1227: the publication boundary consumes only the admitted tested bytes ---


def test_no_release_publication_step_overwrites_a_published_file() -> None:
    """A blind overwrite can replace the exact tested asset.

    `--clobber` makes a same-name upload succeed regardless of the bytes
    already stored, which defeats the tested-artifact guarantee the rest of
    this graph establishes.
    """

    source = RELEASE_PATH.read_text(encoding="utf-8")

    assert "--clobber" not in source


def test_credentialed_publishers_check_out_no_candidate_source() -> None:
    """Publication credentials never coexist with candidate code in a job.

    Both publishers hold a write credential, so a checked-out release tree
    would put candidate-controlled scripts in a job that can publish. The
    identity checks they need are available over the API.
    """

    jobs = _load(RELEASE_PATH)["jobs"]

    for name in ("publish-pypi", "publish-github"):
        steps = jobs[name]["steps"]
        assert all(not step.get("uses", "").startswith("actions/checkout@") for step in steps), (
            f"{name} must not check out candidate source"
        )


def test_admission_exports_the_validated_artifact_identity() -> None:
    """Admission is the trust bridge, so it publishes the scalars it validated."""

    jobs = _load(RELEASE_PATH)["jobs"]
    admit = jobs["admit-release"]

    assert set(admit["outputs"]) == {
        "wheel_name",
        "wheel_sha256",
        "sdist_name",
        "sdist_sha256",
    }
    for expression in admit["outputs"].values():
        assert expression.startswith("${{ steps.")
    # The scalars come out of the same command that performs admission, not a
    # separate scan that could disagree with it.
    admit_step = _named_step(admit, "Admit the release evidence")
    assert "--emit-subjects" in admit_step["run"]
    assert admit_step.get("id")


def test_both_publishers_require_the_admitted_artifact_identity() -> None:
    """Each destination operation is gated on the admitted names and digests."""

    jobs = _load(RELEASE_PATH)["jobs"]

    for name in ("publish-pypi", "publish-github"):
        job = jobs[name]
        assert "admit-release" in job["needs"], name
        verify = _named_step(job, "Verify the admitted release distributions")
        env = verify["env"]
        for scalar in ("WHEEL_NAME", "WHEEL_SHA256", "SDIST_NAME", "SDIST_SHA256"):
            assert env[scalar] == f"${{{{ needs.admit-release.outputs.{scalar.lower()} }}}}", (name, scalar)
        # The publisher recomputes the digest itself rather than trusting the
        # artifact channel that delivered the file.
        assert "sha256sum" in verify["run"]
        # Verification precedes the destination write in the job.
        names = [step.get("name") for step in job["steps"]]
        destination = (
            "Publish to PyPI (OIDC trusted publishing)"
            if name == "publish-pypi"
            else "Revalidate, attach, and publish the GitHub Release"
        )
        assert names.index("Verify the admitted release distributions") < names.index(destination), name


def test_pypi_publication_reconciles_the_destination_before_upload() -> None:
    """An already-published version is completed, not overwritten or assumed."""

    publish_pypi = _load(RELEASE_PATH)["jobs"]["publish-pypi"]
    names = [step.get("name") for step in publish_pypi["steps"]]
    reconcile_index = names.index("Reconcile the PyPI destination")
    publish_index = names.index("Publish to PyPI (OIDC trusted publishing)")

    assert reconcile_index < publish_index
    reconcile = publish_pypi["steps"][reconcile_index]
    assert reconcile.get("id")
    # A digest comparison, not an "already exists" response, decides the skip.
    assert "digests" in reconcile["run"]
    assert "sha256" in reconcile["run"]
    publish_step = publish_pypi["steps"][publish_index]
    assert publish_step["if"] == f"steps.{reconcile['id']}.outputs.pending == 'true'"


def test_github_attachment_reconciles_each_asset_before_upload() -> None:
    """Per-asset handling replaces the blind overwrite."""

    attach = _named_step(
        _load(RELEASE_PATH)["jobs"]["publish-github"],
        "Revalidate, attach, and publish the GitHub Release",
    )["run"]

    # GitHub exposes no server-side asset digest, so a byte comparison of the
    # downloaded asset is what distinguishes already-published from conflict.
    assert "gh release download" in attach
    assert "gh release upload" in attach
    assert "--clobber" not in attach


def _run_pypi_reconciliation(
    tmp_path: Path,
    *,
    status: str,
    body: str,
) -> subprocess.CompletedProcess[str]:
    """Execute the PyPI destination reconciliation against a stubbed registry."""

    if shutil.which("bash") is None or shutil.which("jq") is None:
        pytest.skip("the PyPI reconciliation shell policy requires bash and jq")

    script = _named_step(
        _load(RELEASE_PATH)["jobs"]["publish-pypi"],
        "Reconcile the PyPI destination",
    )["run"]

    curl_stub = tmp_path / "curl"
    curl_stub.write_text(
        """#!/bin/sh
set -eu
destination=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) destination="$2"; shift 2 ;;
    *) shift ;;
  esac
done
test -n "$destination"
printf '%s' "$PYPI_BODY" > "$destination"
printf '%s' "$PYPI_STATUS"
""",
        encoding="utf-8",
    )
    curl_stub.chmod(0o700)

    github_output = tmp_path / "github-output"
    github_output.write_text("", encoding="utf-8")
    completed = subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(github_output),
            "EXPECTED_TAG": "v3.4.5",
            "WHEEL_NAME": "raes-3.4.5-py3-none-any.whl",
            "WHEEL_SHA256": "1" * 64,
            "SDIST_NAME": "raes-3.4.5.tar.gz",
            "SDIST_SHA256": "2" * 64,
            "PYPI_STATUS": status,
            "PYPI_BODY": body,
        },
    )
    return completed


def _pypi_outputs(tmp_path: Path) -> dict[str, str]:
    lines = (tmp_path / "github-output").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def _pypi_body(*files: tuple[str, str]) -> str:
    return json.dumps({"urls": [{"filename": name, "digests": {"sha256": digest}} for name, digest in files]})


@pytest.mark.integration
def test_pypi_reconciliation_publishes_an_absent_version(tmp_path: Path) -> None:
    result = _run_pypi_reconciliation(tmp_path, status="404", body="{}")

    assert result.returncode == 0, result.stderr
    assert _pypi_outputs(tmp_path)["pending"] == "true"


@pytest.mark.integration
def test_pypi_reconciliation_skips_an_already_published_release(tmp_path: Path) -> None:
    """Matching destination digests are success, so a rerun completes GitHub."""

    result = _run_pypi_reconciliation(
        tmp_path,
        status="200",
        body=_pypi_body(("raes-3.4.5-py3-none-any.whl", "1" * 64), ("raes-3.4.5.tar.gz", "2" * 64)),
    )

    assert result.returncode == 0, result.stderr
    assert _pypi_outputs(tmp_path)["pending"] == "false"
    assert "already on PyPI" in result.stdout


@pytest.mark.integration
def test_pypi_reconciliation_completes_only_the_missing_distribution(tmp_path: Path) -> None:
    """A partial upload leaves the outstanding file pending, not the whole set."""

    result = _run_pypi_reconciliation(
        tmp_path,
        status="200",
        body=_pypi_body(("raes-3.4.5-py3-none-any.whl", "1" * 64)),
    )

    assert result.returncode == 0, result.stderr
    assert _pypi_outputs(tmp_path)["pending"] == "true"
    assert "does not yet carry raes-3.4.5.tar.gz" in result.stdout


@pytest.mark.integration
def test_pypi_reconciliation_refuses_a_same_name_digest_mismatch(tmp_path: Path) -> None:
    """A published file with different bytes is an incident, never an overwrite."""

    result = _run_pypi_reconciliation(
        tmp_path,
        status="200",
        body=_pypi_body(("raes-3.4.5-py3-none-any.whl", "9" * 64), ("raes-3.4.5.tar.gz", "2" * 64)),
    )

    assert result.returncode != 0
    assert "already stores raes-3.4.5-py3-none-any.whl with different bytes" in result.stderr
    assert "pending" not in _pypi_outputs(tmp_path)


@pytest.mark.integration
@pytest.mark.parametrize("status", ["403", "500", "000"])
def test_pypi_reconciliation_refuses_an_uncertain_destination(tmp_path: Path, status: str) -> None:
    """An ambiguous destination answer is never read as "not published"."""

    result = _run_pypi_reconciliation(tmp_path, status=status, body="{}")

    assert result.returncode != 0
    assert f"HTTP {status}" in result.stderr
    assert "pending" not in _pypi_outputs(tmp_path)


@pytest.mark.integration
def test_github_attachment_accepts_an_already_attached_matching_asset(tmp_path: Path) -> None:
    """A draft carrying the admitted bytes is completed, not re-uploaded."""

    result = _run_github_finalization(
        tmp_path,
        release_states=[
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":false,"tagName":"v3.4.5"}',
        ],
        published_assets=True,
    )

    assert result.returncode == 0, result.stderr
    assert "is already attached with the admitted bytes" in result.stdout
    # Each distribution is compared and left in place; only the evidence that
    # is genuinely absent is written.
    assert (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines() == [
        "download",  # wheel compared
        "download",  # sdist compared
        "upload",
        "download",
        "upload",
        "download",
        "patch",
    ]


@pytest.mark.integration
def test_github_attachment_refuses_a_conflicting_existing_asset(tmp_path: Path) -> None:
    """A same-name asset with different bytes fails visibly (#1227)."""

    result = _run_github_finalization(
        tmp_path,
        release_states=[
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
        ],
        published_assets=True,
        mismatched_download=True,
    )

    assert result.returncode != 0
    assert "already stores raes-3.4.5-py3-none-any.whl with different bytes" in result.stderr
    assert "patch" not in (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines()


def test_publishers_consume_the_original_artifact_and_never_rebuild() -> None:
    """Recovery reuses the admitted bytes; an absent artifact halts the run.

    A publisher that could rebuild would silently replace a same-version
    release when the original artifact has aged out, which is the one outcome
    #1227 and ADR-107 both forbid. The download is therefore the only source
    of publishable bytes, and it is not permitted to fail soft.
    """

    jobs = _load(RELEASE_PATH)["jobs"]
    expected_artifact = "release-distributions-${{ needs.resolve-release.outputs.release_sha }}"

    for name in ("admit-release", "publish-pypi", "publish-github"):
        job = jobs[name]
        download = _named_step(job, "Download the tested release distributions")
        assert download["with"]["name"] == expected_artifact, name
        assert download.get("continue-on-error") is None, name
        # No publisher-side build, and no fallback that could substitute bytes.
        for step in job["steps"]:
            assert "python_closure build" not in step.get("run", ""), name
            assert step.get("continue-on-error") is None, name


@pytest.mark.integration
def test_github_attachment_fails_closed_on_an_uncertain_asset_listing(tmp_path: Path) -> None:
    """An unavailable asset listing is not "nothing is attached yet".

    Reading a failed query as absence would let a transient API error turn
    into an overwrite of an already-published asset.
    """

    result = _run_github_finalization(
        tmp_path,
        release_states=['{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}'],
        asset_list_fails=True,
    )

    assert result.returncode != 0
    assert "upload" not in (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines()


@pytest.mark.integration
def test_github_attachment_accepts_preexisting_matching_evidence(tmp_path: Path) -> None:
    """A retry after evidence was attached but before finalization completes.

    Retained evidence goes through the same reconciliation as a distribution,
    so matching bytes are accepted rather than failing on an existing asset.
    """

    result = _run_github_finalization(
        tmp_path,
        release_states=[
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":false,"tagName":"v3.4.5"}',
        ],
        published_assets=True,
        published_evidence=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Retained 2 evidence documents with verified readback digests" in result.stdout
    # Everything is already attached with the admitted bytes, so the run only
    # compares and then finalizes.
    assert (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines() == [
        "download",
        "download",
        "download",
        "download",
        "patch",
    ]


@pytest.mark.integration
def test_github_attachment_refuses_preexisting_conflicting_evidence(tmp_path: Path) -> None:
    """Divergent retained evidence is an incident, not something to overwrite."""

    result = _run_github_finalization(
        tmp_path,
        release_states=[
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
            '{"databaseId":1234,"isDraft":true,"tagName":"v3.4.5"}',
        ],
        published_assets=True,
        conflicting_evidence=True,
    )

    assert result.returncode != 0
    assert "with different bytes" in result.stderr
    assert "upload" not in (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines()
    assert "patch" not in (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines()
