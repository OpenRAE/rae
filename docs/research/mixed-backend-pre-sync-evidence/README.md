# Issue 1371 pre-synchronization captures

These are byte-for-byte copies of the captures published on issue 1371 before
merging `dev` at `353ccffeaf07fe084485fba86f1029450d7608ad`. Formal release 70 and
specification release 69 collided with releases already published on `dev`.
The incoming published releases retain their canonical paths and version
selection rules.

The [records](records.json) pin each archived file to its original path, digest
and immutable source revision. Paths embedded in these archival documents refer
to that source revision. These are historical records outside the active indexes.
No observation or prior capture byte has been discarded or relabeled.

The subsequent formal release 72 and specification release 71 captures from
the composition run-scope repair are also [preserved with exact digests](../mixed-backend-run-scope-pre-sync-evidence/README.md)
after their identities collided with the issue #1418 integration releases.
