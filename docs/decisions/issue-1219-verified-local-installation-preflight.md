# Issue #1219 Verified Local Installation Preflight

Date: 2026-09-13

Issue: #1219. This is a requirement-free maintenance run. The issue title,
body, acceptance criteria, accepted ADR-106/ADR-107, and the accepted
package-artifact design set are the implementation contract.

This note records architecture guardrails only. It does not implement an
installer, change a cache, qualify a platform, satisfy T05/T06/T07/T16, or
claim that ownership and native GitHub dependency gates are complete.

## Entry gates and scope

Repository history contains the accepted #1168 design and implementations for
#1216 and #1137. Before execution, the live GitHub dependency graph must still
show #1168, #1216, and #1137 satisfied, and a named implementation owner must be
assigned. Repository history and prose references do not replace either gate.

#1219 owns local files, admission, installation, locking, migration from the
four legacy executable caches, and local publication for Conftest, Gitleaks,
Vale, and OSV-Scanner. `tools/maintained_client_acquisition.py` remains the raw
carrier boundary. It must not be absorbed into the installer or bypassed by a
cache, seed, migration, or repair path.

## Canonical authorities and boundaries

| Concern | Canonical incumbent | Guardrail for #1219 |
|---|---|---|
| Artifact identity and manifests | `implementations/tooling/artifacts.lock.json` and `artifact-lock.schema.json` | Consume the selected artifact, canonical platform, raw digest/size, installed manifest, and active policy references. Version may remain display metadata but is not a cache-hit identity |
| Admission and platform policy | `admission-policy.json`, `development-profiles.json`, their existing schemas, and `tools/check_tooling_artifact_policy.py` | Reuse the active-policy, denied-digest, profile/platform, locator, selector, and acquisition-coverage joins. Complete these existing closed shapes if installation format or bounds need authority; do not add a parallel manifest or validator |
| Runtime selection DTO | `LockedArtifactSelection` and `LockedManifestEntry` in `tools/tooling_policy_gate.py` | Extend this validated response only for already-authoritative fields needed by installation, including policy references and executable intent. Do not let wrappers reread JSON or create four DTOs |
| Raw acquisition | `tools/maintained_client_acquisition.py` | Accept only its admitted bytes or an explicit lock-verified local input. No HTTP, retry, redirect, TLS, proxy, framing, response, or locator-fallback logic belongs below this boundary |
| Current local consumers | `tools/policy/conftest_tool.py`, `tools/gitleaks_tool.py`, `tools/vale_tool.py`, and `tools/osv_scanner_tool.py` | Keep public `ensure_*` behavior thin and preserve each execution contract. Remove their duplicate cache-hit, parent, extraction, mode, and publication algorithms |
| Strong existing local check | OSV `_sha256_path()` and `_validated_cache_hit()` plus the #1106 decision | Open without following the leaf, compare `lstat`/`fstat` identity, bound the read, verify regular type/size/digest/mode, and recheck after hashing for every tool. Centralization may strengthen OSV but may not normalize the others below it |
| Portable lock dependency | `filelock==3.32.6` already frozen transitively in `implementations/tooling/python/uv.lock` | If used by repository tooling, make it a direct dependency only of the existing frozen tooling project. Require native locks, a bounded wait, and a persistent lock pathname; disable soft/existence-lock fallback. Do not copy `fcntl`/`msvcrt` loops into each wrapper |
| Transactional precedents | `raes.module_registry._cache`, `_filesystem`, `_cache_integrity`, and their adversarial tests; local-control-plane durability tests | Reuse their invariants: anchored parents, immutable staged trees, full-tree validation, file/directory fsync, atomic rename, stable lock inode, and recovery under the lock. Do not import these private runtime modules or their `SDLParseError`; development tooling has a different authority and error boundary |
| Verification and workflow | ADR-014, `noxfile.py`, `tools/nox_support/`, `.pre-commit-config.yaml`, canonical workflows, `Makefile`, `.ground-control.yaml`, and `.gc/plan-rules.md` | Extend the existing tooling-triggered unit/integration graph and `SessionReporter`; do not create another workflow or a second policy gate |

The internal tooling lock is not an SDL/runtime artifact contract. No portable
schema, controller, DTO, service, repository, module-registry policy, or
`LocalControlPlaneStore` participates in this change.

`safe_tooling_cache_parent()` is the incumbent common cache-parent check, but it
currently proves only containment plus directory/non-symlink shape. Strengthen
or factor that one boundary to add private ownership, mode, anchored-parent, and
filesystem semantics; do not leave its weaker copies in OSV and the wrappers.
The current Conftest self-verification subprocess also runs under the project
environment. A portable-lock dependency must not be duplicated into that
project lock: every tool installation entry point must execute from the frozen
tooling closure selected by #1218, while the project environment remains the
application/test dependency authority.

## Local installation contract

There is one shared installed-tree admission and publication boundary. The
current four installations each contain one executable, but the boundary is an
installed manifest rather than a special-case “downloaded binary exists” test.
That keeps the next package-artifact change able to admit a multi-file tree
without weakening or duplicating the transaction rules.

