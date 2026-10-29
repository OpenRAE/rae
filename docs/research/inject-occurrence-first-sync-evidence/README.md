# Issue 1423 first-synchronization captures

These are byte-for-byte copies of the inject trigger and occurrence captures
at `82cdeb62f270949f568442f2314c50fbc3e13b04`, before merging the integration
branch that includes the inject readback contracts and content-addressed evidence
workflow. Formal release 76 and specification release 75 collide with published
integration history. The incoming published records retain their canonical paths.

The [records](records.json) pin every archived file to its original path, digest
and immutable source revision. Embedded paths refer to that source revision.
No observation is discarded or relabeled. Content-addressed captures retain
these branch observations and record the combined implementation separately.

Capture manifests:

- [Historical formal observations](../../../docs/research/formal-semantic-validation/captures/capture-433c046b053bf4ff80e4ec216c2e0c1a116309cc73afd11d73532004b4cb06a4/manifest.json)
- [Historical specification observations](../../../docs/research/specification-coverage/captures/capture-a5a57351be69b38c88e36f334855f3b15e1c158d64304427299904a352cc2299/manifest.json)
- [Combined formal observations](../../../docs/research/formal-semantic-validation/captures/capture-1cb25772c376bf4caae8076c770469bcd5e373c9369d620fcc93460ffa859996/manifest.json)
- [Combined specification observations](../../../docs/research/specification-coverage/captures/capture-b961393d9cbbc01916a695ae5eb09ba07ccb2d6e069fb33aa8f9a5d3de8d85fe/manifest.json)

The historical captures preserve the branch observations under their original
source pins. The combined captures bind the synchronized implementation, replay
14 supported formal corpus cases and six specification artifacts with 38 passing
typed pointers, and retain the existing bounded claim limits. The 18 declared
participant cases and 126 inject request, occurrence and readback cases pass.
CI performs the independent integration replay before merge.
