# Fixture provenance audit

Issue #1344 asks which test fixtures assert shapes the real system never
produces. This record answers it for this repository on `dev` at `35122105`
(2026-10-09). For every boundary where a test stands in for something the
repository does not control, it records whether the fixture's shape was captured
or inferred. It checks the shapes that matter against the real producer and
lists every divergence found, with its status. It is research evidence, not
contract authority.

- [`inventory.md`](inventory.md) lists each boundary with its provenance, the
  real observation, a verdict and a blast-radius rating.
- [`captures.md`](captures.md) holds the observed responses.
- [Boundary fixture provenance](../../explain/reference/fixture-provenance.md)
  is the convention for new boundary fixtures.

Issue #1344 is labelled `cross-repo`. This audit covers only this repository.
External producers from sibling repositories (LilRAE's APTL backend) appear only
where this repository consumes their output.

## Method

1. Inventory. Fakes, stubs, monkeypatched callables, hand-built payloads and
   corpus files under `implementations/python/tests/` and `contracts/fixtures/`
   were grouped into ten boundary classes: GitHub platform, libvirt API, guest
   appliance, network services and supply chain, subprocess tools, the SQLite
   store and Ground Control client, MCP and filesystem and time, backend
   manifests, runtime snapshots, and release and experiment evidence.
2. Provenance. Each fixture was traced to the production consumer that relies
   on it and labelled `captured`, `inferred`, `synthetic` or `real`. No GitHub
   fixture records where its shape came from, and no libvirt or guest fixture
   points to a captured response.
3. Observation. The audit drove the real producer in the state the consumer
   handles and recorded what came back:
   - read-only GitHub REST and `gh` 2.101.0 calls against `OpenRAE/rae`;
   - libvirt 12.7.0 `test:///default` with production-rendered XML;
   - boots of the production-built guest appliance under `qemu-system-x86_64`;
   - the pinned tool binaries (conftest 0.68.0, gitleaks 8.30.1, osv-scanner
     2.4.0, vale) and Docker 29.7.2;
   - SQLite 3.50.4 under CPython 3.14.4;
   - local servers that fail the way networks fail;
   - LilRAE at `a5833df9`, read only, for its manifest, snapshot and evidence
     shapes.
4. Check the check. For the libvirt fakes and the store lease, production
   already handled the real shape, so the audit disabled the branch that handles
   it and reran the suite. A suite that stays green under that change has fakes
   that never reach reality.

Limits:

- Most probes ran on macOS arm64. curl was also checked in an Ubuntu 24.04
  container.
- No live `qemu:///system` daemon was available.
- GitHub was read, never written. Transferred-issue redirects and `open` release
  assets could not be produced.
- Fixture counts were not recorded for the subprocess, SQLite store, MCP and
  runtime-snapshot classes; the inventory lists their boundaries instead.
- Probes for store migration across releases and request-commitment drift
  recorded no verdict.

## Results

| Class | Fixtures examined | Diverges | Unverified |
|---|---|---|---|
| GitHub platform and workflow runtime | 67 | 7 | 3 |
| libvirt Python API | 98 fake definitions (16 surfaces) | 4 | 1 |
| Guest appliance | 31 | 4 | 2 |
| Network services and supply chain | 171, plus 82 lock values | 8 | 2 |
| Subprocesses and command-line tools | not recorded (12 boundaries) | 2 | 1 |
| SQLite store and Ground Control client | not recorded (7 boundaries) | 4 | 1 |
| MCP, filesystem, time and internal stand-ins | not recorded (7 boundaries) | 3 | 0 |
| Backend manifests and realization envelopes | 52 | 3 | 1 |
| Runtime snapshots and control-plane payloads | not recorded (5 boundaries) | 3 | 0 |
| Release, conformance and experiment evidence | 29 | 1, plus NS-3 | 0 |

Most boundaries match. The divergences cluster where a field or behaviour is
conditional: an empty value that arrives as `null`, a count that can exceed one,
a re-run that mixes attempt numbers, an error that exits 1 with nothing on
stdout, a timestamp that loses its fraction on a whole second, or a
lifecycle precondition a dictionary fake cannot express.

## Divergence register

Each entry gives the fixture, the shape it asserts, what the real producer
returned, the production code that relies on the fixture's shape, the
recommended fix and the status. "Open" means no change in this repository fixes
it yet. The pull requests cited below were open, unmerged, when this record was
written.

### Addressed by open pull requests

- **LV-2: libvirt missing objects raise `KeyError` in the TechVault fakes.**
  Blast M. Fixtures: `T/test_libvirt_backend_techvault_native.py:105-109` and the
  same fakes in `T/test_libvirt_backend_guest_certified.py` and
  `T/test_libvirt_evidence_run.py`. Real: `libvirt.libvirtError` code 42 or 43.
  Production handles code 42/43 (`_techvault_native_ops.py:57`,
  `techvault_lifecycle.py:84`), but no hermetic test reached those branches:
  disabling either left all 128 tests in the three modules passing. Fix: the
  fakes raise the captured codes. Status: #1453 (test only).
- **LV-3: `XMLDesc` echoes the defined XML.** Blast M. Same fixtures. Real:
  memory reads back as `<memory unit='KiB'>131072</memory>` with
  `currentMemory`. Production converts KiB correctly
  (`techvault_observation.py:196`), but no test fed it KiB. Fix: the fakes derive
  their readback from the capture, and a test runs the production readers and
  concern gate on the captured XML. Status: #1453 (test only).
- **CL-1: conftest error output read as "no failures".** Blast H (policy gate).
  Fixture: `T/test_repo_policy_tools.py:1288-1316` models only failure output.
  Real: conftest 0.68.0 exits 1 with an empty stdout when it cannot load or
  evaluate the policy. Production: `tools/policy/conftest_tool.py:86-91` returned
  `[]` for an empty stdout. Fix: raise the existing evaluation error. Status:
  #1455, issue #1454.
- **ST-1: the runtime-owner lease fork test cannot see the non-owner unlock
  guards.** Blast H (single-owner store). Fixture:
  `test_runtime_owner_lease_rejects_and_closes_in_a_different_process_identity`
  patches `os.getpid` in one process. Real: after `fork()` a child that unlocks
  its inherited descriptors releases the parent's `flock`. Production guards are
  correct (`control_plane_store_lease.py:217-231`, `:113-120`), but removing
  either still passes the test. Fix: a test that holds duplicates of the lease
  descriptors and probes both locks. Status: #1459 (test only).
- **TM-1: compensation order sorts timestamps as strings.** Blast H. Fixtures:
  the compensation tests in `T/test_runtime_control_plane_api.py` have one
  compensable step, so none observes the order. Real: RAES
  (`control_plane_execution.py:39-40`) and the LilRAE workflow engine format
  instants with `isoformat()`, which drops the fraction on a whole second, so
  `...:01.001000Z` sorts before `...:01Z`. Production:
  `control_plane_workflows.py:52` sorted the text, against the reverse-completion
  rule in `specs/formal/workflows/compensation.md`. Fix: sort parsed instants.
  Status: #1464, issue #1462.
- **GH-3: `gh release upload` in a job without a checkout.** Blast H. Already
  tracked as #1414. Status: #1415.

### Open: production change needed

- **GH-1: an empty PR description is `null`.** Blast L. Fixtures:
  `T/test_pr_body_guard.py:633`, `T/test_pr_body_policy_migration.py:61` use
  `""`. Production: `tools/check_pr_body.py:467-469` raises a configuration error
  (exit 2) for `null` before the automation exemption runs. Fix: treat `null` as
  an empty body and evaluate the exemption first. The validator file is
  byte-pinned by the #1284 policy migration (`pr-body-policy.yml` and
  `T/test_pr_body_policy_migration.py`), so the fix also moves that pin.
