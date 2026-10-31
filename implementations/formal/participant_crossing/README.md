# Participant-crossing counterexamples

## Finite equivalence decision

The machine check compares both complete rev2 models.
It first repeats every required corpus check.
Only then can it admit a positive model-check binding.
It supplies no proof certificate, runtime-realization result, or independent reproduction.
The [machine-check design](../../../specs/formal/participant-semantics/participant-crossing-machine-check.md)
defines the evidence and publication boundary.

After the existing acquisition and Python environment setup, run offline verification:

```sh
RAES_REQUIREMENT_UID=SEM-232 uv run --offline --no-sync --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s participant-crossing-machine-check
```

The nox session never synchronizes dependencies or acquires missing tools.
Missing inputs fail the check.
Routine verification runs the current graphs and fixed negative controls.
It requires the expected positive baseline decision.
It does not require a new publication after a source edit.

The separately reviewed `machine-check/pin.json` selects an immutable research result.
Use `record` only when collecting a new source-bound research claim.
It does not overwrite the pin or historical evidence.
Explicit publication uses `-- --publish` with the same nox session.
Publication requires exact native replay and a qualified hosted execution record.
Public and scientific claims require their separate reproduction and publication work.

## Fresh reproduction measurement

The reproducer starts a fresh Python worker with no network or ambient environment.
It copies declared source and data files without compiled caches or producer results.
The worker repeats the complete native decision and negative corpus.
Every output byte must match the separately selected reviewed capture.

After the existing tool acquisition and Python setup, run:

```sh
PYTHONPATH=implementations/python/packages:. implementations/python/.venv/bin/python -m implementations.formal.participant_crossing.reproduction --expected-manifest sha256:76422aebb1413e345677eeaa4bea67005e74aa3d9289d185f63f4c69dc838339
```

The expected result is an immutable `reproduction/capture-.../measurement.json` file.
A different digest, missing input, or unavailable sandbox fails the command.
The command never downloads tools or dependencies.
The `--qualified` option requires the existing hosted execution profile.
It stages measurement and allowlisted execution provenance for the canonical CI artifact.

A measurement does not authenticate a reviewer or establish independent acceptance.
The reviewer must select and review its exact digest and corpus review subject.
They must supply an attributable review record and state their separation from production.
Missing review leaves issue 975 incomplete.
The [reproduction design](../../../specs/formal/participant-semantics/participant-crossing-reproduction.md)
defines the execution, review, and claim boundaries.

## Negative corpus

The corpus tests five faults in the complete rev2 models.
It supplies negative evidence for `participant-crossing-dpbb-finite-v1@rev2`.
It proves no positive relation.
It gives no runtime-realization result or mathematical proof.

| Mutation | Strong | Weak | Branching | Divergence-preserving branching |
| --- | --- | --- | --- | --- |
| Hidden denial | false | false | false | false |
| Hidden observation | false | false | false | false |
| Added internal divergence | false | true | true | false |
| Removed transformed delivery | false | false | false | false |
| Later-cut replay admitted | false | false | false | false |

Each mutation also fails against the unchanged concrete model.
Separate controls test the checker adapter.
They use unchanged inputs and known relation cases.
Four checked auxiliary branching formulas explain visible failures.
A separate path-and-cycle check refutes the rev2 divergence mutation.
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

Acquisition uses the official mCRL2 202607.0 release.
It checks the reviewed archive and complete-tree digests.
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
The manifest binds the model, profile, and catalog.
It binds the historical mapping, source, and tool.
It also binds each mutation, result, and witness.
Raw file checksums and canonical JSON subject digests have different meanings.
The corpus is unsigned. A consumer requiring authenticity must reject it.
No candidate field can replace the consumer's selected trust policy.

`cases.json` contains semantic selectors and the exact reversible edge changes.
Its canonical digest fixes the mutation review subject.
Independent review must name that digest and cover every required case.
Source checks and producer-written approval fields cannot substitute for that review.

After an intentional source change, `record` writes a new content-addressed capture.
Review its results and update the separate pin in the same delivery diff.
Historical captures retain their bytes. The pinned rev1 runtime mapping remains historical evidence.
Fresh runtime observations use the separate mapping exporter.
They keep its known mismatches and gaps.

The [design](../../../specs/formal/participant-semantics/participant-crossing-counterexamples.md)
defines the projection, trust boundaries, budgets, and claim limits.
