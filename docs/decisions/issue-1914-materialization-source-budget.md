# Materialization document traversal budget (#1914)

`raes_contracts.runtime_value_limits` owns the fixed `MATERIALIZATION_VALUE_LIMITS` profile.
`MaterializationSource` uses it to validate the full instantiated snapshot.
`admit_materialized_scenario` uses it to admit the returned scenario content.
Both continue to use the existing portable-value traversal implementation.

The profile permits 262,144 nodes and 1,048,576 traversal operations.
Collections permit 65,536 members, including the full source explicitness records.
All other limits remain those of `RUNTIME_SNAPSHOT_VALUE_LIMITS`.
The 4 MiB document limit and full source digest and provenance checks remain mandatory.
Runtime snapshots retain their existing profile.
`PLAN_VALUE_LIMITS` permits 524,288 nodes and 2,097,152 operations to carry the compiled document authority.
Plans permit 16 MiB of aggregate scalar bytes for the source and its compiled authority.
Other plan limits remain unchanged.
No schema, network destination or storage behavior changes.

Regression tests exercise dense 32-node and 64-node fixtures through planning,
backend delivery, report admission and archival. Refusal cases cover altered identities,
128-node input beyond the byte ceiling and compact input beyond the traversal ceiling.
The profile is executable through the existing `validate_realization_value` interface.
