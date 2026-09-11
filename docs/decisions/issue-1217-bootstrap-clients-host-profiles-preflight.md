# Issue 1217 bootstrap clients and host profiles preflight

Date: 2026-09-07

Issue: #1217. Requirement: GOV-913. The issue title, body, acceptance criteria,
accepted ADR-106/ADR-107, and the accepted package-artifact design set are the
implementation contract for this developer/bootstrap supply-chain increment.
The existing GOV-913 reusable-asset policy remains the normative ecosystem
contract and is not redefined here.

This note records architecture guardrails only. It does not implement setup,
qualify a client or platform, accept or amend either ADR, satisfy T01/T02/T03/
T08/T12, or assert that GitHub blockers and ownership gates are complete.

## Entry gates and scope

Repository history contains merged design acceptance (#1168/#1229) and the
#1216 lock/policy implementation (#1236). Before execution, the issue's native
GitHub `blocked_by` relationships must still be checked against the complete
expected edge set in `docs/decisions/package-artifacts/migration.md`, and a
named implementation owner must be assigned. A prose reference, local branch,
or merged prerequisite commit is not a substitute for either live gate.

The branch name does not contain a requirement UID. Implementation and
verification therefore must set `RAES_REQUIREMENT_UID=GOV-913` so the existing
requirement-governance gate evaluates the intended binding and traceability.

#1217 owns qualification of the bootstrap/client/host boundary for I04, I10,
I12, and I16. It may add explicit setup and inspection surfaces for those
profiles. Other issues continue to own generic archive acquisition (#1137),
Python tool/build/smoke resolution (#1218), and cache admission (#1219). They
also own Isabelle archive/tree admission (#1220), live VM input closure (#1222),
OCI mirror/import (#1223), action-transitive admission (#839), and complete
offline export/import (#1225).

## Authority and concept boundaries

| Concern | Canonical incumbent | Guardrail for #1217 |
|---|---|---|
| Ecosystem reusable-asset trust policy | `specs/supply-chain/reusable-asset-trust-integrity.md`, `contracts/schemas/asset-trust/reusable-asset-trust-policy-v1.json`, ADR-071, and `implementations/python/tests/test_reusable_asset_trust_policy.py` | Treat #1217 as developer/bootstrap supply-chain qualification contributing to GOV-913; do not add host tools, native packages, qualification evidence, or developer profiles to the reusable-asset family contract or clone its schema/model validators |
| Action implementation | Literal full commit in `.github/workflows/*.yml`, checked by `implementations/tooling/actions-policy.json` | Keep `actions/setup-python` and `astral-sh/setup-uv` source identity separate from every interpreter/uv payload they install |
| Immutable bootstrap payload | `implementations/tooling/artifacts.lock.json` and its admission policy | Record exact CPython/uv distributions, platform/ABI, raw and installed identity here; do not put action commits, native package-manager resolution, or Python dependency graphs here |
| Python dependency resolution | `implementations/python/pyproject.toml` and `implementations/python/uv.lock` | Preserve the 3.11--3.14 support bounds; do not copy package versions/hashes into bootstrap profiles. #1218 owns the tool/build/smoke closure |
| Artifact selection profile | Existing `profiles` collection in `implementations/tooling/profiles/development-profiles.json` | Continue to own canonical platform aliases, supported locked artifacts, contexts, locators, and trust-root references |
| Host/bootstrap policy | The same versioned development-profile authority and `profiles.schema.json` | Represent required trust anchors, native clients/packages, capabilities, privilege boundary, credential references, and offline-kit references as a distinct host-profile shape joined by ids; do not overload an artifact-selection profile or create an unrelated profile registry |
| Observed qualification evidence | A bounded, reviewed qualification record referenced by the host profile and T-case id | Record the tested image/repository snapshot, exact installed versions, capability results, implementation commit, policy hashes, context, and evidence digest. Evidence reports an observation; it never becomes the policy or a version selector |
| Generic tool identity | Existing four-platform entries in `artifacts.lock.json` | Reuse their raw/installed manifests and existing platform normalization; qualification must execute all four tools on Linux x86_64/arm64 and macOS x86_64/arm64 without copying their digests into host evidence |
| Proof isolation | `tools/isabelle_tool.py`, `tools/isabelle_sandbox.py`, `tools/check_participant_opacity_proof.py`, and ADR-106/#1109 | Qualify the existing Linux x86_64-only Bubblewrap, fontconfig/font, locale, resource, filesystem, and network boundary; do not create a second proof runner |
| Native/container/live prerequisites | Native package manager and host runtime; existing Docker/Podman and `tools/real-daemon/` probes | Record client/daemon/hypervisor capability separately. A CLI version cannot imply a running daemon, KVM access, privileges, image availability, or live-backend certification |

Artifact policy, host policy, and qualification evidence are three different
planes. Policy states what is required; the lock states which immutable bytes
are admitted; evidence states what a particular host/run demonstrated. A base
image digest, native repository signing root, package version, executable
version, and behavioral capability result are distinct fields and must not be
collapsed into one `version` or `trust` string.

Evolve `development-profiles.json` and its existing closed schema atomically.
Keep artifact-selection profiles intact and add a separately named host-profile
collection in that document, with semantic joins enforced by the existing
tooling-policy validator. Do not create a second validator, published contract,
Pydantic DTO, or runtime profile under `contracts/profiles/`. If the change makes
currently valid v1 documents invalid, advance the internal schema version
rather than silently redefining v1.

Because the lock currently permits one active record per `artifact_id`, each
supported CPython feature line needs a stable logical id (for example, a
feature-line identity) plus an exact payload version. Do not weaken uniqueness,
dependency joins, or selector bindings merely to place four versions under one
ambiguous id. A later exact patch refresh then changes the payload selected for
that feature-line id without changing workflow/action identity. `3.14t` is a
separate advisory identity/support level and must not enter the blocking
standard-interpreter set or satisfy a release-support query.

## Reused validation and execution boundaries

All policy/config changes must continue through the single fail-closed path:

1. `tools.policy.common.safe_repo_path()` and
   `load_bounded_json_object()` enforce repository containment, bounded regular
   files, UTF-8 JSON objects, and duplicate-key rejection. Internal schemas use
   Draft 2020-12 with local fragment references only.
2. `tools/check_tooling_artifact_policy.py` and
   `tools/tooling_artifact_policy_artifacts.py` own shape/semantic validation,
   normalized identity uniqueness, profile/platform/locator joins, artifact
   dependencies, policy evidence, denied digests, and forbidden executable
   data. Extend this validator for host-profile joins instead of adding a
   bootstrap-only validation path.
3. `tools/tooling_artifact_policy_actions.py`,
   `tools/tooling_artifact_policy_selectors.py`, and
   `tools/tooling_artifact_policy_discovery.py` continue to discover all tracked
   action, selector, runtime-selection, and acquisition surfaces. Setup action
   commits, CPython feature-line selectors, uv payload selectors, native
   profile ids, and any workflow consumer must drift-check against their owning
   authority rather than a repeated test constant.
4. `tools/tooling_policy_gate.py` remains the dependency-light boundary from
   bootstrap consumers to fully validated lock selection. Extend its reviewed
   selection shape only when a consumer needs a locked payload; host inspection
   must not turn it into a package manager, shell interpreter, or HTTP client.
5. `tools/nox_support/policy_lanes.py`, `tools/nox_support/config.py`, the
   canonical Nox graph, and `SessionReporter` remain the workflow and
   observability path. Profile data/evidence changes already belong to the
   tooling trigger. Hooks, CI, and Ground Control remain thin invokers.

Native setup and host inspection are separate operations. Inspection is
read-only, unprivileged, deterministic, and produces stable logical findings.
Provisioning is an explicit operator/workflow step using the selected OS package
manager or a reviewed base image. It may not auto-escalate privileges, add an
unreviewed repository/key, or mutate the host while supposedly validating it.
Do not build a cross-platform package-manager abstraction: a small fixed adapter
per actually qualified native family is sufficient.

## Curl and bootstrap trust contract

The qualified generic client is a currently supported curl whose behavior is
equivalent to 8.4.0 or newer for unknown-length `--max-filesize` enforcement.
The version string is necessary evidence, not sufficient evidence. T08 must run
the real selected client against controlled 429/503, disconnect, TLS failure,
HTTPS redirect, slow response, and unknown-length oversize fixtures, with a
subprocess wall deadline. A vendor backport is admitted only when the same
behavioral evidence is bound to the exact package/image identity.

The production adapter may own fixed argv, a controlled environment, an output
path, process supervision, exit classification, and bounded local hashing. It
must delegate HTTP, retry, redirect, proxy, TLS, status, and framing behavior to
curl. It must select HTTPS-only initial/redirect protocols, disable user curlrc,
avoid insecure TLS and trusted-redirect behavior, use bounded native retries and
redirections, and never wrap curl in another retry engine. Fixture-server code
for T08 stays test-only and cannot be imported by production acquisition.

Ubuntu 22.04's stock client must not be accepted merely because it is named
`curl`. When its behavior is inadequate, provision a qualified curl through a
reviewed native repository/package snapshot, signed base image, or offline
bootstrap kit. Do not fall back to `tools/http_download.py`, Python networking,
an older curl, or remote script execution. The bootstrap root is the reviewed
OS/vendor signing root plus reviewed image/repository identity; a downloader
cannot manufacture trust in its own replacement.

The offline bootstrap kit is a credential-free, digest-indexed closure. Its
manifest binds the installed uv and Python trees to their locked raw payloads
and the complete tooling-policy digest. An importer receives the producer's
manifest digest outside the archive and verifies it before executing imported
code. For #1217 it must describe or contain the trusted native
bootstrap for Git/history, CA roots, hashing, supported curl, and GH CLI. It
also covers exact uv/CPython payloads and the selected proof/container/native
host prerequisites. Complete export/import, status freshness, and all downstream
package/build/OCI content remain #1225 work. No `curl | sh`, `wget | shell`,
unverified source archive, mutable package channel, or ignored acquisition
failure is permitted.

## Security and information flow

The intended design crosses these layers:

- **Repository/config shape:** the closed internal schemas, bounded JSON loader,
  regular-file/no-symlink checks, normalized ids, semantic joins, selector drift,
  action coverage, and acquisition discovery all pass before selection or host
  setup. Unknown fields, duplicate ids/keys, unresolved references, ambiguous
  platforms, missing evidence, and unsupported profiles fail closed.
- **Authentication and authorization:** public profiles require no private
  credential. Enterprise/mirror profiles may carry only a stable credential
  reference plus provider, namespace/audience, access mode, and least-privilege
  purpose. A reference neither resolves a secret nor grants admission. Image and
  repository trust roots are reviewed independently of read credentials.
- **Secret handling and environment binding:** reuse
  `has_secret_bearing_locator()`, Gitleaks, private-key detection, and the
  workflow's explicit least-privilege `permissions`. Reject credentials or
  interpolation in URLs/policy/evidence, inline headers, keys, tokens, CA
  contents, signed queries, and arbitrary environment maps. If a maintained
  client needs authentication, inject it through its supported protected
  environment/file/stdin mechanism, never argv, URL, generated evidence, cache
  key, or public log. Do not inherit user curlrc, proxy variables, `HOME`, or a
  broad ambient environment into qualification.
- **OS/process exposure:** inspection runs fixed executable paths/argv with
  stdin closed, bounded stdout/stderr, timeouts, and a minimal environment.
  Provisioning may use an explicitly selected native package manager and
  reviewed repository roots, but no validator invokes `sudo`, changes host
  security policy, mounts daemon sockets, or enables user namespaces. Tokens,
  signed URLs, proxy credentials, and private paths do not enter process argv.
- **Proof isolation:** preserve `/usr/bin/bwrap`, the fixed read-only runtime
  allowlist, `--unshare-net`, empty ambient environment, private state, resource
  limits, `C.UTF-8`, fontconfig/font checks, and Linux x86_64 platform boundary.
  Missing Bubblewrap, fonts/locale, or permitted namespace support is an
  unavailable-profile failure, never a proof skip or permission to retry on the
  host network. Operators may choose an approved host policy; tooling does not
  disable AppArmor, SELinux, seccomp, namespaces, or another host control.
- **Errors and observability:** reuse `PolicyFailure`/`failures_to_json()` for
  static policy and `SessionReporter` START/PASS/FAIL/SKIP for Nox stages.
  Proof failures remain `IsabelleToolError`. Host/client qualification exposes
  stable reason codes, logical tool/profile/capability ids, sanitized version
  evidence, and evidence locations. Do not add a parallel exception hierarchy
  or print raw native stderr, response bodies, full locators, credential refs,
  private package names, or arbitrary environment values.
- **Persistence:** reviewed Git policy, setup guidance, and bounded qualification
  records are the only new repository state. No database, service repository,
  shared writable cache, marker-as-trust, credential store, or control-plane
  persistence integration belongs here.

## Platform and evidence guardrails

- CPython 3.11, 3.12, 3.13, and 3.14 standard builds are blocking support
  claims. Reuse `pyproject.toml`, the CI interpreter matrix, exact interpreter
  assertions, and clean distribution smokes from #1097. Record implementation,
  exact patch/build/ABI/distribution identity and OS/architecture; a minor
  selector or successful setup-action step is not payload evidence.
- Make every claimed interpreter/OS/architecture tuple explicit. T02 must prove
  the supported Python wheel/ABI closure on Linux arm64 and both macOS
  architectures as well as the Linux x86_64 T01/T03 path; no Cartesian support
  claim may be inferred from separate Python and generic-tool lists. A 3.11
  profile that claims OCI module extraction must select 3.11.4 or newer, matching
  the existing fail-closed safe-tar boundary.
- CPython 3.14t retains the existing scheduled/manual, `continue-on-error`,
  runtime-asserted advisory lane. It must remain visibly distinct in profile,
  evidence, and result aggregation.
- T02 reuses the four canonical generic-tool platform identities already in the
  lock. Each tool must actually execute and match raw/installed manifests. A
  platform label, cross-build, URL existence, or mocked argv is insufficient.
- Proof support is Linux x86_64 only. macOS and arm64 evidence must return an
  explicit unsupported/native-proof diagnosis and may point to a qualified
  Linux x86_64 host/VM; it cannot silently omit the proof stage.
- Container and live-native records separately state CLI, daemon, API,
  privileges, architecture, and execution result. Preserve the ordinary local
  optional-lane semantics, while required proof and release profiles remain
  hard failures.
- Every T01/T02/T03/T08/T12 record binds the implementation commit, T id,
  host/base-image and native-repository identity, exact package/client/payload
  versions, relevant capabilities, profile/platform/context, lock/policy
  hashes, command or harness identity, outcome, limitations, and evidence
  digest/location. Evidence must distinguish not-run, unsupported, failed, and
  passed; no aggregate green result may erase a missing required case.

## Extensibility seam

The extension seam is an explicit `host_profile_id` joined to a canonical
`platform_id`, context, locked bootstrap payload ids, named native capability
requirements, and evidence record. A future Ubuntu/macOS image, CPython feature
line, curl backport, enterprise mirror, or offline kit adds one reviewed profile
or evidence variant. Where needed, it also adds one fixed native-family adapter,
not workflow conditionals or a new schema/validator per consumer. Capability ids
map to implementation-owned probes, never to commands stored in policy data.

## Gotchas and anti-patterns

- Do not equate action SHA, setup-action release, payload version, payload
  digest, installed executable version, and behavioral qualification.
- Do not equate OS name with base-image identity, package name with exact native
  package evidence, signed repository metadata with an immutable snapshot, or a
  credential with a trust root.
- Do not place native packages in `uv.lock`, Python dependencies in the generic
  lock, host profiles in portable SDL contracts, or tool qualification in
  runtime backend DTOs/services/repositories.
- Do not duplicate platform aliases, generic-tool manifests, Python support
  bounds, action commits, proof limits, or selector literals. Join the canonical
  authorities and make drift a validation error.
- Do not make policy JSON executable through argv, commands, package hooks,
  environment interpolation, or arbitrary probes. Do not introduce a generic
  package manager or bootstrap plugin system.
- Do not accept version-only curl evidence, mock-only T08 coverage, curlrc,
  insecure TLS, trusted credentials across redirects, unbounded output, outer
  retries, or custom HTTP/redirect/TLS/framing code.
- Do not use pipe-to-shell installers, live checksum discovery, mutable
  `latest`/branch selectors, existence-only cache hits, suppressed native
  package failures, or network fallback in an offline profile.
- Do not silently skip required proof, weaken Bubblewrap isolation, bind the
  host root/home, disable host security controls, or call a missing proof
  prerequisite a theorem failure.
- Do not treat the existing `tools/real-daemon/` advice that disables libvirt's
  QEMU security driver as a generally qualified host setup. That legacy live
  certification boundary remains explicit and belongs to #1222; #1217 must not
  copy it into public, proof, container, or reusable native profiles.
- Do not treat a checked-in qualification record as current revocation or
  vulnerability status, retained availability, complete offline export, or
  production-service activation.

## Non-goals and implementation boundaries

- No custom acquisition transport and no migration/deletion of
  `tools/http_download.py`; #1137 owns that cutover.
- No Python tool/build/smoke dependency lock, package resolution change, or
  support for CPython 3.15; #1218 and a future interpreter qualification own
  those changes.
- No local cache/install concurrency, extraction, atomic publication, proof
  archive/tree admission, live VM image closure, OCI mirror/import, or
  transitive action-payload admission.
- No enterprise repository deployment, secret resolution, offline export/import
  completion, authenticated status snapshot, intake/promotion service,
  SBOM/provenance, release admission/publication, retention/GC, or DR claim.
- No SDL/runtime schema, controller, DTO, service, repository, package ontology,
  backend realization semantic, proof theorem, or public contract change. In
  particular, do not amend or duplicate ADR-071's GOV-913 reusable-asset family
  policy, published schema, reference model, fixtures, or validators.
- No automatic privilege escalation, host-security reconfiguration, protected-
  branch merge, feature-PR merge, infrastructure purchase, or assertion that a
  profile is qualified before its exact required evidence is reviewed.
