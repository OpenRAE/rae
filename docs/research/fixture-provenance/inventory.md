# Test-boundary inventory

This inventory lists every boundary class the #1344 audit examined. A boundary
is a place where a test fixture, fake, stub or hand-built payload stands in for
something this repository does not control. For each boundary it records where
the fixture's shape came from, what the real producer returned, and how much
damage a wrong shape could do. The audit ran on `dev` at `35122105`.
[`index.md`](index.md) explains the method and keeps the divergence register.
[`captures.md`](captures.md) holds the observed shapes.

Column meanings:

- **Provenance**: `captured` (copied from a real response), `inferred` (written
  from documentation, a sibling call, or what the code expects), `synthetic`
  (deliberately artificial and labelled as such), or `real` (the test drives
  the real producer). A qualifier narrows a label. `real, protocol-limited`
  and `real, ASCII-only` mean the test drives the real producer with only part
  of its inputs. `captured once` means one response was copied from a producer
  whose output changes between requests.
- **Verdict**: `match`, `match in effect` (the fake differs from the real shape
  only in a way the consumer already handles), `diverges`, `unverified` (no
  real response could be obtained), or `n/a` (nothing consumes the shape).
- **Blast**: `H` for a security control, an authorization or data-integrity
  path, or a rarely exercised automated path; `M` for a path that fails closed
  but blocks real work; `L` for a hot path that fails loudly.

Paths are relative to the repository root. `T/` is `implementations/python/tests/`
and `P/` is `implementations/python/packages/`.

## GitHub platform and workflow runtime

67 hand-built fixtures, `gh` stubs and assumed platform behaviors in 16 test
modules, plus about 25 `github.*` and default-environment reads across the 11
workflows. None of the fixtures records its source.

