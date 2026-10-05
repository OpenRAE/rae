# Execution and recovery requirements

Status: normative. The optional `execution_policy` section carries author
requirements into native provisioning, orchestration and evaluation plans.
It does not supply an executor, an effect authorization, or a trial allocator.
Its embedded profile version is `execution-policy/v1`.

## Complete lexical policies

`execution_policy` contains an optional `default` and up to 256 `scopes`.
Each scope contains `namespace` (a lexical module path, default empty), `scope`
(a canonical RFC 6901 semantic pointer, default the empty root pointer), and a
complete `policy`. Duplicate namespace/pointer identities MUST be rejected;
the root default and an explicit empty root scope are duplicates.

Resolve policies at the defining module, then the nearest enclosing semantic
pointer. A nearer policy replaces the complete value, including its defaults;
fields MUST NOT be overlaid from another policy. Scope order MUST NOT affect
resolution. An imported module default becomes a scope restricted to that
module; it MUST NOT replace unrelated root or sibling defaults. Imported
clock/evidence references and semantic declaration pointers are rewritten by
the ordinary composition machinery, including nested binding keys and private
declaration renames. A namespace-wide policy spanning exported and private
descendants MUST retain its complete value for every resulting lexical owner.
A workflow call retains the callee's
definition policy. A node feature, condition or inject binding retains its
template's definition policy unless an explicit node/application scope supplies
a complete replacement. Ambient caller defaults MUST NOT rebind a definition.

Supported scope owners are the root; the `nodes`, `features`, `conditions`,
`injects`, `identity_domains`, `accounts`, `content`, `generated_artifacts`,
`persistent_volumes`, `events`, `scripts`, `stories`, `workflows`, `propositions`,
`assertions` and `objectives` sections; their named declarations; node
`features`/`conditions`/`injects` binding collections and entries; and workflow
`steps` collections and entries. Scopes MUST resolve, and module namespaces
MUST identify a surviving declaration owner. Other locations MUST be rejected
until their owning native execution contract carries these requirements.

Omission supplies no permission for a second effect. Existing authored workflow
retry graphs, participant episodes and trial cleanup contracts retain their
own semantics. A workflow's one-invocation policy does not erase its internal
retry steps. An explicit policy on an existing retry step MUST agree with that
step's authored `max_attempts`; implementations MUST NOT multiply attempts
across workflow, operation, transport and recovery layers.

## Policy fields and consistency

| Field | Meaning/default |
| --- | --- |
| `schema_version` | `execution-policy/v1`; other versions fail closed. |
| `policy_id`, `revision` | Author identity and revision; revision defaults to `1`. |
| `response` | Required: `terminate`, `hold`, `reconcile`, `continue`, `retry`, `resume` or `new-trial`. |
| `failure_classes` | Selected classes: `delivery`, `backend-refusal`, `operation`, `intentional-fault`, `continuity`, `invalid-evidence`; default `[operation]`. |
| `validity` | `preserve`, `qualify` or `invalidate`; default `preserve`. A requested response never rewrites an observed outcome. |
| `retry` | Existing execution retry policy: total `max_attempts` including the initial attempt; `after_effect_policy` is `disallow`, `idempotent`, `reset` or `compensate`, with its existing reset/compensation obligation references. Default one attempt/disallow. |
| `effect_classes` | Eligible `absent`, `applied`, `partial` classes; default empty. |
| `budget_ms`, `delay_ms` | Total invocation/repetition budget and fixed inter-attempt delay; budget defaults absent, delay zero. Budgets never reset on restart. |
| `clock_basis`, `clock_ref` | `apparatus` by default; `semantic` requires a resolving authored clock reference. Apparatus basis forbids that reference. |
| `evidence_refs` | Resolving SDL evidence requirement identities; default empty. Requirements are not proof that evidence exists. |
| `on_exhausted` | `terminate` by default, or `new-trial` for bounded retry. |
| `fresh_trial_limit` | Separate positive allocation limit, required exactly when response/exhaustion requests a new trial. |

`retry` response requires more than one total attempt, a positive budget,
nonempty effect classes and evidence references, and delay strictly below the
budget. Other responses permit exactly one invocation and forbid repetition
conditions. Applied/partial repetition requires an explicit after-effect
posture other than `disallow`. Reset/compensation references follow the existing
execution-retry-policy consistency rules. Recovery responses other than
`terminate` require explicit evidence. Class/reference lists MUST be unique.
Limits are strict integers bounded by 2^53−1; policy identifiers/references are
bounded by 256 characters, evidence/cleanup references by 64 entries, semantic
pointers by 4096 characters and namespace depth by 31.

`continue` proceeds after qualifying the selected failure without replaying the
failed invocation. `hold` preserves the context pending evidence/authority;
`reconcile` asks its native owner to establish effects before deciding further
action. `resume` requests continuity of the same admitted work. `terminate`
ends the selected native operation scope. None of these choices implicitly
terminates or restarts a participant episode or experiment trial.

`new-trial` requests allocation through the existing experiment/trial authority
with a new run identity and admitted initialization/isolation. It MUST NOT be
implemented by retrying the old operation or changing its terminal result.
Participants, experiments and physical OT are not mandatory scenario features.
Intentional faults MUST retain their declared class and validity disposition.
Technical idempotency, durability or an IT/OT label never supplies author intent.

## Native plans and admission

Each selected operation carries `execution_policy`: the complete policy,
application `scope`, `governing_scope` (lexical namespace plus `#` plus pointer),
namespace, native `retry_unit` (`native-operation` or `workflow-step`) and exact
materialized `evidence_requirements`. Explicit workflow
step requirements additionally occupy `execution_policy_scopes`. No authored
runtime policy is hidden in arbitrary payload metadata. Projection,
inspection, reconstruction and content commitments MUST preserve these
values. Editing source defaults changes new plan commitments; recovered plans
retain the original admitted values. Deletion without an extant authored owner
does not acquire repetition permission from a current default.

Backend manifest and operation capabilities may declare `execution_policy`
support: version, responses, maximum attempts and after-effect postures. Missing
support is unsupported, not permission to ignore requirements. Planning MUST
preserve the requested policy and issue error diagnostics for incompatibility;
it MUST NOT clamp attempts or substitute a recovery choice.

The current native plan/operation profile has no general continuation carrier,
trial allocation binding, or resolved retry-triggered cleanup admission.
Consequently `resume`, `new-trial` (including exhaustion), and reset/compensate
repetition remain representable but fail executable admission with explicit
continuation, trial-authority or cleanup-authority diagnostics. A provider MUST
NOT advertise general continuation in this profile. Supporting another choice
requires current contextual willingness, remaining budgets and required
evidence; a static capability declaration alone does not establish these.

For the optional backend operation protocol, resolve the command through its
native authority, verify its native contract/kind/identity/content digest and
policy support, and require the exact request-bound, capability-bound willing
admission response. Refusal blocks admission even when support was declared.
This check does not replace authentication, authorization, reservation,
one-use effect claims, cleanup proof or terminal publication. The optional
protocol does not enable supervision on legacy runtime targets.
