# Issue 1223: OCI mirror and pre-seeded release-test image preflight

**Date:** 2026-09-16

**Status:** Architecture preflight; implementation authority remains issue 1223

**Design authority:** issue 1168, ADR-106, ADR-107, and
`docs/decisions/package-artifacts/`.

## Purpose and entry gate

Issue 1223 extends the already-landed #1110 release-only real-container gate
with a reviewed OCI acquisition/import/export path. It must preserve the
reviewed index, the selected platform manifest, its config and layers, and the
evidence needed to prove that the imported image is the same graph. It does not
rebuild the release gate or introduce development OCI semantics.

Execution may begin only after the native GitHub blocking relationships recorded
by issue 1168 are satisfied and Backend and Release name the implementation
owner. A prose dependency reference, successful local test, or accepted ADR is
not a replacement for either live gate.

## Authority and boundary

| Concern | Canonical incumbent | Binding boundary |
| --- | --- | --- |
| Release-required versus optional local behavior | #1110, `.github/workflows/release-please.yml`, `test_reference_backend_docker_integration.py` | Keep `RAES_DOCKER_INTEGRATION_REQUIRED` as the one closed selector. Required mode fails for absent runtime/input, zero cases, and skips; optional local/PR behavior remains visibly optional. |
| Runtime image admission | `ImageTrustPolicy` in `raes_reference_backend.drivers.oci_image_trust` | A runtime image is admitted only by the existing digest-pinned/explicit operator policy. Mirror selection is transport location, not a new image-trust override. |
| Native execution and portable diagnostics | `OciDeploymentDriver` | Preserve fixed argv, closed runtime names, bounded subprocesses, private native output, ownership labels/readback, existing diagnostic codes, rollback, and retryable teardown state. |
| Tooling input/policy selection | `implementations/tooling/artifacts.lock.json`, `implementations/tooling/profiles/`, `tools/tooling_policy_gate.py`, `tools/check_tooling_artifact_policy.py` | OCI client/platform/policy facts belong in the existing reviewed tooling authority and its static policy gate, not in SDL contracts, runtime package resolution, a new lock, or ad-hoc workflow literals. |
| OCI graph movement | maintained Skopeo plus Docker/Podman | Use native client export/import/copy operations. Repository code may construct validated fixed argv, bound local files, hash/read back identities, classify exits, and enforce a wall timeout; it must not implement HTTP, registry protocol, retry, redirect, TLS, framing, or an alternate image puller. |
| Release evidence and retention | ADR-107 and `docs/decisions/package-artifacts/operations.md` | Retain the reviewed index, every required selected platform manifest/config/layer, and evidence/receipt together. A tag, cache hit, mirror digest assertion, or selected child manifest alone is not an equivalent identity. |

There is no controller, DTO, repository, service, public schema, or SDL surface
to add. Checked-in lock/profile policy, the release workflow, the OCI driver,
and the existing Nox/pytest path are the repository equivalents. The runtime
module registry and SDL workload package authority remain out of scope.

## Binding design guardrails

The OCI input record must express a closed, validated selection: logical image,
reviewed multi-platform index digest, each required platform tuple and selected
manifest digest, config digest, layer digest set, client/tool identity, and the
applicable policy/profile identity. Import and release execution must prove this
record before use and must fail if an expected platform object is missing, an
unexpected/wrong-platform object appears, or any digest changes. The selected
platform manifest is evidence *within* the reviewed index graph, never a
replacement for the index identity.

The record belongs in the canonical development-artifact lock and its existing
admission/profile schema family: extend the `oci-image` variant in
`artifacts.lock.json`, `artifact-lock.schema.json`,
`admission-policy.json`, and the corresponding tooling-policy validation only
as needed to make the complete graph and closed context selectable. The current
generic `oci-image` handling proves `oci-index-digest` but has no fields or
semantic checks for selected manifests, configs, or layers; accepting this
feature through that index-only shape would be an integrity regression. Do not
create a second OCI lock, ad-hoc manifest JSON schema, or policy loader. The
same canonical validator must enforce uniqueness of image/platform identities,
closed keys, safe bounded local payload paths, graph membership, policy/profile
binding, and retention/evidence identity before any native-client invocation.

