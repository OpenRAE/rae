# Independent multi-operation crossing construction

Issue [#1395](https://github.com/OpenRAE/rae/issues/1395) adds
`participant-crossing-multi-operation-dpbb-finite-v1@rev1`. The
[governed rules](../../../specs/formal/participant-semantics/participant-crossing-multi-operation-models.md)
define at most two fresh identities, complete synthetic requests, separate
history/policy coordinates, cached-result observations and bounded response
loss with clean P1 restart. It introduces no runtime retry or enforcement change,
mandatory author annotation, author-time proof or production checker dependency.

## Construction and independence

The abstract authority is `multi_abstract.py`: its own total policy table,
request/body/policy/history retry predicate and semantic completion rules.
The concrete authority is `multi_concrete.py`: independently authored validation,
current candidate resolution, deny-first gates, scoped claim comparison,
record preparation, atomic commit and effect/result stages. Their worklists
are independently implemented. They share only closed vocabulary, dataclass
plumbing and inert graph storage. Neither imports the other, a shared policy
or replay oracle, executable runtime code or an equivalence witness.

Source dependency checks, transition ownership, complete closure and domain
checks support review; distinct names or hashes alone do not establish
independent derivation. The mandatory pre-publish construction review examines
these authorities. Construction is not an equivalence check or an independent
reproduction of a positive theorem.

The [manifest](../../../specs/formal/participant-semantics/crossing-models/multi-rev1/manifest.json)
records exact state/semantic-transition/projected-transition/initial counts,
all domain cardinalities, identity mapping, profile/catalog/projection pins,
runtime/contract source inventory and artifact digests. Both graphs are complete
reachable fixed points, with unlimited visible retry cycles and a fixed fresh
operation budget. No sampled schedule, depth truncation, saturation or wraparound
is used. The private ledger is a formal coordinate, not a production store.

## Reproduce and drift check

| Authority | States | Semantic transitions | Initial states |
| --- | ---: | ---: | ---: |
| Abstract SEM-230 rev1 | 14,230 | 30,165 | 1 |
| Concrete API-423/RUN-319 rev1 | 52,334 | 68,269 | 1 |

The finite base domains include two keys/operations/receipts, two policy cuts,
six input classes, two request-body commitments, three crossing heads, three
effect counts and four knowledge masks. The manifest enumerates every domain.

Use a fresh interpreter in the trusted delivery checkout, whose sources remain
unchanged during collection:

```sh
RAES_REQUIREMENT_UID=SEM-232 PYTHONPATH=implementations/python/packages \
  uv run --project implementations/python --frozen \
  python -m implementations.formal.participant_crossing --profile multi
```

The default is read-only comparison against the complete retained bundle.
`--write` creates an absent bundle after all checks, or accepts an identical
bundle. It refuses changed published bytes. No network, checker, credentials or
environment-selected semantics are used. Fixed repository outputs retain the
trusted-parent and exclusive-writer publication boundary.

AUT is stored in ordered line-aligned `.part` artifacts to respect the existing
500 KiB per-file repository limit. Concatenating **exactly** the manifest's
`aut_parts` in order yields the complete standard AUT byte stream, whose digest,
byte length and readback counts are separately pinned. An individual fragment
is not a complete model. Original semantic edges have ordered JSON pages.
State maps retain column names and original values; their ledger column indexes
the model's digest-bound ledger dictionary. Pages include their first ordinal.
This is lossless nonsemantic encoding, not a state-space quotient.

The published draft behavioral-profile schema admits the new closed variant
alongside the original DPBB and opacity variants. Both-carrier joins, exact
loaders and incompatible opacity rejection remain mandatory. Old payload
canonical identities are unchanged; an old reader rejects the new variant.
The sharded schema publication ledger records the additive contract change.

## Relationship to #971 and #972

The #971 profile bytes, independently owned rev2 model sources, AUT/state maps
and manifest remain unchanged. Shared contract/export changes honestly invalidate
the old bundle's current-source comparison. They do not overwrite its historical
pins. Its full recorded source closure reproduces at
`a391904a7ceaced035be2c90d54e2660679de6bb`; current sources still reconstruct
identical rev2 graph/state-map bytes, and the retained artifact digests are
checked. The #971 CLI reports drift in the newer checkout. The existing
#972–#976 target remains rev2; this new profile needs its own mapping, comparison,
negative-result and independent-reproduction admission.

Runtime anchors include exact `OperationAdmissionContext` and `_semantic_request()`
binding, `_require_same_idempotency_replay()` accepting decision or result heads,
unresolved-policy failure without participant facts, current caller authorization,
and actor/scope status readback. The synthetic head vector fixes all other
writers. Preparation callbacks can precede incumbent resolution; replay makes
no zero-callback or exactly-once external-effect claim.

Uncovered realization paths include transformed-ingress revalidation, actual
multi-commit action authorization/terminalization, final-sink flow control,
opacity/modular control, mixed-runtime composition heads, supervisory handoff,
retrieval projection, directed delivery and inject dispatch, P2 authorization
and HTTP envelopes, admission denials, ephemeral/legacy retry proofs, concurrent
providers, interrupted effects, uncertain commits, indeterminate reconciliation,
status-read response loss and P0 run loss. Existing action/restart fixtures disable
final-sink flow control; they are runtime behavior anchors for that fixture,
not evidence of default governed enforcement.

Relevant model/profile/projection, contract, retry/recovery or runtime-source
drift invalidates affected current mapping evidence until reviewed and rechecked.
Hashes detect drift; they do not establish correspondence. A status read after
key conflict does not deliver a participant payload. A fresh key after response
loss may duplicate an already completed effect.

SEM-232 remains DRAFT. Model construction establishes no bisimulation, live
realization, backend conformance, noninterference, opacity, arbitrary-history,
latency, throughput, concurrency or universal recovery result. SEM-230/API-423/
RUN-319 retain their ACTIVE contracts and adoption/enforcement boundaries.
