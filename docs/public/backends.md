# Check a backend boundary

Use backend manifests and conformance fixtures to state what an implementation
accepts and what it can realize.

RAES separates three questions:

1. Is the SDL document valid?
2. Can a processor compile the requested meaning?
3. Can a selected backend realize the compiled request?

A valid scenario can still exceed a backend's declared capabilities. Read the
backend report and keep unsupported or degraded results with the run evidence.

The repository includes contracts, stubs, and conformance tests. It does not
ship a concrete deployment backend or a managed environment service. A backend
distribution, such as [LilRAE](https://github.com/OpenRAE/lilrae), owns
concrete realization, credentials, allocation, and teardown. RAES 7.0.0 was the
last release to bundle the reference and libvirt backends. Read the
[concrete backends migration](https://github.com/OpenRAE/rae/blob/main/docs/migration/concrete-backends.md)
for the removed imports and commands.

Run conformance from an installed release. Use `raes conformance backend` or
`run_fixture_suite(profile=...)` for fixture conformance of a backend profile.
Use `run_target_conformance(target)` with your own runtime target to check the
surface that the target declares. Fixture conformance does not prove a live
deployment.

Start with the [backend schemas](https://github.com/OpenRAE/rae/tree/main/contracts/schemas/backend-manifest)
and the [conformance API](api/contracts.rst).

Backends can also report what they built as SDL. The runtime saves this record
with the run. See [SDL run records](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/materialization-attestations.md)
for the contract and setup.

Backends can report unplanned children and later inventory changes through the
[runtime descendant contract](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/runtime-descendant-inventory.md).
It preserves the original scenario and runtime-owned provenance.

The optional operation-supervision profile defines requests, progress,
cancellation and effect reports for backend authors. Read the
[protocol and migration guide](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/backend-operation-supervision.md).
These contracts keep unknown effects explicit. Publishing them does not certify
that a backend can interrupt work or recover after a failure.

The [trial unit](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/backend-trial-unit.md) defines a typed
in-process handoff for one admitted entry. An adapter binds the protocol to an
injected runtime target. It returns execution observations and separate cleanup
evidence. The interface does not install a trial executor.

Mixed-backend bridges, time services and readers can describe one admitted edge
or handoff with the execution binding and stage report contracts. Read the
[mixed-backend migration note](https://github.com/OpenRAE/rae/blob/main/docs/migration/mixed-backend-execution.md).
These reports keep execution, delivery and observation apart. Declaring the
contracts does not prove support, and the runtime does not read them.