The stable extensibility seam is a closed OCI input/profile identifier bound to
an explicit required-platform set. Adding a registry mirror, target platform,
or future image changes that record and its policy/evidence; it must not add
free-form image references, arbitrary Skopeo/Docker/Podman argument arrays, or
per-workflow conditionals. Mirror-only and pre-seeded contexts must have no
unconditional public pull and no public fallback. Credentials, CA/trust
references, and registry endpoints are operational configuration references,
never image identifiers, argv values, cache keys, evidence names, or logs.

The real-container tests currently use fixed workspace labels and the driver
derives native names solely from the RAES address. This is insufficient for
concurrent runs. Generate one opaque, bounded run namespace at the test/harness
boundary, pass it as the driver's existing `workspace`, and feed the same
namespace into native resource naming while retaining the readable address
suffix. Cleanup must target only resources carrying the exact workspace and
address ownership proof. Both normal completion and every failure path must
execute teardown; failed deletion remains a reported test failure rather than
being hidden by `--rm`, a broad label sweep, or best-effort cleanup.

## Cross-cutting security and validation surface

| Layer | Required treatment |
| --- | --- |
| Repository/config admission | Reuse repository-confinement, tracked-regular-file, bounded JSON/profile validation, and aggregate `PolicyFailure` reporting from the tooling-policy modules. Reject unknown keys, duplicate logical/platform identities, traversal, symlinks, special files, oversize artifacts, and unbound generated evidence. |
| Policy semantics | Validate the full index-to-platform-manifest/config/layer graph and required platform set before a client import/pull or daemon execution. Bind the client/platform/profile and evidence to the same reviewed policy; syntactic digest shape alone is insufficient. |
| Environment and secrets | Start from a minimal environment. Do not inherit proxy, registry, Docker config, credential-helper, or ambient image override state unless the selected profile explicitly owns a safe reference. Never put credentials, tokens, private registry URLs, or CA material on argv or in emitted evidence. |
| OS/native client boundary | Invoke only maintained Skopeo/Docker/Podman clients with fixed argv and bounded timeouts; retain the OCI driver's closed runtime allowlist. No shell, no `shell=True`, no custom network stack, and no outer acquisition retry loop. Isolate per-run temporary workspace/cache paths with restrictive permissions. |
| Error envelope and observability | Reuse the driver's coarse portable diagnostics and existing release/JUnit reporting. Record safe logical image/platform/digest, policy/client identity, source class (preseed/mirror/public where allowed), duration, bytes, and cleanup outcome. Do not emit native stderr, registry response bodies, daemon IDs, credentials, or private locator text. |
| Persistence/evidence | Treat export payloads and daemon/client caches as untrusted carriers. Revalidate retained OCI objects and receipts on import; preserve evidence beside the graph. Writable caches are disposable and never become an authority or a successful-import marker. |

## Qualification boundary

Issue 1223 supplies the OCI slice of T07, T10, T11, T13, and T17 in
`operations.md`. Evidence must name the exact implementation revision, policy
and profile, client versions, required platforms, complete OCI identity graph,
source class, egress condition, test/JUnit result, concurrent run namespaces,
and cleanup result. It must not claim qualification for unrelated generic,
Python, proof-runtime, promotion, signing, or publisher controls.

## Gotchas and explicit non-goals

- Do not treat a mutable tag, one platform digest, `docker save` output, a
  local daemon cache hit, or `skopeo` success as proof that the reviewed
  multi-platform identity survived.
- Do not pre-pull publicly before mirror-only/pre-seeded selection, fall back
  to a public registry after a mirror/import failure, or add an integrity
  bypass such as an arbitrary image environment variable.
- Do not make a test server or fault proxy into production transport code.
- Do not add a second image policy, OCI manifest schema, exception hierarchy,
  workflow DAG, cache format, resource cleaner, or subprocess wrapper.
- Do not widen cleanup to names/prefixes alone: a concurrent foreign resource
  must never be removed. Do not swallow teardown failure.
- Do not change SDL workload package authority, runtime module-registry
  resolution, release publication/admission architecture, or ordinary optional
  Docker/Podman behavior. This issue does not promise every runtime, registry,
  architecture, or disconnected environment beyond its explicit qualified
  profile.
