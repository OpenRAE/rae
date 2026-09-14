# Issue #1222: Live-runner acquisition preflight

Issue #1222 is the contract; this is requirement-free architecture guidance,
not an implementation plan or qualification record. ADR-106 and ADR-107 are
already accepted through #1168 / PR #1229. Do not amend their accepted-content
pins to deliver this consumer migration. Before implementation, assign a named
Backend/Platform owner and verify the native GitHub blockers recorded in
[migration.md](package-artifacts/migration.md): #1168, #1217, #1218 and #1137.
Their current API state and an implementation owner were not established by
this repository-only preflight; landed files alone do not discharge that gate.

## Decision and existing authorities

Both `tools/real-daemon/run_aws_smoke.sh` and `run_aws_guest_certify.sh` must
consume the same admitted setup path. Keep AWS CLI provisioning, service
credentials and API availability at the existing external-service boundary.
Acquisition policy belongs to the tooling authorities below, never inline
shell pins, SDL runtime package declarations, or libvirt backend manifests.

| Concern | Canonical incumbent and required boundary |
|---|---|
| Input identity and admission | `implementations/tooling/artifacts.lock.json`, `admission-policy.json`, `profiles/development-profiles.json` and their internal schemas. VM bytes need reviewed source, exact raw size and digest, platform, trust/redistribution decision and profile binding. Installation cannot discover its own accepted checksum. |
| Validation and discovery | `tools/check_tooling_artifact_policy.py`, `tooling_policy_gate.py`, `tooling_artifact_policy_{common,artifacts,discovery,inventory,selectors}.py`; `selector-bindings.json` and `inventory-coverage.json`. Select through the gate before acquisition; reconcile I13's legacy-remediation sites with actual consumers rather than hiding them under an external-service disposition. |
| Host/bootstrap | `tools/bootstrap_profile.py` and the profile schema/semantic joins. Reuse uv/CPython payload selection, kit verification and qualification outcomes; create an exact live-host profile, not a claim that a GitHub-hosted Ubuntu profile also qualifies EC2. |
| Python resolution | Project `pyproject.toml` / `uv.lock` and `implementations/tooling/python/` own their respective graphs. `tools/python_closure_profiles.py`, `python_closure.py`, `python_closure_wheelhouse.py` and `generate_python_closures*.py` own frozen contexts and generated hash-complete exports. Add the opt-in libvirt closure through this authority without duplicating the project graph in the generic artifact lock. |
| Generic transfer and local admission | `tools/maintained_client_acquisition.py` owns fixed maintained-curl invocation, local-input admission and sanitized failure classes. `tools/verified_tool_installation.py` owns supported executable-tree installation, locks and immutable seeds. Reuse each within its supported artifact shape; a VM disk is not an executable archive. |
| Execution and evidence | Existing `LibvirtDeploymentDriver`, `LibvirtProvisioner`, `raes_operations.libvirt_evidence_run`, `_evidence_run_native`, `_evidence_run_validation` and `run_artifacts` retain lifecycle, ownership, certification, redaction and persistence authority. Bootstrap qualification is separate operator evidence. |

No currently admitted VM artifact class is present in the closed artifact-lock
enum. Represent any necessary VM/native extension explicitly in the existing
internal schemas and semantic joins; do not misclassify a disk as `generic-cli`,
add an unvalidated JSON sidecar, or publish a new SDL schema. The development
container's immutable Ubuntu snapshot/profile and
`tooling_artifact_policy_container.py` are an existing native-closure precedent,
not a VM image or a libvirt-host qualification.

## Host and closure guardrails

- Replace the mutable SSM `stable/current` AMI selection with a reviewed
  region/architecture/owner/image binding. AMI and snapshot identifiers are
  provider identities, not raw-file SHA-256 digests; hashing their text or using
  EBS capacity as byte size proves nothing. Bind the qualified image to its
  retained build/input evidence. Downloadable VM/base objects separately need
  raw digest/size verification. Do not promise portable AMI export where the
  provider/image does not support it.
- A native closure includes authenticated immutable repository metadata, trust
  roots, exact packages and their transitive dependencies, or an admitted image
  containing them. `apt-get update` against current repositories plus a package
  name/version list is insufficient. Account for QEMU utilities, libvirt daemon,
  client and libraries, seed ISO tooling, kernel and static x86_64 BusyBox;
  source-building libvirt-python additionally requires the interpreter ABI,
  compiler, headers, pkg-config, build backend and build-time dependencies.
  Frozen uv sync alone cannot freeze these. Prefer an admitted compatible wheel
  when available; do not allow implicit sdist/build-isolation network fallback.
