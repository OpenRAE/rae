# Concrete backends migration

Issue #967 removes the concrete backends from RAES.
[ADR-115](../decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md)
records the decision. It supersedes
[ADR-063](../decisions/adrs/adr-063-reference-emulation-backend.md).

RAES keeps SDL, processing, the portable runtime and control contracts,
conformance, dry fixtures, and test doubles. A backend distribution owns
concrete realization, credentials, resource allocation, native lifecycle,
rollback, and teardown.

## Versions

| Item | Version |
| --- | --- |
| Last RAES release that bundles the concrete backends | RAES 7.0.0 |
| First RAES release without the concrete backends | The release after RAES 7.0.0 (a breaking change) |
| First independent backend release | LilRAE 8.1.0 (PyPI `lilrae`) |
| Tested pairing for LilRAE 8.1.0 | RAES 6.0.1, which LilRAE 8.1.0 pins |

LilRAE ships its own RAES backend. It does not use the removed RAES packages at
runtime. Install and operate it with the
[LilRAE documentation](https://github.com/OpenRAE/lilrae). A LilRAE release that
supports the release after RAES 7.0.0 is a LilRAE release decision.

The libvirt backend and its TechVault live gate have no successor in RAES or in
LilRAE 8.1.0.

## Removed Python imports

| Removed import | Replacement |
| --- | --- |
| `raes_reference_backend` and all of its modules | LilRAE for local realization. `raes_backend_stubs` for test doubles. |
| `raes_backend_libvirt` and all of its modules | No replacement in RAES. |
| `raes_operations.libvirt_evidence_run` | No replacement in RAES. |
| `raes_operations.techvault_live` | No replacement in RAES. |
| `raes_operations.cross_backend_corpus` | No replacement in RAES. |
| `raes_operations.realization_conformance` | `raes_conformance.conformance.run_target_conformance()` |
| `raes_operations.deterministic_participant_fixtures` | No public replacement. The synthetic fixtures are now test-only. |
| Private `raes_operations` evidence-run, TechVault cleanup, and corpus modules | No replacement in RAES. |
| `raes_operations.run_artifacts` helpers `portable_artifact_ref`, `run_artifact_path`, `serialize_run_artifact`, and `atomic_write_json_artifact` | No replacement in RAES. |
| `raes_conformance.conformance.reference_participant_opacity` | Supply a backend-owned harness to the generic participant-opacity runner in `raes_conformance.conformance.participant_opacity_probes`. |

`raes_operations.run_artifacts.RunMaterializationArchive` and
`is_valid_run_id_label` stay. `RuntimeManager` and `RuntimeControlPlane` use
the archive for protected materialization records.

## Removed commands

| Removed command | Replacement |
| --- | --- |
| `raes libvirt techvault validate-live` | No replacement in RAES. |
| `raes libvirt techvault guest-certify` | No replacement in RAES. |
| `raes libvirt evidence validate` | No replacement in RAES. |
| `raes corpus build` | No replacement in RAES. |

The `nox -s integration_docker` session and the container integration CI lanes
are also removed. Their only subject was the removed reference backend.

## Conformance from an installed release

A backend runs conformance from an installed RAES release. It does not need a
source checkout:

1. Install the RAES release.
2. Run `raes conformance backend --profile <profile>` for fixture conformance.
3. Call `run_fixture_suite(profile=...)` from `raes_conformance.conformance`
   to check the published fixtures for a backend profile.
4. Call `run_target_conformance(target)` with your own `RuntimeTarget` to
   check the runtime surface that your target declares.

Fixture conformance does not prove a live deployment. Keep live evidence in the
backend's own release gate.

## Existing native resources

RAES no longer manages containers, libvirt domains and networks, guest images,
or TechVault state that the removed backends created. Installing or upgrading
RAES never discovers, adopts, rolls back, or destroys these resources.

Before you upgrade past RAES 7.0.0, do these steps:

1. Stop the runs that use the removed backends.
2. Remove their native resources with the RAES 7.0.0 commands or with native
   tools (`docker`, `podman`, or `virsh`).
3. Keep the run archives and evidence that you need. RAES does not delete them.

## Downstream code

Code that imports a removed module fails with the release after RAES 7.0.0.
Replace the import before you upgrade. For example, the LilRAE test suite
imports `raes_reference_backend` in one test. LilRAE must replace that import
before it adopts the release after RAES 7.0.0.

Use `raes_backend_stubs` or a small test-local double for test substrates. Do
not copy the removed backend into a test double.
