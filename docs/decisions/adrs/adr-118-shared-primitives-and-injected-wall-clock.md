# ADR-118: Shared Primitives and an Injected Wall Clock

## Status

accepted

## Date

2026-10-31

## Classification

Classification: FM2
Required artifacts: ADR invariant list (Decision §5), unit tests (each shared function and each wall-clock owner), differential tests (graph functions against the replaced algorithms on every small graph), fixed byte and digest vectors, structural ownership test
Waivers: none

The decision moves dependency-graph mechanics into a shared module.
It keeps every graph result, digest, timestamp and message.

## Context

Issue #1710 found local copies of six primitives in the packages:
JSON Pointer token escapes, sorted JSON text, SHA-256 digests, graph algorithms,
the current UTC time and timestamp parsers.
The copies use different options, so equal-looking code gives different bytes.
Persisted records, evidence and signatures contain those bytes and their digests.

Nineteen runtime modules import the private `_utc_now` of one module.
Thus a test cannot replace the time without a patch of each private alias.

## Decision

### 1. One public owner for each primitive

Each primitive has one public module in `raes_contracts`, the lowest package layer (ADR-036):

| Primitive | Owner |
| --- | --- |
| JSON Pointer tokens (RFC 6901) | `raes_contracts.json_pointer` |
| RFC 8785 bytes and digests | `raes_contracts.canonical` |
| Sorted `json.dumps` text | `raes_contracts.json_serialization` |
| SHA-256 | `raes_contracts.digests` |
| Cycle checks, dependency order, cyclic components | `raes_contracts.graphs` |
| Wall-clock reads, UTC text, timestamp parsers | `raes_contracts.timestamps` |

The owners import only the standard library and `rfc8785`.
Domain owners keep projections, framing, validation and error translation.

### 2. Named variants

Where callers need different behavior, the owner gives each variant its own name.
The sorted JSON variants keep their exact `json.dumps` options, because existing digests use them.
New digests use `raes_contracts.canonical`.
A change from one variant to another, or to RFC 8785, changes bytes and needs a digest migration.

The four timestamp parsers keep their own grammar, offset rule and messages.
`graphlib` gives the cycle check and the planner's dependency order.
The shared Tarjan gives every cyclic component, because `graphlib` reports only one cycle.

### 3. Injected wall clock

`raes_contracts.timestamps.WallClock` is a callable that returns an aware UTC `datetime`.
`utc_now` reads the system clock.
These owners read the time through a `wall_clock` argument:

- the runtime control plane and its run contexts;
- the participant scheduler and the tool-action ledgers;
- the local store and the store maintenance entry point;
- the remote operation authority;
- the backend participant runtime base and the stub backend components.

A helper without an owner receives the clock from its caller.
A run uses the clock of its engine and cannot replace it.
Thus experiment deadlines and trial-unit checks read one time source.

Public constructors and entry points default to `utc_now`.
The clock is a trusted Python dependency.
No SDL document, environment variable, HTTP request or MCP call can set it.
There is no global clock setter.
Semantic clocks (ADR-090), monotonic watchdogs and Temporal workflow time stay separate.

### 4. Enforcement

A structural test scans the package sources.
It refuses wall-clock reads, SHA-256 construction, pointer token escapes, sorted compact `json.dumps` calls
and direct `rfc8785` serialization outside their owner modules.
Ruff `TID251` does not carry these bans, because the tooling lint lane checks `tools/` with the same configuration.
The `tools/` primitives are in a later refactor chunk.

### 5. Invariants

1. Each digest and each persisted byte sequence is identical to the value before this decision.
2. Token encoding replaces `~` before `/`, and decoding replaces `~1` before `~0`. The pointers `""` and `"/"` stay distinct.
3. Each graph result keeps its order, members and failure timing.
4. Each parser accepts and refuses the same inputs, keeps the same offset rule and raises the same message.
5. Each owner reads its wall clock at the same place and the same number of times.
6. The owner modules import no SDL, processor, runtime or backend module.

## Alternatives Considered

- A process-wide clock with a public setter. It is global state and allows one clock for each process.
- RFC 8785 for every sorted JSON call. It changes Unicode, key order and number bytes, so it changes digests.
- One parser for every timestamp. The four parsers accept different inputs, so one parser changes admission.
- A third-party graph library. The standard library and the shared Tarjan give the same results without a new dependency.

## Consequences

- New code finds each primitive in one place, and the structural test keeps the copies from returning.
- Tests construct owners with fixed clocks and need no private patches.
- Owner constructors have one more optional argument.
- The legacy JSON variants stay until a digest migration retires them.
