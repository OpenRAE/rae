# Inject readback pre-synchronization captures

These byte-for-byte copies preserve the issue #1423 and #1366 captures from
`9c720a10ea91d90c4aa0e7484734df9d56b8f820` before merging `dev` at
`35e9559c07dcbc99150fad733f4b9ffb2630f99f`. Formal release 73 and specification release 72
collided with published mixed-backend captures. Formal release 74 depended on
the original release 73, so its original baseline chain is preserved here too.

The incoming releases keep their canonical paths. The [records](records.json)
pin every original path, digest and source revision. Embedded paths refer to
that source revision; these records are outside the active indexes.
Specification release 73 also remains an unchanged active historical capture.

Formal release 75 and specification release 74 capture the synchronized source.
The original observations and capture bytes remain preserved without relabeling.
