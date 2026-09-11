# ADR-106: Developer Package and Artifact Management

## Status

accepted

Accepted by the maintainer through merged PR #1229 for issue #1168.

## Date

2026-09-05

## Classification

Classification: FM3

Required artifacts: acquisition/publication inventory, common-criteria decision matrix, authority and trust invariants, promotion/cache state model, failure and operating-context acceptance matrix, dependency-ordered migration, operations and recovery procedures.

Waivers: this change delivers design documents and issue dependencies only.
Executable cache, network, promotion, and publication changes belong to the
implementation issues. Their concurrency and crash tests are specified in the
design; no implementation, performance measurement, formal proof, offline
qualification, or service-level result is claimed here.

## Context

Issue #1137 exposed upstream availability failures in required checks. Four
tool wrappers use `tools/http_download.py`; Isabelle and vocabulary refresh
commands have separate network code. Some checksums are reviewed in Git;
Conftest and Gitleaks obtain theirs from the same release service as the bytes.
Python project dependencies have a frozen lock, but isolated build and tool
environments can resolve additional dependencies. CI actions, OS packages,
test images, and release artifacts introduce further acquisition boundaries.

PR #1140 proposed a repository-owned HTTP implementation. It was closed
without merging before this decision. Its socket, redirect, response-framing,
and retry implementation is rejected. The existing helper on `dev` also has
to be removed; rejecting the PR alone does not finish the migration.

The [inventory](../package-artifacts/inventory.md) records the actual baseline,
including the already-landed #1110 and #1125 release controls. SDL runtime
package declarations and reusable module resolution have different authorities.

## Decision

### Authority and mechanism

Adopt a layered architecture with native ecosystem clients:

1. Reviewed Git files select immutable inputs and integrity requirements.
   `implementations/python/uv.lock` remains the Python resolution authority.
   A development-artifact lock, build/tool dependency locks, bootstrap profile,
   and action-policy records fill its coverage gaps without duplicating its
   package resolution. Their proposed paths and ownership are specified in the
   [architecture](../package-artifacts/architecture.md).
2. A trusted intake job retrieves candidate bytes into quarantine, checks their
   identity, integrity evidence, license/redistribution eligibility and security
   policy, and proposes lock updates for review. Installation never discovers
   and accepts a new digest automatically.
3. Immutable promoted storage holds verified inputs and release evidence.
   It exposes Python Simple API, generic HTTPS, and OCI interfaces as appropriate.
   An enterprise repository manager may implement these interfaces. Public
   development must work without a private service or enterprise credentials.
4. Retain `uv` for Python environments. Retain upstream-maintained, SHA-pinned
   CI actions for orchestration and setup, and native package managers for OS
   bootstrap. Use maintained `curl` for the small reviewed set of generic
   archives and data snapshots; use Docker/Podman and Skopeo for OCI images.
   Repository adapters own selection, local integrity checks and installation,
   never HTTP behavior. Raw archive acquisition is an enumerated exception,
   not permission to build a general package manager.
5. Nox remains the verification graph. Release publication retains the exact-SHA
   and required-container prerequisites, adding digest-bound artifact admission,
   SBOM/provenance and immutable promotion as described in
   [ADR-107](adr-107-artifact-promotion-and-release-admission.md).

### No custom HTTP stack

Repository acquisition code must not implement HTTP clients, retries, backoff,
redirect traversal, proxy negotiation, TLS, framing, streaming network reads,
or protocol timeout handling. This includes wrappers around `urllib`,
`http.client`, `requests`, or `httpx` that retain acquisition transport policy.
Those behaviors come from maintained clients or infrastructure.

Fixed argument construction, initial locator/profile validation, process exit
classification, a subprocess wall-time limit, bounded local hashing, safe
archive admission and atomic local publication remain repository responsibilities.
No retry loop may wrap the maintained client's retry loop. A host-restricted
enterprise egress policy belongs to its proxy/firewall, not a redirect parser.

Remove `tools/http_download.py` in #1137; migrate Isabelle, vocabulary refresh
and live-runner acquisition in their separately ordered issues. The design
does not claim the baseline has already satisfied this rule. The milestone
cannot finish while any inventoried development acquisition retains it.

### Availability and isolation

Profiles explicitly distinguish public online, local pre-seeded, enterprise
mirror-only, concurrent runner and disconnected operation. A missing object
fails required work; neither an alternate version nor a disabled check is a
fallback. Mirrors may change a reviewed locator through approved profile
configuration but cannot change the expected bytes. Corruption, revocation,
identity failure and authorization denial stop acquisition.

Untrusted PRs receive only public inputs and isolated writable caches. They
cannot access enterprise credentials or write promoted storage, trusted runner
images, release evidence, or a cache later trusted by a privileged job.

### Scope and nonclaims

This is development and delivery infrastructure, not SDL package semantics,
scenario distribution policy, workload package modeling, or runtime module
registry authority. Shared storage is possible with separate namespaces,
credentials, policies and manifests; it grants no shared semantic authority.
The existing runtime OCI resolver is not repurposed as a development installer.

This decision does not buy or deploy a repository product, promise public
upstream uptime, claim that GitHub-hosted Actions run without GitHub, certify
macOS proof execution, or claim bit-for-bit reproducible wheels. Supported
contexts, limits, qualification evidence and operations targets are explicit
in the design set.

## Alternatives Considered

The [decision matrix](../package-artifacts/decision-matrix.md) evaluates all
classes against the same security, availability, portability, operation,
bootstrap and maintenance criteria.

- A mandatory Artifactory-, Nexus-, or Cloudsmith-class service centralizes
  operations, but introduces a service and credential dependency for public
  contributors. These remain conforming enterprise storage choices.
- Aqua and Hermit reduce per-tool installation work and offer declarative
  manifests. They introduce another bootstrap, registry and update authority;
  neither replaces Python resolution, OS provisioning, Actions or publication.
  A mandatory CLI manager is not selected for the current small tool set.
- OCI for every artifact provides content addressing but forces an adaptation
  layer for Python installation and cannot bootstrap its own client. OCI is
  selected for images and portable image export, not as the only interface.
- Setup actions alone leave local and disconnected users without a matching
  path. Native packages alone cannot select every required upstream tool.
- Keeping the current downloaders leaves duplicated transport and incomplete
  integrity authority. Adding a more elaborate downloader is rejected.

## Consequences

There is one reviewable integrity policy across several maintained clients.
Warm caches improve speed; retained promoted objects provide outage recovery.
Deleting either must not change the meaning of a successful verification.

OpenRAE still owns a small amount of local admission and cache code. Its scope
is constrained and tested, including process crashes, concurrent writers and
tampering. Enterprise operators own storage credentials, egress, backup and
availability. Security and release maintainers own revocation and promotion.
Named operational owners must be assigned before their services are activated.

The [migration program](../package-artifacts/migration.md) provides one issue
per reviewable change, native GitHub dependencies, the incumbent disposition,
and the final acceptance gate. Implementation begins only after design
acceptance; closing #1168 does not claim that the migration issues are shipped.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-09-06 | #1229 | Recorded the maintainer acceptance already established by merged PR #1229 and added the ADR to the accepted-content pin manifest. |
