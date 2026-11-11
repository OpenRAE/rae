<a id="participant-information-flow-control-migration"></a>

# Adopt governed participant crossings

## Versions and purpose

Source: `Legacy carriers and a runtime without a crossing resolver`.
Target: `SEM-230/API-423/RUN-319 opt-in or required profile at an exact cut`.

## Before you start

Use RAES 11.0.2.
Keep original manifests, snapshots, histories, and reader pins.
The operator needs authority to select the profile.
That authority must also permit installation of its trusted resolver.
Changing the selection can change data release.
It can also change native action admission.
Do not expose administrative credentials or raw histories to participants.

1. Select legacy, opt-in, or required behavior using the adoption phases below.
2. Before admission, check contracts and feature strength.
3. Check caller bindings, evidence owners, and store compatibility.
4. Install the resolver through the existing runtime configuration.
5. Install the exact compiled context there too.
6. Test missing authority and evidence.
7. Confirm refusal before releasing a governed participant view.
8. Keep the crossing record separate from delivery and observation evidence.

Issue #802 adopts the SEM-230/API-423/RUN-319 boundary.
Existing scenarios and participant carriers keep their historical meaning.
So do histories, manifests, and backend profiles. The governing decisions are ADR-061, ADR-075,
ADR-085, and ADR-095.

## Compatibility contract

Check the [producer/reader matrix and carrier inventory](../explain/reference/participant-flow-compatibility.md#compatibility-contract)
before choosing an adoption phase. Accepting a shape alone does not establish semantic compatibility.
It does not establish operational compatibility.

## Adoption phases

Legacy selects no positive participant-policy capability.
It configures no crossing resolver. Existing carriers remain valid under their
historical meaning. Their participant-control posture is unknown or
unsupported.

Opt-in requires the target's applicable API-407 feature strengths and required contracts.
It requires a configured trusted resolver.
Caller and audience bindings must resolve.
Trusted compiled/runtime state must provide the evidence. The shared mediator is mandatory for that selected scope. There is
no per-request legacy bypass.

Required means the selected backend profile requires the applicable features
and strengths. Missing requirements cause refusal at their owning gate.
Required inputs include the resolver, contract, and capability.
They also include binding, policy coordinate, evidence, and compatible store state.
The gate can reject startup, target selection, or the operation.

Downgrade is the existing API-407/RUN-319 policy path, not a migration
fallback. `resolve_participant_feature_support()` requires the exact downgrade
policy and provenance references. It records effective strength, limitations, disclosure, and provenance.
It removes stronger claims. Legacy absence never
authorizes downgrade.

## Data preservation

Never reconstruct an old crossing decision from timestamps or logs.
Do not infer it from views, current policy, or an empty default. Keep source/result identity and digests in their owning carriers.
Keep markings, provenance, evidence, order, limitations, and loss there too. New API-423 records describe only crossings evaluated at an exact governed state cut.
Append them beside incumbent records, not inside them.

The [compatibility reference](../explain/reference/participant-flow-compatibility.md) lists the paired fixtures and their bounds.

Run the focused evidence with:

```console
RAES_REQUIREMENT_UID=SEM-230 implementations/python/.venv/bin/python -m pytest \
  -q implementations/python/tests/test_issue_802_participant_control_migration.py
```

## Rollout and rollback

Roll out by selected backend profile, feature strength, resolver, and trusted scope key.
The key must distinguish run/scenario, participant, direction, and interaction kind. This permits egress-before-ingress or participant-by-
participant adoption without global environment switches.

Before the first governed write, rollback may restore the earlier
manifest/profile/resolver selection and rerun the legacy fixtures. After a governed write, rollback is asymmetric.
Stop or drain new governed work.
Retain a resolver and schema-aware reader.
Keep the append-only snapshot, operation, idempotency, crossing-history, and audit write set. Never delete crossing history.
Never rewrite it as an incumbent carrier.
Never select an older snapshot because it omits governed facts.

No legacy surface is deprecated by issue #802. A later deprecation must use `specs/evolution/deprecation-records.yaml`.
It must name its replacement and notice window.
It must prove that the old surface remains supported. No removal is scheduled.

## Claim boundary

The migration fixtures, parsers, adapters, and runtime tests provide bounded conformance evidence only.
They do not prove native-backend realization or universal noninterference.
They do not establish trace inclusion, equivalence, simulation, refinement, or bisimulation.
They do not establish epistemic equivalence, timed or probabilistic security, model checking, or proof.

## Check the result and recover

Success is a crossing evaluated and committed at its exact governed state cut.
It does not reconstruct historical enforcement.
It does not establish universal noninterference.
Follow the asymmetric rollback rules after the first governed write.
Reconcile pending effects through the original owner before native cleanup.
Read the [crossing schema](../../contracts/schemas/participant-runtime/participant-crossing-occurrence-v1.json)
and [participant boundary explanation](../public/participant-control-explanation.md).
