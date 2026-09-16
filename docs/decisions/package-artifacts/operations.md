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
| T02 | Public local Linux arm64 and macOS arm64 | All four CLI tools execute with matching raw/installed hashes; supported Python wheel/ABI closure works; native Isabelle unsupported diagnosis is explicit |
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

### Verified local CLI installation qualification

Issue #1219 implements the local generic-CLI slices of T05, T06, T07 and T16
for Conftest, Gitleaks, Vale and OSV-Scanner. All four wrappers use
`tools/verified_tool_installation.py`; raw acquisition remains owned by the
maintained client. The installed-tree key binds artifact, canonical platform,
raw SHA-256, `install-v1`, active policy references and the canonical installed
manifest. Version-keyed files are migration inputs only.

The implementation uses a native `filelock` lock from the frozen tooling
closure, private same-filesystem staging, full opened-inode verification,
immutable file/tree modes, file and directory fsync, and atomic directory
rename. Invalid current or legacy content is quarantined without reacquisition.
Immutable seeds are explicit read-only inputs copied into a private job tree.
NFS, SMB, FUSE and unknown filesystem semantics are rejected.

Run the local evidence harness through the existing integration suite:

```console
RAES_REQUIREMENT_UID= uv run --project implementations/python --frozen \
  python -m pytest -q -m integration \
  implementations/python/tests/test_issue_1219_verified_tool_installation.py
```

The harness emits the exact OS, Python, filesystem, lock-library and install-
policy identities plus elapsed case results. It runs 32 cold processes, 100
warm local clients, kills a publisher at every durable checkpoint, verifies
live-publisher exclusion and dead-owner recovery, and injects disk exhaustion.
The adjacent unit cases cover archive traversal, links, special files,
duplicates, bombs, cache/seed tampering, hardlinks, private-root modes and
legacy quarantine.

The existing bootstrap qualification matrix runs the mechanism-level harness
through `nox -s local-installation-qualification` on every supported Linux and
macOS host profile. It binds each measured slice into the canonical bootstrap
qualification record as a `slice_results` entry with its harness digest.
Slices are never projected into canonical passed T05/T06/T07/T16 records. A
legacy version-keyed cache that is group-writable only within a user-private
group is a valid migration carrier; any other principal's write access remains
terminal.
Those cases also cover distinct OS principals, proof, repository services, OCI,
export and program-wide GC and remain assigned to their downstream migration
owners until complete case harnesses exist. A multi-user deployment must use an
immutable root-owned seed and private job trees; it must not turn this local
installed tree into a shared writable cache.

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

Issue #839 extends T04/T23 through the same gate. Tests independently change an
action source, transitive payload/capability/service disposition, literal
use-site input, origin, credential class, permission, runner, protected manual
path, cache role, reusable-workflow contract, and Dependabot target/group. The
v2 policy also treats action-referenced locked payloads as runtime selection
consumers. T08 continues to use the maintained real-curl fixture below; T10
continues to describe maintained-client enterprise evidence and is not claimed
by the action policy's bounded service exceptions.

Native client failure tests may use a controlled test server or a commodity
fault-injection proxy. Test fixture protocol handling is not a production
acquisition implementation. Maintain a few meaningful end-to-end cases against
the actual clients; mocks of argv alone cannot prove the profile's behavior.

### Issue #1226 output-bound release evidence

`.github/workflows/release-please.yml` generates, signs, admits and retains the
release evidence. `tools/release_evidence.py` is the entry point;
`release_evidence_sbom.py` reconciles the runtime closure,
`release_evidence_documents.py` renders the documents,
`release_evidence_verifier.py` bounds the maintained verifier, and
`release_evidence_admission.py` decides admission.

Exact identities: CycloneDX 1.6 documents and the `raes-build-inventory/v1` and
`raes-release-evidence/v1` records; `actions/attest-build-provenance`
`4d101475d8b20a2381f78447822ac1eab6504dd8` (v4.2.2) over
`actions/attest` `508db95dd578ae2727ebd6217d5ba78e4fbda05d`; verification through
`gh attestation verify` pinned to the producer identity in
`implementations/tooling/admission-policy.json`; closure profile
`public-linux-x86_64-cp312-all-extras` on `public-ubuntu-24.04-x86_64`.
Evidence binds the `tooling_policy_sha256` aggregate alongside separately named
raw project-lock, tool-lock and build-constraint digests.

