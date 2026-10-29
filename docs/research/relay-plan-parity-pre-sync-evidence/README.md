# Issue 1425 pre-update evidence

These are byte-for-byte copies of PR #1433's formal release 70 and
specification release 69 at `46d0fb1016518bae49f859d42525b3e7f282d2bb`.
Their numbered paths collided with releases already admitted on `dev`; those
admitted releases retain their canonical paths.

The [records](records.json) pin every archived file to its original path,
digest, and immutable source revision. Embedded paths refer to that revision.
These historical records are outside the active indexes; no observation has
been discarded or relabeled as a current result.

Fresh content-addressed captures replay the updated branch. Retained outcomes
and bounded claim limits are unchanged; this retained corpus makes no new
realization, HTTP relay, or backend-honesty claim. The dedicated issue-1425
regression tests establish those provisioning behaviors.
