#!/usr/bin/env python3
"""Render only locked image identity for the native Docker build."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.operational_logging import run_application  # noqa: E402

from tools.tool_versions import DEVCONTAINER_BASE_IMAGE_VERSION  # noqa: E402
from tools.tooling_policy_gate import ArtifactPolicyError  # noqa: E402

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
        raise ArtifactPolicyError("host profile must name the reviewed development base image artifact")
    platform_id = str(host["platform_id"])
    if platform_id not in _OCI_PLATFORMS:
        raise ArtifactPolicyError("container host profile names a platform without an OCI platform mapping")
    identity = str(host["base_image_identity"])
    registry_reference = identity.rsplit(":", maxsplit=1)[0] if ":" in identity else identity
    selection = load_tooling_artifact_selection(
        artifact_id="devcontainer-base-image",
        version=DEVCONTAINER_BASE_IMAGE_VERSION,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
    )
    if len(selection.raw_manifest) != 1 or not selection.release.startswith(_DIGEST_PREFIX):
        raise ArtifactPolicyError("development base image selection must pin one index and one platform manifest")
    return {
        "host_profile_id": host_profile_id,
        "platform_id": platform_id,
        "oci_platform": _OCI_PLATFORMS[platform_id],
        "base_image_reference": f"{registry_reference}@{_DIGEST_PREFIX}{selection.raw_manifest[0].sha256}",
        "base_image_index_digest": selection.release,
        "base_image_digest": f"{_DIGEST_PREFIX}{selection.raw_manifest[0].sha256}",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-profile-id", required=True)
    args = parser.parse_args(argv)
    try:
        plan = build_plan(host_profile_id=args.host_profile_id)
    except ArtifactPolicyError as exc:
        print(f"devcontainer-image: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