- Keep libvirt-python and native build prerequisites opt-in. Default contributor
  tool/project environments must not start requiring a compiler, daemon, AWS
  credentials or KVM. The existing generic Python closure does not establish a
  live libvirt ABI closure merely because `uv sync --all-extras` succeeds.
- `bootstrap_profile.native_setup_plan()` deliberately refuses mutable native
  installation. Host profiles declare `host_security_control_changes:
  prohibited`. The current scripts' `security_driver = "none"`, root QEMU
  user/group and guest runner's `sudo bash -lc` cannot be carried into a claimed
  qualified profile by silently weakening that policy. Qualify least-privilege
  access to the daemon, images, seed files and guest fact channel under the host's
  existing security controls. An incompatible host is unsupported, not repaired
  by disabling confinement or making private run trees world-writable.
- TCG (`domain type="qemu"`) is distinct from KVM. Validate the selected emulator,
  daemon access and architecture; require `/dev/kvm` access only for an explicitly
  selected accelerated profile. Generic profiles list libvirt/QEMU/KVM as optional;
  that is not successful live-runner qualification. Missing required capabilities
  fail the requested live run with a bounded diagnosis.
- Reuse `_initramfs`/guest-appliance preflight for regular, executable, static
  x86_64 ELF BusyBox and TechVault's kernel preflight. Bind the actual selected
  kernel/BusyBox bytes to the closure rather than relying on PATH or newest
  `/boot/vmlinuz-*`. Existing deterministic `newc` generation needs no host
  `cpio`. Kernel content caching and appliance digests prove identity after
  selection, not trusted acquisition; see the [boot-artifact decision](issue-1094-libvirt-boot-artifact-reliability.md).

## Cross-cutting layers the implementation must pass

| Layer | Required treatment |
|---|---|
| Repository files and shapes | Use `safe_repo_path()` / `load_bounded_json_object()` in `tools.policy.common`, tracked regular-file admission, bounded duplicate-key-rejecting JSON, local-only schema resolution and the existing semantic joins. Host, artifact, policy, platform, Python ABI, export and consumer references must agree. A schema-valid profile alone is not qualified. |
| Environment and configuration | Select closed host/Python/context identifiers. Reuse `closure_environment()` to discard ambient indexes, credentials, Python paths and interpreter downloads; use qualified executable paths because its PATH originates at the caller. Mirror URL validation remains credential-free HTTPS with no public fallback. Do not source arbitrary environment files or accept command/argv/env overlays in policy data. |
| Runtime shapes | Leave installer fields out of `RuntimeConfiguration`, SDL environment bindings and `target._CONFIG_KEYS`. Existing libvirt target construction validates mode/manifest/envelope pairing; TechVault `validate_driver_configuration()` validates URI, flags and names. `LibvirtEvidenceRunConfig` currently exposes only mode and URI: new execution parameters must traverse the real constructor/validation path, not be assumed to pass through a permissive dictionary. |
| Authentication and secrets | AWS CLI keeps its existing profile/provider credential chain on the caller; never copy cloud credentials into userdata, source bundles, guests or tooling caches. Tool profiles store credential references only. Keep fork/untrusted runs away from enterprise credentials and trusted writable seeds. This creates no HTTP API/controller/auth model; existing control-plane role, target-binding and error gates remain unchanged. |
| Shell, SSH and OS exposure | Validate `RUN_ID` through `run_artifacts.is_valid_run_id_label()` before any interpolation or path use. The current nested shell/Python `-c` interpolation occurs before Python validation and is unsafe. Pass data through fixed argument/file interfaces with deliberate remote-shell quoting; reject option/command injection. Never place tokens, private keys or signed URLs in argv, xtrace, stdout, userdata or raw exception output. Keep temporary keys mode 0600 and run directories private from creation. |
| Host trust and authorization | Disabling SSH host-key verification is not a trustworthy source/evidence handoff. Use an authenticated host-identity mechanism and scoped known-hosts state. Do not treat the artifact digest as SSH authentication. Preserve libvirt ownership checks and daemon authorization; do not broaden ingress or service privileges to make acquisition succeed. |
| Filesystem and concurrency | Admit local inputs as bounded regular files, verify raw digest/size before parsing with QEMU or executing/installing, and reverify the transferred copy. Protect parent directories and reject link/path escapes; bind validation to the bytes consumed. Private staging and atomic publication must prevent partial success under interruption/disk exhaustion. Preserve the incumbent immutable-seed/verified-installation behavior for tools instead of inventing another cache. |
| Failures and observability | Reuse maintained-client reason codes and Python closure failure categories for acquisition. Keep backend `Diagnostic`/`DriverResult`/`ApplyResult`, `_native` exception classification and `_observability.record_suppressed_failure()` intact. Do not add a parallel exception hierarchy or expose raw client stderr, tracebacks, URIs or native XML in public evidence. |
| Evidence and persistence | Retain `validate_libvirt_evidence_run_artifact()` before `atomic_write_json_artifact()`, embedded contract validation, redaction, fresh challenge and operation/configuration/appliance binding. Store input/profile qualification separately and associate runs by safe identifiers/digests; do not inject bootstrap/AWS fields into closed scenario-evidence structures or runtime snapshots. |