The cache identity is derived from the validated artifact id, canonical
platform id, locked raw content digest, active versioned installation-policy
identity, and canonical installed-manifest content. A version-only directory,
filename, marker, successful prior run, or existence check is never a hit. An
unrelated global policy revision should not churn every installation; a change
to installation semantics must select a new versioned policy identity.

`LockedArtifactSelection` currently omits `policy_refs`, and
`LockedManifestEntry` currently drops the lock's `executable` field. Those are
authority-projection gaps, not reasons to invent a cache schema. The validated
selection must carry the existing policy and mode intent through the sole DTO
boundary before the cache key or filesystem is touched.

The lock currently identifies the selected installed member but does not expose
the accepted architecture's explicit archive format and member/count/decoded-
size rules. Safe archive admission cannot be inferred from a URL suffix or
implemented as three wrapper-specific defaults. If fixed class bounds are not
sufficient, add a closed format/bounds branch to the existing artifact lock and
schema and project it through the same selection DTO. Data may select only a
closed implementation-owned format and numeric bounds; it may not select code,
commands, callbacks, filters, or plugins.

Archive admission applies before reading a selected member. It bounds metadata,
member count, names, path depth, declared member and aggregate sizes, and rejects
absolute/traversing/duplicate/conflicting paths, symlinks, hardlinks, devices,
FIFOs, sockets, sparse or otherwise unsupported entries. Only reviewed regular
files in the installed manifest become installed content. Direct OSV bytes use
the same raw and installed manifest checks without pretending to be an archive.

The filesystem transaction has these indivisible properties:

- The dedicated installation and lock roots are privately owned, non-symlink
  directories with no group/other write access. Creation uses explicit private
  modes independent of ambient umask. A cross-user writable root is rejected,
  not repaired or silently relocated.
- Staging is unpredictable, exclusive, private, and on the destination
  filesystem. Files are created without following links and are not executable
  while unverified. Hardlinked or multiply linked installed leaves are rejected.
- One maintained native lock protects one logical publication identity. The
  lock pathname persists; its existence is not ownership or validity. Kernel
  release after process death permits the next holder to clean only
  transaction-stage names protected by that same lock and continue. PID age or
  lock-file deletion is not dead-owner recovery.
- The winner rechecks for a valid installation after acquiring the lock. It
  validates raw bytes, complete archive shape, staged installed content, owner,
  type, link count, exact mode/size/digest, then makes the installed tree
  non-writable, fsyncs files and directories, atomically renames it, fsyncs the
  parent, and reopens/revalidates the committed result before returning it.
  Unsupported durability semantics cannot be swallowed while claiming T05.
- A consumer observes absence or one complete immutable tree. No executable is
  replaced in place and no “valid” marker is published separately from content.
  Required callers perform the opened-inode/type/mode/digest check immediately
  before execution; OSV's current per-use strength remains the floor.

An immutable read-only seed is a carrier, not a trusted writable cache. It is
explicitly selected, revalidated against the same lock/policy, and copied into
an independently staged private job tree. No seed, cache, local input, `HOME`,
XDG directory, environment variable, or shared filesystem is discovered as an
implicit fallback. NFS, SMB, FUSE, and any filesystem whose native lock,
same-filesystem rename, inode, mode, or directory-fsync behavior is not
qualified for the selected root fail explicitly.

## Failure, migration, and observability

Policy-shape failures remain deterministic `PolicyFailure` records. Operational
installation failures remain sanitized `RuntimeError` failures at the current
tool boundary, using stable reason tokens where classification is required.
Do not introduce an exception hierarchy parallel to `PolicyFailure`, and do not
reuse `OSVScanOutcome`: clean, findings, and scanner-error describe scanner
results, not artifact installation.

Availability failure may end at the maintained client's bounded behavior.
Wrong raw bytes, unsafe archives, installed mismatch, unsafe cache shape,
tampering, revocation, unsupported filesystem semantics, lock timeout, and
durability failure are terminal integrity/policy outcomes. They must be visible
and must not trigger deletion-and-redownload, another origin, another profile,
or a weaker cache path. The current OSV test and #1106 wording that silently
unlink and reacquire an invalid file are superseded for #1219 and must not be
generalized.

The version-keyed Conftest, Gitleaks, Vale, and OSV directories are legacy
inputs, never new-cache hits. Migration occurs under a stable artifact/platform
migration lock so two new digest identities cannot race over one legacy path.
Legacy content is moved without following it to a private non-executable
quarantine, then reverified there with the opened-inode/type/mode/size/digest
rules and a stable logical outcome. Exact installed content may be copied from
quarantine through the new private staging transaction as an explicitly
recorded legacy-installed carrier; it is not raw provenance or general seed
authority. A failed revalidation remains quarantined and terminal, and does not
cause acquisition in the same invocation. Repair is a separate explicit
invocation after the failure has been recorded. Quarantine retention/incident
handling stays distinct from a performance cache and from the later promoted-
storage lifecycle.

