# Migration and native issue dependencies

## Current scope — #1313

The original #1168 design was accepted in #1229. The #1313 amendments to
[ADR-106](../adrs/adr-106-developer-package-and-artifact-management.md) and
[ADR-107](../adrs/adr-107-artifact-promotion-and-release-admission.md) narrow that
design to connected local development, GitHub-hosted CI and ordinary release
byte identity/recovery. Historical service/disconnected prescriptions elsewhere
in this design set do not reintroduce cancelled work.

The following state was checked against GitHub's native dependency API on
2026-09-17. Immediate blockers are listed for active work; closed issues retain
historical edges, not outstanding delivery obligations.

| Issue | Current outcome or scope | State | Immediate blockers |
|---|---|---|---|
| #1224 | Enterprise intake/distribution/promotion service | Cancelled, not planned | None active |
| #1225 | Complete disconnected development bundles | Cancelled, not planned | None active |
| #1228 | Enterprise retention/revocation/DR/load qualification | Cancelled, not planned | None active |
| #1227 | Publish tested bytes and recover partial publication | Open | #1110, #1125, #1218, #1226 (all completed) |
| #684 | Actual public PyPI/GitHub publication acceptance | Open | #1110, #1125 (completed), #1227 |
| #1277 | Verify and document a small supported set of container entry points | Open | None |
| #1313 | Simplify merged tooling without weakening useful guarantees | This change | Not a blocker for #1227, #684 or #1277 |
| #935 | Concurrent CI with complete coverage | Completed | Historical #1168, #1219, #839 |

The active release chain is #1227 → #684. No open issue depends on cancelled
#1224, #1225 or #1228, and #1313 has no native blocking edges. The closed
#1224 → #1225 → #1228 edges remain audit history only.

## Retained implementation and cleanup

| Landed work | Retain | Simplify in #1313 |
|---|---|---|
| #1216, #1218 | Reviewed artifact hashes; frozen project/tool/build resolution; installed wheel/sdist smokes | Selection no longer evaluates unrelated workflows, containers or qualification records; remove site accounting, duplicate version tables and unused tool exports |
| #1217, #1268 | Exact bootstrap bytes and honest platform support; patched dependencies | Connected bootstrap; TLS fixture group opt-in; qualification only on relevant inputs/manual dispatch; no renewed policy hash |
| #1137 | Maintained curl and reviewed checksums | No custom HTTP stack restored |
| #1219, #1220 | Extraction safety, private ownership, locks, atomic publication, crash recovery, full proof-tree integrity and sandbox | Remove shared-seed and filesystem-type qualification machinery |
| #1221 | Raw acquisition and incumbent vocabulary semantic identity | No semantic authority changes |
| #1222 | Exact VM owner/name, verified guest/bootstrap bytes, authenticated SSH, host security and real backend tests | Signed native repositories and hash-pinned online Python installation; no full local wheelhouse or snapshot prerequisite |
| #1223, #1110 | Required digest-pinned real-container lane, unique names and teardown | Direct native pull, no same-job export/import or mirror/pre-seeded distribution mode |
| #839 | Action source pins, credential isolation, actual publishing permissions | Native workflows/updater config own execution; no parallel expression/use-site/Dependabot model |
| #1238 | Optional non-root container and tested setup lifecycle | Native Dockerfile owns packages; no immutable snapshot condition for future arm64 qualification |
| #1226, #1125 | Useful SBOM/provenance, trusted producer and exact source/output identity | Release input inventory follows native release workflow calls; no enterprise storage gate |

Intel Mac support is not restored merely by separating the TLS fixture:
the runtime still requires patched dependencies and a supported binary closure.
No vulnerable downgrade or untested platform is promised. #1277 remains the
owner of client-entry-point acceptance, not an enterprise qualification program.

## Ownership, cutover and verification

[MAINTAINERS.md](../../../MAINTAINERS.md) names one accountable maintainer.
Responsibility labels are not independent humans; there is no mandatory deputy.
Read-only candidate jobs and privileged publishers remain separate machine
trust boundaries.

Each removal keeps the useful behavior tests of its owning consumer. Verify
selected-input isolation and refusals, native workflow pins/permissions,
trigger inclusion/exclusion, maintained downloads, private installer
concurrency/crashes/corruption, frozen builds and installed smokes, proof
isolation and affected real-container behavior. Preserve #935's canonical
parallel graph and coverage handoff. No performance or availability improvement
is claimed without measurement.

AWS operations, actual publication, protected-branch and PR merges are not
authorized by this cleanup. Required unavailable inputs remain failures;
partial release recovery must preserve original bytes, not rebuild or overwrite
a published version. #1227 and #684 retain their own delivery evidence.

The original inventory, alternatives and accepted ADR bodies remain explicitly
historical. Native dependency changes must be reconciled with this document;
use `GET /repos/OpenRAE/rae/issues/{number}/dependencies/blocked_by` and
`blocking`, not a prose graph as an execution authority.
