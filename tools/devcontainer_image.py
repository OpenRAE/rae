#!/usr/bin/env python3
"""Render the reviewed development-container build plan from policy authority.

The image configuration owns no version, digest, package, or platform fact. Every
value below is resolved from the development artifact lock and the reviewed host
profile through the existing fail-before-acquisition policy gate, so a Dockerfile
or dev-container edit can never become a second authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.tool_versions import DEVCONTAINER_BASE_IMAGE_VERSION  # noqa: E402

BASE_IMAGE_ARTIFACT_ID = "devcontainer-base-image"
_DIGEST_PREFIX = "sha256:"
_OCI_PLATFORMS = {"linux-x86_64": "linux/amd64"}


def build_plan(  # NOSONAR -- explicit closed-response checks keep the plan fail-closed.
    *,
    host_profile_id: str,
) -> dict[str, Any]:
    """Return the exact reviewed inputs one container host profile's image build may use."""

    from tools.tooling_policy_gate import (
        load_tooling_artifact_selection,
        load_tooling_host_profile_selection,
    )

    host_selection = load_tooling_host_profile_selection(host_profile_id=host_profile_id)
    host = host_selection["host_profile"]
    if host.get("base_image_artifact_ref") != BASE_IMAGE_ARTIFACT_ID:
        raise RuntimeError("host profile must name the reviewed development base image artifact")
    platform_id = str(host["platform_id"])
    if platform_id not in _OCI_PLATFORMS:
        raise RuntimeError("container host profile names a platform without an OCI platform mapping")
    identity = str(host["base_image_identity"])
    registry_reference = identity.rsplit(":", maxsplit=1)[0] if ":" in identity else identity
    selection = load_tooling_artifact_selection(
        artifact_id="devcontainer-base-image",
        version=DEVCONTAINER_BASE_IMAGE_VERSION,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
    )
    if len(selection.raw_manifest) != 1 or not selection.release.startswith(_DIGEST_PREFIX):
        raise RuntimeError("development base image selection must pin one index and one platform manifest")
    snapshot = host.get("native_repository_snapshot")
    user = host.get("development_user")
    if not isinstance(snapshot, str) or not isinstance(user, dict):
        raise RuntimeError("container host profile must declare a package snapshot and development user")
    packages = {*host["offline_kit"]["host_prerequisite_package_ids"], *host.get("development_package_ids", [])}
    return {
        "host_profile_id": host_profile_id,
        "platform_id": platform_id,
        "oci_platform": _OCI_PLATFORMS[platform_id],
        "base_image_reference": f"{registry_reference}@{_DIGEST_PREFIX}{selection.raw_manifest[0].sha256}",
        "base_image_index_digest": selection.release,
        "base_image_digest": f"{_DIGEST_PREFIX}{selection.raw_manifest[0].sha256}",
        "native_repository_snapshot": snapshot,
        "package_ids": sorted(packages),
        "development_user": {"name": user["name"], "uid": user["uid"], "gid": user["gid"]},
        "policy_sha256": host_selection["policy_sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-profile-id", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build_plan(host_profile_id=args.host_profile_id), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
