# Operations, failure behavior and acceptance

## Ownership and activation

This is an implementation acceptance contract. Targets below are proposed
minimums, not measurements of an existing service. A profile is not qualified
until its issue records actual evidence, a named primary/deputy and the tested
client/OS/provider versions. Repository maintainers accept that record.

| Role | Accountable decisions and routine work |
|---|---|
| Tooling | Client/bootstrap versions, artifact lock coverage, developer installation, platform smoke, removal of bespoke acquisition; weekly update proposals |
| Security | Trust roots, action admission, quarantine/revocation, redistribution/security exceptions, vulnerability snapshot freshness, incident response |
| Platform | Enterprise service selection, native snapshots and runner images, namespace ACLs, secret delivery, egress, monitoring, capacity, GC and DR |
| Release | Hashed build/smoke closure, SBOM/provenance, admission bundle, publisher identities, environment/tag controls, partial-publication recovery |
| Proof / Backend / Semantics / Docs | Qualification of their inventory rows and consumer-specific acceptance; maintain the distinction between input integrity and domain meaning |

The first deployment record must identify all service endpoints, region/site,
public versus private visibility, budget/quota owner, supported targets, artifact
format/export support, key/CA references, maintenance window and escalation
contact. It must contain no credential values. An unnamed service has no
operational readiness claim. No hosted provider is silently selected by this ADR.

## Retention, status and recovery targets

- Retain every raw object, required native repository snapshot, lock/policy and
  verification bundle referenced by a supported release or supported offline
  export. Keep at least 90 days after the last supported reference expires.
  Release wheels, sdists, SBOMs, provenance and admission records are retained
  for the supported release lifetime plus at least one year. Legal holds and
  redistribution limits override deletion/replication defaults explicitly.
- Unpromoted candidates expire after 14 days; ordinary job reports after 14
  days unless attached to an admission record. Security quarantine has restricted
  access and a 90-day investigation minimum, extended by a recorded hold.
  Derived caches may be evicted at any time through supported maintenance.
- An authenticated admission/status snapshot has a monotonic sequence,
  issued-at, expires-at, policy hash and denied identities/digests. Release
  admission requires a snapshot no older than 24 hours. Offline verification
  permits at most 30 days and reports the snapshot time; a stricter site policy
  wins. Reinstalling old media cannot lower the locally accepted sequence.
  Expiry evaluation requires a trusted host clock; detected clock rollback or
  inability to establish time fails admission. A status snapshot cannot predict
  revocations that happen after export.
- Required release vulnerability evidence must be no older than 24 hours;
  offline scans at most 30 days, explicitly labeled by database timestamp.
  Failure to obtain or validate a database is not a clean scan. An authorized
  exception records scope, expiry and reason; the package client cannot grant it.
- Promoted supported objects and release evidence require two failure-independent
  retained copies before the durable-availability claim. Completed promotion
  has an RPO of zero for those bytes; status/config/audit backups target an RPO
  of one hour. The initial enterprise recovery target is one working day.
  Quarterly restore drills must demonstrate those targets or record a reduced
  profile. Two buckets under one failing account are not independent recovery.
- Default qualification load is 32 simultaneous same-host installers for one
  object and 100 independent service clients, including cold and warm access.
  Operators may claim a higher capacity only with evidence. Record hardware,
  bandwidth, input size, p50/p95 latency, error rate and disk use. A proof archive
  is measured separately from a small CLI binary; no fabricated latency target
  substitutes for measurement.

GC computes reachability from supported locks, release admission bundles,
offline-export manifests and holds. It marks candidates, waits seven days,
rechecks references and then deletes through provider/client-supported APIs.
It never edits a live uv cache or deletes a lock held by an active installer.
Provider-generated cache keys and artifact names do not substitute for this
reference graph. GC must retain OCI indexes, all selected manifests/layers and
referenced signature/provenance objects together.

Monitor acquisition outcome class, logical artifact/platform/digest, policy
revision, cache/replica/origin source class, duration, byte count, lock wait,
quarantine count, status/DB age, remaining disk/quota, promotion/backup lag,
restore failures and publication state. Alert on any integrity failure,
unauthorized promotion attempt, missing supported object or stale release
status. Never log credentials, raw client stderr, signed URLs, response bodies
or private package names into public PR logs. Public diagnostics use logical
ids and stable failure codes; restricted audit holds the authorized detail.

## Operator procedures

### Outage, rate limit or removal

Classify the failure through the maintained client's exit status. Required
work fails after its bounded budget; preserve safe diagnostics. Public clients
may use an approved same-digest replica/origin in the defined order. Enterprise
mirror-only clients stop. Confirm the retained object and restore its original
bytes to an approved provider if necessary; verify the restored digest before
enabling readers. Repository relocation changes locators through review without
changing the digest. If all retained copies and upstream bytes are lost, mark
that profile unavailable and make a new reviewed input selection. Never bless
new bytes under the old digest/version or disable the dependent gate.

