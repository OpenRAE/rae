# Issue 1423 pre-synchronization captures

These are byte-for-byte copies of the inject trigger and occurrence captures
published at `2bf8c1ad138b51f6ce35bc762c41cf675b3e93f7` before synchronizing with `dev`.
Formal release 73 and specification release 72 collided with the mixed-backend
releases already published on `dev`. The incoming published releases retain
their canonical paths.

The [records](records.json) pin every archived file to its original path, digest
and immutable source revision. Embedded paths refer to that source revision.
These historical records are outside the active indexes; no capture byte or
observation has been discarded or relabeled.

Fresh captures will record the synchronized implementation and discriminator
repair without promoting the retained corpus to inject execution evidence.