- **GH-2: GitHub ignores closing keywords in PRs that target `dev`.** Blast M.
  Fixture comment: `T/test_pr_body_guard.py:295-296`. Real: PR #1413 says
  `Closes #1361` and has `closingIssuesReferences: []`. Production:
  `tools/check_pr_body.py:164-187` describes its pattern as "the closing
  references GitHub reads". Keywords in squashed commit messages do act once
  `dev` reaches `main`, and nothing checks them. Fix: check commit messages for
  closing references in `tools/check_pr_title.py`, which already receives them,
  and correct the docstring.
- **GH-4: more than one verified attestation per artifact.** Blast H. Fixture:
  `T/test_issue_1226_attestation_verifier.py:99-103`. Real: gh 2.101.0 prints one
  entry per verified attestation, and re-attesting byte-reproducible builds adds
  entries with the same identity. Production:
  `tools/release_evidence_verifier.py:107-111` refuses any list longer than one
  (`verifier-ambiguous-attestation`), so a re-run or repair of an attested tag
  can never be admitted. Fix: refuse only distinct identities.
- **GH-5: a partial re-run mixes attempt numbers.** Blast M. Fixture:
  `T/test_issue_1226_release_admission.py:283-287` treats another attempt as a
  replay. Real: run 36342459179. Production:
  `tools/release_evidence_admission.py:398-408` requires exact attempt equality,
  so "re-run failed jobs" after a transient admission failure cannot pass. Fix:
  keep `run_id` strict and accept `1 <= index attempt <= GITHUB_RUN_ATTEMPT`.
