"""Stage only admitted finite evidence and allowlisted hosted provenance."""

import os
import platform
import re
import tempfile
from pathlib import Path

from raes_contracts.errors import EvidenceIntegrityError, OperationalError, RaesError
from raes_contracts.operational_logging import run_application

from tools.bootstrap_profile import (
    observe_current_python_identity,
    observe_host_identity,
)
from tools.bounded_tool_process import run_bounded
from tools.python_closure_profiles import (
    assert_runtime_matches_profile,
    load_python_closure_profile,
)
from tools.tooling_policy_gate import (
    load_tooling_host_profile_selection_with_current_interpreter,
)

from . import machine_check as machine
from .counterexample_corpus import encoded
from .export import digest, publish_bundle
from .ingress import read_bytes

OUTPUT_PATH = ".cache/raes-sdl/machine-check-publication"
HOST_PROFILE = "model-check-ubuntu-26.04-x86_64"
PYTHON_PROFILE = "public-linux-x86_64-cp314-all-extras"


def probe(command: list[str]) -> str:
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        run_bounded(command, stdout=stdout, stderr=stderr, wall_seconds=10)
        stdout.seek(0)
        payload = stdout.read(8193)
    if len(payload) > 8192:
        raise EvidenceIntegrityError("execution provenance exceeds limit")
    try:
        return payload.decode("ascii")
    except UnicodeDecodeError:
        raise EvidenceIntegrityError("invalid execution provenance") from None


def execution_record(root: Path, manifest_digest: str) -> dict:
    source = os.environ.get("RAES_MACHINE_CHECK_SOURCE_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", source) is None:
        raise EvidenceIntegrityError("missing immutable CI source revision")
    if probe(["/usr/bin/git", "-C", str(root), "rev-parse", "HEAD"]).strip() != source:
        raise EvidenceIntegrityError("CI source revision mismatch")
    selected = load_tooling_host_profile_selection_with_current_interpreter(HOST_PROFILE)
    host = selected["host_profile"]
    observed_base, observed_repository, checks = observe_host_identity(host)
    if any(item["outcome"] != "passed" for item in checks):
        raise OperationalError("model-check host identity is not qualified")
    packages = host["host_prerequisite_package_ids"]
    payload = probe(["/usr/bin/dpkg-query", "-W", "-f=${Package}\t${Version}\n", *packages])
    versions = {}
    for line in payload.splitlines():
        fields = line.split("\t")
        if (
            len(fields) != 2
            or fields[0] not in packages
            or re.fullmatch(r"[a-zA-Z0-9.+:~_-]{1,128}", fields[1]) is None
        ):
            raise EvidenceIntegrityError("invalid native prerequisite identity")
        if fields[0] in versions:
            raise EvidenceIntegrityError("duplicate native prerequisite identity")
        versions[fields[0]] = fields[1]
    if set(versions) != set(packages):
        raise OperationalError("missing native prerequisite identity")
    closure = load_python_closure_profile(root, PYTHON_PROFILE)
    assert_runtime_matches_profile(closure)
    kernel = platform.release()
    if re.fullmatch(r"[a-zA-Z0-9.+_-]{1,128}", kernel) is None:
        raise EvidenceIntegrityError("invalid kernel identity")
    return {
        "schema": "participant-crossing-machine-check-execution/v1",
        "manifest_digest": manifest_digest,
        "source_revision": source,
        "host_profile": HOST_PROFILE,
        "observed_base": observed_base,
        "observed_repository": observed_repository,
        "native_packages": versions,
        "kernel": kernel,
        "python_profile": PYTHON_PROFILE,
        "observed_python": observe_current_python_identity(),
        "python_lock_digest": digest(read_bytes(root, closure.project_lock.relative_to(root).as_posix())),
        "tool_lock_digest": digest(read_bytes(root, closure.tool_lock.relative_to(root).as_posix())),
        "sandbox": "required-successful-native-replay",
        "non_claims": ["immutable-host", "independent-reproduction"],
    }


def publish(root: Path) -> None:
    bundle, pin = machine.load_retained(root)
    machine.admit_bundle(root, bundle, pin)
    # A fresh native replay is required here too: this CLI cannot upload a skipped check.
    if machine.build_bundle(root) != bundle:
        raise EvidenceIntegrityError("publication replay drift")
    record = execution_record(root, pin)
    machine.check_sources(root)
    publish_bundle(root, {**bundle, "execution.json": encoded(record)}, OUTPUT_PATH)


def main() -> int:
    try:
        publish(machine.ROOT)
    except OSError, RaesError:
        print("crossing machine check: publication refused")
        return 1
    print(OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
