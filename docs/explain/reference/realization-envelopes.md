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
(`raes_contracts.vocabulary.ObservationStrength`):

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

## The published libvirt-qemu configurations

The `contracts/realization-envelopes/libvirt-qemu/` envelopes describe three
material configurations. RAES 7.0.0 was the last release to bundle the libvirt
backend that produced them. Issue #967 removed that backend
([ADR-115](../../decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md)).
The envelopes stay as published contract data. A backend that claims one of
them must supply its own realization and evidence.

- **`generic`**: a qcow2/cloud-init driver. Its concerns are `driver-reported`.
- **`techvault-appliance`**: a generated BusyBox initramfs appliance. It reads
  topology, architecture, image, resources, and network back at
  `daemon-observed` provenance. Guest concerns are `unsupported`.
- **`guest-certified-appliance`**: a guest-observing appliance that certifies
  concerns from **inside** the guest.

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

## Keeping claims honest

The envelope, the observer, the falsification tests, and the evidence artifact
move together, so an envelope cannot drift into overclaiming:

- A guest-certified claim must come from the production apply path
  (`RuntimeManager.plan`, then `RuntimeControlPlane.submit_provisioning`, then
  the backend's provisioner). A direct driver call, a hand-built spec, or a fake
  connection can exercise a leaf. It cannot certify a concern.
- Each guest observation becomes a `RealizationObservation` at
  `guest-observed` provenance. The backend compares it to the requested
  realization. A later stage never repairs an earlier one.
- **Native-proof boundary.** An artifact is certifying only when the production
  driver and transport produced it. An injected fake driver is
  non-certifying, so a simulation can never be published as a real proof.
- **Falsification-first** ([ADR-021](../../decisions/adrs/adr-021-falsification-first-claim-evidence-gate.md)):
  tests feed wrong addresses, tampered digests, dead services, stale or
  duplicate facts, and incomplete cleanup, and assert that each one fails.
- Guest facts are captured evidence. They stay in the validated artifact, not
  in the runtime snapshot, per the observability/evidence-plane separation
  ([ADR-066](../../decisions/adrs/adr-066-observability-evidence-plane-separation.md)).

The backend distribution owns the producer, the native proof run, and its
evidence. Historical libvirt proof records stay in the issue preflights and
research captures. They are not current installation instructions.

## Limits

One canonical guest-certified appliance proves a bounded concern set on a single
appliance. It does not prove all images, operating systems, service kinds, or
ACL mechanisms; those are disclosed `unsupported` rather than approximated.
Broadening coverage belongs to the backend distribution that claims the
envelope.