- **GH-7: `run_started_at` resets on re-run.** Blast L. Fixture:
  `T/test_ci_latency_report.py:12-123`. Production:
  `tools/ci_latency_report.py:129-137` reports the re-run delay as queue time.
  Fix: record the attempt and measure attempt 1 separately.
- **LV-1: the generic driver identifies native objects by name only.** Blast H.
  Fixture: `T/test_libvirt_backend_driver.py:111-125` stores objects in a
  name-keyed dictionary that accepts any UUID. Real: a name or UUID collision
  raises code 9, so a RAES-owned object can live under another name (after a
  `name_prefix` change, a provider-name change or a rename). Production:
  `deployment.py:428-430` and `:464-490` treat a name miss as absence; destroy
  then reports the object removed while it keeps running. Fix: fall back to
  `lookupByUUIDString` and `networkLookupByUUIDString` on the owned UUID, and
  make the fakes raise code 9 on collisions.
- **GU-1: the guest reports far less memory than the domain has.** Blast H.
  Fixtures: `T/test_libvirt_backend_guest_certified.py:115` (120), `:490`, `:683`.
  Real: `memory_mib 81` from `MemTotal` at 128 MiB; the committed July evidence
  says 78. Production: `guest_observation.py:65` and `:245-246` accept 112-128,
  so a real guest fails certification. Fix: measure firmware "System RAM" in the
  probe and bump the probe policy, or derive the tolerance from measurements.
- **GU-2: the guest's account `disabled` report is constant.** Blast H.
  Fixtures: `T/test_libvirt_backend_guest_certified.py:183`, `:600`, `:608`.
  Real: every account reports `1`. Production: enabled accounts are written with
  `*` (`guest_appliance.py:178`) and the report treats `*` as disabled (`:246`);
  the SDL pipeline also sets `lock_passwd=True` for every account
  (`realization/_cloud_init.py:122`) and `techvault_matrix.py:132` maps that to
  `disabled`. Fix: report only `!` as disabled and carry the authored `disabled`
  separately from `lock_passwd`.
- **GU-3: cloud-init reads `user-data` as YAML.** Blast M. Fixture:
  `T/test_libvirt_backend_cloudinit.py:28-31` checks with `json.loads`. Real:
  PyYAML turns `json.dumps` surrogate pairs into lone surrogates, and
  cloud-init's UTF-8 write fails. Production: `cloudinit.py:120`. Fix: emit YAML
  `\U` escapes for astral-plane characters and use `yaml.safe_load` as the oracle.
- **TM-2: naive `requested_at` values pass admission.** Blast M, latent: only
  tests construct the admission today. Fixture: `T/test_runtime_fact_bindings.py`
  uses `Z` timestamps. Real: a value built with `datetime.isoformat()` from a
  naive datetime, or a date-only value, is admitted (`runtime_fact_dispatch.py:36`)
  and binding raises `TypeError` (`runtime_fact_binding_policy.py:119-124`). Fix:
  require an offset at admission.
- **NS-1: curl over HTTP/2 on macOS.** Blast M, macOS profile only. Fixture:
  `_CurlFixture` in `T/test_issue_1217_bootstrap_profiles.py:776-819` speaks
  HTTP/1.x only. Real: macOS curl 8.7.1 exits 56 for a size-limit breach and does
  not retry a 503 over HTTP/2. Production:
  `tools/maintained_client_acquisition.py:236-243` recognizes only 63, and
  `:146-151` relies on curl's retries. Fix: pass `--http1.1`, the protocol the
  qualification covers.
