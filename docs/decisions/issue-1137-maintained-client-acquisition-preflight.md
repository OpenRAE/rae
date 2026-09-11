# Issue #1137 maintained-client acquisition preflight

Date: 2026-09-11

Issue: #1137. This is a requirement-free maintenance run; the issue title,
body, acceptance criteria, accepted ADR-106 design set, and landed #1216/#1217
authorities are the implementation contract.

This note records architecture guardrails only. It does not implement the
four-tool migration, change an artifact identity, qualify a new client or
platform, or claim any T01/T02/T08--T10/T23 result.

## Existing authorities and boundaries

| Concern | Canonical incumbent | Guardrail for #1137 |
|---|---|---|
| Artifact, version, platform, source, raw bytes and installed bytes | `implementations/tooling/artifacts.lock.json` | Consume the existing Conftest, Gitleaks, Vale and OSV-Scanner entries through `tools/tooling_policy_gate.py`. Do not restore live checksum discovery or duplicate digests, sizes, URLs or platform maps in wrappers or tests |
| Artifact/profile/admission shape | The six closed documents and schemas under `implementations/tooling/`, validated by `tools/check_tooling_artifact_policy.py` | Policy validation and exact selection occur before cache lookup, local input or curl. Update discovery/inventory coverage with the cutover; do not add another config schema or validator |
| Qualified generic client | The curl capability, fixed hardened argv, minimal environment, preflight and real-client evidence in `tools/bootstrap_profile.py`, `development-profiles.json` and `bootstrap-qualification.yml` | The production acquisition path and T08 must use one implementation of this qualified process boundary. Do not copy or independently tune curl options in four wrappers |
| Tool versions | `tools/tool_versions.py`, drift-bound to the lock by `selector-bindings.json` | Keep it as a checked consumer projection, not a second identity authority |
| Installation and cache admission | The existing four wrappers, with the stronger OSV safeguards recorded by the issue #1106 decision | Preserve consumer-specific archive/direct-binary admission and OSV no-follow, opened-file identity, atomic replace and scan-outcome behavior. Shared cache locking/publication redesign belongs to #1219 |
| Verification and diagnostics | Nox, `SessionReporter`, the policy lane, the dedicated OSV lane and `bootstrap-qualification.yml` | Required lanes still fail hard. Acquisition reports only a logical tool id and stable reason code; Nox remains the user-facing stage envelope |

This issue owns only Conftest, Gitleaks, Vale and OSV-Scanner acquisition and
the deletion of `tools/http_download.py` after its last consumer moves. The
remaining Isabelle, vocabulary, live-runner, governance API and runtime OCI
network surfaces retain the dispositions and owners already recorded in
`inventory-coverage.json` and `docs/decisions/package-artifacts/migration.md`.
Their presence must not be hidden, pulled into this issue, or used to claim that
the later repository-wide migration is complete.

## Intended acquisition boundary

The repository may own a narrow process adapter, not an HTTP client. The seam
is below `tools/bootstrap_profile.py` and the four installers: one implementation
owns qualified-curl preflight, fixed argv, a controlled environment, closed
stdin, a private output path, the subprocess wall deadline, output cleanup and
stable exit classification. Bootstrap qualification and production acquisition
both call that seam so the tested argv cannot drift from the argv that required
lanes use. Factoring this already-existing boundary to avoid a bootstrap/wrapper
import cycle is consolidation, not permission to grow a downloader framework.

The adapter must not expose headers, arbitrary curl flags, arbitrary environment
maps, callbacks, plugins, retry predicates or response objects. It must not parse
HTTP status, headers, `Retry-After`, redirect targets or framing, and it must not
wrap curl in an outer retry/fallback loop. The maintained client owns HTTP,
native retries, redirects, proxy and TLS behavior.

The #1217 fixed behavior remains authoritative: `/usr/bin/curl` from the
qualified host profile; `--disable` first; silent safe output; `--fail`;
HTTPS-only initial and redirect protocols; bounded redirects, native retries,
retry time, connection time and transfer time; `--max-filesize`; no insecure
TLS, trusted redirect or retry-all-errors; and a subprocess wall deadline. The
raw lock entry's exact size is the acquisition size bound. A general CLI input
must never exceed ADR-106's 256 MiB class ceiling even if malformed policy is
somehow presented.

