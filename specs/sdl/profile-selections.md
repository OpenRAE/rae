# Typed selections around built-in profiles

The [domain-profile contract](../../docs/explain/reference/domain-profiles.md)
extends a containing selection without changing the meaning of its built-in
cases. A private profile pins its namespace, identity, revision, definition,
schema and semantic contract. Installing a definition establishes neither
execution support nor participant authority.

## Selection owners

| Selection | Extension | Controls that remain with the existing owner |
| --- | --- | --- |
| `GeneratedArtifact.generator` | `DomainProfileBindingModel` alongside certificate and SSH generators | Output paths, lifecycle, sensitivity, producer-private disposition, read-only consumers and delivery modes |
| `Content.service_materialization` | Shared binding alongside `service-content/v1` and `service-search-index-schema/v1` | Content target and type; the selected built-in cases retain their service, tenant, conflict and readback requirements |
| `Account.materialization_profile` | Optional shared binding | Account owns credentials; mailbox inventory refers to the account |
| `IdentityDomain.profile` | Shared binding alongside Active Directory | Domain/account authority and authored controller/join relationships; DNS and NetBIOS names are required for Active Directory |
| `IdentityFacade.protocol` | Shared binding alongside OIDC | Named service reference and enterprise authority |
| Forest trust type; federation protocol and mapping intent | Shared binding alongside built-in selections | Forest membership, trust direction, federation direction and tenant-claim ownership |
| `ParticipantInteractiveAccess.channel` | Shared binding alongside SSH and RDP | Exact compute target, optional account, starting-account eligibility and duplicate endpoint checks |
| Participant resource kind | `DomainProfileCoordinateModel` alongside the six built-in measures | Existing integer quantity, unit, accounting mode, meter, reset, budget, pool, reservation and evidence contracts |
| Node OS family | Existing governed vocabulary extension | Coupled OS family/distribution/release compatibility; no second OS profile registry |

Strings continue to select the precise built-in cases. An unknown string does
not become an executable protocol or generator. Private selections use the
typed binding or coordinate, including its pinned definition digest.

Facade, federation and interactive-access selections describe intent at their
existing descriptor boundaries. They do not create a native login, trust
operation, credential disclosure or connection grant. Participant operational
control remains with issues #1068–1072 and
[ADR-108](../../docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md).
Typed channel identity survives participant compilation; selecting another
protocol cannot expand `starting_accounts`.

## Provisioning admission

Artifact, service, account and domain selections use the existing
[plan-profile authority](plan-realization-profiles.md). Their binding owner is
the exact `#/resources/<compiled-address>`, with contract
`plan-realization-profiles-v1`, family `resource-realization`, phase `planning`,
use `constraint` and author-supplied provenance. Contexts are respectively
`artifact-generation`, `service-materialization`, `account-materialization`
and `identity-domain`. A domain selection belongs to its existing
`domain-controller-placement` in the same domain; related node and account
topology carriers preserve that binding.

The planner derives exact recursive constraints from the authored value and
uses only the independently configured target context to resolve the pinned
definition. Programmatic authority must agree with the source binding and its exact recursive constraint; it may retain unrelated programmatic bindings. A
missing definition, unsupported semantic contract, changed target context,
wrong owner or contradictory selection fails before mutation. Capability
coordinates advertise candidates; the existing preparation and execution
checks still require granular operation support. Selected public bindings
remain typed in results, snapshots and requested reports.

Profile values have the selected schema's meaning. Core does not infer service
readback fields from arbitrary private values. The two built-in service
materialization cases retain all their existing readback and state ownership
rules. A backend claiming another semantic contract must implement its
parameters and verification at the existing profile validation boundary.

Module composition qualifies compiled resource owners and source-pointer owners
through the existing symbol map, including nested bindings. Moved owners gain deterministic, bounded host-local binding IDs so repeated imports remain distinct. The
`account-materialization` host reserves `mailbox_ref` as a governed mailbox
reference and qualifies it with the owning node; mailbox inventory also retains
its qualified `account_ref`. Other private values and definition coordinates
are preserved. Core does not rewrite arbitrary strings inside private schema
values or accept a dangling owner as authority.