| Boundary | Consumer | Fixture | Provenance | Real observation | Verdict | Blast |
|---|---|---|---|---|---|---|
| `pull_request.body` on a PR without a description | `tools/check_pr_body.py:467-469` | `T/test_pr_body_guard.py:633`, `T/test_pr_body_policy_migration.py:61` | inferred | `"body": null` (REST, PR #25); webhook schema allows `["string","null"]` | diverges (GH-1) | L |
| PR author and head ref for the automation exemption | `tools/check_pr_body.py:190-200` | `T/test_pr_body_guard.py:524-541` | inferred | Dependabot head `dependabot/github_actions/dev/...`; release PRs target `main` | match | M |
| PR title and optional body for the title lint | `tools/check_pr_title.py:259-280` | `T/test_pr_title_guard.py:138-150`, `:271-288` | inferred | title is a string; body is a string or null and is handled | match | L |
| Issues REST read for the closing-route check | `tools/pr_body_issue_scope.py:69-101` | `T/test_pr_body_guard.py:199-217`, `:374-384`, `:561-588` | inferred | open issue without `pull_request`; PR-backed issue with `pull_request`; `"body": null` | match | M |
| Issues REST 301 for a transferred issue | `tools/pr_body_issue_scope.py:79-86` | none | none | no transferred issue available to capture | unverified | L |
| Closing keywords in PR bodies that target `dev` | `tools/check_pr_body.py:164-187`, `:296-314` | `T/test_pr_body_guard.py:228-317` | inferred | default branch is `main`; PR #1413 (base `dev`) says `Closes #1361` and has `closingIssuesReferences: []` | diverges (GH-2) | M |
| `gh api git/blobs --jq .content` | `.github/workflows/pr-body-policy.yml:47-58` | `T/test_pr_body_policy_migration.py:40-56` | inferred | base64 wrapped at 60 columns; decodes to the pinned digests | match | H |
| `gh api pulls/N/commits --jq` | `.github/workflows/pr-title-lint.yml:57-63` | `T/test_pr_title_guard.py:239-262` | inferred | raw multi-line text | match | L |
| `gh release view --json databaseId,isDraft,tagName` | `.github/workflows/release-please.yml` | `T/test_release_workflows.py:84-100` | inferred | `{"databaseId":401554295,"isDraft":true,"tagName":"v6.0.1"}` | match | H |
| `gh release view --json assets` | `.github/workflows/release-please.yml:1070-1080` | `T/test_release_workflows.py:186-193` | inferred | `.assets[].name` present; assets also carry `state` and `digest` | match | M |
| `gh release upload` without a checkout | `.github/workflows/release-please.yml:1104` | `T/test_release_workflows.py:202-215` | inferred | run 36967479436: `failed to run git: fatal: not a git repository` | diverges (GH-3) | H |
| Tag ref and annotated-tag dereference | `.github/workflows/release-please.yml:746-791` | `T/test_release_workflows.py:301-306`, `:801-835` | inferred | lightweight tag `type: commit`; annotated tag `type: tag`, then commit | match | H |
| PATCH `releases/{id}` response | `.github/workflows/release-please.yml:1156-1170` | `T/test_release_workflows.py:137` | inferred | `id` is a number and `draft` a boolean (GET) | match | M |
| release-please action outputs | `.github/workflows/release-please.yml:47-99` | `T/test_release_workflows.py:1238-1263` | inferred | `RELEASE_PLEASE_TAG: v6.0.1`, 40-hex SHA | match | H |
| `gh attestation verify --format json` identity fields | `tools/release_evidence_verifier.py:115-143` | `T/test_issue_1226_attestation_verifier.py:24-38` | inferred | same fields and values in the real v6.0.1 output | match | H |
| Number of verified attestations per artifact | `tools/release_evidence_verifier.py:107-111` | `T/test_issue_1226_attestation_verifier.py:99-103` | inferred | gh 2.101.0 returns every verified attestation for a digest | diverges (GH-4) | H |
| `GITHUB_RUN_ATTEMPT` across the jobs of one run | `tools/release_evidence_admission.py:398-408` | `T/test_issue_1226_release_admission.py:283-287` | inferred | run 36342459179: carried-over jobs started in attempt 1, re-run jobs in attempt 2 | diverges (GH-5) | M |
| `GITHUB_SHA` and `GITHUB_WORKFLOW_SHA` | pass-through, `tools/release_evidence.py:103-110` | `T/test_issue_1226_release_evidence_cli.py:56-70` | synthetic | both are `3d59d0eb...` in the v6.0.1 evidence index; the fixture's distinct values deliberately check that the two fields map separately (`docs/decisions/package-artifacts/issue-1226-preflight.md:84-85`) | match | L |
| `GITHUB_SHA` on `workflow_dispatch` | `tools/release_evidence.py:105`, `:449` | same as above | inferred | every listed release run was a `push` run | unverified | M |
| Runner image environment | `tools/bootstrap_profile.py:652-671` | `T/test_issue_1217_bootstrap_profiles.py:548-577` | inferred | `ImageOS` `ubuntu24`; image versions match the documented format | match | L |
| `GITHUB_HEAD_REF` and `GITHUB_BASE_REF` | `tools/check_requirement_governance.py:147-148` | `T/test_requirement_governance.py:192-203` | inferred | PR #1409: head `dev`, base `main`; empty on push | match | L |
| Actions runs and jobs JSON | `tools/ci_latency_report.py:129-141` | `T/test_ci_latency_report.py:12-123` | inferred | `run_started_at` resets on re-run | diverges (GH-7) | L |
| Workflow event fields | the 11 workflows | `T/test_pr_body_guard.py:715-727`, `T/test_issue_1313_workflow_policy.py:61-90` | inferred | `merged` and `merge_commit_sha` filled on close; Phase E run 37161479661 has `pull_requests: []` and the workflow carries the PR number in `run-name` | match | H |
| Release asset `state` | `.github/workflows/release-please.yml:1078-1102` | `T/test_release_workflows.py:186-193` | inferred | OpenAPI enum `uploaded`, `open`; an `open` asset cannot be produced read-only | unverified | L |

## libvirt Python API

98 fake definitions: 71 fake methods on fake connections and objects, 2
`sys.modules["libvirt"]` error stubs and 25 inline stubs. They reduce to 16 faked
API surfaces. The observations come from libvirt 12.7.0 (`test:///default`) with
production-rendered XML, unless the row says otherwise.

| Boundary | Consumer | Fixture | Provenance | Real observation | Verdict | Blast |
|---|---|---|---|---|---|---|
| `libvirtError` identity and `get_error_code()` | `P/raes_backend_libvirt/drivers/libvirt/_native.py:61-87` | `T/test_libvirt_backend_driver.py:36-51` | inferred | `libvirt.libvirtError`, not a `KeyError`, integer code | match | L |
| Missing domain or network, generic-driver fakes | `P/raes_backend_libvirt/drivers/libvirt/_native.py:208-226` | `T/test_libvirt_backend_driver.py:127-137` | inferred | code 42 `Domain not found`; code 43 `Network not found: ...` | match | H |
| Missing domain or network, TechVault-family fakes | `P/raes_backend_libvirt/_techvault_native_ops.py:48-62`, `P/raes_backend_libvirt/techvault_lifecycle.py:70-90` | `T/test_libvirt_backend_techvault_native.py:105-109` and two sibling modules | inferred | code 42 or 43, never `KeyError` | diverges (LV-2) | M |
| Missing nwfilter | `P/raes_backend_libvirt/drivers/libvirt/deployment.py:397`, `:442` | `T/test_libvirt_backend_driver.py:105-109` | inferred | libvirt's `nwfilterLookupByName` (`src/nwfilter/nwfilter_driver.c`) raises `VIR_ERR_NO_NWFILTER` (62); the test driver has no nwfilter driver | unverified | H |
| `defineXML` and `networkDefineXML` identity | `P/raes_backend_libvirt/drivers/libvirt/deployment.py:428-430`, `:464-490` | `T/test_libvirt_backend_driver.py:111-125` | inferred | a name or UUID collision raises code 9; an owned object can live under another name | diverges (LV-1) | H |
| `nwfilterDefineXML` | `P/raes_backend_libvirt/drivers/libvirt/deployment.py:400-404` | `T/test_libvirt_backend_driver.py:99-103` | inferred | libvirt's `virNWFilterObjListAssignDef` (`src/conf/virnwfilterobj.c`) rejects a name or UUID mismatch with code 9 and updates in place only when both match; the test driver has no nwfilter driver | unverified | L |
| `create()` | `P/raes_backend_libvirt/drivers/libvirt/deployment.py:222` | `T/test_libvirt_backend_driver.py:68-71` | inferred | `create()` on a running domain raises code 1; production catches any exception | match | L |
| `destroy()` on an inactive object | `P/raes_backend_libvirt/drivers/libvirt/_native.py:188-205` | `T/test_libvirt_backend_driver.py:73-76` | inferred | code 55 `domain is not running`; production tolerates 55 | diverges (LV-4) | L |
| `undefine()` | `P/raes_backend_libvirt/drivers/libvirt/deployment.py:434`, `:455`, `:482` | `T/test_libvirt_backend_driver.py:78-79` | inferred | a running persistent domain becomes transient and stays listed; refusals (managed save, snapshots, NVRAM) are not modeled | diverges (LV-4) | M |
| `isActive()` | `P/raes_backend_libvirt/drivers/libvirt/deployment.py:149-150` | every fake | inferred | `0` and `1` as integers | match | L |
| `UUIDString()` | `P/raes_backend_libvirt/drivers/libvirt/_native.py:134-148` | `T/test_libvirt_backend_techvault_native.py:67-70` returns `None` | inferred | always a lowercase string | match in effect | L |
| `name()` | `P/raes_backend_libvirt/techvault_lifecycle.py:151-160` | TechVault fakes | inferred | string | match | L |
| `XMLDesc(0)` | `P/raes_backend_libvirt/techvault_observation.py:171-198` | three TechVault-family modules | inferred | normalized readback: `<memory unit='KiB'>131072</memory>`, `currentMemory`, `<vcpu placement='static'>` | diverges (LV-3) | M |
| `listAllDomains()` and `listAllNetworks()` | `P/raes_backend_libvirt/techvault_lifecycle.py:139-148` | TechVault fakes | inferred | defined but inactive objects are listed | match | L |
| `get_error_domain()` and `get_error_level()` | none | `T/test_libvirt_failure_observability.py:47-51` | inferred | not consumed | n/a | - |
| `libvirt.open()` | `P/raes_backend_libvirt/drivers/libvirt/_native.py:158-160` | not faked (connection injected) | - | a bad URI raises code 38; never returns `None` | match | L |

Committed real-daemon evidence covers less than its names suggest:
`tools/real-daemon/libvirt_smoke.py` has no committed output. A copy run against
`test:///default` with only the URI changed passed 3 of 12 checks, because the
harness predates the renames in #736 and #730 and the absence classification in
#1191. `tools/real-daemon/evidence/guest-certified-asr519-20260712T031842Z.json`
was string-edited after capture in `13f67129`: the retired project name in its
resource names and guest paths was replaced with `raes`, so names such as
`raes-evidence-guest-vm` were never reported by a daemon. The edit left the shape
fields unchanged.

## Guest-side libvirt appliance

31 fixtures in 9 test modules plus `T/libvirt_interface_fixtures.py`, checked
against six boots of the production-built appliance under `qemu-system-x86_64`
(Ubuntu noble `busybox-static` 1.36.1, kernel `linux-image-6.8.0-1067-aws`),
`virsh test:///default`, `qemu-img`, PyYAML 6.0.3 and upstream cloud-init and
libvirt source.

| Boundary | Consumer | Fixture | Provenance | Real observation | Verdict | Blast |
|---|---|---|---|---|---|---|
| Guest `MemTotal` | `P/raes_backend_libvirt/guest_appliance.py:219`, `P/raes_backend_libvirt/guest_observation.py:65`, `:245-246` | `T/test_libvirt_backend_guest_certified.py:115`, `:490`, `:683` | inferred | `memory_mib 81` at 128 MiB; committed evidence says 78; 207 at 256 MiB | diverges (GU-1) | H |
| Guest account `disabled` report | `P/raes_backend_libvirt/guest_appliance.py:177-178`, `:246` | `T/test_libvirt_backend_guest_certified.py:183`, `:600`, `:608` | inferred | every account reports `1`; enabled accounts are written with `*` | diverges (GU-2) | H |
| Serial fact channel line endings | `P/raes_backend_libvirt/guest_transport.py:86-98` | `T/test_libvirt_backend_guest_certified.py:141` | inferred | raw bytes end in `\r\n`; `splitlines()` handles them | match in effect | L |
| Other fact lines (interfaces, content, services) | `P/raes_backend_libvirt/guest_appliance.py:213-259` | `T/test_libvirt_backend_guest_certified.py:108-141` | inferred | same format in the boot capture | match | - |
| Fact-file ownership under libvirtd | `P/raes_backend_libvirt/guest_transport.py:75-83` | stub transport, never reads a file | inferred | libvirt source creates the file root-owned `0600`; no live daemon was available | unverified | M |
| Initramfs archive | `P/raes_backend_libvirt/_initramfs.py:128-160` | `T/test_libvirt_boot_artifacts.py:68`, `:200-218` | synthetic | the kernel unpacked the production archive and ran `/init` | match | - |
| Static BusyBox ELF preflight | `P/raes_backend_libvirt/_initramfs.py:216-284` | `T/test_libvirt_boot_artifacts.py:26-56` | synthetic | real static, PIE, arm64 and Mach-O binaries classify as expected | match | - |
| `raes.challenge` kernel argument | `P/raes_backend_libvirt/techvault_matrix.py:232-236` | `T/test_libvirt_backend_guest_certified.py:30` | inferred | round-trips in the boot | match | - |
| cloud-init `user-data` parsing | `P/raes_backend_libvirt/cloudinit.py:106-121` | `T/test_libvirt_backend_cloudinit.py:28-31` uses `json.loads` as the oracle | inferred | cloud-init uses `yaml.safe_load`; astral-plane characters come back as lone surrogates | diverges (GU-3) | M |
| NoCloud `meta-data` | `P/raes_backend_libvirt/cloudinit.py:124-140` | `T/test_libvirt_backend_cloudinit.py:113-135` | inferred | PyYAML parses it to a mapping | match | - |
| `genisoimage` argv and exit code | `P/raes_backend_libvirt/drivers/seed.py:111-133` | `T/test_libvirt_backend_driver.py:211-218` | inferred | argv matches upstream NoCloud documentation; tool not available locally | unverified | L |
| Committed guest evidence artifact | `P/raes_operations/_evidence_run_native.py:99-141` | `T/test_libvirt_backend_guest_certified.py:747-773`, `T/test_libvirt_evidence_run.py:61-74` | synthetic | the committed artifact fails the current validator with 2 problems; no test loads it | diverges (GU-4) | M |

## Network services and supply chain

140 fixtures or hand-built payloads (about 190 parametrized cases) across curl
acquisition, bootstrap, vocabulary snapshots, the module registry, OCI images,
release evidence and archives. The audit also re-checked 52 locked artifact
values against their producers. A further 31 fixture builders and 30 lock values
cover the Isabelle and generic-tool archives.

| Boundary | Consumer | Fixture | Provenance | Real observation | Verdict | Blast |
|---|---|---|---|---|---|---|
| curl exit codes and retries over HTTP/2 | `tools/maintained_client_acquisition.py:146-151`, `:236-243`; `tools/bootstrap_profile.py:70-71` | `T/test_issue_1217_bootstrap_profiles.py:776-819` (`http.server`, HTTP/1.x only) | real, protocol-limited | macOS curl 8.7.1: oversize transfer and HTTP 503 both exit 56, no retry; with `--http1.1`: 63 and 22 after 3 attempts; Ubuntu 24.04 curl 8.5.0 returns 63 on both protocols | diverges (NS-1) | M |
| `curl --version` text | `tools/maintained_client_acquisition.py:85-89` | `T/test_issue_1137_maintained_client_acquisition.py:86`, `:138` | inferred | parsed correctly | match | L |
| TLS rejection exit codes | `tools/maintained_client_acquisition.py:26`, `:238` | `T/test_issue_1217_bootstrap_profiles.py:900-928` | real | self-signed, expired, wrong-host and untrusted-root endpoints exit 60 | match | H |
| Redirects and unknown-length bodies | `tools/maintained_client_acquisition.py:139-157` | `_CurlFixture` routes | real | GitHub 302 to a signed CDN URL is followed; unknown length is bounded | match | H |
| NIST CSF export byte identity | `tools/check_nist_csf_defensive_vocabulary.py:219-224` | `T/test_issue_1221_*.py:70-75`, `:129-151` | captured once | two downloads gave 107517 and 107518 bytes with different digests; neither matches the lock | diverges (NS-4) | L |
| ATT&CK, ATLAS and W3C snapshots | `acquire_locked_bytes` | `T/test_issue_1221_*.py` | captured | digests and sizes equal the lock | match | L |
| uv, CPython, actions/python-versions and sonar-scanner archives | `tools/bootstrap_profile.py:445-507` | lock | captured | producer digests equal the lock | match | H |
| conftest, gitleaks, vale and osv-scanner release assets | `tools/verified_tool_installation.py:160-228` | `T/test_issue_1137_*.py:383-395`, `T/test_issue_1219_*.py:35-207` | inferred | all 12 assets equal the lock and install through the production code | match | H |
| Isabelle archive | `tools/verified_tree_archive.py:280-362` | `T/test_issue_1220_isabelle_acquisition.py:40-79` | inferred | both mirrors serve the locked size; CI admits the real archive | match | H |
| OCI distribution API for `oci:` imports | `P/raes/module_registry/__init__.py:156-186` | `T/test_sdl_module_registry.py:96-170` | inferred | ghcr.io, Docker Hub and ECR Public answer `401` with a `Bearer` challenge; blobs redirect with `307` | diverges (NS-2) | M |
| Docker Hub alpine image graph | `tools/oci_release_image.py:115-181` | lock | captured | digests, sizes and `diff_ids` are byte-exact | match | H |
| `docker image inspect` output | `tools/oci_release_image.py:54` | `T/test_oci_release_image.py:68-83` | inferred | CI run 37270742395 passed against a real daemon | match | H |
| `docker run` and `docker container inspect` | `P/raes_reference_backend/drivers/oci.py:288-367` | `T/test_reference_backend_oci_driver.py:19-50` | inferred | ID on stdout, pull progress on stderr | match | M |
| OCI layer list | `tools/tooling_artifact_policy_oci.py:102-108` | `T/test_tooling_artifact_policy.py:1584-1587` | inferred | the linux/amd64 manifest of the Docker Official Image `tomcat:latest` (`sha256:594377d0...`) lists one empty layer three times | diverges (NS-5) | L |
| Lock-shaped image selection fixture | no current consumer | `T/test_oci_release_image.py:122-124`, `:154-155` | inferred | the real lock names the platform manifest; arm64 has variant `v8` | n/a (NS-6) | L |
| gh output with no attestation | `tools/release_evidence.py:292-307` | `T/test_issue_1226_attestation_verifier.py:74-77` | inferred | exit 1, empty stdout, stderr `Error: HTTP 404` | diverges (NS-7) | L |
| Release build inventory subjects | `tools/release_evidence_admission.py:314-320` | `T/test_issue_1226_release_admission.py:70`, `:172`; `T/test_issue_1227_release_publication.py:64` | inferred | the real inventory has 3 subjects; the sdist-built test wheel equals the wheel | diverges (NS-3) | M |
| CycloneDX 1.6 SBOM | `tools/release_evidence_documents.py:75-150` | `T/test_issue_1226_evidence_documents.py:24-107` | inferred | real SBOMs validate with 0 errors | match | L |
| PyPI per-version JSON | `.github/workflows/release-please.yml:809-848` | `T/test_release_workflows.py:1378-1497` | inferred | digests present; 404 body `{"message": "Not Found"}` | match | H |
| curl failure output in the PyPI check | `.github/workflows/release-please.yml:809-822` | `T/test_release_workflows.py:1394-1411` | inferred | curl prints `000` and exits 6; the stub exits 0 | diverges (NS-8) | L |
| AWS EC2 CLI JSON | `tools/real-daemon/run_aws_smoke.sh:70-146` | none | none | not captured | unverified | M |
| Lock digests for actions that download their own tools | scorecard and sonar actions | lock | captured | the consuming actions pull by tag or check a signature, so the lock digest is not enforced | unverified | M |

## Subprocesses and command-line tools

The audit drove each tool with the production argv in the states the consumer
handles. Fixture counts were not recorded for this class.

| Boundary | Consumer | Fixture | Provenance | Real observation | Verdict | Blast |
|---|---|---|---|---|---|---|
| `conftest test --output json` | `tools/policy/conftest_tool.py:59-106` | `T/test_repo_policy_tools.py:1288-1316` (failure output only) | inferred | load and evaluation errors exit 1 with an empty stdout, which the runner read as no failures | diverges (CL-1) | H |
| `conftest verify` | `tools/policy/conftest_tool.py:109-125` | `T/test_repo_policy_tools.py:486` (command wiring) | inferred | exits 1 on a parse error, 0 on a policy whose evaluation conflicts only on real input | match | M |
| gitleaks directory scan over a symlink farm | `tools/nox_support/runner.py:361-380` | `T/test_issue_1350_fixture_secret_scan.py:19-83` | real | the production argv reports leaks through `--follow-symlinks`; exit 1 with findings | match | H |
| osv-scanner exit codes | `tools/osv_scanner_tool.py:17-33` | `T/test_repo_policy_tools.py:3233-3266` | inferred | 0 clean, 1 findings, 127 network failure, 128 no packages | match | M |
| vale exit codes | docs nox lane | none | - | 0 clean, 1 alerts, 2 runtime error; both non-zero codes fail the lane | match | L |
| git path listings without `-z` | `tools/nox_support/runner.py` (`_changed_paths`, `_tracked_repo_paths`), `tools/policy/common.py` (`changed_paths`) | scratch repositories with ASCII names | real, ASCII-only | git quotes non-ASCII and control-character paths; the runner drops them and the policy helper returns the quoted string | diverges (CL-2) | M |
| `docker image inspect` and `docker run` | see the network table | - | - | Docker 29.7.2 output matches the fixtures | match | M |
| Isabelle build output and `bwrap` errors | `tools/isabelle_tool.py:345-349`, `:414-422` | `T/test_issue_963_participant_opacity_proof.py:227-241` | inferred | upstream sources print `bwrap: ` and `Finished <session>`; CI replay passes | match | M |
| `uv build --sdist` file name | `tools/python_closure.py` | fake writes `raes-1.tar.gz` | inferred | the distribution name is `raes`, so `raes-<version>.tar.gz` | match | L |
| pytest JUnit XML for the docker lane | release workflow skip check | string assertions only | inferred | real JUnit marks skips with `<skipped>` as the parser expects | match | M |
| coverage.py JSON | `tools/nox_support/test_lanes.py` | coverage fixtures | inferred | coverage.py 7.13.5 JSON has `totals.covered_lines` and `totals.num_statements` | match | L |
| `check-jsonschema` | schema checks | - | - | not captured before the audit stopped | unverified | L |

## SQLite control-plane store and the Ground Control client

The observations come from probes that run the store's SQL and the production
`LocalControlPlaneStore` against SQLite 3.50.4 under CPython 3.14.4 on macOS.

| Boundary | Consumer | Fixture | Provenance | Real observation | Verdict | Blast |
|---|---|---|---|---|---|---|
| Driver shapes: `BLOB` read-back, unique and primary-key violations, nested `BEGIN IMMEDIATE`, `SQLITE_BUSY` | `P/raes_runtime/control_plane_store_local*.py` | store tests | real | errors and return values as the store expects | match | H |
| WAL sidecars, backup journal mode, VFS fallbacks | `P/raes_runtime/control_plane_store_maintenance.py` | store tests | real | WAL persists through backup; non-database files raise `DatabaseError` | match | M |
| `PRAGMA quick_check` on a corrupt file | store admission | `_QuickCheckFailureConnection` fake (`T/test_issue_1092_control_plane_crash_consistency.py:1028`) returns a non-`ok` row | inferred | index and page damage return non-`ok` rows and admission refuses; a damaged table root or truncation raises `sqlite3.DatabaseError` from the PRAGMA itself | diverges (ST-3) | L |
| Runtime-owner lease across `fork()` | `P/raes_runtime/control_plane_store_lease.py:217-231` | `T/test_issue_1092_control_plane_crash_consistency.py:2432` (`test_runtime_owner_lease_rejects_and_closes_in_a_different_process_identity`) patches `os.getpid` in one process | inferred | a forked child that calls `LOCK_UN` on its inherited descriptor releases the parent's lock; the simulated fork cannot observe that | diverges (ST-1) | H |
| Commit failure | `P/raes_runtime/control_plane_store_local_codec.py:13-24` | `T/test_run_310_supervisory_lifecycle.py:872`, `T/test_runtime_control_plane_api.py:1878` raise `OSError("commit failed")` inside the transaction body | inferred | a real commit failure raises `sqlite3` errors from `commit()`; the per-operation connection close discards it, so nothing persists | diverges (ST-2) | L |
| Ground Control HTTP client transport | `tools/policy/requirement_governance.py` | `T/test_requirement_governance.py:150-152` fakes `HTTPError`, `URLError` and `TimeoutError` | inferred | a dropped connection, a truncated body, an HTML login page and non-UTF-8 JSON raise exceptions that are not `GroundControlError` | diverges (ST-4) | M |
| Store migration across releases and request-commitment drift | store migration code | store tests | - | probes were written but recorded no verdict | unverified | H |

## MCP, filesystem, time and internal stand-ins

| Boundary | Consumer | Fixture | Provenance | Real observation | Verdict | Blast |
|---|---|---|---|---|---|---|
| MCP stdio wire: initialize, tools/list, tools/call | `P/raes_mcp` | MCP tool tests call the functions directly | inferred | protocol `2025-11-25`; all 31 tools declare an output schema; structured and text content agree | match | M |
| Rejected MCP arguments | `P/raes_mcp` | `T/test_experiment_authoring.py:195-206` passes `spec_content` as a string | inferred | a client that sends an object gets the framework's validation error, which includes `input_value` and, for small inputs, the value | diverges (TM-3) | L |
| Filesystem errors (`flock`, `O_NOFOLLOW`, `O_DIRECTORY`, `fsync` on directories) | store paths and lease | store and installation tests | real | macOS error classes and errnos captured | match | M |
| Workflow step timestamps for compensation order | `P/raes_runtime/control_plane_workflows.py:52` | `T/test_runtime_control_plane_api.py:2148`, `:2277` have one compensable step | inferred | producers drop the fraction at a whole second (`...:01Z` then `...:01.001000Z`), so the string sort reverses them | diverges (TM-1) | H |
| Runtime-fact `requested_at` | `P/raes_runtime/runtime_fact_dispatch.py:36`, `P/raes_runtime/runtime_fact_binding_policy.py:119-124` | `T/test_runtime_fact_bindings.py:107`, `:233-243` use `Z` timestamps | inferred | a naive or date-only value is admitted, then binding raises `TypeError` | diverges (TM-2) | M |
| Unavailable container runtime | `P/raes_reference_backend/drivers/oci.py` | driver tests | inferred | a stopped Docker daemon gives `reference-backend.driver.command-failed` | match | L |
| LilRAE `aptl-evidence-bundle/v1` and `aptl.run-record/v2` exports | cross-backend corpus consumer | hand-built exports in `T/test_cross_backend_corpus.py:109-177` | inferred | both exports, as LilRAE's producer source at `a5833df9` builds them, pass the corpus checks | match | M |

## Backend manifests and realization envelopes

52 fixtures: 37 corpus files and 15 in-test constructions, compared with the
stub, reference, libvirt and LilRAE APTL producers (LilRAE at `a5833df9`, read
only).

| Boundary | Consumer | Fixture | Provenance | Real observation | Verdict | Blast |
|---|---|---|---|---|---|---|
| Stub backend manifest | conformance validators | `contracts/fixtures/.../backend-manifest-v2/valid/stub.json` | captured | 116 of 116 paths equal the producer apart from the version | match | L |
| Reference processor manifest | `ProcessorManifestV2Model` | `contracts/fixtures/.../processor-manifest-v2/valid/reference.json` | captured | 14 of 14 paths equal apart from the version | match | L |
| Processor and backend mutual compatibility | `P/raes_processor/trial_realization.py:224-228`, `P/raes_processor/trial_compiler/apparatus.py:389-401` | `T/test_sce_002_trial_realization.py:67` and `T/test_runtime_contracts.py:81` patch `compatibility.backends`; `:91` renames the backend to match | inferred | the real processor declares `["stub"]` only; every non-stub backend is rejected | diverges (MF-1) | M |
| Mixed-runtime manifest anti-substitution check | `P/raes_runtime/mixed_runtime.py:212-214` | `T/test_issue_1016_mixed_runtime_coordination.py:278-291` | inferred | the APTL manifest keeps authored OS order and a list where the round trip sorts and uses a tuple, so the admitted manifest is rejected | diverges (MF-2) | M |
| Capture offers | `P/raes_processor/capture_admission.py:212-218` | `T/test_sce_002_trial_compiler.py:361-385` | inferred | no producer emits an offer | unverified | M |
| Negative backend-manifest corpus | `T/test_backend_manifest.py:1179-1183` | 9 files under `backend-manifest-v2/invalid/` | inferred | each file fails for its named defect and for incidental ones | diverges (MF-3) | L |
| Plan inspection with `--manifest` | `P/raes_cli/processor.py:136-145` | `T/test_plan_inspection_cli.py:88-190` | captured | envelope-bearing manifests are refused, as documented | match | L |
| Published realization envelopes | envelope loaders | `contracts/realization-envelopes/*` | captured | producer output equals the files | match | L |
| APTL manifest admission | conformance and service materialization | negative paths only | - | the real APTL manifest is admitted | match | L |

## Runtime snapshots and control-plane payloads

| Boundary | Consumer | Fixture | Provenance | Real observation | Verdict | Blast |
|---|---|---|---|---|---|---|
| Receipts, statuses and snapshot carriers | conformance and contracts | `contracts/fixtures/` runtime fixtures | captured | real payloads carry the same keys | match | M |
| Snapshot validated by target conformance | conformance hermetic projection | conformance tests | inferred | the projection omits `realization_envelope` and `realization_provenance`, which the `/snapshot` API publishes | diverges (RS-1) | M |
| Public snapshot used by the SEM-222 test | `/snapshot` route | the test serializes with the durable store | inferred | the public route drops episode closure records and mixed-composition state that the store keeps | diverges (RS-2) | M |
| Participant behavior history in a real snapshot | conformance semantics | corpus adds `participant.*` entries with empty payloads | inferred | a `/snapshot` from the real control plane with behavior history has no `participant.behavior` entry and fails semantic conformance | diverges (RS-3) | M |
| LilRAE snapshot projection | `RuntimeSnapshotEnvelopeModel`, conformance | - | - | a projection as LilRAE's producer source at `a5833df9` builds it is accepted with 0 diagnostics | match | L |

## Release, conformance and experiment evidence

29 fixtures across 10 boundaries. The table lists seven. The other three match:
the release evidence index and SBOM subject hash, the optional `task_ref` and
`apparatus_context_ref` checks on evidence records, and the hand-authored
lineage ledger example.

| Boundary | Consumer | Fixture | Provenance | Real observation | Verdict | Blast |
|---|---|---|---|---|---|---|
| Release build inventory | `tools/release_evidence_admission.py:314-316` | see NS-3 | inferred | 3 subjects; derived wheel equals the wheel | diverges (NS-3) | M |
| Evidence record `capture_spec_ref` | `P/raes_contracts/evidence_satisfaction.py:98-107` | all 5 files under `contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/` | inferred | LilRAE's builder omits `ref_version`; the schema accepts the record and the validator rejects it | diverges (EV-1) | M |
| libvirt evidence-run artifact | cross-backend corpus | the test drives the real producer | real | descriptor `{libvirt-qemu, 5.0.0}` | match | L |
| Conformance report | release workflow | `T/test_backend_conformance_cli.py:43-63` | captured | real producers pass the same case validator | match | L |
| Minimal plans | operation routes | `contracts/fixtures/.../plans/*/valid/minimal.json` | inferred | a real plan posted to the API returns 200 | match | L |
| Trial compiler identity vectors | `T/test_sce_002_trial_compiler.py:748-758` | `identity-vectors.json` | captured | golden values from the real function | match | L |
| Formal-evidence archives | `tools/formal_semantic_validation` | `docs/research/formal-semantic-validation/evidence/` | captured | pinned and replay-checked | match | L |