### Integrity incident or revocation

Stop consumption/promotion of the affected identity. Security records the
denial and publishes a higher-sequence status snapshot; Platform blocks the
namespace/object and preserves restricted evidence. Enumerate affected locks,
releases, runner seeds and exported bundles. Online clients recheck status;
disconnected sites receive the signed update through their authorized media
process. Until imported, they have only their documented freshness window,
not immediate revocation awareness. Rotate compromised credentials/keys through
their owners, invalidate derived installations, and require fresh admission
before restoring use. Preserve historical release provenance.

### Offline export and import

1. Choose exact source SHA, target OS/architecture/interpreter, profile and
   lock/policy revision. Compute the full closure: raw tools and executable
   tree manifests, Python wheelhouse and build dependencies, interpreter/uv
   bootstrap, OS package metadata/packages or signed base image, proof archive
   and native prerequisites, OCI graph, source history, trust roots, dated
   status/vulnerability data and notices. Live GitHub/OSV/Ground Control service
   calls are explicitly outside the exported capability.
2. Produce a credential-free export index listing each relative path, size,
   digest, artifact identity, platform and policy reference. Include signature/
   attestation verification material and its accepted producer identity. Sign
   the index using the approved export authority; its bytes/digest are retained.
3. Verify the export on the connected side, transfer by the site's approved
   media process, then verify again before importing into quarantined local
   stores. Reject duplicates, traversal, absolute paths, symlinks, malformed
   indexes, wrong platform, missing references, revoked artifacts, expired
   status or a lower accepted sequence. Review redistribution eligibility
   before any public export; secrets are never a bootstrap dependency.
4. Import through maintained Python/native/OCI/provider interfaces. Digest-
   preserving OCI copy must include the selected platform graph; do not retag
   content and assume the reviewed multiarch digest survived. Run a complete
   preflight with egress denied and empty client caches, then the selected core
   verification graph. A cache-only successful rerun is not import qualification.
5. Retain the export/import receipts and checks. Public publication and live
   freshness checks resume only in an authorized connected context. Local
   reports list every unevaluated live check without claiming the full hosted
   pipeline passed.

### Disaster recovery and release recovery

Restore storage/configuration to a new empty instance, verify trust/status
sequence and retained object digests, reconstruct supported indexes with
maintained tools, and rerun admission before opening read traffic. Test the
loss of both application metadata and derived caches. Do not restore expired
promotion credentials from a backup; provision scoped replacements.

If a publisher's result is uncertain, query the destination with the maintained
client and compare release identity and content. If PyPI succeeded, repair
GitHub using the same admission bundle. If bytes are missing after Actions
retention, restore that bundle; do not rebuild and call the outputs identical.
A mismatched same-version object requires incident handling and a reviewed new
release. Rollback changes the client/profile or promoted pointer to an earlier
still-admissible immutable object; revocation cannot be rolled back by selecting
an older snapshot. Reverting an installer change never restores custom HTTP
code, existence-only cache trust or skipped required tests.

## Qualification and acceptance cases

Every case records implementation commit, exact tools/OS/provider, input
lock/policy hashes, context, command or harness, result and evidence location.
The migration table assigns owners. These are executable test requirements for
future implementation, not tests claimed to have passed in the design change.

