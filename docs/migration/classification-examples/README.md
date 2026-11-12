# Classification examples

This page describes retained evidence.
It is not a classification catalogue or deployment guide.
The JSON files keep their original source revisions and digests.
For conversion with RAES 11.0.2, use [move historical classifications](../external-classifications.md).
For current authoring, use [the SDL task route](../../public/sdl/index.md).

`techvault.bindings.json` resolves four historical node/route associations against `examples/scenarios/techvault.sdl.yaml`.
The paired `techvault.scheme.json` lists historical author labels.
An author supplied that catalogue explicitly.
It is **not** an authoritative CWE snapshot.
The original source supplied no CWE revision.
Confidence is unknown. Review is unreviewed.

These assertions are new examples.
The author chooses their perspective, relationship, assertion time, and loss explicitly.
They are not inferred facts from history.
The migration API does not supply them by default.

`historical-inventory.json` retains every removed declaration and association from six edited examples.
It keeps the immutable source revision and byte digest.
It also keeps the legacy projection digest and source pointers.
Unreferenced declarations remain historical author content.
No native subject is invented for them.
The native YAML alone defines the scenario configuration.

Use `migrate_sdl_classifications` for atomic conversion of supported canonical legacy source.
Follow the [migration guide](../external-classifications.md).
Supply explicit assertion context.
Authorize each declaration removal or omission.

To disclose an assertion to a participant, render it as ordinary SDL `content.text`.
Include its binding document digest and binding ID in that content.
Use the existing participant-directed inject delivery and observation boundary.
Apply the existing disclosure policy too.
Retain delivery evidence separately.
A sidecar or eligibility declaration alone does not add content, delivery, or knowledge.