Qualification and acquisition have different interpretations of the same
client result. `run_curl_qualification()` currently treats curl exit 63 as a
passing observation because T08 is proving that the client enforced its size
limit. Production acquisition must treat that outcome as terminal failure and
must never pass a partial/oversized output to integrity or installation code.
Every nonzero exit, wall timeout, inadequate client, unsafe output shape or
post-transfer size mismatch removes the staged output.

Local input is an explicit alternative carrier for the selected raw object. It
is not a new identity source and does not bypass policy selection. The seam is a
caller-supplied `Path` (or equivalent explicit parameter), not an ambient
environment variable, cache discovery rule, `file:` URL, redirect, user curlrc
or automatic fallback. Validate it as a bounded regular non-symlink file,
without following a swapped final component, then apply the same raw size and
SHA-256 check as a network result. If local input is missing, unsafe or wrong,
fail terminally without trying the network. A later explicit invocation may
select another approved carrier for the same expected bytes.

The order of trust is fixed: complete tooling-policy validation and exact
artifact/platform/profile selection; existing installed-cache validation;
explicit local input or one maintained-client invocation; raw size/digest
verification; consumer-specific type/archive and installed size/digest
verification; existing publication; execution. Type, archive, raw/installed
integrity, identity, unsupported-platform and local-input failures occur outside
curl and are never retried or converted into availability fallback.

## Cross-cutting layers the design must pass

- **Repository and config shape.** Reuse the bounded regular-file JSON loader,
  closed Draft 2020-12 schemas, normalized platform/profile joins, denied-digest
  and secret-locator checks, selector bindings, tracked-source acquisition
  discovery and exact site counts. `load_tooling_artifact_selection()` remains
  the sole DTO boundary. Its `LockedArtifactSelection` and
  `LockedManifestEntry` already carry every field the four installers need; no
  acquisition DTO or duplicate platform table is warranted.
- **Authentication and secret handling.** Current public profiles are
  credential-free. Policy rejects interpolation, URL user-info and secret query
  keys before selection; the process adapter again accepts only absolute
  credential-free HTTPS. Do not add auth headers, netrc, credential files or
  enterprise secret resolution here. With no credentials there is nothing to
  forward across origins. Enterprise egress/authentication belongs to reviewed
  profiles and maintained proxy/firewall infrastructure in its owning issue.
- **Environment binding and OS exposure.** Use the qualified fixed executable,
  fixed argv, closed stdin and the #1217 minimal locale/PATH environment. Do not
  inherit `HOME`, curlrc, proxy variables or a broad caller environment. The
  public reviewed URL and private output path may appear in process argv; a
  token, signed locator, header, credential reference/value or secret local path
  may not. Local file reading stays in process and does not place a source path
  in curl argv.
- **Filesystem and persistence.** Curl writes only into private staging, never
  directly to the executable cache path. Preserve safe cache-parent checks,
  regular-file/type checks, exact raw and installed manifests, cleanup and the
  existing consumer publication behavior. Do not centralize cache namespaces,
  add cross-process locks, markers, databases, shared writable stores or silent
  repair in #1137. In particular, no refactor may weaken OSV's per-use bounded
  no-follow hashing, inode consistency checks, executable check, atomic replace
  and fsync behavior.
- **Errors and observability.** Static-policy failures remain `PolicyFailure`
  records and Nox stages remain `SessionReporter` START/PASS/FAIL/SKIP records.
  Operational acquisition failures remain sanitized `RuntimeError` messages at
  the installer boundary; do not create a parallel exception hierarchy or
  conflate them with `OSVScanOutcome`. Never expose raw curl stderr, response
  bodies, full redirected/signed locators, native exception text or environment
  values. Stable reason classes include unavailable/inadequate client, transfer
  failure, deadline, size limit and unsafe output.
- **Consumer admission.** Conftest, Gitleaks and Vale retain their selected
  regular archive-member and installed size/digest checks. OSV retains the
  raw-equals-installed direct-binary check and its distinct clean/findings/
  scanner-error exit semantics. Bound reads of selected archive members by the
  reviewed installed size; an archive parse/type/shape failure is terminal.

## Verification guardrails

T01 and T02 must exercise the required lanes and all four platform selectors
through the actual migrated acquisition path, including clean local input.
T08 must continue using the controlled test-only server and the real qualified
curl for 429/503, disconnect, TLS rejection, HTTPS redirect, slow response and
unknown-length oversize behavior. Keep fixture protocol code test-only. A mock
of argv or exit status does not replace this coverage.

