# Participant tool support migration

API-414 extends the draft processor and backend v2 manifests.
Existing manifests without tool declarations remain readable.
Their absence declares no participant tool-profile support.
Tool-free scenarios retain their existing admission behavior.

Processor `capabilities.participant_tools` declares profile semantic revisions, feature support, and capacity.
Backend `capabilities.participant_runtime.tool_profiles` declares profile semantic revisions and capacity.
Backend strength stays in `capabilities.participant_runtime.feature_support`.
The governed features are `tool_affordances` and `scoped_tool_affordances`.
They use the existing API-407 support levels and evidence references.

Use `participant-tool-profile/v1` for the ACT-619 binding and selector semantics.
An authored profile's `semantic_version` does not select this protocol revision.
Preserve the instantiated snapshot digest to identify exact authored content.

Exact support can have finite capacity limits.
Bounded support requires typed capacity and corresponding constraint references.
Its semantics remain exact inside that capacity.
Weak or unsupported declarations do not admit tool profiles.
Participant implementation expectations do not substitute for processor or backend support.

Old closed readers reject new manifest fields.
Upgrade those readers before producing the new fields.
Omit unused optional blocks when communicating with old readers.
Omission cannot make a tool-bearing scenario admissible.
No automatic migration or native tool implementation is provided.

Schema publication records carry the revised content hashes.
The generated reference bundle must match the published schemas.
Static conformance checks record declared support separately from observed execution.
The [design](../decisions/issue-304-participant-tool-support.md) defines the comparison boundaries.

Capacity fields are `max_bindings_per_profile` and `max_participants_per_binding`.
Both accept positive integers; omission means no declared capacity limit.
Canonical constraint references are `tool_profiles.max_bindings_per_profile` and `tool_profiles.max_participants_per_binding`.
These references also identify processor capacity fields under `participant_tools`.
Bounded declarations must name every declared capacity field and no other constraint.
Exact declarations cannot introduce an unevaluated constraint reference.
Other non-empty limitation, disclosure, and evidence references describe the claim.
Their presence is not proof that the referenced evidence exists or establishes execution.