- **T03**: `test_issue_1226_runtime_closure.py` drives the declared CPython
  3.11-3.14 / ABI / extras qualification of the reconciliation. The base closure
  is resolved independently of extras, `dev` and `docs` components are labelled
  rather than recorded as unconditional runtime, and inconsistent metadata fails
  instead of omitting an edge. `test_issue_1226_target_markers.py` binds each
  reviewed target's full marker environment, so a cross-OS or patch-sensitive
  projection no longer inherits the generator host.
- **T04**: `test_issue_1226_release_evidence_cli.py` and
  `test_release_workflows.py` prove the credential isolation at the real
  boundary rather than by reading workflow YAML shape. The approved producer set
  comes from reviewed policy, so a foreign signer cannot approve itself; the
  build job holds no OIDC, attestation, promotion or publishing authority; and
  the signer holds no publication identity and checks out nothing.
- **T19**: `test_issue_1226_release_admission.py` covers missing, extra and
  replaced wheel, sdist or SBOM, an SBOM naming a foreign subject, a substituted
  input inventory, a sidecar swap, a run/attempt replay, a drifted policy hash,
  a missing attestation, a foreign producer, a valid signature from the wrong
  workflow, and malformed or oversized evidence. Each asserts a distinct stable
  failure class and that admission refuses before any publisher obtains usable
  output. `test_issue_1226_attestation_verifier.py` covers the verifier
  boundary: an empty, ambiguous, malformed or oversized verdict never becomes
  admission.

