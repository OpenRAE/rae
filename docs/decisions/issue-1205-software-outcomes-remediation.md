# Software outcomes and acquisition: remediation brief

Issue: [#1205](https://github.com/OpenRAE/rae/issues/1205).
Design status: architecture assessed; repository boundary confirmed by the maintainer.

## Gap claim

The #1198 inventory audit and #1200 reproducer distinguish an intended installed
component from its installation recipe. `RuntimeSoftwareComponent` already
permits an omitted version, but offers no ordered version domain or explicit
acquisition refinement. `RuntimePackage.repository` is an APT-only final-state
contract. Neither a free-form `source` label nor accepting another manager name
establishes an installation route or an enrolled, ready agent.

The motivating downstream case exposed a generic expressivity gap. Its concrete
topology and live acceptance belong downstream. RAE owns semantics, contracts
and conformance: no scenario-specific inventory, installation workflow, backend
adapter or live deployment qualification is introduced by this change.

## Existing surface audit

- `runtime.software_components` and ADR-034 own node-local component identity
  and required presence; they are the canonical software requirement surface.
- `runtime.packages` and #847 own exact distribution-package coordinates. Their
  APT v1 repository remains required final state, including its trust binding.
- `runtime.applications`, services, forwarding agents, monitoring managers,
  propositions and tasks own interaction and behavior. Component presence does
  not establish those outcomes.
- Filesystem inventory, processes, local identity, network and service-manager
  units describe their respective final-state facts, not installation recipes.
- `source.build`, artifacts and module distribution concern delivery or build
  provenance. They cannot silently become runtime repository configuration.
- #1202's typed domain profiles provide namespace, revision, content identity,
  offline resolution and operation-specific support. #1204's plan profile host
  authenticates required profile constraints and independent backend support.
- #1203/#1204's recursive relation, explicitness provenance, source-occurrence
  mapping and preparation/result admission preserve binding leaves and inherited
  openness. Software must use that common enforcement boundary.
- ADR-064/066 and #1212/#1112 own selected observation demand and capture
  admission. Profile-definition integrity is distinct from a package digest or
  experimental acquisition provenance.

## Lineage and precedent

ADR-034 separates component identity from package rows and invocation. ADR-033
classifies facts by semantic locus. ADR-105 and the #1201 candidate contract
explicitly select `runtime.software_components` and keep application versions
distinct from package versions. #847 rejects source-label semantics; its exact
APT shorthand must retain its documented meaning. The repository's language
extensibility research connects this decision to CUE conjunction, JSON Schema
required vocabularies, namespace-aware extension handling and PROV's distinction
between derivation and specialization. This extends existing owners.

## Literature and practice

[Debian Policy §5.6.12](https://www.debian.org/doc/debian-policy/ch-controlfields.html#version)
defines epoch, upstream version and Debian revision, with its own ordering.
[RPM's version specification](https://rpm.org/docs/6.0.x/man/rpm-version.7)
defines EVR and distinct segment, tilde and caret rules. These support explicit
comparison relations, not lexicographic ordering or equating application and
package versions. Unsupported relations must be refused honestly.

[Wazuh's agent connection documentation](https://documentation.wazuh.com/current/user-manual/agent/agent-management/agent-connection.html)
separates enrollment and active connection from installation. This motivates
generic separation of presence from behavior obligations. Concrete connection
and telemetry qualification remains a downstream responsibility.

## Alternatives

1. Evidence-only documentation leaves the software refinement gap unresolved.
2. Adding only a DNF member to the package repository union preserves compulsory
   package coordinates and fails the private-profile and internal-route cases.
3. A new software inventory duplicates ADR-034 and creates reconciliation and
   identity ambiguity.
4. Extend component requirements and reuse the recursive/profile contracts for
   selected refinements, with an explicit compatibility path for package rows.
   This is the design direction under review.

## Architecture constraints

Minimal component declarations must not acquire manager, version, repository,
digest or evidence requirements. Explicit versions and selected acquisition or
final repository constraints bind independently. Shared repository/trust identity
must have an owning definition and validated references. An insecure described
target is a fact or constraint, never operator acquisition authorization.
Parsing and comparison perform no network access, credential lookup or plugin
loading. Unknown required semantic support refuses before mutation.

## Documentation defense

The implementation must document authoring, canonical ownership, compatibility,
version relation limits, final-state versus acquisition identity, private typed
profiles, backend capability limits and independent reporting/demand. Public
schema changes require a matching publication ledger and generated bundle.
Global release and authoring-tool migration remain #1210's responsibility.

## Verification plan

Use red/green tests for sparse software, independently selected version domains,
legacy APT equivalence, shared references, private and insecure descriptions,
and unsupported admission. Exercise parser/compiler/portable-plan/runtime
boundaries, including rejected results retaining the predecessor. Qualify the
generic behavior composition and the Kali refinement ladder, with negative mutations
and explicit evidence-strength labels. Test internal routes without experimental
telemetry and separately selected reporting detail. Update SEM-218 traceability,
run targeted regressions, repository policy and requirement governance, then the
configured completion, review, pre-commit, CI and Sonar gates.

## Clause mapping

The following map records RAE implementation evidence, not native deployment
qualification. Paths are relative to `implementations/python/`.

- [x] SEM-218 binding declarations versus delegated concerns:
  `packages/raes_processor/compiler/software_constraints.py:14` and
  `tests/test_issue_1205_software_carriage.py:50` preserve exact/range conjunction.
- [x] SEM-218 unsupported requirements must not be approximated:
  `packages/raes_processor/semantics/realization_support.py:48` and
  `tests/test_issue_1205_software_carriage.py:66` reject unsupported relations.
- [x] Issue: software outcome without manager, repository or distribution
  version: `packages/raes/runtime_software.py:66` and
  `tests/test_issue_1205_software_carriage.py:32`. Behavior retains existing
  service/condition/proposition owners; component identity is not behavior proof.
- [x] Issue: progressive explicit private acquisition refinements:
  `packages/raes_processor/compiler/software_profiles.py:104` and
  `tests/test_issue_1205_software_profiles.py:31` use independent pinned admission.
- [x] Issue: transient route versus final shared repository/trust identity:
  `packages/raes/runtime_software_repositories.py:67` and
  `tests/test_issue_1205_repository_state.py:16` establish one shared identity;
  final absence and dangling returned links are also tested in that file.
- [x] Issue: distinct application/package versions and exact shorthand:
  `packages/raes_processor/compiler/software_constraints.py:14`,
  `tests/test_issue_1205_package_identity.py:64` and
  `tests/test_issue_1205_profile_execution.py:96` retain exact coordinates and
  require a defined installed correspondence relation before effects.
- [x] Issue: route qualification within the maintainer-approved repository
  boundary: `tests/test_issue_1205_software_profiles.py:111` exercises APT,
  RPM, private APT, private, cache/offline and image values without advertising
  native execution support. Existing #1204 profile preparation/result tests
  and the software profile execution test qualify the generic effect gate.
  Product enrollment/readiness/telemetry journeys are not RAE acceptance work.
- [x] Issue: insecure described state grants no acquisition authorization:
  `tests/test_issue_1205_software_profiles.py:196` checks explicit insecure
  repository/trust descriptions and unsupported target admission.
- [x] Issue: unrestricted, exact, older/newer and range software versions:
  `packages/raes_contracts/software_versions.py:68` and
  `tests/test_issue_1205_software_versions.py:18` cover independent predicates,
  boundaries, incomparable values, semantic identity and composition.
- [x] Issue: Kali refinement ladder preserves freedom and explicit tools:
  `tests/test_issue_1205_kali_ladder.py:12` uses the existing governed OS
  extension mechanism; required/optional tools use the common recursive relation.
- [x] Issue: internal routes need no authored profile, digest or experimental
  provenance: `tests/test_issue_1205_software_profiles.py:82` and
  `tests/test_issue_1205_software_carriage.py:32` verify sparse authoring.
- [x] Issue: separately selected software/OS reporting without installation
  telemetry: `tests/test_issue_1205_software_reporting.py:14` exercises the
  existing observation-demand lifecycle, truthful basis and retention/export
  prohibitions. The overlay's whole-surface audit led to reusing these owners,
  not introducing a software-specific observation protocol.

## Repository evidence maintenance

The [ADR-034 amendment](adrs/adr-034-runtime-software-component-inventory.md)
records the decision in-band under ADR-059, with matching amendment and canonical
pin records. Its historical terminology classification retains the same three
occurrences, with the whole-file hash updated for the recorded amendment.

Source-pinned repository gates require new immutable captures when the
implementation changes. Specification coverage release 8.0.0 and formal
semantic-validation release 10.0.0 replay the existing protocols for this
change. Their claims remain bounded to those protocols, with two compiler
result-digest deviations recorded explicitly. Historical captures are unchanged.
The dependency closure also updates the tooling-policy fingerprint; host
qualification records retain their explicit `not-run` status.

The requirement-ownership mapping names SEM-218 separately from the general
semantics phase because its accepted contract changes also require publication,
dependency-closure and current-source evidence maintenance. The original
prerequisite gate remains intact; backend implementations, downstream scenarios
and unrelated control-plane contracts remain outside this ownership mapping.