## Protected account/mailbox reference case

The reference target installs `account-mailbox-materialization/v1` semantics.
Its public value contains only `mailbox_ref`. That reference selects a mailbox
under `nodes.<node>.runtime.mail_services.<service>.mailboxes.<mailbox>` whose
`account_ref` resolves to the owning account placement. The top-level account
retains the [credential-binding contract](account-credential-bindings.md): one
primary password fixture, including an intentionally empty fixture, plus
optional operator credential references. No second authored credential store
or action language is introduced.

An explicitly configured `InProcessMailboxSink` independently authorizes the
exact account/mailbox pair. The reference provisioner checks the selected
semantic contract, account posture, mailbox join and sink authorization before
driver mutation. Every credential-bearing account on this target must have exactly one admitted materialization owner. Only this protected sink receives fixture material. It keeps
private authentication state, verifies candidates, retains operator references
without resolving them, replaces old mailbox state on materialization and
cleans it up when the account is deleted. It is an in-process reference
demonstration; Brad-Edwards/aptl#668 owns docker-mailserver realization and the
service smoke test.

The demonstrated mailbox inventory supports enabled user mailboxes with
password fixture authentication. General mail-service configuration,
alternative account authentication, mailbox roles and domain/store/local-user
links require other installed semantics. Unsupported posture fails before
mutation. For a mailbox-only inventory with explicit profile ownership, that
profile owns verification; the compiler retains the exact inventory constraint
without inferring a guest mail-server readback. Other mail-service inventory
retains its existing verification requirements. Explicit experimental
observation and evidence declarations remain independent.

Fixture values, operator reference identifiers and authentication verifiers
are absent from generic plan projections, persisted snapshots, APIs, reports,
diagnostics and logs under the credential projection boundary. They must not
be copied into public profile values, definitions or provenance. Low-level
backend calls remain inside the protected execution boundary defined by the
credential contract; callers publish only the admitted runtime result.

## Private generation and resource accounting

The reference target also installs `public-seed-digest-artifact/v1`: its public
`seed` produces ASCII SHA-256 hex bytes. Definitions in an independently
configured private namespace select these semantics without adding a core
generator enum member. The reference consumer projection returns only an
explicitly selected output for the exact consumer node. Producer-private
outputs remain inaccessible. The reference implementation supports mount
delivery; environment consumers require a backend that supports that mode.
Outputs and projections are backend state, not captured specimen obligations.

A private resource coordinate resolves to
`participant-resource-measure/v1` semantics. The host constructs the existing
binding from the quantity's unit, accounting mode, meter reference and reset
mode. Independent namespace, schema and semantic support must admit all four.
The configured pool must support the exact measure and at least one admitted
reset mode. Each demand is checked again against its actual reset mode.

The existing reservation and measured-settlement ledger enforces capacity,
generation, pool identity, fairness and evidence. The six built-in dimensions
retain their original units and completeness rules; adding a private measure
does not add a compulsory dimension to every participant policy. A profile
does not add a new accounting algorithm, unit conversion or reset mode.

## Complete abstract model

This model needs no concrete generator, identity mechanism, profile definition
or capture declaration:

```yaml
name: abstract-model
nodes:
  host:
    type: compute
```

Open choices remain with the backend. Merely using an internal generator,
identity setup or resource mechanism creates no authoring or capture duty.
Executable examples and rejection cases are in
[`test_issue_1208_profile_selections.py`](../../implementations/python/tests/test_issue_1208_profile_selections.py),
[`test_issue_1208_profile_boundaries.py`](../../implementations/python/tests/test_issue_1208_profile_boundaries.py)
and [`test_issue_1208_resource_profiles.py`](../../implementations/python/tests/test_issue_1208_resource_profiles.py).
