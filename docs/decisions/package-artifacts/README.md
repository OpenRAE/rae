# Developer package and artifact management

## Current scope

[Issue #1313](https://github.com/OpenRAE/rae/issues/1313) corrects the original
#1168 design to match connected local development and GitHub-hosted CI.
The amendments to [ADR-106](../adrs/adr-106-developer-package-and-artifact-management.md)
and [ADR-107](../adrs/adr-107-artifact-promotion-and-release-admission.md)
supersede conflicting historical requirements on merge.

The project has [one accountable maintainer](../../../MAINTAINERS.md).
Responsibility labels do not create independent human reviewers or a deputy.
Credential separation between build/test and publishing jobs is still required.

Keep locked input identity, native clients, safe private caches, frozen builds,
installed-package smokes, proof isolation, concurrent CI and output-bound
release provenance/SBOM. No enterprise distribution/promotion/revocation
service, full disconnected bundle, mandatory independent backup, service-load,
retention/GC service or recovery-drill program is required.

- [Architecture](architecture.md): current authority boundaries, then historical design.
- [Operations](operations.md): current maintenance and verification, then historical targets.
- [Migration](migration.md): current native dependency graph and cancelled/narrowed work.
- [Inventory](inventory.md) and [decision matrix](decision-matrix.md): historical analysis with current dispositions.
- [Tooling guide](../../../implementations/tooling/README.md): commands and implementation owners.

#1224, #1225 and #1228 are cancelled as not planned. #1227 owns ordinary
release-byte verification and partial-publication recovery; #684 owns actual
PyPI/GitHub publication acceptance; #1277 owns verified dev-container entry
points. This cleanup adds no blanket blocker for those issues.

The original 2026-09-05 design was accepted in #1229. Historical sections and the
[#1226 preflight](issue-1226-preflight.md) retain that record, but cannot
reintroduce cancelled requirements. SDL runtime package/module semantics,
portable contracts and their trust authorities are unchanged.
