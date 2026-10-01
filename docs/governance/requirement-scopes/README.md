# Issue-bound requirement scopes

An issue that changes artifacts owned by different requirements can record a
reviewed delivery scope in `docs/governance/requirement-scopes/<issue>.json`.
This is repository workflow authority, not a public RAES data contract.
Requirement statements and traceability remain in `docs/requirements/`;
phase prerequisites and ownership remain in `tools/policy/requirement_order.yaml`.

The closed `requirement-scope/v1` object has five fields:

- `schema_version`: exactly `requirement-scope/v1`.
- `issue_number`: the positive integer from the numeric issue-branch prefix.
- `primary_requirement_uid`: the primary UID passed to existing workflow gates.
- `requirement_uids`: a nonempty, unique list containing the primary and every
  assigned UID. Keep this identical to the issue's Requirements section, updated
  through Ground Control's issue-requirements operation.
- `bindings`: exact repository-relative filenames mapped to nonempty, unique
  lists of scoped UIDs. No glob, directory-prefix, default-owner, or inferred
  assignment is supported. Assign the manifest itself and every delivery file.

Each changed file must have an assignment. Every assigned owner independently
passes its existing status, prerequisite, ownership, and traceability checks.
Shared files must pass **all** assigned owners; a passing check for another UID
cannot compensate for a failure. Every scoped UID is checked even when an
incremental staged diff contains none of its files. Existing exceptions remain
bound to their own UID; missing assignments and invalid scope cannot be waived
through another requirement. This feature introduces no policy exceptions.

The resolver selects only the issue's canonical filename from the current
branch. In detached CI, the canonical workflow supplies the exact branch through
`RAES_REQUIREMENT_BRANCH`. Otherwise `GITHUB_HEAD_REF`, then the Git branch,
provide context. A primary UID supplied through the existing CLI/environment
must agree with the manifest. The canonical CI resolver, Make/Nox policy, hooks,
and direct requirement checker use the same resolver. Scoped branches cannot
use `--skip-requirement`.

Unreadable, malformed, duplicate-key, oversized, or symlinked scope authorities
fail closed. A missing scope retains the existing single-UID workflow only when
the canonical path has never been established in the Git index or retained
history (including the integration-base ref). Deleting, renaming, or committing
removal of an established scope fails before any requirement-free skip. History
inspection failures also fail closed; intentional retirement requires a reviewed
change to this lifecycle policy, not deletion of its authority file. Scope data never supplies executable commands,
credentials, remote URLs, or alternate authority paths. The configured
repository requirement source remains offline, and unavailable authority never
falls back to another source.

Adding another owned file requires a reviewed exact assignment and truthful
traceability on that owner. Adding another UID also requires expanding the
issue's Requirements section and checking its prerequisites. Published delivery
manifests can remain as history; only the matching issue branch activates one.
