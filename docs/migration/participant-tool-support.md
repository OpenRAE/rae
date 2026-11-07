<a id="participant-tool-support-migration"></a>

# Participant tool support compatibility

## Versions and purpose

Source: `Tool-free processor/backend v2 manifests with omitted optional tool blocks`.
Target: `Explicit participant-tool-profile/v1 support and capacity declarations`.
This reference applies to Python RAES 11.0.2.
Each contract keeps its own identity and rules.
This page supplies no converter. It installs nothing.

API-414 extends the draft processor and backend v2 manifests.
Existing manifests without tool declarations remain readable.
Their absence declares no participant tool-profile support.
Tool-free scenarios retain their existing admission behavior.

Processor `capabilities.participant_tools` declares profile semantic revisions.
It also declares feature support and capacity.
Backend `capabilities.participant_runtime.tool_profiles` declares profile semantic revisions.
It also declares capacity.
Backend strength stays in `capabilities.participant_runtime.feature_support`.
The governed features are `tool_affordances` and `scoped_tool_affordances`.
They use the existing API-407 support levels and evidence references.

Use `participant-tool-profile/v1` for the ACT-619 binding and selector semantics.
An authored profile's `semantic_version` does not select this protocol revision.
Preserve the instantiated snapshot digest to identify exact authored content.

Exact support can have finite capacity limits.
Bounded support needs typed capacity.
It also needs the matching constraint references.
Its semantics remain exact inside that capacity.
Weak or unsupported declarations do not admit tool profiles.
Expected participant behavior cannot replace processor or backend support.

Old closed readers reject new manifest fields.
They can also reject the new governed feature terms.
Upgrade those readers before producing the new fields.
Use prior feature terms and omit unused optional blocks for a legacy, tool-free manifest.
Omission cannot make a tool-bearing scenario admissible.
No automatic migration or native tool implementation is provided.

Schema publication records give contract identity, schema path, and stability.
They do not carry content hashes.
Git records schema changes.
The generated reference bundle must match the published schemas.
Static checks record declared support.
Observed execution stays separate.
The [design](../decisions/issue-304-participant-tool-support.md) defines the comparison boundaries.

The capacity fields are `max_bindings_per_profile` and `max_participants_per_binding`.
Both accept positive integers.
Omission means no declared capacity limit.
Canonical constraint references are `tool_profiles.max_bindings_per_profile` and `tool_profiles.max_participants_per_binding`.
They also name the processor capacity fields under `participant_tools`.
Bounded declarations must name every declared capacity field and no other constraint.
Exact declarations cannot introduce an unevaluated constraint reference.
Other non-empty limitation, disclosure, and evidence references describe the claim.
A reference does not prove that evidence exists.
It does not establish execution.

## Continue

For coordinated adoption, follow [revised-control migration](revised-control.md).
For execution, use [admit participant tool actions](../public/guides/invocation-tool-actions.md).
The [tool-support design](../decisions/issue-304-participant-tool-support.md) explains the boundary.
