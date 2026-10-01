# Check a backend boundary

Use backend manifests and conformance fixtures to state what an implementation
accepts and what it can realize.

RAES separates three questions:

1. Is the SDL document valid?
2. Can a processor compile the requested meaning?
3. Can a selected backend realize the compiled request?

A valid scenario can still exceed a backend's declared capabilities. Read the
backend report and keep unsupported or degraded results with the run evidence.

The repository includes contracts, stubs, a reference emulation backend, and
conformance tests. It does not ship a production deployment backend or managed
environment service.

Start with the [backend schemas](https://github.com/OpenRAE/rae/tree/main/contracts/schemas/backend-manifest)
and the [conformance API](api/contracts.rst).

Backends can also report what they built as SDL. The runtime saves this record
with the run. See [SDL run records](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/materialization-attestations.md)
for the contract and setup.

The optional operation-supervision profile defines requests, progress,
cancellation and effect reports for backend authors. Read the
[protocol and migration guide](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/backend-operation-supervision.md).
These contracts keep unknown effects explicit. Publishing them does not certify
that a backend can interrupt work or recover after a failure.