| Test | Context / stimulus | Required result |
|---|---|---|
| T01 | Fresh public Linux x86_64 runner, empty caches, no enterprise credentials | Bootstrap through trusted native/setup clients; exact locked inputs; full required core/proof checks |
| T02 | Public local Linux arm64, macOS x86_64 and arm64 | All four CLI tools execute with matching raw/installed hashes; supported Python wheel/ABI closure works; native Isabelle unsupported diagnosis is explicit |
| T03 | CPython 3.11–3.14 clean build and install, all declared extras and target ABI | Frozen project/tool closure, hashed isolated build closure, wheel and sdist smokes outside checkout. Preview interpreters do not satisfy release support |
| T04 | Fork PR changes tool URL, lock, action or arbitrary install hook and runs malicious code | No private mirror credential, trusted cache write, promotion capability or publication token available; privileged jobs never execute candidate policy/scripts |
| T05 | 32 processes install same cold CLI/proof object; kill publisher at each durable step | Complete matching installed tree or explicit failure; no partial executable, shared temp collision, stale-marker success or stuck lock; a survivor can finish |
| T06 | Two users/jobs, hostile symlinks, modified binary, replaced inode, archive traversal/hardlinks/bomb | Reject before execution; preserve OSV protections for all clients; one user cannot populate another's trusted installation |
| T07 | 100 service clients, cold/warm inputs, quota exhaustion and disk full | Measure load envelope; bounded waits/failures, no corruption; admission/promotion atomicity and job-private environments remain intact |
| T08 | Native-client fixture: 429/503, disconnect, TLS rejection, HTTPS redirect, slow/oversize body | Qualified commodity retry/limit behavior; total process budget enforced; no insecure downgrade, secret-bearing log or repository protocol handling |
| T09 | Upstream outage/removal/relocation; approved replica available, then all copies absent | Same-digest recovery only; explicit hard failure when closure missing; lock unchanged by acquisition |
| T10 | Authenticated enterprise Simple API/generic/OCI endpoints; missing auth and cross-origin redirect | Mirror-only mapping, namespace/CA policy; no public fallback or credential propagation; wrong digest and 401/403 terminal |
| T11 | Export/import into clean air-gapped Linux x86_64 machine with empty caches and egress blocked | Bootstrap, core tests, docs, frozen builds and proof succeed from complete closure; all live checks reported not evaluated |
| T12 | Offline macOS/arm64 tool profile and Linux arm64 Python profile | Exact tools/interpreters work from target-specific export; unavailable proof/daemon capabilities cannot be relabeled successful |
| T13 | Missing wheel/build dependency/font/interpreter/OCI layer; corrupt, wrong-platform or malicious export | Preflight identifies missing logical objects and fails without network attempts or executing imported content |
| T14 | Stale/replayed status or vulnerability snapshot; revoked digest; signing key rotation | Reject expired/rolled-back/denied content; validate approved new trust root; dated offline evidence cannot claim current online status |
| T15 | Restore from independent backup after cache and primary repository loss | Complete supported lock closure, status monotonicity and release evidence recover within recorded RPO/RTO; repeat readback hashes |
| T16 | GC during reads/install/promotion; retained image has a referrer and supported offline export | No referenced object/evidence deleted; stale unreferenced data collected only after grace; provider-native maintenance used |
| T17 | OCI multiarch mirror/import and required release run; daemon absent, zero tests or skips | Index/platform/config/layer digests unchanged; required failures remain failures; simultaneous runs have unique resource names |
| T18 | Source SHA moved, tag retargeted, wrong run/attempt or artifact replaced after approval | Protected publisher freshly rejects stale identity, producer or subject digest; #1110/#1125 remain mandatory |
| T19 | Missing/extra wheel/sdist/SBOM, wrong SBOM subject, missing attestation or foreign signer | Artifact admission fails before any publisher obtains usable output; source and build/runtime inventory distinctions preserved |
| T20 | PyPI succeeds, GitHub fails; ambiguous success; Actions artifact expires | Compare destination and retained admitted bytes; recover only pending destination; no overwrite, tag move or rebuild under same version |
| T21 | ATT&CK/ATLAS/NIST/W3C ActivityStreams/FIPA refresh and live-runner bootstrap | Same source-specific raw and canonical snapshot identities, no custom network code; verified VM/native/uv closure, no pipe-to-shell or ignored acquisition failure |
| T22 | Full tracked acquisition/configuration scan after migration | Every inventory row owned and dispositioned; no development acquisition imports or calls a repository HTTP implementation; no mutable/unreviewed install bypass |
| T23 | A tool's version/digest/platform mapping changes in one entry point but not its authority | Deterministic policy failure across Nox, hooks, workflows, docs/bootstrap and release; failed coverage of a new path blocks qualification |
| T24 | Current protected release from admitted inputs with configured external controls | Wheel/sdist consumption from PyPI and GitHub works, corpus/CLI/conformance smoke passes, SBOM/provenance resolve, evidence retained; docs-only promotion creates no release |

### Issue #1216 policy-gate evidence

T22 and T23 are implemented as deterministic, offline policy coverage for this
issue. They do not claim that the downstream acquisition migrations in
issues #1137 and #1217–#1228 have landed.

- T22: `tools/check_tooling_artifact_policy.py` validates the six closed schemas
  and policy records under `implementations/tooling/`, requires exactly one
  disposition for every I01–I16, A01–A07, O01–O04, C01–C04, S01–S02 and D01
  inventory row, checks every tracked workflow action against its exact commit,
  rejects an unowned acquisition path or unknown dynamic executable, and checks
  the discovered site count for already covered paths. Runtime lock-selection
  calls are discovered across all tracked Python files and must exactly equal
  the declared consumer mapping. The acquisition-path dispositions identify the
  owning native client or downstream remediation issue.
- T23: `implementations/python/tests/test_tooling_artifact_policy.py` changes
  version, digest, canonical platform identity, selector bindings, workflow
  action references and acquisition paths independently. Each drift case must
  fail before the governed cache or network function is reached. The same gate
  is the first repository-policy stage and is called directly by each current
  generic-tool and vocabulary acquisition entry point.

Native client failure tests may use a controlled test server or a commodity
fault-injection proxy. Test fixture protocol handling is not a production
acquisition implementation. Maintain a few meaningful end-to-end cases against
the actual clients; mocks of argv alone cannot prove the profile's behavior.
