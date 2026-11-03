# Shared-primitives completion for issue #1779

PR #1820 is the single delivery for issue #1779. The existing random-stream
and ingress work is incorporated through real merges, preserving its history.
The Python implementation and published schemas remain unchanged.

## Package ownership

| Package | Public responsibility | Standard or existing implementation |
| --- | --- | --- |
| base/clock | Injected UTC wall clock; one system-clock owner | time, callable interface |
| base/timestamp | Four named timestamp policies and Python-compatible UTC text | time parsing and explicit grammar normalization; governed leap-second dates |
| base/softwareversion | Closed numeric-triplet, Debian and RPM relation identities, bounded predicates | Debian Policy ordering and go-rpm-version; exact big.Int epochs outside library int epochs |
| base/domain | Closed scalar-domain membership and validation | Typed descriptors; exact numeric-type distinctions; softwareversion |
| base/value | Bounded JSON snapshot values, strict unknown-carrier rejection, aggregate budgets | Iterative walk of the ingress JSON value types; no reflection-based serialization or custom marshal callbacks |
| base/fault | Six ADR-116 error categories with errors.Is/errors.As support | Standard error wrapping; stable value-free codes |
| base/logrecord | Value-free records, bounded chains/groups and escaped control characters | log/slog handler wrapping; no library-global logging configuration |
| base/graph | Cycle detection, FIFO dependency order and sorted cyclic components | Iterative traversals; no recursive stack growth |
| base/secretref | Operator-managed secret-reference identity | ASCII grammar and 256-byte bound; no secret resolution |
| base/digest | Published digest-string grammar in addition to SHA-256 rendering | Existing package; standard encoding libraries |

`versions.py` contains schema identifiers rather than comparison behavior.
Their authority remains the published schemas; generated contract bindings in
#1780 own the corresponding Go identifiers. Python's Pydantic base class has
no Go inheritance analogue: closed Go structs and strict ingress/model decoding
replace it. This does not authorize unknown fields or unmodeled digest carriers.

## Security and data flow

Untrusted bytes -> bounded ingress -> closed JSON values -> bounded value
validation -> canonical encoding -> digest. Unsupported Go values are refused
before encoding; no type/module name is substituted into digest bytes.
Version text -> fixed grammar and length limits -> exact epoch comparison ->
installed package comparator -> bounded membership. No version or profile input
selects code, imports, commands, network calls or host inspection.

Clock reads are injected into callers. The only direct wall-clock read belongs
to the system clock implementation and has a narrow documented lint exception.
Logging strips error messages, custom value callbacks and unsafe source paths;
it bounds chains, groups and record lengths before handing records to a host
handler. It never invokes an error's Error method to describe that error.

## Verification

Record accepted values and refusals through Python reference cases. Keep
compatibility changes already approved for ingress explicit in corpus outcomes.
Use exact numeric comparison and independent implemented-command coverage.
Port the timestamp/leap-second/offset, software-version, pointer, graph, logging,
input-bound and digest regression cases. Run targeted tests locally in the
network-free, credential-free sandbox. CI owns complete suites, mutation and
fuzz campaigns. Collect fixes before one consolidated push.

## Dependency sources

- https://github.com/knqyf263/go-deb-version (MIT)
- https://github.com/knqyf263/go-rpm-version (MIT)
- ADR-116, ADR-118, ADR-121 and ADR-122 in this repository.

The evaluated go-deb-version library converts digit runs to machine integers,
which cannot preserve the governed 256-character domain. Its overflow behavior
is unsuitable here. Debian ordering therefore follows the published Debian
Policy algorithm directly, comparing normalized digit strings by length and
lexical order; no machine integer conversion occurs. The RPM adapter strips
and compares epochs exactly before using the maintained library.

Reference: https://www.debian.org/doc/debian-policy/ch-controlfields.html#version

## Public interfaces and invariants

The entry points are `clock.Read`/`System`, the four `timestamp.Parse*`
functions and `Format`, `softwareversion.Installed`/`NewDomain` and its
`Membership`, `domain.In` with the closed descriptor types,
`value.Validate`/`Canonical` with `Default`/`Runtime`/`Plan` limits,
`fault.New`/`CategoryOf`, `logrecord.NewHandler`/`Describe`/`Escape`,
`graph.HasCycle`/`Order`/`Cycles`, `secretref.Valid`/`Validate`, and
`digest.Valid`/`SHA256`.

The change is FM1: local validation, typed membership, uniqueness and graph
mechanics. It adds no workflow or planner semantics. The invariants are:

- A comparison uses an installed version implementation only when every
  semantic-identity field matches. Epochs and Debian digit runs never narrow
  to a machine integer. Unsupported bounds retain the 256-character limit.
- Scalar membership distinguishes Boolean, integer and floating-point values.
  Numeric conversion overflow is a refusal, as in the reference.
- Every value walk has finite depth, node, operation, member and byte budgets;
  cyclic input cannot bypass them. Only model owners grant document limits.
- Canonical encoding refuses unknown carriers before any callback can run.
- Graph traversal uses explicit stacks; dependency order uses a FIFO queue;
  all externally observed ordering is deterministic.
- Logging never invokes foreign error/value callbacks, includes exception
  values or source paths, or configures a global handler. Message escaping
  preserves the reference's 8,192-character ceiling.
- Time reads use the injected clock. Timestamp text retains microseconds and
  authored offsets, including Python 3.14.7's fractional zero-hour offsets.

Python exception tracebacks, exception groups, message interpolation and logger
application setup are language/runtime mechanisms. Go uses typed string
messages and host-owned `slog` setup; the primitive bounds structured groups
and owned error chains and drops source PCs. It never extracts foreign stacks.
The reference's privacy and control-character safeguards remain enforced.
