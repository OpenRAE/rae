# Reference Emulation Backend (Removed)

RAES 7.0.0 was the last release to bundle the reference emulation backend
(`raes_reference_backend`, RUN-314). Issue #967 removed it, together with the
libvirt backend.
[ADR-115](../../decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md)
records the decision. It supersedes
[ADR-063](../../decisions/adrs/adr-063-reference-emulation-backend.md).

A backend distribution now owns concrete realization. For a personal local
backend, use [LilRAE](https://github.com/OpenRAE/lilrae).

RAES keeps these surfaces for backend authors:

- the backend protocols and the backend manifest;
- the published contracts, profiles, realization envelopes, and fixtures;
- the installed conformance facade and `raes conformance backend`;
- the in-memory test doubles in `raes_backend_stubs`.

The [concrete backends migration](../../migration/concrete-backends.md) lists
the removed imports and commands and their replacements. ADR-063 and the issue
#197 preflight keep the historical design.
