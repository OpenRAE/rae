"""Install the reviewed Temporal CLI input for hosted integration tests only."""

import argparse
import hashlib
import json
import os
import tarfile
import tempfile
from pathlib import Path

from tools.check_tooling_artifact_policy import select_tooling_artifact


def install_temporal_cli(archive_path: Path, destination: Path, *, repo_root: Path):
    lock = json.loads(
        (repo_root / "implementations/tooling/artifacts.lock.json").read_text()
    )
    version = next(
        item["version"]
        for item in lock["artifacts"]
        if item["artifact_id"] == "temporal-cli-runtime-test"
    )
    selected = select_tooling_artifact(
        repo_root,
        artifact_id="temporal-cli-runtime-test",
        version=version,
        platform_id="linux-x86_64",
        profile_id="public-linux-x86_64",
    )["platform"]
    raw, binary = selected["raw_manifest"][0], selected["installed_manifest"][0]
    if (
        archive_path.stat().st_size != raw["size"]
        or hashlib.sha256(archive_path.read_bytes()).hexdigest() != raw["sha256"]
    ):
        raise ValueError("Temporal CLI input does not match its reviewed identity")
    with tarfile.open(archive_path) as archive:
        members = [
            item
            for item in archive.getmembers()
            if item.name in {"temporal", "./temporal"}
        ]
        if (
            len(members) != 1
            or not members[0].isfile()
            or members[0].size != binary["size"]
        ):
            raise ValueError("Temporal CLI input has an invalid executable layout")
        stream = archive.extractfile(members[0])
        assert stream is not None
        content = stream.read(binary["size"] + 1)
    if (
        len(content) != binary["size"]
        or hashlib.sha256(content).hexdigest() != binary["sha256"]
    ):
        raise ValueError("Temporal CLI executable does not match its reviewed identity")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o700)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    install_temporal_cli(
        args.archive, args.destination, repo_root=Path(__file__).resolve().parents[2]
    )
