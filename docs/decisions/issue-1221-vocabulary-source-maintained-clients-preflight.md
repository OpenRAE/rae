# Issue 1221 vocabulary source acquisition preflight

Date: 2026-09-14

Issue: #1221. This is a requirement-free maintenance change. The issue and the
accepted ADR-106/ADR-107 design set form the contract. This work creates no
requirement UID or portable SDL authority.

This note records architecture guardrails only. It does not implement source
acquisition, change a vocabulary or source snapshot, qualify a remote result,
or satisfy T09, T11, T13, or T21.

## Entry gates and scope

Repository history contains the accepted design (#1168/#1229). It also contains
the artifact policy (#1216/#1236), bootstrap work (#1217/#1244), and the shared
client boundary (#1137/#1246). Before coding, check the live GitHub `blocked_by`
links against `docs/decisions/package-artifacts/migration.md`. Assign a named
owner too. Merged commits and prose do not replace those live gates.

The issue outcome names ATT&CK, ATLAS, and NIST CSF. The accepted I14 inventory
assigns all five sources to #1221. Required case T21 also names W3C
ActivityStreams and FIPA. Their checker still has custom urllib and redirect
code. The maintainer must settle this scope before coding. Either #1221 removes
network code for all five sources, or the issue and T21 must assign the last two
paths elsewhere. Work on only three sources cannot claim T21 or I14 is complete.

## Authority and concept boundaries

| Concern | Canonical incumbent | Guardrail for #1221 |
|---|---|---|
| Upstream raw identity | `implementations/tooling/artifacts.lock.json` `raw_manifest` entries selected by `tools/tooling_policy_gate.py` | Preserve exact raw SHA-256 and size. Do not copy them into portable source models. |
| Raw retention and redistribution | Artifact `retention_class`, `license`, `authenticity`, and `policy_refs`, plus `docs/decisions/package-artifacts/operations.md` | Keep raw objects as supported inputs. Preserve notice and review refs. A cache or fetch is not retained storage. |
| Checked-in snapshot identity | Lock `installed_manifest` plus `contracts/concept-authority/*-source-v1.json` | Verify the exact checked-in bytes. Do not redefine these files as raw manifests. |
| Canonical semantic digest | Each source artifact and its checker | Preserve its current meaning. ATT&CK/ATLAS share the raw digest value. NIST hashes normalized categories, not XLSX bytes. |
| Vocabulary meaning | `controlled-vocabularies-v1.json`, its Pydantic models, schemas, fixtures, and conformance checks | Feed bytes to the current parsers. Do not change terms, order, normalization, provenance, or adoption rules. |
| Acquisition mechanism | `tools.maintained_client_acquisition.acquire_locked_bytes()` | Reuse qualified curl or exact local input. Add no downloader, HTTP facade, retry loop, redirect handler, or provider SDK. |
| Policy selection | `load_tooling_artifact_selection()` and `LockedArtifactSelection` | Select exact artifact, version, `source-any`, and `source-snapshot` first. Add no parallel DTO or lock parser. |
| Workflow | Normal offline Nox and the explicit checker remote mode | Default checks stay offline. Fresh remote and reviewed local-raw checks are distinct, exclusive modes with honest labels. |

Raw identity, checked-in identity, semantic identity, provenance, and freshness
are separate facts. Equal digest strings do not merge them. Provider metadata,
a redirect, a current response, or an upstream checksum cannot approve bytes.
Only the reviewed lock and policy can do that.

## Reused cross-cutting path

The intended design passes through the existing layers in this order:

1. `tools/check_tooling_artifact_policy.py` loads the closed internal schemas.
   It reuses `safe_repo_path()` and `load_bounded_json_object()`. It rejects
   unsafe files, duplicate keys, schema drift, secret-bearing locators, broken
   joins, denied digests, selector drift, and unowned acquisition paths.
2. `tools/tooling_policy_gate.py` returns the one validated
   `LockedArtifactSelection`. Its selected URL and `LockedManifestEntry` are the
   only transport and raw-admission inputs.
3. `acquire_locked_bytes()` admits one local file or one curl transfer. Both use
   the same locked size and digest. Local failure is terminal. It cannot fall
   back to the network.
4. Existing source-specific extraction remains in the owning checker:
   ATT&CK STIX JSON, ATLAS YAML, NIST XLSX, and, if confirmed in scope, the
   ActivityStreams HTML and FIPA PDF checks. Raw admission must precede parsing.
5. Keep the current Pydantic `ContractModel` and source metadata checks. Keep
   the canonical digest, content, and `ControlledVocabularyCatalogModel` checks.
   Generated schemas and their publication ledger stay unchanged. This issue
   does not allow a semantic change.

There is no controller, runtime service, repository object, or database path in
this change. Repo state stays in the reviewed policy and checked-in snapshots.
Promoted storage and full offline export stay with later issues.

## Security and information flow

- **Authentication and authorization:** the source profile is public and has no
  credentials. It uses reviewed HTTPS locators and the system CA. Tokens, signed
  URLs, logins, response headers, and provider data cannot approve bytes.
  Enterprise auth and mirror choice are out of scope.
- **Secrets and locators:** reuse `has_secret_bearing_locator()` and the closed
  schemas. Reject credentials, secret expansion, inline headers, signed queries,
  custom CA data, and URLs from the environment. A fixed User-Agent does not
  justify a general header or credential escape hatch.
- **Environment/config shape:** add no ambient `RAES_*` override, proxy map,
  curlrc use, HOME-based config, or hidden fallback. The client has a small
  `LC_ALL`/`LANG`/`PATH` environment and disables curlrc. Pass a local raw path
  as a clear CLI or function input, not as an env switch.
- **OS/process exposure:** keep the absolute curl path and fixed argv. Keep
  HTTPS-only rules, native bounds, closed stdin, muted client output, and the
  wall deadline. Keep private temp output and no-follow file reads. Public URLs
  may enter argv. Credentials and private or signed URLs may not.
- **Errors and observability:** reuse stable reason codes, `PolicyFailure`, the
  checker stderr prefix, and Nox `SessionReporter`. Add no error class tree.
  Hide curl stderr, bodies, local paths, env values, provider data, and secret
  URLs. Evidence must say `fresh-remote` or `reviewed-local-raw`. Offline success
  cannot claim remote equality.

## Extensibility seam

The seam is the current exact selection tuple:
`(artifact_id, version, platform_id="source-any", profile_id="source-snapshot")`.
It feeds `acquire_locked_bytes(..., local_input=...)`. Network and local paths
must yield one admitted `bytes` value before parsing. A new source adds a lock
entry and one semantic parser. It does not add transport, a lock reader, a raw
schema, or provider logic to the shared client.

## Gotchas and anti-patterns

- Do not put raw digest, size, or retention fields in the published source
  schemas. The internal artifact lock owns that plane.
- Do not compare NIST's raw XLSX SHA-256 to its canonical category digest, and do
  not infer from equal ATT&CK/ATLAS values that raw and canonical identity are
  the same concept.
- Do not parse unadmitted bytes. HTML errors, short data, a wrong release, a
  missing raw file, changed checked-in JSON, or a mismatch must fail first.
- Do not keep checker host lists or custom redirect policy as a second approval
  layer. The reviewed locator/profile and curl own those concerns.
- Do not wrap curl retries, iterate alternate locators, auto-refresh the lock,
  accept a provider checksum, or fall back from corrupt/local/auth failures.
- Do not make normal Nox verification network-dependent or let an offline run
  set the same result/evidence label as the opt-in fresh remote operation.
- Do not copy large raw files into the semantic corpus. A temp download or cache
  is not the retained source of record.
- Do not add a shared vocabulary acquisition service merely to remove repeated
  calls. Transport is shared; parsing and normalization are intentionally
  source-specific.
- Update acquisition-discovery dispositions and runtime selector bindings with
  any changed call surface; a clean functional test does not excuse policy drift.

## Non-goals and implementation boundaries

- No vocabulary refresh, term change, source-version change, canonicalization
  change, public schema change, or modification of adoption/adaptation meaning.
- No general downloader, provider SDK, resolver, package manager, remote
  checksum discovery, cache installation scheme, or new retry/redirect/TLS/
  framing code.
- No runtime module-registry, SDL package, backend workload, controller, API,
  service, repository, DTO, or persistence change.
- No mirror deployment, promotion, full air-gap export, revocation service, GC,
  DR, or release work. Those remain #1224/#1225/#1228 boundaries.
- No claim that repository history proves live GitHub dependencies, that an
  unnamed owner satisfies ownership, that offline evidence is fresh, or that
  T09/T11/T13/T21 passed without exact tool/platform/policy evidence.
