# Independent Crossing Model Construction

Issue: [#971](https://github.com/OpenRAE/rae/issues/971).

The executable profile is `participant-crossing-dpbb-finite-v1@rev2`.
It covers one fresh operation and its retries. It does not change runtime retry
behavior, require scenario annotations, or run a checker on participant requests.
[Multiple operations](https://github.com/OpenRAE/rae/issues/1395) require their
own profile. The [formal rules](../../../specs/formal/participant-semantics/participant-crossing-models.md)
resolve the original design's request reuse, head exhaustion, decision/change
ordering and crossing-completion ambiguities. The user approved this scope.

## Construction evidence

| Model | States | Transitions | Initial states |
| --- | ---: | ---: | ---: |
| SEM-230 abstract, rev2 | 88 | 107 | 1 |
| API-423/RUN-319 concrete kernel, rev2 | 178 | 197 | 1 |

Both are complete reachable fixed points, not depth-limited samples. The
[manifest](../../../specs/formal/participant-semantics/crossing-models/rev2/manifest.json)
records domain counts, initial coordinates, source/profile/catalog identities
and artifact digests. Each model has an AUT graph and a canonical JSON state
map retaining the original hidden label classes. The only checker tau name is
`internal`; no native tau encoding is accepted.

The complete base domains have cardinalities participant=1, audience=1,
controller=1, episode=1, request=1, policy-cut=2, input=5, decision=6, replay=3,
delivery=4 and history-head=4. Intent has 31 ambient values (none plus the
request/input/cut/replay product); last has 13 (none plus request/cut/decision).
Abstract phase has 5 values; concrete phase has 9, gate and capability each 3.
Reachability removes inconsistent products. h2/h3 are declared but unreachable
because only one fresh logical result can commit. No history counter saturates.

## Independent construction review

| Boundary | Abstract authority | Concrete authority |
| --- | --- | --- |
| Decision | Own total cut/input policy table | Own deny-first gate and capability branches |
| Completion | Visible decision or observation records the abstract result | Prepare then atomic commit, followed by delivery/observation where applicable |
| Retry | Recorded abstract result; later-cut rejection | Intent/cut validation and reuse of durable result; no second commit |
| Exploration | Deque-based reachable closure | Separate cursor/worklist closure |

The model modules import only the shared closed input vocabulary, dataclass/
collection plumbing and inert graph storage. Neither imports the other, a
shared policy oracle, runtime executable code, or the candidate equivalence
witness. The exporter checks static dependencies, source identities and
transition ownership. These mechanical checks support source review; hashes
alone do not establish independent derivation.

The concrete source inventory names API-423 occurrence/context validation and
RUN-319 gate, mediation, record, commit, history-head, boundary, egress and store
files. Their hashes detect changes requiring renewed mapping review. This
model does not claim to include every live gate, transformed-ingress
revalidation, crash state or backend interaction. #972 must establish the
mapping for a selected runtime configuration. An exact retry returns the
original runtime receipt without executing the action again; model outcome
observations must not be interpreted as a second effect. Runtime history can
advance without a policy revision change; that interaction belongs to #1395.

## Reproduce and check

From a checkout of the delivery revision, use its frozen Python environment:

```sh
PYTHONPATH=implementations/python/packages uv run --project implementations/python --frozen \
  python -m implementations.formal.participant_crossing
```

The default command reconstructs both graphs and compares all retained bundle
bytes and digests. It does not update expectations. To create the bundle in a
clean checkout where the output directory is absent, pass `--write`. Publication
validates all inputs and builds all files before a single directory rename.
An existing identical bundle is accepted; an existing changed bundle is refused.
Model changes require reviewed source/profile identities and a new published
revision. The first delivery's source identity is a SHA-256 commitment to the
exact source inventory, avoiding a self-referential Git commit hash.

No network, checker executable, credentials or environment-selected model is
used by export. `PYTHONPATH` selects the checkout's installed source packages;
it does not select policy behavior. The input domains are fixed by the profile.
Malformed JSON, special files, symlinks, oversized inputs, unknown labels,
truncated models, shared transition authorities and digest drift fail closed.
CLI failures use a fixed message without rejected input or host paths.

## Contract compatibility and assurance

The draft `behavioral-relation-profile/v1` schema adds a discriminated binary
profile variant. Existing opacity profile payloads and their canonical digests
retain their shape; old readers reject the new variant. No compatibility claim
is made for old readers consuming the new DPBB profile. The incumbent local-join
and claim-resolution invariants validate the new variant, including both
carriers. Existing opacity-only consumers reject it through their admission
and claim checks. Valid/invalid fixtures exercise the published schema and its
reference model, and the schema publication entry records the change.

SEM-232 remains DRAFT: model construction is implemented, while its conditional
equivalence result and independent reproduction are not established. SEM-230,
API-423 and RUN-319 retain their existing ACTIVE contracts. This package adds
bounded formal representation and construction evidence, not new enforcement.
No equivalence, live-runtime realization, backend conformance, noninterference,
opacity, latency, probability, concurrency or controller-handoff result follows.
