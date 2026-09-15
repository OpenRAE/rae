# Realization Envelopes and Observation Provenance

This page explains how RAES states, per backend configuration, **which scenario
concerns it can realize and where its proof for each one comes from**. It is
non-normative explanation; the governing decision is
[ADR-070](../../decisions/adrs/adr-070-realization-envelope-semantics.md) and the
formal semantics live in
{download}`specs/formal/realization/envelope-semantics.md <../../../specs/formal/realization/envelope-semantics.md>`.
It is the backend-facing companion to
[Explicitness and Realization Semantics](explicitness-realization-semantics.md)
(which covers author-declaration exactness, SEM-218).

## The problem

"The backend realized the scenario" is not a single claim. A backend can create
a named object at the hypervisor and report success while the guest never
booted, got the wrong address, or is missing the file the scenario asked for.
Honest portability needs each backend to disclose, per concern, *what* it
realizes and *how independently that realization is observed* — and to be unable
to claim more than it can show.

## Observation provenance

Every governed concern carries an **observation source**. The released wire
field and enum retain the legacy name `observation_strength`, but the values are
provenance alternatives rather than a total order. The vocabulary is closed
(`raes_contracts.realization_envelope_carrier.ObservationStrength`):

| Source | Meaning |
| --- | --- |
| `none` | Not observed (the concern is `unsupported` for this configuration). |
| `driver-reported` | The driver asserts it; no independent readback. |
| `daemon-observed` | Read back from the hypervisor/daemon (e.g. libvirt domain/network XML), ownership-checked. Proves the object exists and is configured at the daemon boundary. |
| `guest-observed` | Read from **inside the realized guest** (its own `/proc`, `/sys`, `/etc`, link/file/account/service state). Proves the running system *is* what was requested, not just that an object exists. |

A concern's **disposition** (`realized`, `transformed`, `descriptor-only`,
`unsupported`) says whether and how it is realized; the source says how it is
proven. Sufficiency is claim-specific: coverage scope, value and execution
binding, freshness, declared capability, and any explicit boundary or
independence constraint matter independently of source. When an author leaves
the source unconstrained, either daemon-native or guest-native readback may
corroborate the claim if it satisfies those other conditions; `driver-reported`
self-attestation alone is not authoritative corroboration. An `unsupported`
concern must claim `none` — a configuration cannot disclose observation for
something it does not realize.

Source provenance is separate from visibility and collection effect. Closed
realization scope allows non-mutating native readback, but does not authorize an
in-world probe or sidecar; a claim that cannot otherwise be proved is rejected.
Open scope permits only the available sufficient method with the least effect
on the environment and participants, and any added apparatus is disclosed as
part of the realized form and through the existing augmentation carrier.

## Concerns

The concern taxonomy is closed (`RealizationConcern`): `topology`,
`architecture`, `image`, `resource-allocation`, `network`, `content-placement`,
`account-placement`, `feature-binding`, `service`, `acl`. A realization envelope
discloses a source and disposition for **every** concern, so gaps are explicit
rather than implied.

## Configuration-bound identity

A realization envelope is bound to one **material configuration**, not to a
backend in the abstract. Its secret-free configuration identity (architecture,
image/appliance policy, network policy, supported concern set, guest-observation
transport and probe-policy version, augmentation mechanism) is hashed into a
`configuration_digest`, and the whole envelope into an `envelope_digest`.
Changing a concern's claimed source requires a *new* configuration and envelope
— you cannot relabel one provenance as another. Published envelopes live under
`contracts/realization-envelopes/` and are validated on load.

## The libvirt backend's configurations

The libvirt backend (`raes_backend_libvirt.envelopes.LibvirtDriverMode`) ships
three material configurations:

- **`generic`** — qcow2/cloud-init driver; concerns are `driver-reported`.
- **`techvault-appliance`** — boots a generated BusyBox initramfs appliance and
  reads topology/architecture/image/resource/network back at
  `daemon-observed` provenance; guest concerns are `unsupported`.
- **`guest-certified-appliance`** — boots a guest-observing appliance through the
  production apply path and certifies concerns from **inside** the guest.

The guest-certified envelope discloses (verified against
`contracts/realization-envelopes/libvirt-qemu/guest-certified-appliance-v1.json`):

| Concern | Disposition | Source |
| --- | --- | --- |
| topology | realized | daemon-observed |
| architecture | realized | guest-observed |
| image | realized | daemon-observed |
| resource-allocation | realized | guest-observed |
| network | realized | guest-observed |
| content-placement | realized | guest-observed |
| account-placement | realized | guest-observed |
| feature-binding | unsupported | none |
| service | realized | guest-observed |
| acl | unsupported | none |

