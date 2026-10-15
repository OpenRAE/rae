# Author execution and recovery requirements

The optional SDL `execution_policy` section publishes complete, scoped
requirements under `execution-policy/v1`. See the
[normative specification](../../../specs/sdl/execution-recovery.md) for field
meaning and supported scope owners.

Existing documents need no edit. Omission grants no new permission to repeat
effects and keeps existing workflow retries and trial cleanup semantics.
Do not translate transport durability or service restart settings into author
permission for another scenario effect.

To make a single invocation explicit:

```yaml
name: one-shot
nodes:
  host: {type: compute, os: linux}
execution_policy:
  default:
    policy_id: one-invocation
    revision: '1'
    response: terminate
```

This complete default has one total attempt and `after_effect_policy: disallow`.
The selected provider must explicitly support the policy. Existing backend
manifests omit that support and therefore reject the new request; removing a
diagnostic or silently dropping the field is not a migration strategy.

For bounded retries, choose `response: retry`, set the existing `retry` record
with total `max_attempts`, and declare `budget_ms`, `effect_classes` and resolving
`evidence_refs`. Retry after an absent effect can use `disallow`; applied/partial
effects need a supported explicit posture. Backend idempotency alone cannot
override a one-invocation policy. A narrower scope replaces the whole policy,
so restate every required choice rather than expecting field inheritance.

Import expansion binds module defaults and references to the imported
definition. Explicit node/application policies can override template policies;
an unrelated caller default cannot. Plan inspection shows the chosen policy,
governing scope, version/revision and materialized evidence requirements.
Nested imports preserve those policies through exported/private declaration
renames and rewrite node binding keys together with their policy pointers.
All three native phase plans and HTTP plan reconstruction preserve them, and
policy-only edits change their digests. Recovery must use the admitted plan,
not recompute policy from an edited source document.

`resume`, fresh-trial selection and reset/compensate postures are preserved as
requests but rejected by the current native carrier until their owning
continuation/allocation/cleanup authority can be established. A fresh-trial
limit is distinct from operation attempts. The feature adds neither an
automatic recovery engine nor an experiment requirement for ordinary scenarios.

Providers using the optional
[backend operation protocol](backend-operation-supervision.md) can use
`require_backend_execution_policy_admission` after resolving the native command
artifact. It verifies the exact native commitment and declared policy support
before requiring current contextual willingness. It performs no effect call or
authorization. Keep the existing authorization and terminal-result gates.

Schema consumers should update the affected draft SDL, native plan, backend
manifest, operation capability and embedding schemas together. Fields remain
closed and optional, and omission preserves existing wire payloads. The
published schemas and per-contract publication ledger include the extension
and portable semantic-invariant annotations; JSON Schema shape validation alone
does not execute those semantic obligations.
