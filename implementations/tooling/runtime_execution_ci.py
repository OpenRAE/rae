"""Install the reviewed Temporal CLI input for hosted integration tests only."""

import argparse
import hashlib
import os
import sys
import tarfile
import tempfile
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError  # noqa: E402
from raes_contracts.operational_logging import run_application  # noqa: E402

from tools.check_tooling_artifact_policy import select_tooling_artifact  # noqa: E402

_TEMPORAL_ARTIFACT_ID = "temporal-cli-runtime-test"
_UNPINNED_INPUT = "artifact lock does not pin an executable Temporal CLI test input"


def install_temporal_cli(archive_path: Path, destination: Path, *, repo_root: Path):
    from tools.tooling_artifact_policy_common import ARTIFACT_LOCK_PATH, as_list, read_tooling_document

    # The bounded reader refuses a lock that is unsafe, not UTF-8 JSON or beyond the decoder limits.
    lock = read_tooling_document(repo_root, ARTIFACT_LOCK_PATH)
    versions = [
        item.get("version")
        for item in as_list(lock.get("artifacts"))
        if isinstance(item, Mapping) and item.get("artifact_id") == _TEMPORAL_ARTIFACT_ID
    ]
    if not versions:
        raise InvalidInputError(_UNPINNED_INPUT)
    selected = select_tooling_artifact(
        repo_root,
        artifact_id=_TEMPORAL_ARTIFACT_ID,
        version=versions[0],
        platform_id="linux-x86_64",
        profile_id="public-linux-x86_64",
    )["platform"]
    installed_manifest = selected.get("installed_manifest")
    if not installed_manifest:
        # A reviewed lock entry can carry an installed identity instead of an executable manifest.
        raise InvalidInputError(_UNPINNED_INPUT)
    raw, binary = selected["raw_manifest"][0], installed_manifest[0]
    if (
        archive_path.stat().st_size != raw["size"]
        or hashlib.sha256(archive_path.read_bytes()).hexdigest() != raw["sha256"]
    ):
        raise InvalidInputError("Temporal CLI input does not match its reviewed identity")
    with tarfile.open(archive_path) as archive:
        members = [item for item in archive.getmembers() if item.name in {"temporal", "./temporal"}]
        if len(members) != 1 or not members[0].isfile() or members[0].size != binary["size"]:
            raise InvalidInputError("Temporal CLI input has an invalid executable layout")
        stream = archive.extractfile(members[0])
        assert stream is not None
        content = stream.read(binary["size"] + 1)
    if len(content) != binary["size"] or hashlib.sha256(content).hexdigest() != binary["sha256"]:
        raise InvalidInputError("Temporal CLI executable does not match its reviewed identity")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o700)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        install_temporal_cli(args.archive, args.destination, repo_root=REPO_ROOT)
    except (OSError, tarfile.TarError, InvalidInputError) as exc:
        print(f"runtime-execution-ci: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