Retention: the SBOMs, build inventory and evidence index are attached to the
GitHub Release and digest-compared on readback, so they outlive the seven-day
Actions artifact retention. Retention owner: Release. The existing `--clobber`
on distribution attachment remains the recorded #1227 gap and is deliberately
not used for evidence. Durable admission-bundle storage (#1224), full publisher
admission and same-byte recovery (#1227) and operations qualification (#1228)
remain outside this issue.

This record describes implemented repository behavior. The release-time
execution of T03/T04/T19 against a real tagged release is observed when the next
release runs; the cases above execute in the repository verification graph.

### Issue #1217 bootstrap qualification evidence

The v2 profile authority and `bootstrap-qualification.yml` bind T01, T02, T03,
T08 and T12 to exact host, payload and policy identities. Checked-in records
distinguish `passed`, `failed`, `unsupported` and `not-run`; a profile is not
activated from a pending record. Pull-request qualification retains its bounded
evidence artifact under the exact delivery SHA.

- T01/T03: the blocking CI matrix selects the locked CPython 3.11.16, 3.12.14,
  3.13.15 and 3.14.7 payloads independently of the pinned setup-action commit,
  asserts the exact runtime feature line, installs the frozen closure, and runs
  clean wheel/sdist smokes. The proof-bearing Ubuntu 22.04 lane remains separate.
- T02/T12: the qualification matrix executes the existing lock-selected
  Conftest, Gitleaks, OSV-Scanner and Vale binaries on the four canonical Linux
  and macOS architectures. It exports the target-specific uv and installed-tool
  caches, restores them after deleting the working copies, repeats the frozen
  sync with uv's offline mode, and selects generic binaries through a
  digest-checking path that has no acquisition fallback. The payload kit also
  carries lock-verified raw CPython and uv objects, its own uv executable and a
  managed CPython installation; every restored entry is bound by the kit
  manifest. Linux arm64 and macOS arm64 record the clean target-specific restore
  as T12. Native packages and trust roots are explicit reviewed host
  prerequisites rather than falsely described as archive contents.
- T08: `test_issue_1217_bootstrap_profiles.py` runs the selected curl process
  against a controlled TLS fixture with 429/503 retries, disconnect, TLS
  rejection, HTTPS-only redirect, transfer deadline and unknown-length oversized
  responses. The production qualification argv disables curlrc,
  insecure/trusted redirect modes and outer retries and applies native
  retry/redirect/time/size bounds plus a subprocess wall deadline.
- Host policy and setup: `tools/bootstrap_profile.py` uses fixed argv, closed
  stdin, a minimal environment, sanitized reason codes and explicit native
  setup planning. It never invokes `sudo`, shell evaluation, repository/key installation,
  pipe-to-shell acquisition or host-security reconfiguration.

### Issue #1220 proof input evidence

Isabelle no longer contains repository HTTP transport, mirror loops, a shared
`.download` file, or marker-based trust. `tools/isabelle_tool.py acquire`
selects the reviewed lock entry before touching local state. It then admits the
exact archive through one of two carriers. The first is the qualified curl
client with the separately qualified `large-object` budget: exact size, a
3,600-second transfer bound, a native low-speed abort, curl's own bounded
retries, and a wall deadline that covers the retry window. The second is an
explicit `--local-input` copied from its opened inode. An alternate approved
same-byte mirror is an operator choice (`--locator-ref`) in a new invocation.

`tools/verified_tree_installation.py` extends #1219's transaction to a
multi-gigabyte tree. The lock's `installed_tree` binds the SHA-256 of the
canonical manifest of every file, directory and confined, canonically written relative symlink,
together with exact counts and expanded bytes. The steps are:

1. Admission streams the archive into private staging. It rejects hardlinks,
   devices, traversal, duplicates, and links that resolve through another link
   or outside the tree.
2. The private raw object is keyed by digest and reverified before extraction.
3. The tree is sealed read-only and then published by atomic rename, with Linux
   `sync(2)` durability. APFS cannot rename a read-only directory, so on macOS
   the root is sealed immediately after the rename. A seal that a crash
   interrupts is completed under the identity lock before full revalidation.
4. Every use reverifies the complete tree against the retained manifest.

Tampering quarantines the tree and fails; a later explicit invocation rebuilds
from the retained raw object without network access. On migration, a legacy
archive is verified as a carrier and the legacy tree and marker are quarantined.

The Ubuntu 22.04 proof host's native curl is below the qualified floor. The
qualified Ubuntu 24.04 job therefore fetches the archive, and the proof job
admits it under `bwrap --unshare-net`. The `nox -s proof-input-qualification`
session runs `issue_1220_proof_input_harness.py`. `bootstrap_profile
qualification-evidence --slice-evidence` binds each slice outcome to the exact
harness digest as a `slice_results` entry of the proof host's canonical
qualification record, beside T01. A slice names its canonical case, but no slice
is recorded as a passed case. `nox -s local-installation-qualification` records
the #1219 slices the same way. The slices are:

- T05: 32 cold processes, 100 warm verifiers, publisher kills at every raw and
  tree durability checkpoint, live-publisher exclusion, bounded lock timeout,
  and disk exhaustion. The optional `--real-archive` mode repeats the process
  and crash cases with the reviewed 1.2 GB object.
- T08: `test_issue_1220_isabelle_acquisition.py -m integration -k real_curl`
  exercises the large-object budget against the real curl fixture in bootstrap
  qualification: size, redirect, TLS, disconnect, native retry, low-speed abort,
  and transfer deadline.
- T11: egress-denied admission from a local input, plus `--real-installation`
  full-tree verification and preflight of the real proof closure. The egress
  oracle requires a distinct network namespace and a refused connection to a
  parent-owned loopback listener. A control run without `--unshare-net` must
  observe both conditions false.
- T13: corrupt, oversize, truncated and symlinked inputs and malicious archives
  fail with no network attempt and no execution. `isabelle_tool preflight`
  lists every missing Bubblewrap, fontconfig, font, C.UTF-8 locale, or
  installation prerequisite.

Proof hosts' offline kits must name the native Bubblewrap, fontconfig, font and
locale providers. The kit manifest binds them, and offline-kit verification
probes that closure. Complete disconnected export/import and whole-closure
preflight remain #1225 scope.

### Issue #1218 Python closure evidence

The frozen tooling project, generated build constraints, target-specific smoke
exports, raw wheel manifests, and closed Python closure profiles implement the
Python-owned slices of T03, T10, T11, T13, and T23. Evidence remains explicitly
scoped; it does not relabel generic, OCI, native, proof, or publication controls
as qualified.

- T03: the blocking CPython 3.11–3.14 matrix selects an exact closure profile.
  Compatibility and release lanes build a direct wheel and an sdist-built wheel
  with the same hash-complete Hatchling constraints, then install and exercise
  each distribution outside the checkout.
- T10: public, enterprise mirror-only, and offline contexts are closed profile
  records. Minimal environments discard ambient index, proxy, Python-path,
  virtual-environment, and credential state. Mirror-only selection accepts one
  credential-free HTTPS locator, prohibits public fallback, and reports bounded
  failure categories without response bodies or locator text.
- T11: bootstrap qualification exports target-specific raw wheels and exact
  manifests, verifies the whole restored wheelhouse before installation, keeps
  client caches disposable, and recreates tool and supported project
  environments with network and Python downloads disabled.
- T13: static and runtime checks reject stale generated projections, missing or
  unexpected files, symlinks, non-regular entries, size drift, and SHA-256 drift
  before a package or candidate is installed.
- T23: the canonical tooling-policy gate cross-checks exact direct pins,
  transitive locks, the preserved Z3 pin, build constraints, profile tuples,
  extras/groups, manifest bindings, tracked invocation surfaces, and generated
  projection bytes before acquisition.

Neither the project closure nor the tool closure includes macOS x86_64. The
patched cryptography releases have no macOS x86_64 or universal wheel and there
is no reviewed source fallback, so the macOS x86_64 bootstrap profile was
retired rather than kept on a vulnerable pin (#1268).
Input locks improve repeatability but do not prove byte-identical distributions
across host SDKs, compilers, operating systems, or build times; candidate output
digests are evidence, not release admission.

### Issue #1222 live-runner input closure evidence

Issue #1222 brings the `tools/real-daemon/` AWS smoke and guest-certification
setup (inventory row I13) under the admitted closure. The CirrOS guest disk is
pinned in `artifacts.lock.json` as a `vm-base-image` artifact (reviewed digest,
exact size, source, `official-cirros-download` locator) and selected through the
tooling policy gate by `tools/real-daemon/live_runner_inputs.py`; `uv` is
selected as the host profile's bootstrap payload and verified against the lock;
`libvirt-python` and its build backend (setuptools/wheel) are pinned by exact
version and hash in `tools/real-daemon/live-runner-python.txt` and the reviewed
`tools/real-daemon/live-runner-python-closure.json` manifest, staged as a
verified wheelhouse, and installed **fully offline**
(`--offline --no-index --find-links <wheelhouse> --require-hashes`) so no
distribution or build dependency is resolved from a live index during
certification. The live-runner inputs are execution-bound to their reviewed
authorities: the base image is Canonical's exact published image **name (serial)**
(`tools/tool_versions.py`), resolved to the region's AMI id by owner + exact name
(never "newest"); the native package set installs from an immutable
`snapshot.ubuntu.com` archive timestamp (reproducible versions), with the
`live-runner-ubuntu-24.04-x86_64` host profile as the reviewed authority for the
package set and snapshot; and the declared **cpython-3.14** interpreter is
pre-seeded, validated and used for `uv sync` rather than the ambient system
python. libvirt/QEMU are required while KVM is optional (the runners use TCG
`domain type="qemu"`). The scripts pre-seed and re-verify the transferred bytes,
run under the host's default security driver (no `security_driver="none"`, no
root QEMU user/group), use per-run scoped private directories under the libvirt
images tree, require an explicit reviewed SSH ingress CIDR, pin the instance host
key from the authenticated AWS console output before first contact
(`StrictHostKeyChecking=yes`), transfer only Git-tracked revision-bound source,
and invoke the guest-certified evidence run with a fixed argument vector (pulling
its evidence back before teardown even on failure).

The in-repository slices of the acceptance cases are implemented as the hermetic
`implementations/python/tests/test_issue_1222_live_runner_acquisition.py`:

- **T13**: tampered guest-disk bytes fail admission before boot; an unpinned
  `libvirt-python` requirement is rejected; the reviewed CirrOS digest/size is
  the only admitted identity; the full valid acquisition path is exercised. The
  full missing-native/interpreter/VM and wrong-ABI rejection against a real host
  is an operator obligation, not covered by a Python-only wheelhouse test.
- **T21**: both runner scripts carry no pipe-to-shell bootstrap, no ignored
  download, no ad-hoc curl acquisition, no host-security downgrade and no unsafe
  `RUN_ID` interpolation; uv sync is frozen; the libvirt-python closure is
  installed offline (`--offline --no-index --find-links --require-hashes`); the
  first SSH connection is host-key-verified (`StrictHostKeyChecking=yes`); and
  the apt package set is a subset of the reviewed host profile. The full
  governed-closure boot of both runner paths is operator-run.
- **T07**: per-run unique AWS key/security-group/instance names and scoped run
  directories remove the fixed-resource collisions; cleanup acts only on
  owned resources. The measured cold/warm concurrency, quota-exhaustion and
  disk-full envelope (service target 100 clients, 32 same-host installers) is
  operator-run on the live host and recorded against the pending
  `live-runner-ubuntu-24.04-x86_64-issue-1222-pending` qualification record.

Scope and honesty limits: the CirrOS checksum is an upstream-published integrity
value cross-checked against the release `MD5SUMS` (recorded as `absent-reviewed`
authenticity, not an authenticated publisher signature). `libvirt-python` is
sdist-only; the sdist and its setuptools/wheel build backend are hash-pinned and
installed offline from the pre-seeded wheelhouse, so no build dependency is
resolved from a live index. The native package set installs from an immutable
`snapshot.ubuntu.com` archive timestamp, so package versions are reproducible;
this is the live-runner's own reproducible native closure and does not implement
the broader offline export/import bundle (#1225). AWS provisioning/API behaviour
remains a live external service; local preseed verification can run disconnected,
but no air-gapped-AWS capability is claimed. The reviewed image serial and
snapshot timestamp are advanced by a reviewed edit to `tools/tool_versions.py`.
The live T07/T13/T21 result is `not-run` until an operator records it under the
exact delivery revision.

### Issue #1221 vocabulary source evidence

The opt-in `--verify-remote` acquisition in the five vocabulary source checkers
(`tools/check_attack_tactic_vocabulary.py`,
`tools/check_atlas_tactic_vocabulary.py`,
`tools/check_nist_csf_defensive_vocabulary.py`, and both sources in
`tools/check_autonomous_behavior_vocabularies.py`) is migrated off `urllib` onto
`tools.maintained_client_acquisition.acquire_locked_bytes()`. Each checker
selects its snapshot through `load_tooling_artifact_selection()`
(`profile_id="source-snapshot"`), verifies the pinned HTTPS host/URL, then
admits either freshly transferred bytes or an approved local raw object against
the reviewed `artifacts.lock.json` raw identity before any source-specific
parsing. Raw-byte identity/size (the lock `raw_manifest`) stays distinct from the
source-specific semantic `source_digest`. No checker retains custom transport,
retry, redirect, TLS or framing code. Evidence: implementation commit; tool
`/usr/bin/curl` (>= 8.4.0) invoked only through the shared hardened argv; policy
`source-snapshot-integrity-v1`; input lock `implementations/tooling/artifacts.lock.json`.

- T09 (upstream outage/relocation, approved replica, then all copies absent):
  the `--local-input` / `--activitystreams-local-input` / `--fipa-local-input`
  arguments admit an approved local raw object by the same locked raw identity;
  a missing, corrupt, or mismatched local object is a terminal hard failure with
  no network fallback, and acquisition never rewrites the lock. Recovery is
  same-digest only.
- T11 (air-gapped export/import): the default offline checks
  (source-metadata and catalog validation against the checked-in
  `contracts/concept-authority/*` snapshots) succeed with egress blocked;
  `--verify-remote` is not part of the default Nox policy lanes, so the live
  comparison is reported not evaluated rather than claimed.
- T13 (missing/corrupt/wrong-platform input): selection and lock validation run
  before transport; local-object admission rejects symlinks, non-regular files,
  size drift, and SHA-256 drift without a network attempt and without executing
  imported content.
- T21 (ATT&CK/ATLAS/NIST/W3C ActivityStreams/FIPA refresh): each source keeps
  its exact raw and canonical snapshot identities, acquires only through the
  qualified maintained client, and surfaces an acquisition failure rather than
  ignoring it; no custom network code remains. Verified offline by
  `implementations/python/tests/test_issue_1221_vocabulary_maintained_client_acquisition.py`
  and the existing per-source offline checkers; the tracked-scan disposition is
  recorded under T22 by dropping the four now-transport-free checkers from the
  `acquisition_paths` inventory while their lock-selection consumer bindings
  remain.