The honesty is two-directional: content, accounts, resources, network, and a
service are certified from inside the guest, while `feature-binding` and `acl`
are disclosed `unsupported` rather than faked. One canonical guest is not claimed
to prove every image, OS, or ACL mechanism.

## How guest-certified realization works

For the guest-certified configuration, realization enters through the same
production path a real deployment uses
(`RuntimeManager.plan` → `RuntimeControlPlane.submit_provisioning` →
`LibvirtProvisioner.apply` → the native driver). A direct driver call, hand-built
spec, or fake connection can exercise a leaf but cannot satisfy the native-proof
gate. Then:

1. **Boot.** A guest-observing BusyBox appliance
   (`raes_backend_libvirt.guest_appliance`) is booted on real QEMU. It realizes
   the bounded seeded content, account, and service placements from the plan.
2. **Read back from inside.** The appliance reads its *own* realized state —
   `nproc`/`/proc/meminfo`, `ip addr`/`/sys/class/net`, in-guest file
   `sha256`/mode, `/etc/passwd` posture (no credential material), and service
   process + bound port — and reports bounded, line-oriented facts over a
   credential-free file-backed serial channel
   (`raes_backend_libvirt.guest_transport`). No SSH, no password, no general
   command runner.
3. **Freshness.** A fresh per-run challenge is injected via the kernel command
   line and must be echoed back; a cached or prior-boot report cannot pass.
4. **Stage and compare.** The observer
   (`raes_backend_libvirt.guest_observation`) runs ordered stages (daemon →
   transport → initialization → concern probes → cleanup); a later stage never
   repairs an earlier one. Each concern becomes a `RealizationObservation` at
   `guest-observed` provenance, compared to the requested realization. Failures are
   distinct, stable, redacted `Diagnostic` codes naming the safe RAES address and
   observation level — never raw XML, UUIDs, host paths, URIs, or credentials.
5. **Commit eligibility.** The provisioner cannot return success, changed
   addresses, or a committed snapshot until all required daemon **and** guest
   observations pass. Every failure preserves the baseline snapshot.
6. **Teardown.** Cleanup runs after every attempt (including failures) and
   verifies domains, networks, filters, disks, seed media, and probe artifacts
   are gone; residual state fails the run.

## Keeping claims honest

The envelope, the observer, the falsification tests, and the evidence artifact
move together, so an envelope cannot drift into overclaiming:

- The evidence producer (`raes_operations.libvirt_evidence_run`) binds each guest
  observation to the control-plane operation, the fresh challenge, the selected
  envelope/configuration and appliance digests, and a `sha256:` correlation from
  the ownership-verified native identity, then runs the shared redaction and
  binding validators (`raes_operations._evidence_run_validation`) *before* the
  artifact is written.
- **Native-proof boundary.** A guest-certified artifact is `certifying` only when
  the production driver/transport produced it. An injected fake driver may
  exercise orchestration but is marked non-certifying, so a simulation can never
  be published as a real proof.
- **Falsification-first** ([ADR-021](../../decisions/adrs/adr-021-falsification-first-claim-evidence-gate.md)):
  the hermetic test suite feeds wrong addresses, tampered digests, dead services,
  clamped memory, stale/duplicate facts, and incomplete cleanup, and asserts each
  is detected and fails the run.
- Guest facts are captured evidence, kept in the validated artifact rather than
  the runtime snapshot, per the observability/evidence-plane separation
  ([ADR-066](../../decisions/adrs/adr-066-observability-evidence-plane-separation.md)).

## Reproducing the proof

The hermetic tests run in the default `nox verify` graph and never require
libvirt, KVM, privileges, or network. The native-proof gate is a separate,
opt-in run:

```sh
# Operator/self-hosted command: boots the guest-observing appliance against a
# real libvirt/QEMU daemon and emits a validated evidence artifact.
raes libvirt techvault guest-certify \
  --scenario examples/scenarios/techvault-guest-certified.sdl.yaml \
  --project-dir . --run-id guest-proof-1 --yes
```

The equivalent opt-in pytest is gated on `RAES_REAL_LIBVIRT_URI`, and
`tools/real-daemon/run_aws_guest_certify.sh` runs the whole thing on an
ephemeral, self-cleaning host. A committed real-daemon evidence report lives
under `tools/real-daemon/evidence/`.

## Limits

One canonical guest-certified appliance proves a bounded concern set on a single
appliance. It does not prove all images, operating systems, service kinds, or
ACL mechanisms; those are disclosed `unsupported` rather than approximated.
Broadening coverage is downstream work (issues #716 conformance and #717 final
scenario certification), which consume these guest observations.
