# Plan-level realization profiles

`plan-realization-profiles-v1` attaches optional typed domain-profile constraints
to provisioning plans. Its normative shape is
[`plan-realization-profiles-v1.json`](../../contracts/schemas/plans/plan-realization-profiles-v1.json).
This is a programmatic compiler/planner input, **not new SDL authoring syntax**.
It adopts the offline definition/admission contract from #1202 and the recursive
relation from #1203 at the runtime handoff required by #1204.

## Authority and independent support

`ProvisioningPlan.profile_authority` contains public author-supplied bindings,
pinned admitted definitions with their source/trust provenance, and one recursive
constraint document for every full binding path, including nested bindings.
Each document identifies the exact profile definition digest as its semantic
profile and binds its source projection with `source_binding`. Missing,
duplicate, changed or unbounded documents are invalid. Source checksums are
integrity metadata; only the existing authenticated planner artifact grants
execution authority.

An owner uses `owning_contract_id: plan-realization-profiles-v1`,
`concept_family: resource-realization`, `lifecycle_phase: planning`, and
`use: constraint`. Its canonical address is
`#/resources/<canonical provisioning resource address>`; all descendants retain
that resource owner. The definition must admit the binding's explicit context.
An owner must identify a non-delete resource operation in the original plan.
Profiles cannot introduce resource membership, dependencies, participant
affordances or another runtime domain. Additional portable resources still need
the enclosing collection protocol; an existing profile binding is not such a
grant.

The plan MUST NOT contain operation-support declarations. A target independently
configures its immutable local `DomainProfileResolutionContextModel`: namespace
admissions, exact definitions, support declarations and bounded work limits.
The manifest's `domain_profile_context_digest` commits to this context. The
complete manifest digest in preparation authority binds it to the authenticated
plan. Both registration and pre-apply admission reject a changed context.
Resolution performs no discovery, network access, ambient secret lookup or
handler loading. Standard and private namespaces use the same checks.

Structural admission uses an explicit no-retrieval schema registry containing
only the supplied pinned document and installed specification resources.
Profile `$ref` values MUST be local JSON Pointers; inspection and validation
use the same resolver, including URI decoding and array traversal. Unresolved
references are schema-invalid. Schema resource identities (`$id`) and dialect
declarations (`$schema`) are root-only: nested schema objects MUST NOT rebase
references or switch validators. Annotation data remains inert, but a schema
reached through a reference is subject to these same restrictions. The shared
domain-profile validator enforces this policy for all profile hosts, not only
plans, and disables external retrieval even if structural preflight misses a
reference.

The backend MUST explicitly negotiate both `plan-realization-profiles-v1` and
`backend-realization-preparation-v1`. It exposes `domain_profile_context` and an
installed read-only `validate_profiles(selected_plan)` implementation in addition
to preparation and ordinary validation. Local support must cover structural and
semantic validation, comparison and execution for every exact definition and
semantic contract. The installed validator receives the complete selected plan,
so profile semantics cannot ignore the core/profile conjunction. Schema validity,
digest equality, support rows alone, unknown profiles and opaque carriage are
not permission to execute. No central plugin registry or executable profile data
is introduced.

## Preparation, delivery and reconciliation

Preparation returns selected `profile_bindings` on their provisioning operations.
Their exact binding paths, coordinates and owners are fixed by the plan. Every
nested value must satisfy its original recursive constraint and admitted schema,
and the installed semantic validator must accept the joint selection before
apply. A selected binding uses `backend-selected` provenance and cannot claim
observation evidence. The original author basis and definition provenance remain
in the authenticated authority, rather than being overwritten by selection.

Successful apply returns those typed bindings on the corresponding snapshot
entries. The result boundary requires the exact admitted completion, not merely
another value inside the original domain. It rejects missing, added, relocated,
retyped or changed bindings before publication. Orchestration and evaluation
operations do not acquire profile execution authority. Explicit null remains a
value through both plan and snapshot codecs.

Replanning retains a previously selected binding only while the complete
constraint conjunction still admits it. Changed or revoked authority follows
ordinary resource reconciliation. Teardown removes the resource and its typed
profile state. A rejected successful delivery preserves the immediate trusted
predecessor, including its profile values, across durable reload.

This carrier is exclusively for bounded public execution data. It is not a
credential, arbitrary extension-payload, observation or evidence channel.
Persisted runtime labels are execution state, not independent measurements.
Profiles and exact values create no experimental capture, retention or export
demand; the existing #1212/#1112 owners remain authoritative for those operations.
Semantic contracts requiring unsupported observation or participant behavior
must be refused, not approximated by these bindings.

## Reference implementation

The reference target opts in only when configured with a profile resolution
context. Its installed `portable-resource-labels` semantic contract accepts a
public record of nonempty string keys and string values. These are portable
resource labels only: they do not set guest configuration, infrastructure labels,
access policy or observation claims. Standard and private definitions can refine
that value schema while using the same exact installed semantic contract.

Optional `profile_choices` are backend configuration keyed by exact definition
digest. They supply one candidate value, not a claim of universal coverage or a
search service. Missing choices use the supplied template only if admitted;
unsupported combinations fail before driver mutation. Existing admitted choices
are retained on unchanged reconciliation. The ordinary reference provisioner and
deployment driver still perform core realization; profile support does not
bypass their validators or result-integrity boundaries.

Legacy no-profile plans and backends retain their existing contract. This host
does not imply support for every profile, add SDL syntax, or change the separate
global semantic-version migration owned by #1210.