`SessionReporter` remains the stage envelope. Evidence and public diagnostics
may record logical artifact id, canonical platform, policy id/digest, cache
outcome, duration, lock wait, byte count, and stable failure reason. They must
not emit raw native exceptions, archive payloads, full local paths, raw stderr,
signed locators, credential values, private package names, or environment
contents. Process argv may contain only the verified executable path and the
existing public tool arguments; installation adds no token, header, secret
reference, shell string, or untrusted executable search path.

## Verification contract and unresolved evidence boundary

Focused tests must retain policy-before-cache behavior and each current tool's
execution/result contract while adding real multi-process contention, kill at
each durability boundary, inode/parent swaps, private-root ownership/mode,
malicious archive, immutable-seed copy, terminal tamper, legacy quarantine,
lock timeout/dead-owner recovery, disk-full, and unqualified-filesystem cases.
Mocks can inject individual failures, but T05/T06 require real process and
filesystem behavior. A “two users” T06 result requires distinct OS principals,
not two directories or environment labels.

Every T05/T06/T07/T16 record must reuse the existing qualification-record
authority in `development-profiles.json`, extending its closed case/result
shape rather than creating an evidence schema. It records the exact commit,
tool, canonical platform/host, lock and policy identities, harness and evidence
digests, outcome, limitations, and which slice of the operations case ran.

The accepted operations cases are program-wide while #1219 and its dependency
position are local-tool scoped:

- T05 includes a proof object, but #1220 depends on #1219 and owns Isabelle.
- T07 includes 100 service clients and provider quota behavior, while #1219
  owns no repository service or HTTP behavior.
- T16 includes retained OCI referrers and a supported offline export, owned by
  downstream #1223, #1225, and #1228.

#1219 can execute and record the generic-CLI/local-installation slices without
inventing those downstream systems, but it cannot truthfully label the complete
program-level T05/T07/T16 cases passed. Before issue closure, maintainers must
confirm that scoped evidence plus explicit limitations satisfies the issue, or
align the issue wording/dependency graph with the later full qualification.
Synthetic proof/service/OCI/export fixtures must not erase this boundary or
create circular prerequisites.

## Extensibility seam

The seam is a validated `LockedArtifactSelection`, an explicit raw carrier, an
explicit private installation root, and a closed installation-policy identity.
All formats converge on one installed-tree admission/publication transaction.
A later larger archive, multi-file tree, immutable service seed, or stricter
policy adds reviewed format/bounds/manifest/profile data or one fixed adapter;
it does not re-edit four wrappers, add URL conditionals, duplicate locks, or
make policy data executable.

## Gotchas and anti-patterns

- Do not key by version, filename, URL, marker, mutable path, or merely the
  installed digest; do not hash a directory name and call that admission.
- Do not perform cache lookup before the complete tooling policy and exact
  artifact/platform/profile selection. A warm cache cannot bypass revocation.
- Do not use `SoftFileLock`, existence locks, unlocked PID files, unbounded
  waits, lock-file unlink recovery, or filelock's soft fallback. Do not hold
  different identity/migration locks in an inconsistent order.
- Do not use `shutil.move` as a durability claim, publish a writable executable,
  replace a live binary in place, or ignore directory-fsync errors on a claimed
  platform.
- Do not use `extractall` without complete prior admission, trust archive mode
  or filename suffixes, inspect only the selected member while ignoring a
  metadata bomb, or accept links/special files because they are not selected.
- Do not silently delete, repair, reacquire, retry, or fall through after an
  integrity failure. Do not treat quarantine as a cache miss.
- Do not share writable installed trees across users, jobs, fork PRs, trusted
  publication, or trust domains. Read-only seeds never receive job writes.
- Do not import private runtime cache/control-plane helpers or leak their domain
  exceptions into tooling. Reuse their safety properties and adversarial-test
  patterns at the correct boundary.
- Do not add a second lock/profile/manifest/evidence schema, duplicate the four
  tool manifests, or put `filelock` into the project/runtime dependency lock.
- Do not weaken OSV scan-result classification, convert scanner/setup failure
  into clean, or broaden this issue into vulnerability-data freshness.

## Non-goals and implementation boundaries

- No HTTP implementation or maintained-client retry/redirect/TLS/framing
  change; no new origin, mirror fallback, enterprise credential flow, proxy,
  retained service, or transport response model.
- No Isabelle/proof installation (#1220), vocabulary migration (#1221), live
  VM closure (#1222), OCI mirror/import (#1223), offline export/import (#1225),
  release admission/publication, or program-wide retention/GC/DR qualification.
- No Python resolver or project dependency change. A direct portable-lock
  dependency, if required, belongs to the already authoritative frozen tooling
  closure and must preserve #1218's generated closure checks.
- No public schema, SDL/runtime package meaning, reusable-asset policy,
  controller, service, repository, database, or external operations activation.
- No claim of hostile-host protection, distributed locks, cross-host writable
  cache safety, exactly-once installation, unlimited concurrency, or automatic
  recovery from integrity incidents.