T09 covers an explicitly supplied same-digest local/approved carrier and hard
failure when no selected input is available; it must also show that acquisition
never mutates the lock. T10 demonstrates terminal authentication denial, HTTPS
and cross-origin credential safety of the actual fixed argv; it does not create
an enterprise credential feature. T23 must continue to fail before cache or
network when a version, raw/installed digest, canonical platform, selector
binding or acquisition path drifts.

Delete transport-only `test_http_download.py` coverage with the helper. Retain
and retarget the meaningful installer tests in `test_tooling_artifact_policy.py`,
`test_repo_policy_tools.py` and `test_vale_tool.py`: policy-before-cache/input,
exact selection, raw and installed mismatch, archive member type/path, symlink
and unsafe cache shapes, local input, cleanup, OSV TOCTOU/bounds/atomicity and
required scanner-result behavior. Retain the real-client tests from
`test_issue_1217_bootstrap_profiles.py` against the shared process seam.

The tracked acquisition inventory must change atomically with deleted and new
call sites. Remove stale production-only Ruff suppressions for the deleted
urllib path, including the obsolete `tools/http_download.py` and
`tools/osv_scanner_tool.py` S310 entries. Keep acquisition discovery capable of
detecting a resurrected repository HTTP helper; a negative policy guard is not
production transport code.

## Extensibility seam

The extension seam is the already-validated selection identity
`(artifact_id, version, canonical platform_id, profile_id)` plus an explicit
source carrier: the selected credential-free HTTPS locator by default, or one
caller-supplied local raw-object path. Both carriers converge before the single
raw manifest check; archive/direct-binary installation remains selected by the
existing tool wrapper, not by executable policy data. A future approved mirror
or profile changes reviewed locator/profile authority without changing hashing,
archive admission or required-lane behavior. It must not add URL-string
conditionals or a second retry/fallback engine to each consumer.

## Gotchas and anti-patterns

- Do not import the whole bootstrap command module into wrappers in a way that
  creates a cycle: bootstrap already imports all four installers for tool
  qualification. Share only the narrow existing curl process boundary.
- Do not consider a curl size-limit exit a successful acquisition, accept a
  merely existing output, download directly to a trusted executable path, or
  retry/fallback after any integrity/type/archive/identity failure.
- Do not add `requests`, `httpx`, `urllib`, sockets, a response facade, status or
  header parsing, sleep/backoff, redirect-host traversal, proxy/TLS policy or an
  outer process retry loop.
- Do not use shell strings, `shell=True`, PATH lookup, arbitrary policy-derived
  argv, `--insecure`, `--location-trusted`, `--retry-all-errors`, netrc, user
  curlrc, credential-in-URL or raw stderr in diagnostics.
- Do not turn local input into `file:` transport, an environment override,
  hidden cache search or automatic public/enterprise fallback. Wrong local
  bytes are an integrity incident, not an availability miss.
- Do not reintroduce live Conftest/Gitleaks checksum metadata, duplicate the
  reviewed Vale/OSV pins, or equate a digest with publisher authenticity.
- Do not replace consumer-specific type/archive admission with a generic
  package-manager/plugin abstraction, and do not weaken or normalize down to
  the least-safe cache helper.
- Do not delete benign URL parsing used by static policy, governance APIs or
  other explicitly dispositioned non-acquisition surfaces merely because this
  issue removes production HTTP transport for four tools.

## Non-goals and implementation boundaries

- No Isabelle or vocabulary acquisition migration (#1220/#1221), live-runner
  bootstrap change (#1222), runtime module-registry rewrite, OCI resolver change
  or governance/API client rewrite.
- No #1219 shared-cache locking, crash-recovery or cross-tenant concurrency
  design; preserve existing installer regressions until that issue replaces the
  local publication boundary.
- No new artifact/profile/admission schema, digest authority, package manager,
  general downloader, enterprise credential flow, proxy/firewall policy,
  retained mirror service, intake/promotion service or offline-export format.
- No vulnerability-gate weakening: OSV findings and scanner/setup failures stay
  distinct hard failures, and a missing scanner never becomes a clean scan.
- No SDL/runtime contract, controller, service, repository, persistence store or
  public schema change, and no claim that the later milestone-wide acquisition
  audit or operations program has completed.
