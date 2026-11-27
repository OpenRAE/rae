# Issue 1843: constraint metadata admission

The existing owner is `raes_contracts.realization_structure`.
Its public normalization, binding and evaluation interfaces remain unchanged.
No schema, dependency, privilege, persistence or data-flow change is needed.

Admission currently constructs a dictionary for each node header and each
origin entry. It then traverses both its fixed keys and supplied values.
For a 40-route application this exhausts the operation budget despite only
1,049 constraint nodes. Document admission alone costs 20,098 operations.

Admit the three node header values and each origin address/value directly.
Keep charging each supplied value, including its scalar bytes, and stop on
the first exhausted limit. Fixed internal field names need no input admission.
This removes temporary allocations and traversal without increasing limits.
Other metadata, scope, identity, depth, member and node checks stay in place.

Targeted regressions cover 30 and 40 routes with two methods, a parameter and
a response under open realization. Verify document/binding retention, both
projection modes, rejection of changed authored paths, allowed open additions,
and deliberate exhaustion. Check scalar limits on origin addresses and header
values separately. Run a temporary mutation restoring the old accounting to
confirm that the route regression detects the defect.