- **NS-2: OCI registries require a Bearer token.** Blast M. Fixture:
  `T/test_sdl_module_registry.py:96-170` serves every endpoint anonymously.
  Real: ghcr.io, Docker Hub and ECR Public answer 401 with a `Bearer` challenge,
  and blobs redirect with 307. Production: `raes/module_registry/__init__.py:156-186`
  treats the 401 as a fetch error. Fix: implement the anonymous token flow
  without forwarding the token to the redirect target.
- **NS-3: the sdist-built test wheel equals the wheel.** Blast M. Fixtures:
  `T/test_issue_1226_release_admission.py:70`, `:172` and
  `T/test_issue_1227_release_publication.py:64`, `:156` use distinct bytes and a
  2-subject inventory. Real: 3 subjects, and the derived wheel has the wheel's
  digest. Production: `tools/release_evidence_admission.py:314-320` passes only
  because the digests coincide. Fix: admit the derived subject against
  `test_subjects`, or make byte identity an explicit gate.
- **EV-1: LilRAE evidence records omit `capture_spec_ref.ref_version`.** Blast M.
  Fixtures: the 5 files under
  `contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/`.
  Real: the schema accepts LilRAE's record and
  `raes_contracts/evidence_satisfaction.py:98-107` rejects it. Fix: compare as
  `run_ref` already does, or require the version in the schema and in LilRAE.
- **MF-1: processor and backend compatibility exists only in fixtures.** Blast M.
  Fixtures patch the pairing: `compatibility.backends` at
  `T/test_sce_002_trial_realization.py:67` and `T/test_runtime_contracts.py:81`,
  and the backend name at `T/test_runtime_contracts.py:91`. Real: the reference processor
  declares `["stub"]`, so every shipped non-stub backend is rejected by
  `trial_realization.py:224-228` and `trial_compiler/apparatus.py:389-401`. Fix:
  declare the certified pairings or document that trial realization is stub-only.
- **MF-2: the mixed-runtime check compares internal representations.** Blast M.
  Fixture: `T/test_issue_1016_mixed_runtime_coordination.py:278-291` builds the
  target through the same round trip the check uses. Real: the APTL manifest's
  authored OS order and list type differ from the round trip. Production:
  `mixed_runtime.py:212-214`. Fix: compare canonical contract forms.
- **RS-1, RS-2, RS-3: conformance and the SEM-222 test validate projections that
  differ from the published snapshot.** Blast M. Real, from one live control
  plane: the hermetic conformance payload omits `realization_envelope` and
  `realization_provenance`, which the `/snapshot` API publishes (RS-1); the
  public route drops the closure and mixed-composition state that the store
  serializer keeps, and the SEM-222 test reads the store serializer (RS-2); a
  `/snapshot` with participant behavior history, set up as in
  `T/test_runtime_control_plane.py`, fails semantic conformance because it has no
  `participant.behavior` entry, which the corpus supplies with an empty payload
  (RS-3). Fix: validate the payload the public producers emit, and build corpus
  snapshots from the real pipeline.
- **ST-4: Ground Control transport failures escape classification.** Blast M.
  Fixture: `T/test_requirement_governance.py` fakes `URLError` and `HTTPError`.
  Real: dropped connections, truncated bodies, HTML login pages and non-UTF-8
  bodies raise other exceptions. Production: `tools/policy/requirement_governance.py`
  maps only some failures to `GroundControlError`. Fix: classify transport and
  decoding errors as unavailable.
- **CL-2: git path listings without `-z`.** Blast M, latent (no non-ASCII path
  is tracked today). Real: git quotes such paths. Production: `_changed_paths`
  and `_tracked_repo_paths` in `tools/nox_support/runner.py` drop them, and
  `changed_paths` in `tools/policy/common.py` returns the quoted text. Fix: use
  `-z` listings.
- **TM-3: rejected MCP arguments echo the input value.** Blast L.
  `T/test_experiment_authoring.py:195-206` asserts no `input_value` in the
  rendered result, passing `spec_content` as a string. Real: an object argument
  gets the MCP framework's validation error with `input_value`. Fix: handle
  argument validation errors in the server.

