# Issue 1238 development-container preflight

Date: 2026-09-12

Issue #1238 provides an optional, reproducible OCI development environment. It
does not replace native setup, turn a development image into a runtime image,
or reopen the separate Python-closure (#1218) and disconnected-kit (#1225)
work. This note is a design boundary, not an implementation plan or a platform
qualification record.

## Decision and authority boundaries

The image must be a consumer of the development-artifact policy, never a
second authority for Python, uv, generic CLI tools, native package selection,
or platform support. Extend the existing `host_profiles` collection in
`implementations/tooling/profiles/development-profiles.json` and its existing
schema/semantic validator with one reviewed OCI host profile per declared
Linux platform. Each profile joins its canonical `platform_id` to an exact OCI
base-image digest, reviewed native repository/snapshot and trust-root identity,
native prerequisite package ids, and the already locked bootstrap payload ids.
The Dockerfile and dev-container config select that profile; they must not
repeat package versions, tool versions, hashes, URLs, architecture aliases, or
base tags.

`implementations/tooling/artifacts.lock.json` remains the only authority for
CPython, uv, and the four generic CLI raw/installed manifests. The project and
tool `uv.lock` files remain the Python dependency authorities. Existing
`tools.bootstrap_profile`, `tools.tooling_policy_gate`, and the locked tool
installers remain the only routes to select, acquire, verify, and execute
those payloads. A Dockerfile `RUN` command must not become a parallel curl,
archive-extraction, checksum, or package-resolution implementation.

The initial ordinary-development image may declare Linux amd64 and arm64 only
when each has a distinct reviewed profile and clean-build qualification. If
either is not qualified, the supported set must be narrowed and enforced in
the image/dev-container configuration and documentation; an emulated build,
an image index label, or a successful pull is not qualification. The native
GitHub `blocked_by #1217` relationship is a delivery gate and must be created
and maintained; prose is insufficient.

## Required reuse and cross-cutting gates

The implementation must extend, not bypass, these incumbents:

| Concern | Canonical incumbent and required use |
| --- | --- |
| Policy/config shape and drift | `tools.policy.common` bounded loaders and `PolicyFailure`; `tools/check_tooling_artifact_policy.py`, `tools/tooling_artifact_policy_artifacts.py`, selector/inventory discovery, and `implementations/tooling/schemas/profiles.schema.json`. Extend this single fail-closed validator to parse the Dockerfile and dev-container JSON, validate their closed fields against the selected OCI host profile, and inventory any acquisition site. Do not add an ad-hoc image linter, free-form lock, or test-only source of truth. |
| Artifact and bootstrap selection | `implementations/tooling/artifacts.lock.json`, `implementations/tooling/selector-bindings.json`, `implementations/tooling/profiles/development-profiles.json`, `tools/tooling_policy_gate.py`, and `tools/bootstrap_profile.py`. The image must use selections returned from this policy boundary and execute `conftest`, `gitleaks`, `osv-scanner`, and `vale` through their existing verified installers. |
| Python/tool closure | `implementations/python/uv.lock`, `implementations/tooling/python/uv.lock`, generated closure projections, `tools/python_closure.py`, and `tools/generate_python_closures.py`. Do not copy Python requirements, indexes, or wheel hashes into container artifacts; #1218 remains the closure owner. |
| Workflow and reporting | `.github/workflows/bootstrap-qualification.yml`, the canonical Nox graph, `tools/nox_support/policy_lanes.py`, and `SessionReporter`. Add image qualification as an explicit workflow/reporting surface with bounded, sanitized evidence; retain native `verify`/preflight as independently usable paths. |
| Proof | `tools/isabelle_tool.py`, `tools/isabelle_sandbox.py`, `tools/check_participant_opacity_proof.py`, and the proof host profile. The ordinary image has `proof_support: unsupported`; it must diagnose this explicitly. A later proof image is a separate qualified Linux x86_64 host-profile variant and must preserve Bubblewrap, `--unshare-net`, restricted filesystem/environment, fontconfig/font, locale, and resource limits. |
| Container runtime | `nox -s integration_docker` and its `RAES_DOCKER_INTEGRATION_REQUIRED` semantics. The development image does not install, start, mount, or imply a Docker/Podman daemon or socket; optional daemon tests remain host-capability tests. |

The current artifact discovery recognizes Dockerfiles as acquisition surfaces but
does not make a dev-container JSON file a complete image-policy authority.
Extend that discovery deterministically as part of the existing policy gate:
unparseable or unowned configuration, a floating/tag-only base, an unknown
platform, profile/base mismatch, non-snapshot package source, or literal drift
must fail closed. The drift test must derive expectations from the profile/lock
authority, not from duplicated expected strings in a unit test.

## Security, process, and persistence boundary

The intended design passes these layers in order:

1. **Repository shape/policy:** bounded regular-file/no-symlink reads,
   duplicate-key-safe JSON parsing, existing schema validation and semantic
   profile joins admit the OCI profile and dev-container artifacts. The
   repository policy and tooling-artifact policy run before a build or
   acquisition; errors use `PolicyFailure`/`failures_to_json()` rather than a
   container-specific exception family.
2. **Configuration and environment binding:** Dockerfile build arguments,
   dev-container environment, mount declarations, and lifecycle commands are
   a closed allowlist. No arbitrary build args, environment maps, shell hooks,
   interpolated locator, credential reference, token, proxy setting, or user
   home path may enter an image layer, image label, cache key, evidence file,
   or command line. Existing secret scanning, private-key detection, and
   GitHub workflow least-privilege rules remain applicable.
3. **OS/process exposure:** install only reviewed native packages from the
   selected immutable repository/snapshot using fixed noninteractive commands;
   no pipe-to-shell installer, `latest`, floating action/base tag, unverified
   download, or inherited package repository/key. Create and use a non-root
   development user. Mount the checkout without changing its ownership and
   give that user dedicated writable cache locations; reject privileged mode,
   host networking, a daemon socket, broad host mounts, or a baked user state.
   Tool probes/acquisition retain fixed argv, closed stdin, minimal environment,
   bounded output and timeouts.
4. **Errors, evidence, and caches:** retain stable reason codes and
   `SessionReporter` START/PASS/FAIL/SKIP results. Qualification evidence must
   record source revision, declared base digest, resulting image digest,
   platform, profile/lock hashes, and commands, but no raw stderr, credentials,
   full environment, private host paths, or cache contents. Image layers are
   immutable build output; checkout, uv/tool caches, and proof state are
   disposable user-writable mounts, never trust or persistence authorities.

## Extensibility seam and non-goals

`host_profile_id` is the required seam: a future image family, apt snapshot,
base-digest refresh, platform, or qualified proof variant adds a reviewed
profile plus evidence, while the one policy validator resolves it. The
Dockerfile must be parameterized only by that closed profile selection and
canonical platform—not by user-supplied package/tool versions or arbitrary
URLs. A multi-platform manifest may aggregate qualified variants but may not
hide a platform-specific selection behind a generic `linux` value.

Do not introduce a new profile registry, schema, DTO/service/repository,
exception hierarchy, workflow graph, package-manager abstraction, image
bootstrap script, or container runtime abstraction. Do not bake a checkout,
credentials, tokens, SSH material, daemon socket, Python virtual environment,
or reusable mutable cache into the image. Do not claim native Isabelle support
on arm64 or macOS, skip a failed Bubblewrap setup, relax host security controls,
or reclassify proof failure as ordinary image smoke success. Do not make
offline export/import, Python closure ownership, production deployment,
VM/libvirt/KVM provisioning, or native workstation removal part of this issue.

## Implementation note: ready-on-open setup

A development container that needs manual commands after it opens fails the
issue's purpose, so `devcontainer.json` runs one fixed lifecycle command,
`/usr/bin/python3 -m tools.devcontainer_setup`, as its `updateContentCommand`.
That entry point is not an image bootstrap script in the sense above: it runs in
the mounted checkout rather than in an image layer, adds no acquisition,
extraction, checksum, or package-resolution logic of its own, and only composes
the incumbents in order: host-profile selection through the policy validator,
`tools.bootstrap_profile` fetch and install for the locked uv and CPython,
frozen `uv sync` for both projects, the verified generic-tool installers, and
`pre-commit install`. It treats the cache volume as untrusted, re-verifies every
cached archive against the lock, and swaps rebuilt clients in atomically.

Both Linux architectures are declared: `container-ubuntu-24.04-x86_64` and
`container-ubuntu-24.04-arm64` bind their per-platform manifests of one pinned
base index, and each is qualified only by a native clean build in the
`development-image` workflow matrix. The Dockerfile's first step refuses any
other architecture, and the drift gate requires that guard to equal the
qualified profile set.
