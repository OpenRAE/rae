# Classification examples

`techvault.bindings.json` resolves four historical node/route associations
against the current `examples/scenarios/techvault.sdl.yaml`. Its paired
`techvault.scheme.json` is an explicitly authored catalog of historical author
labels, **not** an authoritative CWE snapshot. The original source supplied no
CWE revision. Confidence is unknown and review is unreviewed.

These are newly authored illustrative assertions: their perspective,
relationship, assertion time and loss are explicit example choices, not guessed
historical facts and not defaults supplied by the migration API.

`historical-inventory.json` retains every removed declaration and association
from the six edited examples, with immutable source revision, byte digest,
legacy projection digest and source pointers. Unreferenced declarations remain
historical author content here; no arbitrary native subject is invented for
them. The native YAML alone defines the scenario configuration.

For an atomic conversion of a supported canonical legacy source, use
`migrate_sdl_classifications` as described in the
[migration guide](../external-classifications.md). It requires explicit
assertion context and authorization for any declaration removal or omission.

To disclose a selected assertion to a participant, render it as ordinary SDL
`content.text`, including the binding document digest and binding id in that
content. Apply the existing participant-directed inject delivery, observation
boundary and disclosure policy; retain delivery evidence separately. A sidecar
or its eligibility declaration alone does not add content, delivery or knowledge.