### Open: smaller corrections

Blast L unless marked.

- **GH-6:** `T/test_issue_1226_release_evidence_cli.py:70` asserts
  `source_sha != workflow_sha`; real releases record the same SHA. Nothing in
  production depends on them differing. Fix: make the fixture values equal.
- **LV-4:** generic-driver fakes: `nwfilterDefineXML` as an unconditional upsert
  (also in the comment at `deployment.py:392-393`), `destroy()` succeeding on an
  inactive object (real: code 55), `undefine()` leaving the object findable, and
  `UUIDString()` returning `None`.
- **GU-4 (blast M):** the committed guest evidence artifact fails the current validator
  with 2 problems and no test loads it. Fix: recapture it or mark it historical.
- **NS-4:** the NIST CSF export is regenerated per request, so `--verify-remote`
  always fails. Fix: lock the canonical digest the checker already computes.
- **NS-5:** `tools/tooling_artifact_policy_oci.py:102-108` rejects repeated layer
  digests, which real manifests contain.
- **NS-6, NS-7, NS-8:** inert or harmless fixture drift in
  `T/test_oci_release_image.py:122-124`, `T/test_issue_1226_attestation_verifier.py:74-77`
  and the curl `000` stub in `T/test_release_workflows.py:1394-1411`.
- **MF-3:** 9 negative backend-manifest corpus files fail for incidental reasons
  as well as their named defect. Fix: derive each from the current valid stub
  with one mutation and assert the reason.
- **ST-2:** commit-failure fixtures raise `OSError` inside the transaction body;
  real commit failures raise `sqlite3` errors from `commit()`. Atomicity holds on
  real SQLite because the connection is closed after each operation.
- **ST-3:** severe corruption raises `sqlite3.DatabaseError` from
  `PRAGMA quick_check` instead of the store's integrity error; admission still
  refuses.

## What remains

- The open divergences above need production changes. GH-2, GH-4, GH-5, NS-3,
  MF-1, GU-1 and GU-2 also involve a release-admission or semantics choice that
  belongs to the maintainer.
- Unverified boundaries: transferred-issue redirects, `GITHUB_SHA` on
  `workflow_dispatch`, `open` release assets, libvirt code 62 for a missing
  nwfilter under current code, fact-file ownership under a live libvirtd,
  `genisoimage`, the AWS EC2 CLI JSON, lock digests for self-downloading actions,
  `check-jsonschema`, store migration across releases, and capture offers.
- Findings for sibling repositories are listed below. Filing them in those
  repositories is outside this change.

## Findings for sibling repositories

The failure class is not specific to this codebase. These observations apply
wherever LilRAE, env-packs, adapters or hub use the same platform, tool or
pattern:

- Every sibling's default branch is `main`, so closing keywords in PR bodies that
  target `dev` close nothing, while keywords in commit messages act on promotion.
- Workflow-run `pull_requests` lists open PRs only; a Phase E workflow triggered
  on `pull_request: closed` sees `[]`. LilRAE has the same Phase E workflow.
- `pull_request.body` can be `null`, and `run_started_at` resets on re-run.
- A `gh` call without `--repo` in a job without a checkout fails with
  `not a git repository`. `gh api` paths with `{owner}` or `{repo}` resolve
  through git too.
- Release attestations accumulate per digest; a verifier must not treat several
  attestations with one identity as ambiguous, nor bind to one run attempt across
  jobs (env-packs attests releases).
- libvirt reports missing objects as `libvirtError` codes 42, 43 and 62, treats
  name and UUID as separate identities, and returns normalized XML. A fake that
  classifies errors by type must register its error class as
  `sys.modules["libvirt"].libvirtError`.
- `http.server` fixtures speak HTTP/1.x only; macOS curl changes exit codes and
  retries over HTTP/2.
- Public OCI registries need the anonymous Bearer token flow.
- conftest exits 1 with an empty stdout on load and evaluation errors.
- `datetime.isoformat()` drops the fraction on a whole second, so timestamps from
  one producer must be compared as instants, not strings.
- Never build the "real" side of an equality check through the code under test.
