# Issue 1371 run-scope repair pre-synchronization captures

These are byte-for-byte copies of the captures published with the issue #1371
composition run-scope repair before merging `dev` at
`5d78a429ba9030f288db4527623f3b50bb2f53fd`. Formal release 72 and specification
release 71 collided with the issue #1418 releases already published on `dev`.
The incoming published releases retain their canonical paths.

The [records](records.json) pin every archived file to its original path, digest
and immutable source revision. Embedded paths refer to that source revision.
These historical records are outside the active indexes; no capture byte or
observation has been discarded or relabeled.

Formal release 73 and specification release 72 replay the synchronized source.
Retained outcomes, classifications and bounded claim limits remain unchanged.
