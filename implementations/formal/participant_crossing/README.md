# Participant-crossing counterexamples

The corpus tests five deliberate faults against the complete single-operation rev2 models.
It supplies negative evidence for `participant-crossing-dpbb-finite-v1@rev2`.
It establishes no positive equivalence, runtime realization, or mathematical proof.

| Mutation | Strong | Weak | Branching | Divergence-preserving branching |
| --- | --- | --- | --- | --- |
| Hidden denial | false | false | false | false |
| Hidden observation | false | false | false | false |
| Added internal divergence | false | true | true | false |
| Removed transformed delivery | false | false | false | false |
| Later-cut replay admitted | false | false | false | false |

Every mutation also fails the selected relation against the unchanged concrete model.
Unchanged-input and separate relation-calibration controls test the checker adapter.
Four checked auxiliary branching formulas explain visible failures.
An independent path-and-cycle check establishes the narrow rev2 divergence refutation.
The abstract graph has no internal edges; this argument does not cover arbitrary graph pairs.

## Acquire and replay

Use a Linux x86_64 host with the runtime and sandbox prerequisites in
`model-check-ubuntu-26.04-x86_64`.
The canonical workflow uses the supported Ubuntu 26.04 runner.
Keep host security controls enabled; an unavailable sandbox is a failed check.
Inspect native prerequisites through the existing tooling command:

```sh
implementations/tooling/python/.venv/bin/python -m tools.bootstrap_profile setup-plan model-check-ubuntu-26.04-x86_64
implementations/tooling/python/.venv/bin/python -m tools.mcrl2_tool acquire
```

Acquisition uses the official mCRL2 202607.0 release and the reviewed raw and complete-tree digests.
Use `--local-input /path/to/mcrl2-202607.0_x86_64.deb` for an already downloaded carrier.
The Debian reader exposes package files without installing the package or running its scripts.
The upstream package's `usr/share/doc/mcrl2/copyright` contains the Boost Software License 1.0.
The complete admitted tree retains that license and the package's libraries.

Check retained evidence without executing the native checker:

```sh
PYTHONPATH=implementations/python/packages:. implementations/python/.venv/bin/python -m implementations.formal.participant_crossing.counterexample_corpus check
```

Recompute every comparison and require identical retained bytes:

```sh
PYTHONPATH=implementations/python/packages:. implementations/python/.venv/bin/python -m implementations.formal.participant_crossing.counterexample_corpus replay
```

Replay never downloads a missing checker. It verifies the installed tree before use.
Full test and integration suites run in CI. Local tests select explicit relevant modules or cases.

## Evidence and review

The reviewed `specs/formal/participant-semantics/counterexamples/pin.json` selects the immutable capture.
The manifest binds model, profile, catalog, historical mapping, source, tool, mutation, result, and witness identities.
Raw file checksums and canonical JSON subject digests have different meanings.
The corpus is unsigned. A consumer requiring authenticity must reject it.
No candidate field can replace the consumer's selected trust policy.

`cases.json` contains semantic selectors and the exact reversible edge changes.
Its canonical digest is the mutation review subject in the manifest and pin.
Independent review must name that digest and cover every required case.
Source checks and producer-written approval fields cannot substitute for that review.

After an intentional source change, `record` writes a new content-addressed capture.
Review its results and update the separate pin in the same delivery diff.
Historical captures retain their bytes. The pinned rev1 runtime mapping remains historical evidence.
Fresh runtime observations use the separate mapping exporter and retain its explicit incompatibilities and gaps.

The [design](../../../specs/formal/participant-semantics/participant-crossing-counterexamples.md)
defines the projection, trust boundaries, budgets, and claim limits.
