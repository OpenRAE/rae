from __future__ import annotations

CONTFEST_VERSION = "0.68.0"
GITLEAKS_VERSION = "8.30.1"
OSV_SCANNER_VERSION = "2.4.0"
VALE_VERSION = "3.15.2"
ISABELLE_VERSION = "2025-2"
DEVCONTAINER_BASE_IMAGE_VERSION = "24.04"
CIRROS_GUEST_DISK_VERSION = "0.6.2"

# Live-runner (issue #1222) reviewed host/native bindings. The base image is
# bound by Canonical's exact published image name (serial), which is
# region-independent and reproducible, resolved to the region's AMI id by owner +
# exact name (never "newest"). The native package closure is pinned to an
# immutable snapshot.ubuntu.com archive timestamp so apt installs reproducible
# versions.
LIVE_RUNNER_UBUNTU_IMAGE_OWNER = "099720109477"
LIVE_RUNNER_UBUNTU_IMAGE_NAME = "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-20260911"
LIVE_RUNNER_NATIVE_SNAPSHOT = "20260901T000000Z"
LIVE_RUNNER_CPYTHON_ARTIFACT = "cpython-3.14"