The source handoff is part of the closure: the scripts currently copy selected
trees without `.git`, tooling policy, the frozen tooling project or all packaging
inputs. The policy gate discovers **Git-tracked** consumers; it cannot be assumed
to validate that partial remote tree. Use a source/input preseed that preserves
the metadata needed by the canonical gate, or an explicitly admitted handoff
whose validation does not silently skip discovery. Include required build inputs
such as the root README and contracts; do not rsync arbitrary ignored local
state or credentials. Bootstrap must not depend on first downloading the
validator's own unverified interpreter/dependencies.

## Isolation, extensibility and honest verification

Private local and remote roots must contain venvs, uv caches, overlays, seeds,
guest facts and partial downloads. Filesystem isolation does not isolate AWS
key/security-group names or libvirt domains/networks/nwfilters. The smoke uses
fixed `raestest` / `raesprov` names, a shared CirrOS path, a fixed temporary overlay
and a broad prefix purge. Guest evidence also has a fixed production driver
prefix. Select exclusive per-run hosts/daemons where those contracts require it,
or thread supported run-scoped names through the owning execution seam. Cleanup
must act only on positively owned resources; never delete another run's key pair
or purge objects merely because they share a prefix. Preserve failing status,
report incomplete cleanup, and make `--keep` resource/key retention explicit.

The extensibility seam is **host profile + acquisition context + Python closure
profile + admitted local input root**, shared by both runners. A new mirror,
region or supported host tuple should select reviewed data without duplicating
installer logic or changing expected bytes. Execution mode, run root and admitted
VM path belong at the existing harness/driver boundary. Do not add arbitrary
script hooks or a new workflow engine. Keep the generic client's current 256 MiB,
30-second and in-memory limits visible: larger future VM inputs need reviewed,
bounded local file admission and native-client parameters in the same acquisition
layer, not global unbounded limits or a second HTTP implementation.

Verification must use [operations T07, T13 and T21](package-artifacts/operations.md):

- T07 requires measured cold/warm concurrency, quota/disk-full failures, bounded
  completion and absence of cross-run mutation. The service target is 100 clients;
  the operating contract also specifies 32 same-host installers. Record the exact
  exercised slice; two fake runs do not establish either capacity or AWS behavior.
- T13 must reject missing native/build/interpreter/VM inputs, wrong ABI/platform,
  corrupt sizes/digests, malicious links and incomplete seeds before consuming
  imported code or attempting network fallback. A Python wheelhouse test alone
  does not cover the native closure. Preseed raw inputs and immutable metadata,
  not an opaque warm uv cache or a marker file.
- T21 requires the actual admitted VM/native/uv/libvirt closure and both runner
  paths. Remove pipe-to-shell, ignored downloads and unconditional readiness
  sentinels; timeout waiting for setup must fail. Preserve evidence on failed
  guest runs without allowing evidence-copy/cleanup success to replace failure.
  The vocabulary-refresh slice belongs to #1221.

Record exact source SHA, tool/platform/ABI and image identities, lock/policy
digests, source class, outcomes and measured limits. Reuse the existing
passed/failed/unsupported/not-run vocabulary. The opt-in real-libvirt pytest can
skip when dependencies are absent; a zero exit with skips cannot satisfy a
requested certification. Domain existence/attached ISO does not prove guest
boot or guest-observed facts. Injecting a custom driver factory makes the current
guest evidence non-certifying; do not bypass that distinction to configure a run.

Keep Nox, `.ground-control.yaml`, repo policy and tooling-policy checks. Use
`test_tooling_artifact_policy.py`, `test_issue_1217_bootstrap_profiles.py`, Python
closure tests, `test_libvirt_evidence_run.py`, `test_libvirt_boot_artifacts.py` and
the opt-in real-libvirt tests as incumbent test boundaries. Do not make ordinary
`nox verify` require real libvirt or cloud access. Do not fabricate a requirement
UID for this issue; disclose any existing requirement-context gate mismatch.

## Non-goals

No AWS provisioning/API rewrite, cloud-service offline claim, new package
manager/HTTP transport, acquisition retry/redirect/TLS/framing code, SDL package
or module-registry redesign, release/promotion service deployment, global offline
export implementation (#1225), or guest-certification semantic change. Local
preseed verification can be disconnected; AWS APIs remain live external services.
This note supplies no approved digests, native package set, named owner, measured
qualification result or permission to weaken host security.
