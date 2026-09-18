# Issue 1277: development-container entry-point preflight

**Date:** 2026-09-18
**Status:** Architecture preflight; implementation authority remains issue #1277

## Decision and scope boundary

Issue #1277 documents observed use of the already-qualified optional connected
development container. It does not qualify another client, runtime, host,
architecture, authentication method, signing path, proof host, or container
daemon. A configured client route is not a verified route. In particular, the
existing `development-image` CI job exercises the native image lifecycle and
repository setup, but does not establish Dev Containers CLI, VS Code,
Codespaces, Docker, or Podman client behavior.

The one claimable image profile is
`container-ubuntu-24.04-x86_64`: Linux x86_64, Ubuntu 24.04 base manifest,
non-root `raes` user, connected locked bootstrap, and `proof_support: unsupported`.
The profile, not prose, is the platform authority. Native arm64,
emulation, Codespaces, rootless Podman, and plain Docker remain unverified
unless this issue records an actual successful route with its exact host and
client/runtime versions. An observed Git behavior may be documented narrowly;
do not infer an authentication or signing support matrix from image packages.

## Existing authority to reuse

| Concern | Canonical incumbent | Required boundary |
| --- | --- | --- |
| Image/profile identity | `implementations/tooling/profiles/development-profiles.json`, `artifacts.lock.json`, `tools/devcontainer_image.py` | Retain the single selected container host profile and digest projection. Documentation must not restate a tag, platform alias, or package list as another authority. |
| Dockerfile and client configuration | `.devcontainer/Dockerfile`, `.devcontainer/devcontainer.json` | These are the native configuration owners. `tools/tooling_artifact_policy_container.py` and `tools/tooling_artifact_policy_devcontainer.py` are the closed shape/drift gate; use them rather than a documentation-specific configuration parser or checklist. |
| Setup and persistence | `tools/devcontainer_setup.py`, `tools/bootstrap_profile.py`, verified installers | The lifecycle command remains the sole setup entry point. Its cache is local, disposable, re-verified input state; it is neither installation evidence nor a distribution/provenance service. |
| Contributor checks | `CONTRIBUTING.md`, `docs/DEVELOPMENT_WORKFLOW.md`, `noxfile.py`, `tools/nox_support/{graph,policy_lanes,runner}.py` | Point to existing frozen Nox commands and `SessionReporter` outputs. Do not add a dev-container-specific verification graph, hook, or command wrapper. |
| CI evidence | `.github/workflows/bootstrap-qualification.yml`, `test_issue_1238_development_container.py` | Preserve CI's clean-image/setup evidence as image qualification only. Record client-route observations separately in the PR; they must name revision, host OS/architecture, client/runtime versions, commands, and result. |
| Trust and requirement governance | `specs/supply-chain/reusable-asset-trust-integrity.md`, ADR-071, `tools/requirement_context.py`, `tools/check_requirement_governance.py` | GOV-913 remains the broad trust requirement; this issue changes no reusable-asset schema or runtime trust policy. On this numeric branch, governed checks use `RAES_REQUIREMENT_UID=GOV-913`. |

## Cross-cutting security and validation surface

| Layer | Guardrail for this issue |
| --- | --- |
| Repository/config shapes | Documentation must describe only fields admitted by the existing bounded, duplicate-key-safe JSON loader and closed dev-container policy: reviewed Dockerfile/context, non-root users, named cache volume, fixed setup command, and restricted `remoteEnv`. Do not propose `runArgs`, `privileged`, `initializeCommand`, extra mounts, build args, host commands, or editor environment/command injection to make a route work. |
| Environment and secrets | No route may pass host tokens, SSH keys, credential-helper settings, proxy credentials, or signing material through configuration, image layers, cache names, shell tracing, logs, or argv. The documented route may rely on an already working host mechanism only as an observed limitation; it must not promise forwarding. |
| OS/process exposure | Retain the non-root user, no `sudo`, no daemon/socket, no host network, and cache-only mount boundary. Setup's existing fixed-argv, closed-stdin, frozen-lock path and error handling stay authoritative. Do not add shell wrappers or a client-specific installer. |
| Error envelope and observability | Preserve `DevcontainerSetupError`'s one-line contributor diagnosis, policy `PolicyFailure`/`failures_to_json()` output, and Nox `SessionReporter`. PR evidence must be bounded and sanitized: revision, public host/runtime versions, commands, exit/result, and observed limitation; never raw environment, daemon diagnostics, credentials, or private remote URLs. |
| Capability separation | `participant-opacity-proof` must still refuse without Bubblewrap isolation; `integration_docker` remains an optional host-capability lane unless its existing required selector is explicitly set by release policy. Neither failure may be converted to a skip, privileged container, socket mount, or claimed container support. |

## Documentation and evidence guardrails

The documentation change should make at least two actually exercised routes
reproducible, and label every route it did not exercise. It may remove a
support claim instead of labelling it. It must not say that a route is
supported merely because `devcontainer.json` exists, the CI smoke can emulate
its lifecycle, an image builds, a client can pull it, or an editor advertises
Dev Containers compatibility.

**Delivered scope, recorded 2026-09-18.** The verification host carried no
editor client and no display, so the VS Code open action could not be
exercised. The delivered evidence covers the Dev Containers CLI route and the
plain Docker route. It labels VS Code, Codespaces, Apple Silicon emulation and
rootless Podman unverified. Issue #1277 admits this narrowing: it asks for a
route to be verified only when it is intentionally supported and accessible,
and it states that testing all of them is not a completion condition. A run
that gains an editor client records the VS Code observation as a bounded
addition, exactly as the extension seam below describes.

The documented commands must remain references to the existing entry points:
`devcontainer up`/`exec` for the CLI route, VS Code's Dev Containers open
action for the VS Code route, `tools.devcontainer_setup` only for its existing
lifecycle, and frozen `nox` commands for checks. The stable extension seam is
the native client/runtime choice at the documentation boundary; adding a
verified client later adds a bounded observation and a short route, not client
settings, policy branches, profiles, cache formats, or runtime abstractions.

## Gotchas, anti-patterns, and non-goals

- Do not conflate an image/platform qualification with end-to-end editor or
  CLI qualification; do not conflate a CLI being installed with a reachable
  daemon, nor a package's presence with credential forwarding or signing.
- Do not claim repeat lifecycle timing/semantics without observing the client:
  the configured `updateContentCommand` is client-managed, while manual setup
  is explicitly available and idempotent.
- Do not duplicate profile, lock, Dockerfile, dev-container schema, validation,
  exception, logging, workflow, or test logic in documentation tooling.
- Do not broaden #1277 into #1313's policy simplification, an image redesign,
  arm64 qualification, Codespaces prebuilds, proof support, Docker/Podman
  daemon support, or an authentication/signing test matrix.
- Do not alter GOV-913's published reusable-asset trust schema, ADR-071, SDL
  contracts, runtime module registry, release admission, or protected-branch
  workflow. This preflight performs none of those changes and makes no support
  claim for an unobserved environment.
